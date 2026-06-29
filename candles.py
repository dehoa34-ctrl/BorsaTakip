"""
candles.py — Mum (candlestick) formasyonları tarama modülü.

investing.com'un "candlestick" sekmesi ve candlesticker.com mantığıyla, OHLC
verisinden boğa / ayı / kararsız formasyonlarını tespit eder. Tek bir indikatör
gibi değil; fiyatın kendi davranışından (price action) çıkan desenlerdir.

Çıktı:
    - latest  : en son mumda/dizide oluşan formasyonlar (en aksiyon alınabilir)
    - history : son N mumda görülen formasyonlar (yeniden eskiye)
    - summary : boğa/ayı/nötr sayımı + genel eğilim
"""

import numpy as np
import pandas as pd

import flow as _flow


# ─────────────────────────────────────────────────────────────────────────────
#  DOĞRULAMA (Validation) — formasyonu "kandırılması zor" hale getiren filtreler
#  1) Hacim: formasyon günü hacmi 10-gün ortalamasının >=1.5 katı olmalı (Z-score)
#  2) Trend/Konum: boğa dönüşü ancak ÖNCE düşüş varsa geçerli (zirvede yutan = dağıtım)
#  3) POC: çekiç türlerinde fitil POC altından likidite alıp döndüyse GERÇEK ayı tuzağı
# ─────────────────────────────────────────────────────────────────────────────
def _get_karanlik_oda_ratio_live(symbol):
    """BIST hisseleri için bugünkü karanlık oda hacim oranını sorgular."""
    if not symbol:
        return None
    try:
        import data_fetcher
        sym = symbol if symbol.endswith(".IS") else symbol + ".IS"
        t = data_fetcher.Ticker(sym)
        df_5m = t.history(period="1d", interval="5m")
        if df_5m is not None and not df_5m.empty:
            # 17:50 - 18:05 arası barlar (BIST kapanış seansı)
            closing_vol = df_5m[
                ((df_5m.index.hour == 17) & (df_5m.index.minute >= 50)) | (df_5m.index.hour == 18)
            ]["Volume"].sum()
            total_vol = df_5m["Volume"].sum()
            return float((closing_vol / total_vol) * 100) if total_vol > 0 else 0.0
    except Exception:
        pass
    return None


