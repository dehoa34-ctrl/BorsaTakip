"""
swing_train.py — Faz 2 "Güven Skoru" modeli + bilimsel kıyas.

Soru 1: Hacim göstergeleri (MFI/OBV/CMF) saf-fiyat indikatörlerine sinyal ekliyor mu?
        → tam feature vs sadece-fiyat CV-AUC kıyası.
Soru 2: Hangi hedef öğrenilebilir? (yön / büyük hareket / güçlü yükseliş / ayı tuzağı)
Soru 3: LightGBM mi XGBoost mu?
Hepsi TimeSeriesSplit (kronolojik, sızıntısız) ile.

Kazanan kombinasyon üretime kaydedilir: models/swing_confidence.joblib
"""

import os
import json
import numpy as np
import pandas as pd
import joblib

from sklearn.model_selection import TimeSeriesSplit, cross_val_score
from sklearn.calibration import CalibratedClassifierCV
from lightgbm import LGBMClassifier
from xgboost import XGBClassifier

from swing_dataset import (FEATURES, PRICE_ONLY, FEATURES_FUND, PIT_FEATURES,
                           TARGETS, HORIZON, build_dataset)

HERE = os.path.dirname(os.path.abspath(__file__))
MODEL_DIR = os.path.join(HERE, "models")
MODEL_PATH = os.path.join(MODEL_DIR, "swing_confidence.joblib")
DATA = os.path.join(HERE, "swing_dataset.parquet")


def _load():
    if os.path.exists(DATA):
        try:
            return pd.read_parquet(DATA)
        except Exception:
            pass
    csv = DATA.replace(".parquet", ".csv")
    if os.path.exists(csv):
        return pd.read_csv(csv, parse_dates=["date"])
    return build_dataset()


def models():
    return {
        "LightGBM": LGBMClassifier(n_estimators=300, learning_rate=0.03, num_leaves=31,
                                   subsample=0.8, colsample_bytree=0.8, random_state=42, verbose=-1),
        "XGBoost": XGBClassifier(n_estimators=300, learning_rate=0.03, max_depth=4,
                                 subsample=0.8, colsample_bytree=0.8, random_state=42,
                                 eval_metric="logloss", verbosity=0),
    }


def cv_auc(model, X, y):
    return float(cross_val_score(model, X, y, cv=TimeSeriesSplit(n_splits=4),
                                 scoring="roc_auc", n_jobs=-1).mean())


