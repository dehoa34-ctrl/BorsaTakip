"""
scanner.py — BIST evreni üzerinde kriterli formasyon/teknik tarama.

İdealgo'daki "formasyon tarama" mantığı: bir kritere uyan hisseleri bul, listele,
ve İdealgo'ya geri yüklenebilir TXT (IMKBH'SEMBOL) olarak dışa aktar.

Kriter türleri (ctype):
    teknik    → konsensüs eylemi (Güçlü Al / Al / Nötr / Sat / Güçlü Sat)
    olasilik  → yükseliş olasılığı >= eşik (cval = '70' gibi)
    rsi       → 'asiri_satim' (<=30) / 'asiri_alim' (>=70)
    mum       → 'boga' / 'ayi' (son mumda dönüş) veya formasyon adı parçası (örn 'Yutan')
"""

import concurrent.futures as cf

import yfinance as yf

from technical import get_technical_analysis
from candles import scan_candles
import sources


def _fetch(sym):
    try:
        h = yf.Ticker(sym + ".IS").history(period="6mo", interval="1d")
        if h is None or len(h) < 30:
            return None
        return h
    except Exception:
        return None


def _rsi_of(tech):
    for it in tech["oscillators"]["items"]:
        if it["name"] == "RSI(14)":
            return it["value"]
    return None


def _match(sym, h, ctype, cval):
    try:
        if ctype in ("teknik", "olasilik", "rsi"):
            t = get_technical_analysis(h, sym, "1d")
            if not t.get("ok"):
                return None
            s = t["summary"]
            if ctype == "teknik":
                if s["action"] == cval:
                    return {"symbol": sym, "label": s["action"],
                            "detail": f"Olasılık %{s['bull_prob']} · Al {s['buy']}/Sat {s['sell']}",
                            "price": t["price"]}
            elif ctype == "olasilik":
                thr = float(cval)
                if s["bull_prob"] >= thr:
                    return {"symbol": sym, "label": f"%{s['bull_prob']} yükseliş",
                            "detail": f"{s['action']} · Al {s['buy']}/Sat {s['sell']}",
                            "price": t["price"]}
            elif ctype == "rsi":
                rsi = _rsi_of(t)
                if rsi is None:
                    return None
                if cval == "asiri_satim" and rsi <= 30:
                    return {"symbol": sym, "label": f"RSI {rsi} (aşırı satım)",
                            "detail": s["action"], "price": t["price"]}
                if cval == "asiri_alim" and rsi >= 70:
                    return {"symbol": sym, "label": f"RSI {rsi} (aşırı alım)",
                            "detail": s["action"], "price": t["price"]}

        elif ctype == "mum":
            c = scan_candles(h, sym, "1d")
            if not c.get("ok"):
                return None
            latest = c["latest"]
            if cval in ("boga", "ayi"):
                target = "Boğa" if cval == "boga" else "Ayı"
                pats = [p for p in latest if p["type"] == target]
                if pats:
                    return {"symbol": sym, "label": ", ".join(p["name"] for p in pats),
                            "detail": f"{target} formasyonu", "price": c["price"]}
            else:
                pats = [p for p in latest if cval.lower() in p["name"].lower()]
                if pats:
                    return {"symbol": sym, "label": ", ".join(p["name"] for p in pats),
                            "detail": pats[0]["type"], "price": c["price"]}
    except Exception:
        return None
    return None


def scan_universe(ctype, cval, symbols=None, limit=None, max_workers=10):
    syms = symbols if symbols else sources.BIST_CORE
    if limit:
        syms = syms[:limit]

    def work(sym):
        h = _fetch(sym)
        if h is None:
            return None
        return _match(sym, h, ctype, cval)

    results = []
    with cf.ThreadPoolExecutor(max_workers=max_workers) as ex:
        for r in ex.map(work, syms):
            if r:
                results.append(r)
    # fiyatı olanları başa, ada göre sırala
    results.sort(key=lambda x: x["symbol"])
    return {"ctype": ctype, "cval": cval, "scanned": len(syms),
            "matches": results, "count": len(results)}
