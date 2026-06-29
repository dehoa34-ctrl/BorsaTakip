"""
fundamentals.py — Temel analiz (5 ana rasyo) + KURAL-TABANLI Tuzak Filtresi / Onay Mekanizması.

Neden kural-tabanlı (ML değil)? yfinance GÜNCEL temel veriyi verir, geçmişe-dönük
(point-in-time) değil. Geçmiş ML eğitimine katmak LEAKAGE olur. Bu yüzden temel veriyi
kullanıcının tarif ettiği mantıkla bir FİLTRE/ONAY katmanı olarak kullanırız:
  - Teknik/akıllı para AL diyor AMA temel zayıf (yüksek borç + eksi büyüme) → "Spekülatif / Boğa Tuzağı"
  - Teknik iyi VE temel güçlü (yüksek ROE + düşük borç) → "GÜÇLÜ AL onayı"

Kaynak: yfinance (.IS). 5 rasyodan 4'ü mevcut; Net YP Pozisyonu/Özsermaye yfinance'de yok (N/A).
"""

import time

_CACHE = {}
_TTL = 3600  # 1 saat


def _pct(x):
    return round(x * 100, 1) if x is not None else None


def get_fundamentals(symbol):
    sym = symbol if symbol.endswith(".IS") else symbol + ".IS"
    now = time.time()
    if sym in _CACHE and now - _CACHE[sym][0] < _TTL:
        return _CACHE[sym][1]

    try:
        import data_fetcher
        info = data_fetcher.Ticker(sym).info or {}
    except Exception:
        info = {}

    debt = info.get("totalDebt")
    cash = info.get("totalCash")
    ebitda = info.get("ebitda")
    net_debt = (debt - cash) if (debt is not None and cash is not None) else None
    net_debt_ebitda = round(net_debt / ebitda, 2) if (net_debt is not None and ebitda) else None
    growth = info.get("earningsQuarterlyGrowth")
    if growth is None:
        growth = info.get("revenueGrowth")

    float_shares = info.get("floatShares")
    shares_outstanding = info.get("sharesOutstanding")
    fdo = round((float_shares / shares_outstanding) * 100, 2) if (float_shares and shares_outstanding) else None

    f = {
        "favok_growth": _pct(growth),                 # Çeyreklik kâr/ciro büyümesi (FAVÖK proxy)
        "net_debt_ebitda": net_debt_ebitda,           # Net Borç / FAVÖK
        "roe": _pct(info.get("returnOnEquity")),      # Özsermaye kârlılığı
        "pe": round(info["trailingPE"], 2) if info.get("trailingPE") else None,    # F/K
        "pb": round(info["priceToBook"], 2) if info.get("priceToBook") else None,  # PD/DD
        "fx_position_equity": None,                   # Net YP Pozisyonu/Özsermaye (yfinance vermiyor)
        "fdo": fdo,                                   # Fiili Dolaşım Oranı (FDO)
        "name": info.get("shortName") or sym,
    }
    f["quality"] = _quality(f)
    _CACHE[sym] = (now, f)
    return f


def _quality(f):
    """
    Temel kalite skoru (-100..+100) + etiket. Eksik veri nötr sayılır.
    """
    score = 0
    pts = 0
    roe, ndE, g, pe, pb = f["roe"], f["net_debt_ebitda"], f["favok_growth"], f["pe"], f["pb"]

    if roe is not None:
        pts += 1
        score += 40 if roe >= 30 else (25 if roe >= 20 else (10 if roe >= 10 else -20))
    if ndE is not None:
        pts += 1
        score += 30 if ndE < 0 else (20 if ndE < 2 else (-10 if ndE < 4 else -35))
    if g is not None:
        pts += 1
        score += 25 if g >= 25 else (12 if g > 0 else -25)
    if pb is not None:
        pts += 1
        score += 12 if pb < 1.5 else (0 if pb < 4 else -12)
    if pe is not None and pe > 0:
        pts += 1
        score += 10 if pe < 8 else (0 if pe < 25 else -10)

    if pts == 0:
        return {"score": None, "label": "Temel Veri Yok", "level": "na"}
    norm = max(-100, min(100, int(score / pts * 2.5)))
    if norm >= 45:
        label, level = "Güçlü Temel", "strong"
    elif norm >= 10:
        label, level = "Sağlam Temel", "ok"
    elif norm > -25:
        label, level = "Orta / Karışık", "mixed"
    else:
        label, level = "Zayıf Temel (Riskli)", "weak"
    return {"score": norm, "label": label, "level": level, "coverage": pts}


# ─────────────────────────────────────────────────────────────────────────────
#  Tuzak Filtresi / Onay Mekanizması — teknik + akıllı para + temeli birleştirir
# ─────────────────────────────────────────────────────────────────────────────
def fuse(technical_signal, flow_score, fundamentals):
    """
    technical_signal: get_signals 'signal' (GÜÇLÜ AL/AL/TUT/SAT/GÜÇLÜ SAT)
    flow_score: -1..+1 akıllı para skoru (flow.money_flow.score)
    Dönüş: birleşik görüş + tuzak/onay uyarısı.
    """
    q = fundamentals.get("quality", {})
    level = q.get("level", "na")
    tech_bull = technical_signal in ("GÜÇLÜ AL", "AL")
    tech_bear = technical_signal in ("GÜÇLÜ SAT", "SAT")
    flow_bull = (flow_score or 0) > 0.2
    flow_bear = (flow_score or 0) < -0.2

    verdict, tone, note = technical_signal, "neutral", ""

    # Boğa Tuzağı: teknik/akıllı para AL ama temel zayıf
    if (tech_bull or flow_bull) and level == "weak":
        verdict = "SPEKÜLATİF (Boğa Tuzağı Riski)"
        tone = "warn"
        note = "Teknik/akıllı para alım gösteriyor AMA temeller zayıf (yüksek borç / eksi büyüme). Yükseliş spekülatif olabilir — güven düşürüldü."
    # Onay: teknik iyi + temel güçlü
    elif tech_bull and level == "strong":
        verdict = "GÜÇLÜ AL (Temel Onaylı)"
        tone = "strong"
        note = "Teknik sinyal güçlü VE temeller sağlam (yüksek ROE / düşük borç). Yüksek kaliteli alım adayı."
    elif tech_bull and level == "ok":
        verdict = "AL (Temel Destekli)"
        tone = "ok"
        note = "Teknik alım, temeller makul — destekleyici."
    # Gizli değer: teknik SAT ama temel çok güçlü → dikkat
    elif tech_bear and level == "strong":
        verdict = technical_signal + " (ama temel güçlü)"
        tone = "mixed"
        note = "Teknik zayıf ama şirket temelleri güçlü; uzun vade için izleme listesi adayı olabilir."

    return {"verdict": verdict, "tone": tone, "note": note,
            "fundamental_label": q.get("label"), "fundamental_score": q.get("score")}
