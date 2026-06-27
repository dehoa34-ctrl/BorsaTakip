"""
ml_dataset.py — KAP arşivi + gerçek fiyatlardan etiketli eğitim seti üretir.

Hedef (kullanıcı kararı): YÖN — bildirimden sonra 3 işlem gününde fiyat yukarı mı?
Etiket y = 1 (yükseliş) / 0 (düşüş veya yatay).

Özellikler (bildirim ANINDAKİ bilgi — sızıntı yok):
    - category (kategori), sentiment_score, category_bias
    - dow (haftanın günü), hour (saat)
    - sym_freq (sembolün arşivdeki bildirim sıklığı ~ aktiflik)
    - rsi14, ret5 (son 5 gün getirisi), px_vs_sma20 (trend), vol_ratio (hacim)
    bildirim tarihine kadar olan fiyatla hesaplanır.
"""

import os
import re
import pickle
import concurrent.futures as cf

import numpy as np
import pandas as pd

import sources

_PCT_RE = re.compile(r"%\s*([0-9]+(?:[.,][0-9]+)?)|([0-9]+(?:[.,][0-9]+)?)\s*%")


def title_magnitude(title):
    """Başlıktaki en büyük yüzde değerini çıkar (bedelsiz %100, temettü %25 ...)."""
    if not title:
        return 0.0
    vals = []
    for m in _PCT_RE.finditer(str(title)):
        g = m.group(1) or m.group(2)
        try:
            vals.append(float(g.replace(",", ".")))
        except Exception:
            pass
    return float(max(vals)) if vals else 0.0

PRICE_CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "price_cache.pkl")


# ─────────────────────────────────────────────────────────────────────────────
#  Fiyat geçmişi (sembol başına, diske önbellekli)
# ─────────────────────────────────────────────────────────────────────────────
def _load_cache():
    if os.path.exists(PRICE_CACHE):
        try:
            with open(PRICE_CACHE, "rb") as f:
                return pickle.load(f)
        except Exception:
            return {}
    return {}


def _save_cache(cache):
    try:
        with open(PRICE_CACHE, "wb") as f:
            pickle.dump(cache, f)
    except Exception:
        pass


def fetch_prices(symbols, period="1y", max_workers=10, cache=None):
    """Sembol → DataFrame (Close, Volume). Diske önbellekli, threadli."""
    import yfinance as yf
    cache = cache if cache is not None else _load_cache()

    todo = [s for s in symbols if s not in cache]

    def work(sym):
        try:
            h = yf.Ticker(sym + ".IS").history(period=period, interval="1d")
            if h is None or len(h) < 30:
                return sym, None
            return sym, h[["Close", "Volume", "High", "Low"]]
        except Exception:
            return sym, None

    if todo:
        with cf.ThreadPoolExecutor(max_workers=max_workers) as ex:
            for sym, df in ex.map(work, todo):
                cache[sym] = df
        _save_cache(cache)
    return cache


# ─────────────────────────────────────────────────────────────────────────────
#  Teknik özellikler (bildirim tarihine kadar)
# ─────────────────────────────────────────────────────────────────────────────
def _rsi(close, period=14):
    d = close.diff()
    g = d.where(d > 0, 0.0).rolling(period).mean()
    l = (-d.where(d < 0, 0.0)).rolling(period).mean()
    rs = g / l.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def _features_at(df, base_pos):
    """base_pos indeksindeki (bildirim günü) teknik özellikler — sadece geçmiş veri."""
    close = df["Close"]
    if base_pos < 20:
        return None
    rsi = _rsi(close).iloc[base_pos]
    sma20 = close.iloc[base_pos - 20:base_pos].mean()
    px = close.iloc[base_pos]
    ret5 = (close.iloc[base_pos] / close.iloc[base_pos - 5] - 1) * 100 if base_pos >= 5 else 0.0
    vol = df["Volume"]
    vol_ratio = vol.iloc[base_pos] / (vol.iloc[base_pos - 20:base_pos].mean() + 1e-9)
    return {
        "rsi14": float(rsi) if pd.notna(rsi) else 50.0,
        "ret5": float(ret5),
        "px_vs_sma20": float((px / sma20 - 1) * 100) if sma20 else 0.0,
        "vol_ratio": float(vol_ratio) if pd.notna(vol_ratio) else 1.0,
    }


# ─────────────────────────────────────────────────────────────────────────────
#  Etiket: +3 işlem günü yön
# ─────────────────────────────────────────────────────────────────────────────
def _label_and_pos(df, event_date, horizon=3):
    idx = df.index
    ed = pd.Timestamp(event_date)
    if idx.tz is not None and ed.tzinfo is None:
        ed = ed.tz_localize(idx.tz)
    pos = idx.searchsorted(ed)
    if pos >= len(idx) - horizon:
        return None, None, None
    base = float(df["Close"].iloc[pos])
    fut = float(df["Close"].iloc[pos + horizon])
    if not base:
        return None, None, None
    ret = (fut - base) / base * 100
    return (1 if ret > 0 else 0), pos, ret


# ─────────────────────────────────────────────────────────────────────────────
#  Eğitim seti
# ─────────────────────────────────────────────────────────────────────────────
def build_dataset(horizon=3, only_meaningful=True, verbose=True):
    sources.init_db()
    rows = [r for r in sources.recent_all(limit=100000) if r["source"] == "KAP" and r["date"]]
    if verbose:
        print(f"Arşivde KAP: {len(rows)}")

    skip_cats = {"Pay Bazında Devre Kesici", "Genel Bilgi"}
    if only_meaningful:
        rows = [r for r in rows if r["category"] not in skip_cats]

    # sembol sıklığı
    freq = {}
    for r in rows:
        freq[r["symbol"]] = freq.get(r["symbol"], 0) + 1

    symbols = sorted(set(r["symbol"] for r in rows))
    if verbose:
        print(f"Fiyat çekilecek sembol: {len(symbols)} (önbellekten + canlı)")
    cache = fetch_prices(symbols)

    recs = []
    for r in rows:
        df = cache.get(r["symbol"])
        if df is None or df.empty:
            continue
        y, pos, ret = _label_and_pos(df, r["date"], horizon)
        if y is None or pos is None:
            continue
        feats = _features_at(df, pos)
        if feats is None:
            continue
        # saat
        hour = 0
        if r.get("time"):
            try:
                hour = int(str(r["time"]).split(":")[0])
            except Exception:
                hour = 0
        dow = pd.Timestamp(r["date"]).dayofweek
        title = r.get("title", "")
        recs.append({
            "symbol": r["symbol"], "date": r["date"], "category": r["category"],
            "title": title,
            "sentiment_score": r["score"], "category_bias": r["bias"],
            "title_pct": title_magnitude(title), "title_len": len(title),
            "dow": dow, "hour": hour, "sym_freq": freq.get(r["symbol"], 1),
            **feats, "ret3": round(ret, 2), "y": y,
        })

    data = pd.DataFrame(recs)
    if verbose and len(data):
        print(f"Etiketli örnek: {len(data)} | yükseliş oranı: {data['y'].mean():.1%}")
    return data


if __name__ == "__main__":
    df = build_dataset()
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ml_dataset.csv")
    df.to_csv(out, index=False, encoding="utf-8")
    print("Kaydedildi:", out, df.shape)
