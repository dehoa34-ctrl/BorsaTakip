"""
flow.py — Hacim & Likidite (Akıllı Para) göstergeleri.

PGC (para giriş-çıkış) verisini Python'a alamadığımız için, para akışını MATEMATİKSEL
olarak simüle eden göstergeler: MFI, OBV, CMF, Volume Profile (POC).
Ayrıca fiyat-hacim UYUMSUZLUĞU (divergence) ve TUZAK (bear/bull trap) tespiti.

Felsefe: Klasik fiyat indikatörleri (RSI/MACD) perakendeyi tuzağa düşürür
(RSI 35 → "Sat" derken balina mal topluyor olabilir). Hacim göstergeleri
"para giriyor mu çıkıyor mu" sorusunu yanıtlar — akıllı para filtresi.
"""

import numpy as np
import pandas as pd


# ─────────────────────────────────────────────────────────────────────────────
#  Çekirdek hesaplar
# ─────────────────────────────────────────────────────────────────────────────
def mfi(df, period=14):
    """Money Flow Index (0-100). Fiyatı hacimle ağırlıklandırır."""
    tp = (df["High"] + df["Low"] + df["Close"]) / 3
    rmf = tp * df["Volume"]
    pos = rmf.where(tp > tp.shift(), 0.0)
    neg = rmf.where(tp < tp.shift(), 0.0)
    pos_sum = pos.rolling(period).sum()
    neg_sum = neg.rolling(period).sum()
    ratio = pos_sum / neg_sum.replace(0, np.nan)
    return 100 - (100 / (1 + ratio))


def obv(df):
    """On-Balance Volume (kümülatif). Akümülasyonu/dağıtımı yakalar."""
    direction = np.sign(df["Close"].diff()).fillna(0)
    return (direction * df["Volume"]).cumsum()


def cmf(df, period=20):
    """Chaikin Money Flow. 0 üstü kurumsal alım, altı satım bölgesi."""
    rng = (df["High"] - df["Low"]).replace(0, np.nan)
    mfm = ((df["Close"] - df["Low"]) - (df["High"] - df["Close"])) / rng
    mfv = mfm * df["Volume"]
    return mfv.rolling(period).sum() / df["Volume"].rolling(period).sum()


def volume_profile_poc(df, lookback=120, bins=24):
    """
    Volume Profile → POC (Point of Control): en çok lotun döndüğü fiyat seviyesi.
    Son `lookback` mumun hacmini fiyat kovalarına dağıtır.
    """
    d = df.tail(lookback)
    lo, hi = float(d["Low"].min()), float(d["High"].max())
    if hi <= lo:
        return None, None, None
    edges = np.linspace(lo, hi, bins + 1)
    centers = (edges[:-1] + edges[1:]) / 2
    vol = np.zeros(bins)
    tp = ((d["High"] + d["Low"] + d["Close"]) / 3).values
    v = d["Volume"].values
    idx = np.clip(np.digitize(tp, edges) - 1, 0, bins - 1)
    for i, b in enumerate(idx):
        vol[b] += v[i]
    poc_i = int(np.argmax(vol))
    return float(centers[poc_i]), lo, hi


def _slope(series, n):
    """Son n noktanın normalize eğimi (% / bar)."""
    s = series.dropna().tail(n)
    if len(s) < n:
        return 0.0
    y = s.values
    x = np.arange(len(y))
    m = np.polyfit(x, y, 1)[0]
    base = np.mean(np.abs(y)) or 1.0
    return float(m / base * 100)