def _validate(df, i, ptype, name=None, karanlik_oda_ratio=None):
    vol = df["Volume"]
    close = df["Close"]
    low = df["Low"]
    high = df["High"]

    # 1) Hacim doğrulama (Z-Score > 1.5 ve ortalama ratio >= 1.5)
    win = vol.iloc[max(0, i - 10):i]
    v_mean = float(win.mean()) if len(win) else 0.0
    v_std = float(win.std()) if len(win) > 1 else 0.0
    v_today = float(vol.iloc[i])
    vol_ratio = (v_today / v_mean) if v_mean else 0.0
    vol_z = ((v_today - v_mean) / v_std) if v_std else 0.0
    volume_ok = vol_ratio >= 1.5 and vol_z > 1.5

    # 2) Trend / konum doğrulama (son 5 ve 10 mum yönü)
    trend_ok = True
    trend_label = "Uyumlu"
    if ptype == BULL:
        # Boğa dönüşü öncesinde düşüş trendi olmalı (en az birinde negatif getiri)
        j5 = max(0, i - 5)
        base5 = float(close.iloc[j5])
        prior_ret5 = (float(close.iloc[i-1]) / base5 - 1) * 100 if base5 and i > j5 else 0.0
        
        j10 = max(0, i - 10)
        base10 = float(close.iloc[j10])
        prior_ret10 = (float(close.iloc[i-1]) / base10 - 1) * 100 if base10 and i > j10 else 0.0
        
        trend_ok = (prior_ret5 < -1.5) or (prior_ret10 < -1.5)
        if not trend_ok:
            if prior_ret5 > 1.5 or prior_ret10 > 1.5:
                trend_label = "Dağıtım / Mal Boşaltma Riski (Zirvede Formasyon)"
            else:
                trend_label = "Yatay Piyasa (Sahte Sinyal Riski)"
    elif ptype == BEAR:
        # Ayı dönüşü öncesinde yükseliş trendi olmalı
        j5 = max(0, i - 5)
        base5 = float(close.iloc[j5])
        prior_ret5 = (float(close.iloc[i-1]) / base5 - 1) * 100 if base5 and i > j5 else 0.0
        
        j10 = max(0, i - 10)
        base10 = float(close.iloc[j10])
        prior_ret10 = (float(close.iloc[i-1]) / base10 - 1) * 100 if base10 and i > j10 else 0.0
        
        trend_ok = (prior_ret5 > 1.5) or (prior_ret10 > 1.5)
        if not trend_ok:
            trend_label = "Dip Seviyede Ayı Formasyonu (Sahte)"

    # 3) POC (Hacim Yoğunluğu) — çekiç ve ters çekiç türleri için
    poc_signal = None
    is_hammer = name and any(x in name.lower() for x in ["çekiç", "hammer", "inverted"])
    if is_hammer and i >= 25:
        try:
            poc, _, _ = _flow.volume_profile_poc(df.iloc[:i + 1])
        except Exception:
            poc = None
        if poc:
            lo = float(low.iloc[i])
            cl = float(close.iloc[i])
            if lo < poc and cl > poc:
                poc_signal = "Gerçek Ayı Tuzağı (POC altından likidite alıp döndü)"
            elif cl < poc * 0.98:
                poc_signal = "POC altında — sahte tepki yükselişi (düşüş trendi devam edebilir)"

    # Skor + karar
    score = 0
    # Hacimsiz mumlar çöp hükmündedir (Volume validation cezası/ödülü)
    score += 40 if volume_ok else -30
    score += 30 if trend_ok else -35
    
    if poc_signal:
        if "Gerçek" in poc_signal:
            score += 25
        else:
            score -= 25
            
    # Karanlık oda bonusu (Kesin Ayı Tuzağı - Toplama)
    karanlik_oda_signal = None
    if karanlik_oda_ratio is not None and karanlik_oda_ratio > 15.0:
        if ptype == BULL:
            score += 25
            karanlik_oda_signal = f"Kesin Ayı Tuzağı (Karanlık Odada %{karanlik_oda_ratio:.1f} Toplama)"

    if score >= 60:
        verdict = "Doğrulandı (Güçlü)"
    elif score >= 20:
        verdict = "Kısmi Doğrulama"
    else:
        verdict = "Zayıf / Şüpheli (Sahte Sinyal)"

    # prior_ret olarak son 5 günlük getiri bilgisini dönüyoruz
    j_ret = max(0, i - 5)
    p_ret = (float(close.iloc[i-1]) / float(close.iloc[j_ret]) - 1) * 100 if i > j_ret else 0.0

    return {
        "verdict": verdict, "score": score,
        "volume_ok": volume_ok, "vol_ratio": round(vol_ratio, 2), "vol_z": round(vol_z, 2),
        "trend_ok": trend_ok, "trend_label": trend_label, "prior_ret5": round(p_ret, 2),
        "poc_signal": poc_signal, "karanlik_oda_ratio": round(karanlik_oda_ratio, 2) if karanlik_oda_ratio else None,
        "karanlik_oda_signal": karanlik_oda_signal
    }


# ─────────────────────────────────────────────────────────────────────────────
#  Formasyon kütüphanesi — açıklama + güvenilirlik (candlesticker.com mantığı)
# ─────────────────────────────────────────────────────────────────────────────
BULL = "Boğa"
BEAR = "Ayı"
NEUT = "Kararsız"

