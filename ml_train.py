"""
ml_train.py — KAP haberi → 3 günlük YÜKSELİŞ olasılığı modeli eğitir.

Sızıntısız değerlendirme: ZAMAN bazlı bölme (eski tarihlerle eğit, en yeni %25'te test).
Modeller: Lojistik Regresyon (baz, kalibre olasılık) + Gradient Boosting.
Çıktı: models/kap_direction.joblib + performans raporu.
"""

import os
import json

import numpy as np
import pandas as pd
import joblib

from sklearn.compose import ColumnTransformer
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.pipeline import Pipeline
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
from sklearn.model_selection import TimeSeriesSplit, cross_val_score, GridSearchCV
from sklearn.calibration import CalibratedClassifierCV
from sklearn.metrics import roc_auc_score, accuracy_score, brier_score_loss, classification_report

HERE = os.path.dirname(os.path.abspath(__file__))
DATASET = os.path.join(HERE, "ml_dataset.csv")
MODEL_DIR = os.path.join(HERE, "models")
MODEL_PATH = os.path.join(MODEL_DIR, "kap_direction.joblib")

CAT_FEATURES = ["category"]
TEXT_FEATURE = "title"
NUM_FEATURES = ["sentiment_score", "category_bias", "title_pct", "title_len",
                "dow", "hour", "sym_freq",
                "rsi14", "ret5", "px_vs_sma20", "vol_ratio"]


# Hedef: bildirimden sonra 3 günde BÜYÜK HAREKET (|getiri| > eşik) olur mu?
# Yön tahmini ~0.50 (etkin piyasa); olay-etkisi/volatilite tahmin edilebilir (AUC~0.57).
BIG_MOVE_PCT = 7.0
TARGET_DESC = f"3 işlem gününde |getiri| > %{BIG_MOVE_PCT:g} (büyük hareket / olay etkisi)"


def load_data():
    df = pd.read_csv(DATASET, encoding="utf-8")
    df = df.dropna(subset=["ret3"])
    df["title"] = df["title"].fillna("").astype(str)
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").reset_index(drop=True)
    # Hedefi yeniden tanımla: büyük hareket
    df["y"] = (df["ret3"].abs() > BIG_MOVE_PCT).astype(int)
    return df


def time_split(df, test_frac=0.25):
    n = len(df)
    cut = int(n * (1 - test_frac))
    return df.iloc[:cut], df.iloc[cut:]


def build_pipeline(model):
    pre = ColumnTransformer([
        ("cat", OneHotEncoder(handle_unknown="ignore"), CAT_FEATURES),
        ("txt", TfidfVectorizer(max_features=400, ngram_range=(1, 2), min_df=3), TEXT_FEATURE),
        ("num", StandardScaler(), NUM_FEATURES),
    ])
    return Pipeline([("pre", pre), ("clf", model)])


def candidates():
    # Not: HistGradientBoosting sparse (OneHot+TF-IDF) girdi kabul etmediği için hariç.
    return {
        "Lojistik Regresyon": LogisticRegression(max_iter=2000, class_weight="balanced"),
        "Gradient Boosting": GradientBoostingClassifier(random_state=42),
        "Random Forest": RandomForestClassifier(n_estimators=300, class_weight="balanced",
                                                random_state=42, n_jobs=-1),
    }


def cv_auc(pipe, X, y, n_splits=5):
    s = cross_val_score(pipe, X, y, cv=TimeSeriesSplit(n_splits=n_splits),
                        scoring="roc_auc", n_jobs=-1)
    return float(s.mean()), [float(x) for x in s]


