"""
BorsaTakip AI Analysis — Güncellenmiş main.py
Mevcut endpoint'ler + Yeni Trading Bot API'si
"""

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from typing import Optional, List
import asyncio
import time
import yfinance as yf
import pandas as pd
import uvicorn
import os
import logging
import feedparser

from analysis import get_signals
from technical import get_technical_analysis
from candles import scan_candles
from flow import analyze_flow
from news_engine import classify_item, analyze_category_reaction
import sources
import scanner as scan_mod
from fastapi.responses import PlainTextResponse

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(title="BorsaTakip AI - BIST & ABD Hisse Analizi")

# Static dizin
for d in ["static/css", "static/js"]:
    os.makedirs(d, exist_ok=True)

# ── Haber arşivi: gerçek KAP verisiyle çalışır (örnek/demo tohum KALDIRILDI) ──
try:
    sources.init_db()
    sources.purge_demo()   # eski 'örnek arşiv' satırlarını temizle — her şey gerçek
except Exception as _e:
    logger.warning(f"Haber arşivi hazırlanamadı: {_e}")


# ═══════════════════════════════════════════════════════════════════
#  Var Olan Endpoint'ler
# ═══════════════════════════════════════════════════════════════════

@app.get("/api/ticker/{symbol}")
def get_ticker_info(symbol: str, period: str = "6mo", interval: str = "1d"):
    try:
        ticker = yf.Ticker(symbol)
        history = ticker.history(period=period, interval=interval)
        if history.empty:
            raise HTTPException(status_code=404, detail="Symbol not found")
        latest = history.iloc[-1]
        analysis = get_signals(history, symbol=symbol)
        # ML Güven Skoru (if/else yerine) + akıllı para karakteri
        try:
            import swing_model
            ml = swing_model.predict_from_df(history, symbol=symbol)
        except Exception:
            ml = None
        # Temel analiz (5 rasyo) + Tuzak Filtresi / Onay Mekanizması
        try:
            import fundamentals as fund
            f = fund.get_fundamentals(symbol)
            final_view = fund.fuse(analysis.get("signal", ""),
                                   (ml or {}).get("flow_score", 0.0), f)
        except Exception:
            f, final_view = None, None
        return {
            "symbol": symbol,
            "price": round(latest['Close'], 2),
            "change": round(latest['Close'] - history.iloc[-2]['Close'], 2) if len(history) > 1 else 0,
            "change_percent": round(((latest['Close'] - history.iloc[-2]['Close']) / history.iloc[-2]['Close']) * 100, 2) if len(history) > 1 else 0,
            "analysis": analysis,
            "ml": ml,
            "fundamentals": f,
            "final_view": final_view
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/news/{symbol}")
def get_ticker_news(symbol: str):
    """
    Hisse haberleri — yalnızca GERÇEK veri:
      - BIST için: arşivdeki gerçek KAP bildirimleri (kategorize + duygu)
      - ABD/genel için: yfinance haber akışı
    (Kripto RSS kaldırıldı — sistem hisse odaklı.)
    """
    import time as _t
    from datetime import datetime as _dt
    news_list = []

    # 1) KAP bildirimleri (BIST için, arşivden gerçek)
    try:
        for r in sources.get_history(symbol, limit=15):
            try:
                ts = _dt.strptime(r["date"], "%Y-%m-%d").timestamp() if r.get("date") else _t.time()
            except Exception:
                ts = _t.time()
            news_list.append({
                "title": f"[KAP] {r['title']}",
                "link": r.get("url") or "#",
                "publisher": f"KAP · {r.get('category', '')} · {r.get('sentiment', '')}",
                "providerPublishTime": ts,
            })
    except Exception:
        pass

    # 2) yfinance haber akışı (özellikle ABD hisseleri için gerçek)
    try:
        for item in (yf.Ticker(symbol).news or [])[:8]:
            content = item.get("content", item)
            title = item.get("title") or content.get("title")
            link = item.get("link") or (content.get("canonicalUrl") or {}).get("url") or "#"
            if title:
                news_list.append({
                    "title": title, "link": link,
                    "publisher": item.get("publisher", "Piyasa Haberi"),
                    "providerPublishTime": item.get("providerPublishTime", _t.time()),
                })
    except Exception:
        pass

    if not news_list:
        news_list.append({
            "title": f"{symbol.replace('.IS','')} için güncel haber/KAP bildirimi bulunamadı. "
                     "KAP arşivini 'Haber Zekâsı > KAP Yenile' ile güncelleyebilirsiniz.",
            "link": "#", "publisher": "Sistem", "providerPublishTime": time.time(),
        })
    return news_list[:15]


@app.get("/api/technical/{symbol}")
def get_technical(symbol: str, period: str = "6mo", interval: str = "1d"):
    """
    investing.com tarzı çok-indikatörlü teknik özet (konsensüs + olasılık).
    Tek bir 'al/sat' yerine ~24 göstergenin oy birliğini döndürür.
    """
    try:
        ticker = yf.Ticker(symbol)
        history = ticker.history(period=period, interval=interval)
        if history.empty:
            raise HTTPException(status_code=404, detail="Symbol not found")
        result = get_technical_analysis(history, symbol=symbol, timeframe=interval)
        latest = history.iloc[-1]
        prev = history.iloc[-2] if len(history) > 1 else latest
        result["change"] = round(latest["Close"] - prev["Close"], 2)
        result["change_percent"] = round(
            ((latest["Close"] - prev["Close"]) / prev["Close"]) * 100, 2
        ) if prev["Close"] else 0
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/news-intel/{symbol}")
def get_news_intel(symbol: str):
    """
    Haber Zekâsı: sembol için bildirimleri kategorize + duygu ile sınıflandırır ve
    'aynı tip haber geçmişte geldiğinde hisse ne yaptı' istatistiğini üretir.
    Veri kaynağı bağımsız (KAP takıldığında otomatik zenginleşir).
    """
    try:
        sym = symbol.upper()
        # Canlı haberleri arşive ekle (best-effort, hızlı). KAP arşivi
        # /api/kap/refresh ile doldurulur (Puppeteer ~40sn sürdüğü için burada
        # senkron çağrılmaz).
        try:
            sources.ingest(sources.fetch_symbol_news(sym))
        except Exception:
            pass

        recent = sources.get_history(sym, limit=60)

        # Fiyat geçmişi (tepki hesabı için)
        try:
            price_df = yf.Ticker(sym).history(period="1y", interval="1d")
        except Exception:
            price_df = None

        # Sembolde arşivde geçen her kategori için geçmiş tepki
        reactions = {}
        if price_df is not None and not price_df.empty:
            cats = {}
            for r in recent:
                cats.setdefault(r["category"], []).append({"date": r["date"], "title": r["title"]})
            for cat, events in cats.items():
                if len(events) >= 2 and cat != "Genel Bilgi":
                    res = analyze_category_reaction(price_df, events)
                    if any(res["stats"][k]["n"] for k in res["stats"]):
                        reactions[cat] = res

        # YZ modeli: en güncel bildirim için 3 günlük yükseliş olasılığı
        ml_pred = None
        try:
            import ml_model
            if recent:
                top = recent[0]
                ml_pred = ml_model.predict(sym, top["title"], top.get("date"), top.get("time"),
                                           sym_freq=len(recent))
        except Exception:
            ml_pred = None

        return {
            "ok": True,
            "symbol": sym,
            "recent": recent,
            "reactions": reactions,
            "ml": ml_pred,
            "counts": {
                "total": len(recent),
                "pozitif": sum(1 for r in recent if "Pozitif" in r["sentiment"]),
                "negatif": sum(1 for r in recent if "Negatif" in r["sentiment"]),
            },
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/kap/refresh")
def kap_refresh():
    """KAP bildirimlerini Puppeteer ile yeniden çek ve arşive işle (~40sn)."""
    try:
        rows = sources.fetch_kap_disclosures(force=True)
        return {"ok": True, "fetched": len(rows), "sample": rows[:5]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/model/info")
def model_info():
    """Eğitilmiş YZ modelinin durumu ve performansı."""
    try:
        import ml_model
        return ml_model.model_info()
    except Exception as e:
        return {"ready": False, "error": str(e)[:120]}


@app.get("/api/model/predict/{symbol}")
def model_predict(symbol: str, title: str = "Özel Durum Açıklaması"):
    """Verilen sembol/başlık için 3 günlük yükseliş olasılığı tahmini."""
    try:
        import ml_model
        return ml_model.predict(symbol.upper(), title)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/kap/history")
def kap_history(weeks: int = 8):
    """
    KAP GEÇMİŞ arşivini haftalık aralıklarla toplu çek (geçmiş-tepki için).
    weeks kadar hafta geriye gider; ~(weeks×6sn) sürer.
    """
    try:
        return sources.fetch_kap_history(weeks=max(1, min(weeks, 26)))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/scanner")
def get_scanner(limit: int = 80):
    """
    BIST haber tarama panosu (scalp): arşivdeki son bildirimleri duyguya göre
    sıralayıp pozitif/negatif akışı döndürür. KAP bağlanınca ~600 hisseyi besler.
    """
    items = sources.recent_all(limit=limit)
    pozitif = [i for i in items if "Pozitif" in i["sentiment"]]
    negatif = [i for i in items if "Negatif" in i["sentiment"]]
    return {
        "ok": True,
        "universe": len(sources.BIST_CORE),
        "counts": {"toplam": len(items), "pozitif": len(pozitif), "negatif": len(negatif)},
        "pozitif": pozitif[:30],
        "negatif": negatif[:30],
        "items": items,
    }


@app.get("/api/scan")
def run_scan(ctype: str = "teknik", cval: str = "Güçlü Al", limit: int = 0):
    """
    BIST evrenini kritere göre tara. ctype: teknik|olasilik|rsi|mum.
    limit=0 → tüm evren (~550, biraz sürer). Sonuç dışa aktarılabilir.
    """
    lim = limit if limit > 0 else None
    res = scan_mod.scan_universe(ctype, cval, limit=lim)
    res["universe_total"] = len(sources.BIST_CORE)
    return res


@app.get("/api/scan/export", response_class=PlainTextResponse)
def export_scan(ctype: str = "teknik", cval: str = "Güçlü Al", limit: int = 0,
                symbols: str = ""):
    """
    Tarama sonucunu (veya verilen sembol listesini) İdealgo TXT formatında indir:
    IMKBH'SEMBOL veya CVAL'SEMBOL. symbols verilirse (virgüllü) doğrudan onu biçimler; yoksa tarar.
    """
    if symbols.strip():
        syms = [s for s in symbols.replace(";", ",").split(",") if s.strip()]
    else:
        lim = limit if limit > 0 else None
        res = scan_mod.scan_universe(ctype, cval, limit=lim)
        syms = [m["symbol"] for m in res["matches"]]
    txt = sources.to_ideal_format(syms, prefix=cval)
    fname = f"tarama_{ctype}_{int(time.time())}.txt"
    return PlainTextResponse(content=txt, headers={
        "Content-Disposition": f'attachment; filename="{fname}"'
    })


@app.get("/api/fundamentals/{symbol}")
def get_fundamentals_ep(symbol: str):
    """Temel analiz: 5 ana rasyo + temel kalite skoru (yfinance)."""
    try:
        import fundamentals as fund
        return fund.get_fundamentals(symbol)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/flow/{symbol}")
def get_flow(symbol: str, period: str = "6mo", interval: str = "1d"):
    """
    Hacim & Likidite (akıllı para) göstergeleri: MFI, OBV, CMF, POC +
    divergence ve tuzak (bear/bull trap) tespiti.
    """
    try:
        ticker = yf.Ticker(symbol)
        history = ticker.history(period=period, interval=interval)
        if history.empty:
            raise HTTPException(status_code=404, detail="Symbol not found")
        return analyze_flow(history, symbol=symbol)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/candles/{symbol}")
def get_candles(symbol: str, period: str = "3mo", interval: str = "1d"):
    """
    Mum formasyonları taraması (price-action). Çekiç, Yutan, Yıldız,
    Üç Asker/Karga vb. boğa/ayı/kararsız desenleri tespit eder.
    """
    try:
        ticker = yf.Ticker(symbol)
        history = ticker.history(period=period, interval=interval)
        if history.empty:
            raise HTTPException(status_code=404, detail="Symbol not found")
        return scan_candles(history, symbol=symbol, timeframe=interval)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/history/{symbol}")
def get_ticker_history(symbol: str, period: str = "1mo", interval: str = "1d"):
    try:
        ticker = yf.Ticker(symbol)
        history = ticker.history(period=period, interval=interval)
        if history.empty:
            raise HTTPException(status_code=404, detail="Symbol not found")
        formatted_data = []
        for index, row in history.iterrows():
            if interval in ['1m', '2m', '5m', '15m', '30m', '60m', '90m', '1h']:
                time_val = int(index.timestamp())
            else:
                time_val = index.strftime("%Y-%m-%d")
            formatted_data.append({
                "time": time_val,
                "open": round(row["Open"], 2), "high": round(row["High"], 2),
                "low": round(row["Low"], 2), "close": round(row["Close"], 2)
            })
        return formatted_data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Periyodik otomatik KAP yenileme ────────────────────────────────────────
_KAP_AUTO = os.environ.get("KAP_AUTO", "1") == "1"
_KAP_AUTO_INTERVAL = int(os.environ.get("KAP_AUTO_INTERVAL", "900"))   # sn (15 dk)


async def _kap_auto_loop():
    """Arka planda periyodik olarak KAP'ı yenile (bloklamayan, thread'de çalışır)."""
    await asyncio.sleep(20)   # açılışta biraz bekle
    while True:
        try:
            rows = await asyncio.to_thread(sources.fetch_kap_disclosures, None, True)
            logger.info(f"[KAP-auto] {len(rows)} bildirim yenilendi.")
        except Exception as e:
            logger.warning(f"[KAP-auto] hata: {e}")
        await asyncio.sleep(_KAP_AUTO_INTERVAL)


@app.on_event("startup")
async def _start_kap_auto():
    if _KAP_AUTO:
        asyncio.create_task(_kap_auto_loop())
        logger.info(f"[KAP-auto] etkin (her {_KAP_AUTO_INTERVAL}sn).")


# ── Ana Sayfa ──────────────────────────────────────────────────────────────

@app.get("/")
def get_index():
    with open("static/index.html", "r", encoding="utf-8") as f:
        html_content = f.read()
    ts = int(time.time())
    for js in ["app.js", "technical.js", "candles.js", "newsintel.js", "scan.js"]:
        html_content = html_content.replace(f'src="js/{js}"', f'src="js/{js}?v={ts}"')
    html_content = html_content.replace('href="css/styles.css"', f'href="css/styles.css?v={ts}"')
    return HTMLResponse(content=html_content, headers={
        "Cache-Control": "no-cache, no-store, must-revalidate",
        "Pragma": "no-cache", "Expires": "0"
    })


app.mount("/", StaticFiles(directory="static", html=True), name="static")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=False)
