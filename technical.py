"""
technical.py — investing.com tarzı çok-indikatörlü "konsensüs + olasılık" motoru.

Felsefe:
    Tek bir indikatör (örn. sadece RSI veya sadece MACD) kolayca manipüle
    edilebilir / yanıltıcı olabilir. Bunun yerine ~12 osilatör + 12 hareketli
    ortalamanın OYLARINI toplayıp bir KONSENSÜS üretiyoruz. Tek bir gösterge
    bozulsa bile sonuç çok az etkilenir.

    Çıktı "AL/SAT" emri değil; kaç göstergenin hemfikir olduğunu gösteren bir
    OLASILIK ve "Güçlü Sat … Güçlü Al" arası bir kadran değeridir.
"""

import numpy as np
import pandas as pd


# ─────────────────────────────────────────────────────────────────────────────
#  Eylem etiketleri
# ─────────────────────────────────────────────────────────────────────────────
BUY = "Al"
SELL = "Sat"
NEUTRAL = "Nötr"
OVERBOUGHT = "Aşırı Alış"      # tally'ye girmez (kontra durum)
OVERSOLD = "Aşırı Satış"       # tally'ye girmez (kontra durum)
HIGH_VOL = "Yüksek Hareketli"  # tally'ye girmez (yön değil, volatilite)
LOW_VOL = "Düşük Hareketli"    # tally'ye girmez

# Yalnızca bunlar Al/Nötr/Sat sayımına dâhildir:
_COUNTED = {BUY, SELL, NEUTRAL}


# ─────────────────────────────────────────────────────────────────────────────
#  Düşük seviyeli indikatör hesapları
# ─────────────────────────────────────────────────────────────────────────────
def _rsi(close, period=14):
    delta = close.diff()
    gain = delta.where(delta > 0, 0.0).rolling(period).mean()
    loss = (-delta.where(delta < 0, 0.0)).rolling(period).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def _stoch(df, k=9, d=6):
    low_min = df["Low"].rolling(k).min()
    high_max = df["High"].rolling(k).max()
    fast_k = 100 * (df["Close"] - low_min) / (high_max - low_min).replace(0, np.nan)
    main_k = fast_k.rolling(3).mean()       # %K (yumuşatılmış)
    sig_d = main_k.rolling(d).mean()        # %D
    return main_k, sig_d


def _stoch_rsi(close, period=14):
    rsi = _rsi(close, period)
    low = rsi.rolling(period).min()
    high = rsi.rolling(period).max()
    return 100 * (rsi - low) / (high - low).replace(0, np.nan)


def _macd(close, fast=12, slow=26, signal=9):
    ema_fast = close.ewm(span=fast, adjust=False).mean()
    ema_slow = close.ewm(span=slow, adjust=False).mean()
    macd = ema_fast - ema_slow
    sig = macd.ewm(span=signal, adjust=False).mean()
    return macd, sig


def _atr_components(df, period=14):
    high, low, close = df["High"], df["Low"], df["Close"]
    tr = pd.concat([
        high - low,
        (high - close.shift()).abs(),
        (low - close.shift()).abs(),
    ], axis=1).max(axis=1)
    return tr.rolling(period).mean()


def _adx(df, period=14):
    high, low, close = df["High"], df["Low"], df["Close"]
    up = high.diff()
    down = -low.diff()
    plus_dm = np.where((up > down) & (up > 0), up, 0.0)
    minus_dm = np.where((down > up) & (down > 0), down, 0.0)
    tr = pd.concat([
        high - low,
        (high - close.shift()).abs(),
        (low - close.shift()).abs(),
    ], axis=1).max(axis=1)
    atr = tr.rolling(period).mean()
    plus_di = 100 * pd.Series(plus_dm, index=df.index).rolling(period).mean() / atr
    minus_di = 100 * pd.Series(minus_dm, index=df.index).rolling(period).mean() / atr
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    adx = dx.rolling(period).mean()
    return adx, plus_di, minus_di


def _williams_r(df, period=14):
    high_max = df["High"].rolling(period).max()
    low_min = df["Low"].rolling(period).min()
    return -100 * (high_max - df["Close"]) / (high_max - low_min).replace(0, np.nan)


