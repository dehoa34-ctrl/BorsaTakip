"""
ml_category.py — Kategori-bazlı YÖN modelleri.

Genel yön tahmini ~0.50 (etkin piyasa); ama BAZI kategorilerde yön sinyali var
(örn. Pay Geri Alım). Burada her anlamlı kategori için ayrı bir yön modeli eğitir,
yalnızca sinyal taşıyanları (zaman-serisi CV-AUC >= eşik) saklarız.

Çıktı: models/category_direction.joblib = {kategori: {pipeline, cv_auc, n, up_rate}}
"""

import os
import json

import numpy as np
import pandas as pd
import joblib

from sklearn.compose import ColumnTransformer
from sklearn.preprocessing import StandardScaler
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.pipeline import Pipeline
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import TimeSeriesSplit, cross_val_score

HERE = os.path.dirname(os.path.abspath(__file__))
DATASET = os.path.join(HERE, "ml_dataset.csv")
MODEL_DIR = os.path.join(HERE, "models")
CAT_MODEL_PATH = os.path.join(MODEL_DIR, "category_direction.joblib")

TEXT_FEATURE = "title"
# Kategori sabit olduğu için 'category' one-hot yok; geri kalan özellikler:
NUM_FEATURES = ["sentiment_score", "category_bias", "title_pct", "title_len",
                "dow", "hour", "sym_freq", "rsi14", "ret5", "px_vs_sma20", "vol_ratio"]

MIN_SAMPLES = 180
KEEP_AUC = 0.55      # sadece bu eşiğin üstünde sinyal taşıyan kategoriler saklanır


def _pipe():
    pre = ColumnTransformer([
        ("txt", TfidfVectorizer(max_features=200, ngram_range=(1, 2), min_df=2), TEXT_FEATURE),
        ("num", StandardScaler(), NUM_FEATURES),
    ])
    return Pipeline([("pre", pre), ("clf", LogisticRegression(max_iter=2000, class_weight="balanced"))])


def main():
    df = pd.read_csv(DATASET, encoding="utf-8")
    df["title"] = df["title"].fillna("").astype(str)
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").reset_index(drop=True)
    feats = [TEXT_FEATURE] + NUM_FEATURES

    def cv(g, y):
        if y.nunique() < 2 or min(y.sum(), len(y) - y.sum()) < 30:
            return None
        try:
            s = cross_val_score(_pipe(), g[feats], y, cv=TimeSeriesSplit(n_splits=4),
                                scoring="roc_auc", n_jobs=-1)
            return float(s.mean())
        except Exception:
            return None

    kept = {}
    report = []
    print(f"Toplam örnek: {len(df)}")
    print(f"Kategori-bazlı modeller — YÖN vs OLAY ETKİSİ (eşik CV-AUC>={KEEP_AUC}):\n")

    for cat, g in df.groupby("category"):
        if len(g) < MIN_SAMPLES or cat in ("Genel Bilgi", "Pay Bazında Devre Kesici"):
            continue
        y_dir = (g["ret3"] > 0).astype(int)
        y_imp = (g["ret3"].abs() > 7).astype(int)
        auc_dir = cv(g, y_dir)
        auc_imp = cv(g, y_imp)
        # İki hedeften en iyisini seç
        best_t, best_auc, best_y = None, -1, None
        if auc_dir is not None and auc_dir > best_auc:
            best_t, best_auc, best_y = "direction", auc_dir, y_dir
        if auc_imp is not None and auc_imp > best_auc:
            best_t, best_auc, best_y = "impact", auc_imp, y_imp
        if best_t is None:
            continue
        flag = f"✓ SAKLANDI ({best_t})" if best_auc >= KEEP_AUC else "—"
        print(f"  {cat:32} n={len(g):4}  yön={auc_dir if auc_dir else float('nan'):.3f}  "
              f"etki={auc_imp if auc_imp else float('nan'):.3f}  -> {flag}")
        report.append({"category": cat, "n": int(len(g)), "auc_dir": auc_dir,
                       "auc_impact": auc_imp, "best": best_t, "best_auc": best_auc,
                       "kept": best_auc >= KEEP_AUC})
        if best_auc >= KEEP_AUC:
            pipe = _pipe()
            pipe.fit(g[feats], best_y)
            kept[cat] = {"pipeline": pipe, "target": best_t, "cv_auc": best_auc,
                         "n": int(len(g)), "pos_rate": float(best_y.mean())}

    os.makedirs(MODEL_DIR, exist_ok=True)
    joblib.dump({"models": kept, "num_features": NUM_FEATURES, "text_feature": TEXT_FEATURE,
                 "min_auc": KEEP_AUC}, CAT_MODEL_PATH)
    with open(os.path.join(MODEL_DIR, "category_report.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"\n{len(kept)} kategori modeli saklandı → {CAT_MODEL_PATH}")


if __name__ == "__main__":
    main()
