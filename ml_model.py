"""
ml_model.py — Eğitilmiş modeli yükle ve yeni bir KAP haberi için
3 günlük YÜKSELİŞ olasılığını tahmin et.

Özellikler eğitimle AYNI şekilde (canlı fiyat + kategori/duygu) üretilir.
Model yoksa zarifçe None döner (sistem istatistik motoruyla çalışmaya devam eder).
"""

import os
import functools

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
MODEL_PATH = os.path.join(HERE, "models", "kap_direction.joblib")
CAT_MODEL_PATH = os.path.join(HERE, "models", "category_direction.joblib")


@functools.lru_cache(maxsize=1)
def _load():
    if not os.path.exists(MODEL_PATH):
        return None
    try:
        import joblib
        return joblib.load(MODEL_PATH)
    except Exception:
        return None


@functools.lru_cache(maxsize=1)
def _load_cat():
    if not os.path.exists(CAT_MODEL_PATH):
        return None
    try:
        import joblib
        return joblib.load(CAT_MODEL_PATH)
    except Exception:
        return None


def model_info():
    m = _load()
    if not m:
        return {"ready": False}
    info = {"ready": True, **m.get("meta", {})}
    catm = _load_cat()
    if catm and catm.get("models"):
        info["category_models"] = {
            cat: {"target": v["target"], "cv_auc": round(v["cv_auc"], 3), "n": v["n"]}
            for cat, v in catm["models"].items()
        }
    return info


def _live_features(symbol):
    """Sembolün GÜNCEL teknik özellikleri (rsi14, ret5, px_vs_sma20, vol_ratio)."""
    try:
        import yfinance as yf
        from ml_dataset import _rsi
        h = yf.Ticker(symbol if symbol.endswith(".IS") else symbol + ".IS").history(period="6mo", interval="1d")
        if h is None or len(h) < 25:
            return None
        h = h.dropna(subset=["Close"])   # bugünün boş/tamamlanmamış barını at
        if len(h) < 25:
            return None
        close, vol = h["Close"], h["Volume"]
        rsi = _rsi(close).iloc[-1]
        sma20 = close.iloc[-20:].mean()
        px = close.iloc[-1]
        ret5 = (close.iloc[-1] / close.iloc[-6] - 1) * 100
        vol_ratio = vol.iloc[-1] / (vol.iloc[-20:].mean() + 1e-9)
        return {
            "rsi14": float(rsi) if pd.notna(rsi) else 50.0,
            "ret5": float(ret5),
            "px_vs_sma20": float((px / sma20 - 1) * 100) if sma20 else 0.0,
            "vol_ratio": float(vol_ratio) if pd.notna(vol_ratio) else 1.0,
        }
    except Exception:
        return None


def predict(symbol, title, date=None, time_str=None, sym_freq=5):
    """
    Yeni bir KAP haberi için 3 günlük yükseliş olasılığı.
    Dönüş: {ok, prob_up, label} veya {ok: False} (model/fiyat yoksa).
    """
    m = _load()
    if not m:
        return {"ok": False, "reason": "model_yok"}

    from news_engine import classify_item
    from ml_dataset import title_magnitude
    cls = classify_item(title or "")
    feats = _live_features(symbol)
    if feats is None:
        return {"ok": False, "reason": "fiyat_yok"}

    d = pd.Timestamp(date) if date else pd.Timestamp.now()
    hour = 0
    if time_str:
        try:
            hour = int(str(time_str).split(":")[0])
        except Exception:
            hour = 0

    row = pd.DataFrame([{
        "category": cls["category"],
        "title": title or "",
        "sentiment_score": cls["sentiment"]["score"],
        "category_bias": cls["category_bias"],
        "title_pct": title_magnitude(title or ""), "title_len": len(title or ""),
        "dow": int(d.dayofweek), "hour": hour, "sym_freq": sym_freq,
        **feats,
    }])
    # Güvenlik: sayısal NaN kalırsa 0 ile doldur (model NaN kabul etmez)
    for col in ["sentiment_score", "category_bias", "title_pct", "title_len", "dow",
                "hour", "sym_freq", "rsi14", "ret5", "px_vs_sma20", "vol_ratio"]:
        if col in row and pd.isna(row.at[0, col]):
            row.at[0, col] = 0.0
    try:
        p = float(m["pipeline"].predict_proba(row)[:, 1][0])
    except Exception as e:
        return {"ok": False, "reason": str(e)[:80]}

    # Kategori-özel model (varsa) — global modeli teyit eden ek sinyal
    cat_pred = None
    catm = _load_cat()
    if catm and cls["category"] in (catm.get("models") or {}):
        cm = catm["models"][cls["category"]]
        try:
            cp = float(cm["pipeline"].predict_proba(row)[:, 1][0])
            cat_pred = {"category": cls["category"], "target": cm["target"],
                        "prob": round(cp * 100, 1), "cv_auc": round(cm["cv_auc"], 3)}
        except Exception:
            cat_pred = None

    # Büyük hareketler nadir (~%23 baz oran); etiketler baz orana GÖRE.
    if p >= 0.45:
        label = "Yüksek Etki Beklentisi"
    elif p >= 0.30:
        label = "Orta Etki"
    elif p >= 0.18:
        label = "Hafif Etki"
    else:
        label = "Düşük Etki (sakin)"

    # Yön ipucu: duygu temelli (modelden değil — yön tahmin edilemiyor)
    sent = cls["sentiment"]["label"]
    lean = "yukarı" if "Pozitif" in sent else ("aşağı" if "Negatif" in sent else "belirsiz")

    return {
        "ok": True,
        "impact_prob": round(p * 100, 1),
        "label": label,
        "big_move_pct": m.get("big_move_pct", 7.0),
        "direction_lean": lean,
        "category_model": cat_pred,
        "note": "Model OLAY ETKİSİ (büyük hareket) olasılığını verir; yön değil. Yön için geçmiş tepki istatistiğine bakın.",
    }