def _cci(df, period=14):
    tp = (df["High"] + df["Low"] + df["Close"]) / 3
    sma = tp.rolling(period).mean()
    mad = tp.rolling(period).apply(lambda x: np.abs(x - x.mean()).mean(), raw=True)
    return (tp - sma) / (0.015 * mad.replace(0, np.nan))


def _ultimate(df, s=7, m=14, l=28):
    close, low, high = df["Close"], df["Low"], df["High"]
    prior_close = close.shift()
    bp = close - np.minimum(low, prior_close)
    tr = np.maximum(high, prior_close) - np.minimum(low, prior_close)
    avg_s = bp.rolling(s).sum() / tr.rolling(s).sum()
    avg_m = bp.rolling(m).sum() / tr.rolling(m).sum()
    avg_l = bp.rolling(l).sum() / tr.rolling(l).sum()
    return 100 * (4 * avg_s + 2 * avg_m + avg_l) / 7


def _roc(close, period=12):
    return 100 * (close - close.shift(period)) / close.shift(period)


def _bull_bear_power(df, period=13):
    ema = df["Close"].ewm(span=period, adjust=False).mean()
    bull = df["High"] - ema
    bear = df["Low"] - ema
    return bull + bear  # investing tek değer (toplam güç) gösterir


# ─────────────────────────────────────────────────────────────────────────────
#  Yorumlama kuralları → her indikatör için (değer, eylem)
# ─────────────────────────────────────────────────────────────────────────────
def _last(series):
    """Son geçerli (NaN olmayan) değer."""
    s = series.dropna()
    return float(s.iloc[-1]) if len(s) else float("nan")


def _osc_signals(df):
    close = df["Close"]
    items = []

    # RSI(14)
    rsi = _last(_rsi(close, 14))
    if rsi >= 70:
        act = OVERBOUGHT
    elif rsi <= 30:
        act = OVERSOLD
    else:
        act = BUY if rsi > 50 else (SELL if rsi < 50 else NEUTRAL)
    items.append({"name": "RSI(14)", "value": round(rsi, 3), "action": act})

    # STOCH(9,6)
    k, d = _stoch(df, 9, 6)
    kv, dv = _last(k), _last(d)
    if kv >= 80:
        act = OVERBOUGHT
    elif kv <= 20:
        act = OVERSOLD
    else:
        act = BUY if kv > dv else (SELL if kv < dv else NEUTRAL)
    items.append({"name": "STOCH(9,6)", "value": round(kv, 3), "action": act})

    # STOCHRSI(14)
    sr = _last(_stoch_rsi(close, 14))
    if sr >= 80:
        act = OVERBOUGHT
    elif sr <= 20:
        act = OVERSOLD
    else:
        act = BUY if sr > 50 else SELL
    items.append({"name": "STOCHRSI(14)", "value": round(sr, 3), "action": act})

    # MACD(12,26)
    macd, sig = _macd(close)
    mv, sv = _last(macd), _last(sig)
    act = BUY if mv > sv else (SELL if mv < sv else NEUTRAL)
    items.append({"name": "MACD(12,26)", "value": round(mv, 3), "action": act})

    # ADX(14)
    adx, pdi, mdi = _adx(df)
    av, pv, mv2 = _last(adx), _last(pdi), _last(mdi)
    if av < 20:
        act = NEUTRAL
    else:
        act = BUY if pv > mv2 else SELL
    items.append({"name": "ADX(14)", "value": round(av, 3), "action": act})

    # Williams %R
    wr = _last(_williams_r(df, 14))
    if wr >= -20:
        act = OVERBOUGHT
    elif wr <= -80:
        act = OVERSOLD
    else:
        act = BUY if wr > -50 else SELL
    items.append({"name": "Williams %R", "value": round(wr, 3), "action": act})

    # CCI(14)
    cci = _last(_cci(df, 14))
    act = BUY if cci > 100 else (SELL if cci < -100 else (BUY if cci > 0 else SELL))
    items.append({"name": "CCI(14)", "value": round(cci, 3), "action": act})

    # ATR(14) — yön değil, volatilite
    atr_series = _atr_components(df, 14).dropna()
    atr = float(atr_series.iloc[-1]) if len(atr_series) else float("nan")
    rising = len(atr_series) > 1 and atr_series.iloc[-1] > atr_series.iloc[-2]
    items.append({"name": "ATR(14)", "value": round(atr, 4),
                  "action": HIGH_VOL if rising else LOW_VOL})

    # Highs/Lows(14)
    hl_period = 14
    hh = close.rolling(hl_period).max()
    ll = close.rolling(hl_period).min()
    hl = _last((close - hh) + (close - ll))  # +: tepeye yakın, -: dibe yakın
    act = BUY if hl > 0 else (SELL if hl < 0 else NEUTRAL)
    items.append({"name": "Highs/Lows(14)", "value": round(hl, 4), "action": act})

    # Ultimate Oscillator
    uo = _last(_ultimate(df))
    if uo >= 70:
        act = OVERBOUGHT
    elif uo <= 30:
        act = OVERSOLD
    else:
        act = BUY if uo > 50 else SELL
    items.append({"name": "Ultimate Oscillator", "value": round(uo, 3), "action": act})

    # ROC
    roc = _last(_roc(close, 12))
    act = BUY if roc > 0 else (SELL if roc < 0 else NEUTRAL)
    items.append({"name": "ROC", "value": round(roc, 3), "action": act})

    # Bull/Bear Power(13)
    bbp = _last(_bull_bear_power(df, 13))
    act = BUY if bbp > 0 else (SELL if bbp < 0 else NEUTRAL)
    items.append({"name": "Bull/Bear Power(13)", "value": round(bbp, 3), "action": act})

    return items


