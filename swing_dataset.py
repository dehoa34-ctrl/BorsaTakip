"""
swing_dataset.py — Faz 2 için günlük "Güven Skoru" eğitim seti.

if/else puanlama yerine: her hissenin her günü için TEKNİK + HACIM (akıllı para)
feature'ları çıkarır, ileriye dönük (5 işlem günü) etiketler üretir. Hedef: hacim
göstergelerinin (MFI/OBV/CMF) saf fiyat indikatörlerine sinyal ekleyip eklemediğini
ÖLÇMEK. Sızıntısız: tüm feature'lar t anına kadar; etiket t+5.

Kaynak: price_cache.pkl (ml_dataset ile paylaşılır).
"""

import os
import pickle
import numpy as np
import pandas as pd

from ml_dataset import _load_cache, fetch_prices
import flow
import pit_fundamentals as pf

HORIZON = 5
BIG_PCT = 6.0
STRONG_PCT = 4.0

HERE = os.path.dirname(os.path.abspath(__file__))
LONG_CACHE = os.path.join(HERE, "price_cache_5y.pkl")
PIT_CACHE = os.path.join(HERE, "pit_cache.pkl")


def _load_long_cache():
    """5y fiyat cache'i varsa onu, yoksa 1y cache'i kullan."""
    if os.path.exists(LONG_CACHE):
        try:
            return pickle.load(open(LONG_CACHE, "rb")), "5y"
        except Exception:
            pass
    return _load_cache(), "1y"


def _load_pit():
    if os.path.exists(PIT_CACHE):
        try:
            return pickle.load(open(PIT_CACHE, "rb"))
        except Exception:
            pass
    return {}


# ── Vektörel indikatör kolonları (sızıntısız) ──────────────────────────────
def _rsi(c, n=14):
    d = c.diff()
    g = d.where(d > 0, 0.0).rolling(n).mean()
    l = (-d.where(d < 0, 0.0)).rolling(n).mean()
    return 100 - 100 / (1 + g / l.replace(0, np.nan))


def _adx(df, n=14):
    h, l, c = df["High"], df["Low"], df["Close"]
    up, dn = h.diff(), -l.diff()
    plus = np.where((up > dn) & (up > 0), up, 0.0)
    minus = np.where((dn > up) & (dn > 0), dn, 0.0)
    tr = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    atr = tr.rolling(n).mean()
    pdi = 100 * pd.Series(plus, index=df.index).rolling(n).mean() / atr
    mdi = 100 * pd.Series(minus, index=df.index).rolling(n).mean() / atr
    dx = 100 * (pdi - mdi).abs() / (pdi + mdi).replace(0, np.nan)
    return dx.rolling(n).mean()