# ─────────────────────────────────────────────────────────────────────────────
#  Ana analiz
# ─────────────────────────────────────────────────────────────────────────────
def analyze_flow(df, symbol="", lookback_div=14):
    if df is None or len(df) < 30:
        return {"ok": False, "message": "Hacim analizi için en az 30 mum gerekli."}

    df = df.copy()
    price = float(df["Close"].iloc[-1])
    mfi_s = mfi(df)
    obv_s = obv(df)
    cmf_s = cmf(df)
    poc, vp_lo, vp_hi = volume_profile_poc(df)

    mfi_v = float(mfi_s.dropna().iloc[-1]) if mfi_s.notna().any() else 50.0
    cmf_v = float(cmf_s.dropna().iloc[-1]) if cmf_s.notna().any() else 0.0
    obv_slope = _slope(obv_s, 10)
    price_slope = _slope(df["Close"], lookback_div)
    mfi_slope = _slope(mfi_s, lookback_div)
    obv_slope_div = _slope(obv_s, lookback_div)

    # ── Gösterge tablosu (yorumlu) ──
    def mfi_act(v):
        if v >= 80:
            return "Aşırı Alış"
        if v <= 20:
            return "Aşırı Satış"
        return "Para Girişi" if v > 50 else "Para Çıkışı"

    items = [
        {"name": "MFI(14)", "value": round(mfi_v, 2), "action": mfi_act(mfi_v),
         "desc": "Hacim ağırlıklı para akışı"},
        {"name": "OBV Trend (10g)", "value": round(obv_slope, 2),
         "action": "Akümülasyon" if obv_slope > 0.5 else ("Dağıtım" if obv_slope < -0.5 else "Yatay"),
         "desc": "Kümülatif hacim yönü"},
        {"name": "CMF(20)", "value": round(cmf_v, 3),
         "action": "Kurumsal Alım" if cmf_v > 0.05 else ("Kurumsal Satım" if cmf_v < -0.05 else "Nötr"),
         "desc": "Chaikin para akışı (0 üstü alım)"},
        {"name": "POC (Hacim Yoğunluğu)", "value": round(poc, 2) if poc else None,
         "action": "Fiyat POC Üstü" if (poc and price > poc) else "Fiyat POC Altı",
         "desc": "En çok lot dönen fiyat seviyesi"},
    ]

    # ── Divergence (gizli alım/dağıtım) ──
    divergence = None
    if price_slope < -0.3 and (mfi_slope > 0.3 or obv_slope_div > 0.3):
        divergence = {"type": "Pozitif Uyumsuzluk (Gizli Alım)",
                      "note": "Fiyat düşerken para akışı yükseliyor — kurumsal toplama olabilir."}
    elif price_slope > 0.3 and (mfi_slope < -0.3 or obv_slope_div < -0.3):
        divergence = {"type": "Negatif Uyumsuzluk (Gizli Dağıtım)",
                      "note": "Fiyat yükselirken para çıkıyor — dağıtım/zayıflama olabilir."}

    # ── Tuzak tespiti ──
    low20 = df["Low"].rolling(20).min().iloc[-1]
    high20 = df["High"].rolling(20).max().iloc[-1]
    near_support = price <= low20 * 1.02
    near_resist = price >= high20 * 0.98
    money_in = cmf_v > 0 or obv_slope > 0
    money_out = cmf_v < 0 or obv_slope < 0

    trap = None
    if near_support and money_in and mfi_v < 45:
        trap = {"type": "Ayı Tuzağı", "risk": "Yüksek" if cmf_v > 0.05 else "Orta",
                "note": "Fiyat desteği test ediyor AMA akıllı para (MFI/OBV/CMF) içeri giriyor → Ayı Tuzağı ihtimali."}
    elif near_resist and money_out and mfi_v > 55:
        trap = {"type": "Boğa Tuzağı", "risk": "Yüksek" if cmf_v < -0.05 else "Orta",
                "note": "Fiyat direnci test ediyor AMA para çıkıyor → Boğa Tuzağı ihtimali."}

    # ── Akıllı para karakteri (özet skor -1..+1) ──
    flow_score = np.tanh((cmf_v * 4) + (obv_slope * 0.3) + ((mfi_v - 50) / 50))
    if flow_score > 0.35:
        flow_label = "Akıllı Para Giriyor (Akümülasyon)"
    elif flow_score < -0.35:
        flow_label = "Akıllı Para Çıkıyor (Dağıtım)"
    else:
        flow_label = "Nötr / Kararsız Akış"

    return {
        "ok": True,
        "symbol": symbol,
        "price": round(price, 2),
        "items": items,
        "divergence": divergence,
        "trap": trap,
        "money_flow": {"label": flow_label, "score": round(float(flow_score), 3),
                       "cmf": round(cmf_v, 3), "mfi": round(mfi_v, 1), "obv_slope": round(obv_slope, 2)},
        # ML için ham feature sözlüğü (Faz 2'de kullanılacak)
        "features": {
            "mfi": mfi_v, "cmf": cmf_v, "obv_slope10": obv_slope,
            "price_slope": price_slope, "mfi_slope": mfi_slope, "obv_slope_div": obv_slope_div,
            "price_vs_poc": (price / poc - 1) * 100 if poc else 0.0,
            "near_support": int(near_support), "near_resist": int(near_resist),
        },
    }