PATTERN_INFO = {
    # tek mum
    "Çekiç (Hammer)": (BULL, "Yüksek", "Düşüş trendinin dibinde uzun alt fitilli küçük gövde — alıcıların geri döndüğüne işaret, dönüş sinyali."),
    "Ters Çekiç (Inverted Hammer)": (BULL, "Orta", "Düşüş sonrası uzun üst fitil — boğa dönüşü adayı, teyit ister."),
    "Asılı Adam (Hanging Man)": (BEAR, "Orta", "Yükseliş tepesinde uzun alt fitilli küçük gövde — zayıflama ve olası tepe."),
    "Kayan Yıldız (Shooting Star)": (BEAR, "Yüksek", "Yükseliş tepesinde uzun üst fitil — satış baskısı, dönüş sinyali."),
    "Doji": (NEUT, "Orta", "Açılış≈kapanış — kararsızlık; trend sonunda dönüş habercisi olabilir."),
    "Yusufçuk Doji (Dragonfly)": (BULL, "Orta", "Uzun alt fitilli doji — dipte boğa dönüşü adayı."),
    "Mezar Taşı Doji (Gravestone)": (BEAR, "Orta", "Uzun üst fitilli doji — tepede ayı dönüşü adayı."),
    "Topaç (Spinning Top)": (NEUT, "Düşük", "Küçük gövde, iki yanda fitil — kararsızlık."),
    "Marubozu (Boğa)": (BULL, "Yüksek", "Fitilsiz uzun yeşil gövde — güçlü alıcı kontrolü."),
    "Marubozu (Ayı)": (BEAR, "Yüksek", "Fitilsiz uzun kırmızı gövde — güçlü satıcı kontrolü."),
    # iki mum
    "Boğa Yutan (Bullish Engulfing)": (BULL, "Yüksek", "Küçük kırmızıyı tamamen yutan büyük yeşil — güçlü boğa dönüşü."),
    "Ayı Yutan (Bearish Engulfing)": (BEAR, "Yüksek", "Küçük yeşili tamamen yutan büyük kırmızı — güçlü ayı dönüşü."),
    "Boğa Harami": (BULL, "Orta", "Büyük kırmızının içinde küçük yeşil — düşüş ivmesi zayıflıyor."),
    "Ayı Harami": (BEAR, "Orta", "Büyük yeşilin içinde küçük kırmızı — yükseliş ivmesi zayıflıyor."),
    "Delici Hat (Piercing Line)": (BULL, "Orta", "Kırmızının ortasının üstüne kapanan yeşil — boğa dönüşü."),
    "Kara Bulut Örtüsü (Dark Cloud)": (BEAR, "Orta", "Yeşilin ortasının altına kapanan kırmızı — ayı dönüşü."),
    "Cımbız Dip (Tweezer Bottom)": (BULL, "Orta", "Art arda iki eşit dip — destek ve dönüş."),
    "Cımbız Tepe (Tweezer Top)": (BEAR, "Orta", "Art arda iki eşit tepe — direnç ve dönüş."),
    # üç mum
    "Sabah Yıldızı (Morning Star)": (BULL, "Yüksek", "Düşüş + küçük gövde + güçlü yeşil — klasik boğa dönüşü."),
    "Akşam Yıldızı (Evening Star)": (BEAR, "Yüksek", "Yükseliş + küçük gövde + güçlü kırmızı — klasik ayı dönüşü."),
    "Üç Beyaz Asker (Three White Soldiers)": (BULL, "Yüksek", "Art arda üç yükselen yeşil — güçlü boğa trendi."),
    "Üç Siyah Karga (Three Black Crows)": (BEAR, "Yüksek", "Art arda üç alçalan kırmızı — güçlü ayı trendi."),
}


# ─────────────────────────────────────────────────────────────────────────────
#  Mum geometrisi yardımcıları
# ─────────────────────────────────────────────────────────────────────────────
def _geom(row):
    o, h, l, c = float(row["Open"]), float(row["High"]), float(row["Low"]), float(row["Close"])
    rng = h - l if h - l > 0 else 1e-9
    body = abs(c - o)
    upper = h - max(o, c)
    lower = min(o, c) - l
    return {
        "o": o, "h": h, "l": l, "c": c, "rng": rng, "body": body,
        "upper": upper, "lower": lower,
        "bull": c > o, "bear": c < o,
        "body_pct": body / rng,
        "mid": (o + c) / 2,
    }


def _trend(closes, n=5):
    """Son n mumun eğilimi: -1 düşüş, +1 yükseliş, 0 yatay."""
    if len(closes) < n + 1:
        return 0
    seg = closes[-(n + 1):]
    if seg[-1] > seg[0] * 1.005:
        return 1
    if seg[-1] < seg[0] * 0.995:
        return -1
    return 0


