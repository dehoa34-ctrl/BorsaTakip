"""
ml_explore.py — Alternatif hedeflerde sinyal var mı? (zaman-serisi CV AUC)
Yön tahmini ~0.50 çıktı; burada 'büyük hareket' ve kategori-bazlı hedefleri test ederiz.
"""
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.pipeline import Pipeline
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import TimeSeriesSplit, cross_val_score

df = pd.read_csv("ml_dataset.csv", encoding="utf-8")
df["title"] = df["title"].fillna("").astype(str)
df["date"] = pd.to_datetime(df["date"]); df = df.sort_values("date").reset_index(drop=True)

CAT = ["category"]; TXT = "title"
NUM = ["sentiment_score", "category_bias", "dow", "hour", "sym_freq", "rsi14", "ret5", "px_vs_sma20", "vol_ratio"]
feats = CAT + [TXT] + NUM


def pipe():
    pre = ColumnTransformer([
        ("cat", OneHotEncoder(handle_unknown="ignore"), CAT),
        ("txt", TfidfVectorizer(max_features=400, ngram_range=(1, 2), min_df=3), TXT),
        ("num", StandardScaler(), NUM),
    ])
    return Pipeline([("pre", pre), ("clf", LogisticRegression(max_iter=1000, class_weight="balanced"))])


def cv_auc(y):
    if y.nunique() < 2 or y.sum() < 20 or (len(y) - y.sum()) < 20:
        return None
    try:
        s = cross_val_score(pipe(), df[feats], y, cv=TimeSeriesSplit(n_splits=5), scoring="roc_auc")
        return s.mean()
    except Exception:
        return None


print(f"n={len(df)}")
targets = {
    "Yön (ret3>0)": (df["ret3"] > 0).astype(int),
    "Büyük hareket |ret3|>4%": (df["ret3"].abs() > 4).astype(int),
    "Büyük hareket |ret3|>7%": (df["ret3"].abs() > 7).astype(int),
    "Güçlü yükseliş ret3>4%": (df["ret3"] > 4).astype(int),
    "Güçlü düşüş ret3<-4%": (df["ret3"] < -4).astype(int),
}
for name, y in targets.items():
    a = cv_auc(y)
    rate = y.mean()
    print(f"  {name:32} poz={rate:5.1%}  CV-AUC={'%.3f'%a if a else 'n/a'}")

print("\nKategori-bazlı YÖN (yalnız anlamlı, n>=150):")
for cat, g in df.groupby("category"):
    if len(g) < 150:
        continue
    y = (g["ret3"] > 0).astype(int)
    if y.nunique() < 2:
        continue
    try:
        s = cross_val_score(pipe(), g[feats], y, cv=TimeSeriesSplit(n_splits=4), scoring="roc_auc")
        print(f"  {cat:32} n={len(g):4}  yön CV-AUC={s.mean():.3f}")
    except Exception:
        pass