def _ma_signals(df):
    close = df["Close"]
    price = _last(close)
    periods = [5, 10, 20, 50, 100, 200]
    items = []
    for p in periods:
        if len(close.dropna()) < 2:
            continue
        sma = _last(close.rolling(min(p, len(close))).mean())
        ema = _last(close.ewm(span=p, adjust=False).mean())
        sma_act = BUY if price > sma else (SELL if price < sma else NEUTRAL)
        ema_act = BUY if price > ema else (SELL if price < ema else NEUTRAL)
        items.append({
            "name": f"MA{p}",
            "simple": {"value": round(sma, 4), "action": sma_act},
            "exp": {"value": round(ema, 4), "action": ema_act},
        })
    return items


# ─────────────────────────────────────────────────────────────────────────────
#  Konsensüs / olasılık
# ─────────────────────────────────────────────────────────────────────────────
def _tally(actions):
    buy = sum(1 for a in actions if a == BUY)
    sell = sum(1 for a in actions if a == SELL)
    neutral = sum(1 for a in actions if a == NEUTRAL)
    return buy, sell, neutral


def _classify(buy, sell, neutral):
    """buy/sell/neutral sayımından kadran etiketi + (-1..1) skoru üret."""
    total = buy + sell + neutral
    if total == 0:
        return NEUTRAL, 0.0
    score = (buy - sell) / total      # -1 (tamamen sat) .. +1 (tamamen al)
    if score <= -0.5:
        label = "Güçlü Sat"
    elif score < -0.1:
        label = SELL
    elif score < 0.1:
        label = NEUTRAL
    elif score < 0.5:
        label = BUY
    else:
        label = "Güçlü Al"
    return label, round(score, 3)


def _group_summary(actions):
    buy, sell, neutral = _tally(actions)
    label, score = _classify(buy, sell, neutral)
    return {
        "action": label,
        "score": score,
        "buy": buy,
        "sell": sell,
        "neutral": neutral,
    }