# ─────────────────────────────────────────────────────────────────────────────
#  Tek mumda formasyon tespiti
# ─────────────────────────────────────────────────────────────────────────────
def _detect_at(df, i):
    """df'nin i. indeksindeki mumda biten formasyonları döndürür (isim listesi)."""
    found = []
    closes = df["Close"].values[: i + 1]
    trend = _trend(closes)

    g = _geom(df.iloc[i])
    p1 = _geom(df.iloc[i - 1]) if i >= 1 else None
    p2 = _geom(df.iloc[i - 2]) if i >= 2 else None

    small = g["body_pct"] <= 0.3
    doji = g["body_pct"] <= 0.1
    long_body = g["body_pct"] >= 0.6

    # ── Tek mum ──
    # Doji aileleri
    if doji:
        if g["lower"] >= 2 * g["body"] and g["upper"] <= g["body"]:
            found.append("Yusufçuk Doji (Dragonfly)")
        elif g["upper"] >= 2 * g["body"] and g["lower"] <= g["body"]:
            found.append("Mezar Taşı Doji (Gravestone)")
        else:
            found.append("Doji")
    elif small and g["upper"] > g["body"] and g["lower"] > g["body"]:
        found.append("Topaç (Spinning Top)")

    # Çekiç / Asılı Adam (uzun alt fitil, küçük gövde, kısa üst fitil)
    if g["lower"] >= 2 * g["body"] and g["upper"] <= g["body"] * 0.6 and g["body_pct"] < 0.4:
        if trend < 0:
            found.append("Çekiç (Hammer)")
        elif trend > 0:
            found.append("Asılı Adam (Hanging Man)")

    # Ters Çekiç / Kayan Yıldız (uzun üst fitil)
    if g["upper"] >= 2 * g["body"] and g["lower"] <= g["body"] * 0.6 and g["body_pct"] < 0.4:
        if trend > 0:
            found.append("Kayan Yıldız (Shooting Star)")
        elif trend < 0:
            found.append("Ters Çekiç (Inverted Hammer)")

    # Marubozu (fitilsiz uzun gövde)
    if long_body and g["upper"] <= g["rng"] * 0.05 and g["lower"] <= g["rng"] * 0.05:
        found.append("Marubozu (Boğa)" if g["bull"] else "Marubozu (Ayı)")

    # ── İki mum ──
    if p1:
        # Yutan
        if p1["bear"] and g["bull"] and g["c"] >= p1["o"] and g["o"] <= p1["c"] and g["body"] > p1["body"]:
            found.append("Boğa Yutan (Bullish Engulfing)")
        if p1["bull"] and g["bear"] and g["o"] >= p1["c"] and g["c"] <= p1["o"] and g["body"] > p1["body"]:
            found.append("Ayı Yutan (Bearish Engulfing)")
        # Harami (önceki büyük gövde, içinde küçük gövde)
        if p1["body_pct"] >= 0.5 and g["body"] < p1["body"] * 0.6:
            if p1["bear"] and g["bull"] and g["o"] <= p1["o"] and g["c"] <= p1["o"] and g["o"] >= p1["c"]:
                found.append("Boğa Harami")
            if p1["bull"] and g["bear"] and g["o"] >= p1["o"] and g["c"] >= p1["c"] and g["o"] <= p1["c"]:
                found.append("Ayı Harami")
        # Delici Hat / Kara Bulut
        if p1["bear"] and g["bull"] and g["o"] < p1["l"] and g["c"] > p1["mid"] and g["c"] < p1["o"]:
            found.append("Delici Hat (Piercing Line)")
        if p1["bull"] and g["bear"] and g["o"] > p1["h"] and g["c"] < p1["mid"] and g["c"] > p1["o"]:
            found.append("Kara Bulut Örtüsü (Dark Cloud)")
        # Cımbız (eşit dip / tepe)
        tol = g["rng"] * 0.1
        if abs(g["l"] - p1["l"]) <= tol and trend < 0 and p1["bear"] and g["bull"]:
            found.append("Cımbız Dip (Tweezer Bottom)")
        if abs(g["h"] - p1["h"]) <= tol and trend > 0 and p1["bull"] and g["bear"]:
            found.append("Cımbız Tepe (Tweezer Top)")

    # ── Üç mum ──
    if p1 and p2:
        # Sabah / Akşam Yıldızı
        if p2["bear"] and p2["body_pct"] >= 0.5 and p1["body_pct"] <= 0.3 and g["bull"] and g["c"] > p2["mid"]:
            found.append("Sabah Yıldızı (Morning Star)")
        if p2["bull"] and p2["body_pct"] >= 0.5 and p1["body_pct"] <= 0.3 and g["bear"] and g["c"] < p2["mid"]:
            found.append("Akşam Yıldızı (Evening Star)")
        # Üç Beyaz Asker / Üç Siyah Karga
        if all(x["bull"] and x["body_pct"] >= 0.4 for x in (p2, p1, g)) and g["c"] > p1["c"] > p2["c"]:
            found.append("Üç Beyaz Asker (Three White Soldiers)")
        if all(x["bear"] and x["body_pct"] >= 0.4 for x in (p2, p1, g)) and g["c"] < p1["c"] < p2["c"]:
            found.append("Üç Siyah Karga (Three Black Crows)")

    # Tekrarları kaldır, sırayı koru
    seen, uniq = set(), []
    for f in found:
        if f not in seen:
            seen.add(f)
            uniq.append(f)
    return uniq