def main():
    df = _load().sort_values("date").reset_index(drop=True)
    print(f"Satır: {len(df)} | tarih {df['date'].min().date()}..{df['date'].max().date()}\n")

    grid = []
    # y_beartrap GLOBAL hedefini dışla — near_support hem feature hem etikette (leakage).
    global_targets = [t for t in TARGETS if t != "y_beartrap"]
    print(f"{'Hedef':12} {'Model':9} {'Sadece-Fiyat':>13} {'+Hacim':>9} {'Hacim Katkısı':>14}")
    for t in global_targets:
        y = df[t].astype(int)
        if y.nunique() < 2 or y.sum() < 200:
            continue
        for mname, model in models().items():
            try:
                a_price = cv_auc(model, df[PRICE_ONLY], y)
                a_full = cv_auc(model, df[FEATURES], y)
            except Exception as e:
                print(f"  {t} {mname} hata: {str(e)[:40]}")
                continue
            gain = a_full - a_price
            print(f"{t:12} {mname:9} {a_price:13.3f} {a_full:9.3f} {gain:+14.3f}")
            grid.append({"target": t, "model": mname, "auc_price": a_price,
                         "auc_full": a_full, "gain": gain, "subset": "all"})

    # ── AYI TUZAĞI (doğru kurulum): sadece destekteki satırlar, near_* feature'ları çıkar ──
    sup = df[df["near_support"] == 1].sort_values("date").reset_index(drop=True)
    trap_feats = [f for f in FEATURES if f not in ("near_support", "near_resist")]
    y_trap = (sup["fwd"] > 4.0).astype(int)
    print(f"\nAyı Tuzağı (destek altkümesi n={len(sup)}, sıçrama oranı %{y_trap.mean()*100:.1f}):")
    for mname, model in models().items():
        if y_trap.sum() < 100:
            break
        a_price = cv_auc(model, sup[[f for f in PRICE_ONLY]], y_trap)
        a_full = cv_auc(model, sup[trap_feats], y_trap)
        print(f"  {mname:9} fiyat={a_price:.3f}  +hacim={a_full:.3f}  katkı={a_full-a_price:+.3f}")
        grid.append({"target": "beartrap_subset", "model": mname, "auc_price": a_price,
                     "auc_full": a_full, "gain": a_full - a_price, "subset": "near_support",
                     "features": trap_feats})

    # ── TEMEL VERİ KATKISI (point-in-time, sızıntısız) — PIT olan alt kümede ──
    fund_gain = None
    if "pit_roe" in df.columns:
        sub = df[df["pit_roe"].notna()].sort_values("date").reset_index(drop=True)
        if len(sub) > 2000:
            y = sub["y_big"].astype(int)
            print(f"\nTemel veri katkısı (PIT alt kümesi n={len(sub)}, y_big):")
            for mname, model in models().items():
                a_noF = cv_auc(model, sub[FEATURES], y)
                a_F = cv_auc(model, sub[FEATURES_FUND], y)
                print(f"  {mname:9} teknik+hacim={a_noF:.3f}  +temel={a_F:.3f}  katkı={a_F-a_noF:+.3f}")
                grid.append({"target": "y_big_fund", "model": mname, "auc_price": a_noF,
                             "auc_full": a_F, "gain": a_F - a_noF, "subset": "pit",
                             "features": FEATURES_FUND})
                if fund_gain is None or (a_F - a_noF) > fund_gain:
                    fund_gain = a_F - a_noF

    # En iyi LEGITIMATE kombinasyon (global hedeflerden; PIT alt kümesi kıyas amaçlı)
    eligible = [g for g in grid if g["subset"] in ("all",)]
    best = max(eligible, key=lambda g: g["auc_full"])
    print(f"\n>>> En iyi (leakage-siz): {best['target']} / {best['model']} "
          f"(AUC {best['auc_full']:.3f}, hacim katkısı {best['gain']:+.3f})")
    if fund_gain is not None:
        print(f"    Temel veri katkısı (PIT alt kümesi): {fund_gain:+.3f}")

    # Üretim: kazanan hedef + TAM feature seti (teknik+hacim+temel; NaN'i ağaç modeli işler)
    prod = models()[best["model"]]
    feats_used = FEATURES_FUND if "pit_roe" in df.columns else FEATURES
    ycol = df[best["target"]].astype(int)
    calibrated = CalibratedClassifierCV(prod, method="isotonic", cv=TimeSeriesSplit(n_splits=4))
    calibrated.fit(df[feats_used], ycol)

    os.makedirs(MODEL_DIR, exist_ok=True)
    meta = {"target": best["target"], "model": best["model"], "features": feats_used,
            "subset": "all", "auc": best["auc_full"], "auc_price_only": best["auc_price"],
            "volume_gain": best["gain"], "fund_gain": fund_gain, "horizon": HORIZON,
            "n": int(len(df)), "pos_rate": float(ycol.mean()), "grid": grid,
            "trained_on": df["date"].max().strftime("%Y-%m-%d")}
    joblib.dump({"pipeline": calibrated, "features": feats_used, "meta": meta}, MODEL_PATH)
    with open(os.path.join(MODEL_DIR, "swing_report.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    print(f"\nÜretim modeli kaydedildi: {MODEL_PATH}")
    print(f"Hedef={best['target']} ({TARGET_DESC.get(best['target'],'')}), AUC={best['auc_full']:.3f}")


TARGET_DESC = {
    "y_dir": "5g yön (yukarı mı?)",
    "y_big": "5g büyük hareket (>%6)",
    "y_up": "5g güçlü yükseliş (>%4)",
    "y_beartrap": "ayı tuzağı (destek + güçlü sıçrama)",
}

if __name__ == "__main__":
    main()