# ─────────────────────────────────────────────────────────────────────────────
#  Pivot noktaları
# ─────────────────────────────────────────────────────────────────────────────
def _pivot_points(df):
    """Son tamamlanmış mumun H/L/C/O değerlerinden pivotlar."""
    row = df.iloc[-1]
    H, L, C, O = float(row["High"]), float(row["Low"]), float(row["Close"]), float(row["Open"])
    rng = H - L
    out = []

    def r(x):
        return round(x, 4) if x is not None else None

    # Klasik
    P = (H + L + C) / 3
    out.append({"name": "Klasik", "s3": r(L - 2 * (H - P)), "s2": r(P - rng), "s1": r(2 * P - H),
                "pivot": r(P), "r1": r(2 * P - L), "r2": r(P + rng), "r3": r(H + 2 * (P - L))})

    # Fibonacci
    Pf = (H + L + C) / 3
    out.append({"name": "Fibonacci", "s3": r(Pf - rng), "s2": r(Pf - 0.618 * rng), "s1": r(Pf - 0.382 * rng),
                "pivot": r(Pf), "r1": r(Pf + 0.382 * rng), "r2": r(Pf + 0.618 * rng), "r3": r(Pf + rng)})

    # Camarilla
    Pc = (H + L + C) / 3
    out.append({"name": "Camarilla", "s3": r(C - rng * 1.1 / 4), "s2": r(C - rng * 1.1 / 6), "s1": r(C - rng * 1.1 / 12),
                "pivot": r(Pc), "r1": r(C + rng * 1.1 / 12), "r2": r(C + rng * 1.1 / 6), "r3": r(C + rng * 1.1 / 4)})

    # Woodie
    Pw = (H + L + 2 * C) / 4
    out.append({"name": "Woodie", "s3": r(L - 2 * (H - Pw)), "s2": r(Pw - rng), "s1": r(2 * Pw - H),
                "pivot": r(Pw), "r1": r(2 * Pw - L), "r2": r(Pw + rng), "r3": r(H + 2 * (Pw - L))})

    # DeMark — sadece S1, Pivot, R1
    if C < O:
        X = H + 2 * L + C
    elif C > O:
        X = 2 * H + L + C
    else:
        X = H + L + 2 * C
    Pd = X / 4
    out.append({"name": "Demark", "s3": None, "s2": None, "s1": r(X / 2 - H),
                "pivot": r(Pd), "r1": r(X / 2 - L), "r2": None, "r3": None})

    return out


# ─────────────────────────────────────────────────────────────────────────────
#  Ana giriş noktası
# ─────────────────────────────────────────────────────────────────────────────
def get_technical_analysis(df, symbol="", timeframe="1d"):
    """
    investing.com tarzı tam teknik özet döndürür:
      - oscillators  (12 gösterge + grup özeti)
      - moving_averages (6 periyot × Basit/Üssel + grup özeti)
      - summary (osilatör + MA birleşik konsensüs + yükseliş olasılığı %)
      - pivots
    """
    if df is None or len(df) < 30:
        return {
            "ok": False,
            "message": "Konsensüs için en az 30 mum gerekli.",
            "symbol": symbol,
        }

    df = df.copy()
    price = round(float(df["Close"].iloc[-1]), 4)

    osc_items = _osc_signals(df)
    ma_items = _ma_signals(df)

    osc_actions = [i["action"] for i in osc_items]
    ma_actions = []
    for i in ma_items:
        ma_actions.append(i["simple"]["action"])
        ma_actions.append(i["exp"]["action"])

    osc_summary = _group_summary(osc_actions)
    ma_summary = _group_summary(ma_actions)

    # Birleşik özet
    all_actions = osc_actions + ma_actions
    buy, sell, neutral = _tally(all_actions)
    label, score = _classify(buy, sell, neutral)

    # Yükseliş olasılığı: hemfikir göstergeler arasından Al oranı.
    decisive = buy + sell
    bull_prob = round(100 * buy / decisive, 1) if decisive else 50.0

    summary = {
        "action": label,
        "score": score,
        "buy": buy,
        "sell": sell,
        "neutral": neutral,
        "bull_prob": bull_prob,          # % yükseliş olasılığı
        "bear_prob": round(100 - bull_prob, 1),
        "total_indicators": len(all_actions),
    }

    return {
        "ok": True,
        "symbol": symbol,
        "timeframe": timeframe,
        "price": price,
        "summary": summary,
        "oscillators": {**osc_summary, "items": osc_items},
        "moving_averages": {**ma_summary, "items": ma_items},
        "pivots": _pivot_points(df),
    }
