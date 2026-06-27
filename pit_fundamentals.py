"""
pit_fundamentals.py — POINT-IN-TIME (sızıntısız) temel veri feature'ları.

yfinance çeyreklik bilançolar TARİHLİ gelir (~6-7 çeyrek). Her çeyreğin ratio'sunu
hesaplayıp RAPORLAMA GECİKMESİ (çeyrek sonu + LAG gün; piyasa ancak o tarihte öğrenir)
ile günlük satırlara as-of merge ederiz → geleceği sızdırmaz.

Üretilen feature'lar:
  pit_roe        : TTM Net Kâr / Özsermaye
  pit_nde        : (Toplam Borç - Nakit) / TTM FAVÖK   (banka: NaN)
  pit_rev_growth : Ciro YoY büyüme (%)
  pit_earn_growth: Net Kâr YoY büyüme (%)

NaN'ler kasıtlı bırakılır — LightGBM/XGBoost NaN'i doğal işler (eksiklik de bilgidir).
"""

import os
import pickle
import concurrent.futures as cf

import numpy as np
import pandas as pd

REPORT_LAG_DAYS = 60
PIT_CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pit_cache.pkl")


def _row(df, *names):
    if df is None or df.empty:
        return None
    for n in names:
        if n in df.index:
            return df.loc[n]
    return None


def quarterly_ratios(symbol):
    """Bir hisse için çeyrek-bazlı ratio'lar; avail_date = çeyrek sonu + LAG."""
    import yfinance as yf
    sym = symbol if symbol.endswith(".IS") else symbol + ".IS"
    try:
        t = yf.Ticker(sym)
        qi = t.quarterly_income_stmt
        qb = t.quarterly_balance_sheet
    except Exception:
        return None
    if qi is None or qi.empty or qb is None or qb.empty:
        return None

    rev = _row(qi, "Total Revenue")
    ni = _row(qi, "Net Income", "Net Income Common Stockholders")
    ebitda = _row(qi, "EBITDA")
    debt = _row(qb, "Total Debt")
    cash = _row(qb, "Cash And Cash Equivalents", "Cash Cash Equivalents And Short Term Investments")
    eq = _row(qb, "Stockholders Equity", "Common Stock Equity")
    if rev is None or ni is None or eq is None:
        return None

    # Çeyrekleri kronolojik sırala (eski->yeni)
    cols = sorted(qi.columns)
    recs = []
    for i, c in enumerate(cols):
        try:
            net_q = float(ni.get(c, np.nan))
            rev_q = float(rev.get(c, np.nan))
            eq_q = float(eq.get(c, np.nan)) if eq is not None else np.nan
            ebd_q = float(ebitda.get(c, np.nan)) if ebitda is not None else np.nan
            debt_q = float(debt.get(c, np.nan)) if debt is not None else np.nan
            cash_q = float(cash.get(c, np.nan)) if cash is not None else np.nan
        except Exception:
            continue
        # TTM (son 4 çeyrek) — yeterli geçmiş varsa
        last4 = cols[max(0, i - 3):i + 1]
        ni_ttm = float(np.nansum([ni.get(x, np.nan) for x in last4])) if len(last4) >= 1 else np.nan
        ebd_ttm = float(np.nansum([ebitda.get(x, np.nan) for x in last4])) if (ebitda is not None and len(last4) >= 1) else np.nan
        # YoY (4 çeyrek önce)
        rev_yoy = earn_yoy = np.nan
        if i >= 4:
            c_prev = cols[i - 4]
            rp, np_ = float(rev.get(c_prev, np.nan)), float(ni.get(c_prev, np.nan))
            if rp and not np.isnan(rp):
                rev_yoy = (rev_q / rp - 1) * 100
            if np_ and not np.isnan(np_) and np_ != 0:
                earn_yoy = (net_q / np_ - 1) * 100
        roe = (ni_ttm / eq_q * 100) if (eq_q and not np.isnan(eq_q) and eq_q != 0) else np.nan
        nde = ((debt_q - cash_q) / ebd_ttm) if (ebd_ttm and not np.isnan(ebd_ttm) and ebd_ttm != 0
                                                and not np.isnan(debt_q)) else np.nan
        avail = pd.Timestamp(c) + pd.Timedelta(days=REPORT_LAG_DAYS)
        recs.append({"avail_date": avail, "pit_roe": roe, "pit_nde": nde,
                     "pit_rev_growth": rev_yoy, "pit_earn_growth": earn_yoy})
    if not recs:
        return None
    out = pd.DataFrame(recs).dropna(how="all", subset=["pit_roe", "pit_nde", "pit_rev_growth", "pit_earn_growth"])
    return out.sort_values("avail_date").reset_index(drop=True) if not out.empty else None


PIT_FEATURES = ["pit_roe", "pit_nde", "pit_rev_growth", "pit_earn_growth"]


def build_pit_cache(symbols, max_workers=8):
    cache = {}
    if os.path.exists(PIT_CACHE):
        try:
            cache = pickle.load(open(PIT_CACHE, "rb"))
        except Exception:
            cache = {}
    todo = [s for s in symbols if s not in cache]

    def work(s):
        return s, quarterly_ratios(s)

    done = 0
    with cf.ThreadPoolExecutor(max_workers=max_workers) as ex:
        for s, df in ex.map(work, todo):
            cache[s] = df
            done += 1
            if done % 50 == 0:
                print(f"  PIT {done}/{len(todo)}", flush=True)
    pickle.dump(cache, open(PIT_CACHE, "wb"))
    return cache


def merge_pit(daily_df, pit_df):
    """daily_df (date kolonlu) üzerine pit_df'i as-of (geçmişe doğru) birleştir."""
    if pit_df is None or pit_df.empty:
        for c in PIT_FEATURES:
            daily_df[c] = np.nan
        return daily_df
    left = daily_df.copy()
    left["_key"] = pd.to_datetime(left["date"]).dt.tz_localize(None).astype("datetime64[ns]")
    left = left.sort_values("_key")
    right = pit_df.copy()
    right["avail_date"] = pd.to_datetime(right["avail_date"]).dt.tz_localize(None).astype("datetime64[ns]")
    right = right.sort_values("avail_date")
    merged = pd.merge_asof(left, right, left_on="_key", right_on="avail_date",
                           direction="backward")
    merged = merged.drop(columns=["_key"], errors="ignore")
    for c in PIT_FEATURES:
        if c not in merged:
            merged[c] = np.nan
    return merged


_PIT_MEM = None


def latest_pit(symbol):
    """Canlı tahmin için: bugün itibarıyla en güncel YAYIMLANMIŞ çeyrek ratio'ları.
    Önce diskteki pit_cache.pkl'ye bakar (hızlı), yoksa canlı çeker."""
    global _PIT_MEM
    sym = symbol.replace(".IS", "")
    df = None
    if _PIT_MEM is None and os.path.exists(PIT_CACHE):
        try:
            _PIT_MEM = pickle.load(open(PIT_CACHE, "rb"))
        except Exception:
            _PIT_MEM = {}
    if _PIT_MEM:
        df = _PIT_MEM.get(sym, _PIT_MEM.get(symbol))
    if df is None:
        df = quarterly_ratios(symbol)
    if df is None or df.empty:
        return {c: np.nan for c in PIT_FEATURES}
    avail = df[df["avail_date"] <= pd.Timestamp.now()]
    row = (avail if not avail.empty else df).iloc[-1]
    return {c: (None if pd.isna(row[c]) else round(float(row[c]), 2)) for c in PIT_FEATURES}