def _enrich(names, date_str, df=None, i=None, karanlik_oda_ratio=None):
    out = []
    for n in names:
        info = PATTERN_INFO.get(n, (NEUT, "Orta", ""))
        item = {
            "name": n,
            "type": info[0],      # Boğa / Ayı / Kararsız
            "reliability": info[1],
            "desc": info[2],
            "date": date_str,
        }
        # DOĞRULAMA: hacim + trend/konum + POC (kandırılması zor)
        if df is not None and i is not None:
            item["validation"] = _validate(df, i, info[0], n, karanlik_oda_ratio)
        out.append(item)
    return out


def _date_str(idx, interval):
    if interval in ("1m", "2m", "5m", "15m", "30m", "60m", "90m", "1h"):
        return idx.strftime("%d.%m %H:%M")
    return idx.strftime("%Y-%m-%d")


# ─────────────────────────────────────────────────────────────────────────────
#  Ana giriş
# ─────────────────────────────────────────────────────────────────────────────
def scan_candles(df, symbol="", timeframe="1d", lookback=40):
    if df is None or len(df) < 5:
        return {"ok": False, "message": "Mum taraması için en az 5 mum gerekli.", "symbol": symbol}

    df = df.copy()
    n = len(df)
    last_i = n - 1

    # Son mumda karanlık oda hacim oranını hesapla (sadece BIST günlük analizde)
    k_ratio = None
    if timeframe == "1d" and symbol:
        k_ratio = _get_karanlik_oda_ratio_live(symbol)

    latest = _enrich(_detect_at(df, last_i), _date_str(df.index[last_i], timeframe), df, last_i, k_ratio)

    history = []
    start = max(2, n - lookback)
    for i in range(n - 1, start - 1, -1):
        names = _detect_at(df, i)
        if names:
            # Geçmiş mumlarda karanlık oda bilgisini doğrudan hesaplayamayız (canlı olmadıkları için), bu yüzden None geçiyoruz.
            history.extend(_enrich(names, _date_str(df.index[i], timeframe), df, i, None))

    bullish = sum(1 for h in history if h["type"] == BULL)
    bearish = sum(1 for h in history if h["type"] == BEAR)
    neutral = sum(1 for h in history if h["type"] == NEUT)
    # Doğrulanmış (hacim+trend+POC) formasyon sayısı — asıl güvenilir olanlar
    validated = sum(1 for h in history if h.get("validation", {}).get("score", 0) >= 50)
    if bullish > bearish:
        bias = BULL
    elif bearish > bullish:
        bias = BEAR
    else:
        bias = NEUT

    return {
        "ok": True,
        "symbol": symbol,
        "timeframe": timeframe,
        "price": round(float(df["Close"].iloc[-1]), 4),
        "latest": latest,
        "history": history,
        "summary": {"bullish": bullish, "bearish": bearish, "neutral": neutral,
                    "bias": bias, "validated": validated},
    }