def build_features(df):
    """Bir hissenin df'inden feature kolonları (sızıntısız) + ileriye dönük etiketler."""
    c, h, l, v = df["Close"], df["High"], df["Low"], df["Volume"]
    out = pd.DataFrame(index=df.index)
    # Teknik (saf fiyat)
    out["rsi14"] = _rsi(c)
    ema12, ema26 = c.ewm(span=12, adjust=False).mean(), c.ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26
    out["macd_hist"] = macd - macd.ewm(span=9, adjust=False).mean()
    out["adx"] = _adx(df)
    out["px_vs_sma20"] = (c / c.rolling(20).mean() - 1) * 100
    out["px_vs_sma50"] = (c / c.rolling(50).mean() - 1) * 100
    out["ret5"] = c.pct_change(5) * 100
    out["vol_ratio"] = v / v.rolling(20).mean()
    low14 = l.rolling(14).min()
    out["williams_r"] = -100 * (h.rolling(14).max() - c) / (h.rolling(14).max() - low14).replace(0, np.nan)
    # Hacim / akıllı para (YENİ bilgi)
    out["mfi"] = flow.mfi(df)
    out["cmf"] = flow.cmf(df)
    obv = flow.obv(df)
    out["obv_slope10"] = (obv - obv.shift(10)) / (obv.abs().rolling(20).mean() + 1e-9)
    vwap = (((h + l + c) / 3) * v).rolling(40).sum() / v.rolling(40).sum()  # POC/VWAP proxy
    out["px_vs_vwap"] = (c / vwap - 1) * 100
    # Divergence: fiyat eğimi vs MFI eğimi (14g)
    out["price_slope14"] = (c - c.shift(14)) / c.shift(14) * 100
    out["mfi_slope14"] = out["mfi"] - out["mfi"].shift(14)
    out["bull_div"] = ((out["price_slope14"] < 0) & (out["mfi_slope14"] > 0)).astype(int)
    out["bear_div"] = ((out["price_slope14"] > 0) & (out["mfi_slope14"] < 0)).astype(int)
    # Destek/direnç yakınlığı
    out["near_support"] = (c <= l.rolling(20).min() * 1.02).astype(int)
    out["near_resist"] = (c >= h.rolling(20).max() * 0.98).astype(int)

    # ── İleriye dönük etiketler (t+HORIZON) ──
    fwd = (c.shift(-HORIZON) / c - 1) * 100
    out["fwd"] = fwd
    out["y_dir"] = (fwd > 0).astype(int)
    out["y_big"] = (fwd.abs() > BIG_PCT).astype(int)
    out["y_up"] = (fwd > STRONG_PCT).astype(int)
    # Ayı tuzağı: destekteyken sonraki dönemde güçlü yükseliş
    out["y_beartrap"] = ((c <= l.rolling(20).min() * 1.02) & (fwd > STRONG_PCT)).astype(int)
    return out


PRICE_ONLY = ["rsi14", "macd_hist", "adx", "px_vs_sma20", "px_vs_sma50", "ret5",
              "vol_ratio", "williams_r"]  # hacimsiz kıyas için
FLOW_FEATURES = ["mfi", "cmf", "obv_slope10", "px_vs_vwap", "price_slope14",
                 "mfi_slope14", "bull_div", "bear_div", "near_support", "near_resist"]
FEATURES = PRICE_ONLY + FLOW_FEATURES                 # teknik + hacim
PIT_FEATURES = pf.PIT_FEATURES                         # point-in-time temel
FEATURES_FUND = FEATURES + PIT_FEATURES                # + temel
TARGETS = ["y_dir", "y_big", "y_up", "y_beartrap"]


def _winsor_pit(df):
    """Aşırı YoY büyüme uçlarını kırp (model uçlardan bozulmasın)."""
    for c in ("pit_rev_growth", "pit_earn_growth"):
        if c in df:
            df[c] = df[c].clip(-100, 300)
    return df


def build_dataset(verbose=True, with_pit=True):
    cache, src = _load_long_cache()
    pit = _load_pit() if with_pit else {}
    symbols = [s for s, d in cache.items() if d is not None and len(d) >= 80]
    if verbose:
        print(f"Sembol: {len(symbols)} (kaynak: {src} fiyat, PIT: {sum(1 for v in pit.values() if v is not None)} hisse)")
    frames = []
    for sym in symbols:
        df = cache[sym]
        try:
            f = build_features(df)
        except Exception:
            continue
        f["symbol"] = sym.replace(".IS", "")
        f["date"] = df.index
        # Point-in-time temel veriyi as-of (sızıntısız) ekle
        if with_pit:
            f = pf.merge_pit(f, pit.get(sym))
        frames.append(f)
    data = pd.concat(frames, ignore_index=True)
    if with_pit:
        data = _winsor_pit(data)
    data = data.dropna(subset=FEATURES + ["fwd"]).reset_index(drop=True)
    data = data.sort_values("date").reset_index(drop=True)
    if verbose:
        print(f"Satır: {len(data)} | tarih {data['date'].min().date()}..{data['date'].max().date()}")
        for t in TARGETS:
            print(f"  {t}: pozitif %{data[t].mean()*100:.1f}")
    return data


if __name__ == "__main__":
    d = build_dataset()
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "swing_dataset.parquet")
    try:
        d.to_parquet(out, index=False)
        print("Kaydedildi:", out, d.shape)
    except Exception:
        d.to_csv(out.replace(".parquet", ".csv"), index=False)
        print("Kaydedildi (csv):", d.shape)
