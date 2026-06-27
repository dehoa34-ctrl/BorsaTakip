"""
swing_model.py — Faz 2 "ML Güven Skoru" tahmin edicisi (if/else yerine).

DÜRÜST ÇERÇEVE (ölçümle kanıtlandı):
  - 5 günlük YÖN tahmin edilemiyor (CV-AUC 0.53) → ML 'al/sat güveni' VERMEZ.
  - 5 günlük BÜYÜK HAREKET (>%6) öğrenilebiliyor (CV-AUC 0.627) → model bunu verir.
  - Hacim göstergeleri fiyatın üstüne ~0 katıyor; yine de Faz 1'de YORUM olarak değerli.

Bu yüzden çıktı: "büyük hareket / hareketlilik olasılığı" + akıllı para karakteri.
"""

import os
import functools

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
MODEL_PATH = os.path.join(HERE, "models", "swing_confidence.joblib")


@functools.lru_cache(maxsize=1)
def _load():
    if not os.path.exists(MODEL_PATH):
        return None
    try:
        import joblib
        return joblib.load(MODEL_PATH)
    except Exception:
        return None


def info():
    m = _load()
    return {"ready": bool(m), **(m["meta"] if m else {})}


def predict_from_df(df, symbol=None):
    """OHLCV df'inden ML güven skoru (büyük hareket olasılığı) + akıllı para özeti."""
    m = _load()
    if not m or df is None or len(df) < 60:
        return None
    from swing_dataset import build_features
    import flow as flowmod
    if symbol:
        try:
            df.attrs["symbol"] = symbol.replace(".IS", "")
        except Exception:
            pass

    feats = build_features(df)
    needed = m["features"]
    # Model temel veri (PIT) bekliyorsa canlı en güncel yayımlanmış çeyreği ekle
    pit_cols = [c for c in needed if c.startswith("pit_")]
    if pit_cols:
        try:
            import pit_fundamentals as pf
            sym = (df.attrs.get("symbol") if hasattr(df, "attrs") else None)
            latest = pf.latest_pit(sym) if sym else {c: None for c in pit_cols}
        except Exception:
            latest = {c: None for c in pit_cols}
        for c in pit_cols:
            val = latest.get(c)
            feats[c] = np.nan if val is None else float(val)
    # Sadece teknik+hacim sütunları NaN değilse satırı al (PIT NaN olabilir)
    base = [c for c in needed if not c.startswith("pit_")]
    valid = feats[base].dropna()
    if valid.empty:
        return None
    x = feats.loc[[valid.index[-1]], needed]
    try:
        p = float(m["pipeline"].predict_proba(x)[:, 1][0])
    except Exception:
        return None

    fl = flowmod.analyze_flow(df)
    base = m["meta"].get("pos_rate", 0.3)
    if p >= base * 1.6:
        label = "Yüksek Hareketlilik Beklentisi"
    elif p >= base * 1.1:
        label = "Orta Hareketlilik"
    else:
        label = "Sakin / Düşük Hareketlilik"

    return {
        "ml_confidence": round(p * 100, 1),
        "label": label,
        "target": "5g büyük hareket (>%6) olasılığı",
        "note": "ML modeli YÖN değil, HAREKETLİLİK (büyük hareket) olasılığını verir. Yön için konsensüs+akıllı para karakterine bakın.",
        "flow_character": fl["money_flow"]["label"] if fl.get("ok") else None,
        "flow_score": fl["money_flow"]["score"] if fl.get("ok") else 0.0,
        "trap": fl.get("trap") if fl.get("ok") else None,
        "divergence": fl.get("divergence") if fl.get("ok") else None,
    }


def predict(symbol):
    try:
        import yfinance as yf
        df = yf.Ticker(symbol if symbol.endswith(".IS") else symbol + ".IS").history(period="6mo", interval="1d")
        return predict_from_df(df, symbol=symbol)
    except Exception:
        return None