def main():
    df = load_data()
    print(f"Hedef: {TARGET_DESC}")
    print(f"Toplam örnek: {len(df)} | büyük-hareket oranı: {df['y'].mean():.1%}")
    print(f"Tarih aralığı: {df['date'].min().date()} .. {df['date'].max().date()}")

    feats = CAT_FEATURES + [TEXT_FEATURE] + NUM_FEATURES
    X, y = df[feats], df["y"].astype(int)
    base_rate = max(y.mean(), 1 - y.mean())
    print(f"Baz çizgi (çoğunluk): {base_rate:.3f}\n")

    # 1) Zaman-serisi CV ile en iyi model ailesini seç (sızıntısız ölçüm)
    results = []
    for name, model in candidates().items():
        try:
            mean, folds = cv_auc(build_pipeline(model), X, y)
            print(f"  {name:24} CV-AUC={mean:.3f}  ({', '.join('%.3f'%f for f in folds)})")
            results.append({"name": name, "cv_auc": mean, "folds": folds})
        except Exception as e:
            print(f"  {name:24} hata: {str(e)[:50]}")
    best_res = max(results, key=lambda r: r["cv_auc"])
    print(f"\n>>> En iyi aile: {best_res['name']} (CV-AUC={best_res['cv_auc']:.3f})")

    # 2) Seçilen ailede hiperparametre optimizasyonu (TimeSeriesSplit)
    grids = {
        "Gradient Boosting": (GradientBoostingClassifier(random_state=42),
                              {"clf__n_estimators": [150, 300], "clf__max_depth": [2, 3],
                               "clf__learning_rate": [0.03, 0.06, 0.1], "clf__subsample": [0.8, 1.0]}),
        "Random Forest": (RandomForestClassifier(class_weight="balanced", random_state=42, n_jobs=-1),
                          {"clf__n_estimators": [300, 600], "clf__max_depth": [None, 6, 10],
                           "clf__min_samples_leaf": [1, 5, 20]}),
        "Lojistik Regresyon": (LogisticRegression(max_iter=2000, class_weight="balanced"),
                               {"clf__C": [0.1, 0.3, 1.0, 3.0]}),
    }
    base_model, grid = grids[best_res["name"]]
    print(f"Hiperparametre optimizasyonu ({best_res['name']})...")
    gs = GridSearchCV(build_pipeline(base_model), grid, cv=TimeSeriesSplit(n_splits=4),
                      scoring="roc_auc", n_jobs=-1)
    gs.fit(X, y)
    print(f"  En iyi param: {gs.best_params_}")
    print(f"  Tuned CV-AUC: {gs.best_score_:.3f}")

    tuned_cv = float(gs.best_score_)

    # 3) Holdout (en yeni %25) üzerinde son rapor
    tr, te = time_split(df)
    final = build_pipeline(base_model.set_params(**{k.replace("clf__", ""): v for k, v in gs.best_params_.items()}))
    final.fit(tr[feats], tr["y"].astype(int))
    p = final.predict_proba(te[feats])[:, 1]
    hold_auc = roc_auc_score(te["y"], p) if te["y"].nunique() > 1 else float("nan")
    hold_acc = accuracy_score(te["y"], (p >= 0.5).astype(int))
    hold_brier = brier_score_loss(te["y"], p)
    print(f"\nHoldout (en yeni {len(te)}): AUC={hold_auc:.3f}  Acc={hold_acc:.3f}  Brier={hold_brier:.3f}")
    print("  ", classification_report(te["y"], (p >= 0.5).astype(int), digits=3).replace("\n", "\n   "))

    # 4) Üretim: tüm veriyle + kalibrasyonla yeniden eğit, kaydet
    prod = build_pipeline(base_model)
    calibrated = CalibratedClassifierCV(prod, method="isotonic", cv=TimeSeriesSplit(n_splits=4))
    calibrated.fit(X, y)

    os.makedirs(MODEL_DIR, exist_ok=True)
    meta = {"best_family": best_res["name"], "tuned_cv_auc": tuned_cv,
            "holdout_auc": float(hold_auc), "holdout_acc": float(hold_acc),
            "holdout_brier": float(hold_brier), "best_params": gs.best_params_,
            "families": results, "n": len(df), "base_rate": float(base_rate),
            "trained_on": df["date"].max().strftime("%Y-%m-%d"), "horizon": 3,
            "target_desc": TARGET_DESC,
            "best": {"name": best_res["name"], "auc": float(hold_auc), "cv_auc": tuned_cv}}
    joblib.dump({
        "pipeline": calibrated, "cat_features": CAT_FEATURES, "num_features": NUM_FEATURES,
        "text_feature": TEXT_FEATURE, "target": "big_move", "big_move_pct": BIG_MOVE_PCT,
        "target_desc": TARGET_DESC, "meta": meta,
    }, MODEL_PATH)
    print(f"\nKalibre model kaydedildi: {MODEL_PATH}")

    with open(os.path.join(MODEL_DIR, "report.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
