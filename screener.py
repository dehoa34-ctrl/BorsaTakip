"""
screener.py — Hisse Tarayıcı (Screener) ve İzleme Listesi Rasyo Katmanı.
Valuation, Returns, Profitability, Debt, Growth ve Mali Tablo metriklerini yönetir.
"""

import os
import json
import logging
import threading
import pandas as pd
import numpy as np
import data_fetcher
import sources
import fundamental_advisor

logger = logging.getLogger(__name__)

CACHE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "screener_cache.json")
_update_lock = threading.Lock()
_updating = False

# Arayüzdeki ekran görüntüsündeki BIST verileri (Tohumlama için)
SEED_VALUATION = {
    "A1CAP": {"roic": 68.02, "market_cap": 7.16, "ev": 1.72, "pe": 2.98, "pb": 0.79, "ev_sales": 0.05, "ev_ebitda": 0.20},
    "AEFES": {"roic": 9.57, "market_cap": 125.88, "ev": 190.01, "pe": 13.10, "pb": 1.05, "ev_sales": 0.70, "ev_ebitda": 4.05},
    "AGHOL": {"roic": 10.39, "market_cap": 80.51, "ev": 173.18, "pe": 20.95, "pb": 0.64, "ev_sales": 0.22, "ev_ebitda": 2.19},
    "AHGAZ": {"roic": 13.94, "market_cap": 94.80, "ev": 58.07, "pe": 24.85, "pb": 1.73, "ev_sales": 0.90, "ev_ebitda": 4.37},
    "AKFIS": {"roic": 8.10, "market_cap": 46.06, "ev": 65.44, "pe": 16.38, "pb": 1.29, "ev_sales": 4.01, "ev_ebitda": 11.54},
    "AKSEN": {"roic": 5.37, "market_cap": 101.30, "ev": 154.22, "pe": 24.94, "pb": 1.58, "ev_sales": 3.51, "ev_ebitda": 11.78},
    "ALKLC": {"roic": 15.44, "market_cap": 37.86, "ev": 40.18, "pe": None, "pb": 13.22, "ev_sales": 7.07, "ev_ebitda": 38.28},
    "ALVES": {"roic": 29.56, "market_cap": 4.34, "ev": 8.31, "pe": 39.76, "pb": 1.44, "ev_sales": 0.70, "ev_ebitda": 3.34},
    "ARASE": {"roic": 29.99, "market_cap": 29.23, "ev": 30.23, "pe": 10.83, "pb": 1.31, "ev_sales": 0.79, "ev_ebitda": 3.31},
    
    # Ekstra lider BIST sembolleri
    "THYAO": {"roic": 15.56, "market_cap": 456.40, "ev": 612.30, "pe": 3.45, "pb": 0.81, "ev_sales": 0.65, "ev_ebitda": 4.25},
    "GARAN": {"roic": 24.50, "market_cap": 322.00, "ev": 322.00, "pe": 3.82, "pb": 1.22, "ev_sales": None, "ev_ebitda": None},
    "AKBNK": {"roic": 22.80, "market_cap": 288.50, "ev": 288.50, "pe": 3.58, "pb": 1.15, "ev_sales": None, "ev_ebitda": None},
    "ISCTR": {"roic": 18.90, "market_cap": 252.00, "ev": 252.00, "pe": 4.10, "pb": 1.02, "ev_sales": None, "ev_ebitda": None},
    "YKBNK": {"roic": 20.10, "market_cap": 240.20, "ev": 240.20, "pe": 3.90, "pb": 1.08, "ev_sales": None, "ev_ebitda": None},
    "EREGL": {"roic": 3.80, "market_cap": 185.00, "ev": 235.00, "pe": 18.50, "pb": 0.75, "ev_sales": 1.25, "ev_ebitda": 9.80},
    "SISE": {"roic": 8.90, "market_cap": 160.00, "ev": 205.00, "pe": 11.20, "pb": 0.95, "ev_sales": 1.40, "ev_ebitda": 7.50},
    "BIMAS": {"roic": 28.50, "market_cap": 380.00, "ev": 395.00, "pe": 16.50, "pb": 4.50, "ev_sales": 0.95, "ev_ebitda": 11.20},
    "TUPRS": {"roic": 42.10, "market_cap": 310.00, "ev": 290.00, "pe": 5.80, "pb": 2.80, "ev_sales": 0.55, "ev_ebitda": 4.50},
    "FROTO": {"roic": 38.60, "market_cap": 360.00, "ev": 390.00, "pe": 9.40, "pb": 5.20, "ev_sales": 1.10, "ev_ebitda": 8.90},
    "KCHOL": {"roic": 14.80, "market_cap": 520.00, "ev": 820.00, "pe": 5.40, "pb": 1.40, "ev_sales": 0.40, "ev_ebitda": 3.80},
    "SAHOL": {"roic": 12.50, "market_cap": 180.00, "ev": 310.00, "pe": 4.20, "pb": 0.72, "ev_sales": 0.35, "ev_ebitda": 2.90},
    "ASELS": {"roic": 11.20, "market_cap": 215.00, "ev": 230.00, "pe": 12.80, "pb": 2.10, "ev_sales": 2.40, "ev_ebitda": 10.50},
}

def generate_seed_data():
    """Ekran görüntüsündeki gerçekçi ve seeded hisse rasyolarını oluşturur."""
    data = {}
    
    # 🇹🇷 BIST CORE listesi üzerinden dön
    for sym in sources.BIST_CORE:
        # Değerleme tohum verisini al veya varsayılan üret
        v = SEED_VALUATION.get(sym, {
            "roic": round(np.random.uniform(5.0, 35.0), 2),
            "market_cap": round(np.random.uniform(5.0, 150.0), 2),
            "ev": round(np.random.uniform(5.0, 180.0), 2),
            "pe": round(np.random.uniform(5.0, 35.0), 2) if np.random.rand() > 0.1 else None,
            "pb": round(np.random.uniform(0.5, 5.0), 2),
            "ev_sales": round(np.random.uniform(0.3, 5.0), 2),
            "ev_ebitda": round(np.random.uniform(2.0, 15.0), 2)
        })
        
        # Diğer sekmeler için gerçekçi/seeded test verileri
        item = {
            "symbol": sym,
            "name": sym + " Sanayi ve Ticaret A.Ş.",
            "logo": sym.lower()[:4],
            # Valuation
            "roic": v["roic"],
            "market_cap": v["market_cap"],
            "ev": v["ev"],
            "pe": v["pe"],
            "pb": v["pb"],
            "ev_sales": v["ev_sales"],
            "ev_ebitda": v["ev_ebitda"],
            # Returns (%)
            "ret_1d": round(np.random.uniform(-4.5, 4.5), 2),
            "ret_1w": round(np.random.uniform(-8.0, 12.0), 2),
            "ret_1m": round(np.random.uniform(-15.0, 25.0), 2),
            "ret_3m": round(np.random.uniform(-20.0, 45.0), 2),
            "ret_1y": round(np.random.uniform(20.0, 180.0), 2),
            "ret_ytd": round(np.random.uniform(5.0, 80.0), 2),
            # Profitability (%)
            "gross_margin": round(np.random.uniform(15.0, 60.0), 2),
            "net_margin": round(np.random.uniform(5.0, 35.0), 2),
            "ebitda_margin": round(np.random.uniform(10.0, 45.0), 2),
            "roe": round(v["roic"] * np.random.uniform(0.8, 1.5), 2),
            "roa": round(v["roic"] * np.random.uniform(0.3, 0.7), 2),
            # Leverage / Debt
            "net_debt_ebitda": round(np.random.uniform(-1.0, 4.0), 2),
            "debt_equity": round(np.random.uniform(0.1, 2.5), 2),
            "current_ratio": round(np.random.uniform(0.8, 2.5), 2),
            "quick_ratio": round(np.random.uniform(0.5, 1.8), 2),
            # Growth (%)
            "rev_growth": round(np.random.uniform(10.0, 120.0), 2),
            "earn_growth": round(np.random.uniform(5.0, 150.0), 2),
            "ebitda_growth": round(np.random.uniform(10.0, 130.0), 2),
            # Balance Sheet (mr TL)
            "current_assets": round(v["market_cap"] * np.random.uniform(0.4, 1.2), 2),
            "fixed_assets": round(v["market_cap"] * np.random.uniform(0.3, 1.5), 2),
            "total_assets": 0.0, # hesaplanacak
            "short_liabilities": round(v["market_cap"] * np.random.uniform(0.3, 0.8), 2),
            "long_liabilities": round(v["market_cap"] * np.random.uniform(0.1, 0.6), 2),
            "equity": round(v["market_cap"] / v["pb"], 2),
            # Income Statement (mr TL)
            "revenue": round(v["market_cap"] * np.random.uniform(0.5, 2.5), 2),
            "cost_of_sales": 0.0, # hesaplanacak
            "gross_profit": 0.0, # hesaplanacak
            "operating_income": 0.0, # hesaplanacak
            "ebitda": 0.0, # hesaplanacak
            "net_income": 0.0, # hesaplanacak
            # Cash Flow (mr TL)
            "operating_cf": round(v["market_cap"] * np.random.uniform(0.05, 0.25), 2),
            "investing_cf": round(-v["market_cap"] * np.random.uniform(0.02, 0.15), 2),
            "financing_cf": round(v["market_cap"] * np.random.uniform(-0.08, 0.08), 2),
            "free_cf": 0.0 # hesaplanacak
        }
        
        # Matematiksel bağıntıları hesapla
        item["total_assets"] = round(item["current_assets"] + item["fixed_assets"], 2)
        item["gross_profit"] = round(item["revenue"] * (item["gross_margin"] / 100), 2)
        item["cost_of_sales"] = round(item["revenue"] - item["gross_profit"], 2)
        item["ebitda"] = round(item["revenue"] * (item["ebitda_margin"] / 100), 2)
        item["net_income"] = round(item["revenue"] * (item["net_margin"] / 100), 2)
        item["operating_income"] = round(item["ebitda"] * 0.8, 2)
        item["free_cf"] = round(item["operating_cf"] + item["investing_cf"], 2) # investing eksidir

        # Yapay Zeka Değerlendirme & Yatırım Önerisi Raporunu Üret
        report_data = fundamental_advisor.generate_fundamental_report(sym, item)
        item["score"] = report_data["score"]
        item["recommendation"] = report_data["recommendation"]
        item["recommendation_color"] = report_data["color"]
        item["report"] = report_data["report"]
        
        data[sym] = item

    # Seed dosyasını diske kaydet
    try:
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
        logger.info("Screener tohum verisi başarıyla oluşturuldu.")
    except Exception as e:
        logger.error(f"Screener tohum verisi yazılamadı: {e}")
        
    return data

def get_screener_data():
    """Önbellekteki screener verisini yükler. Dosya yoksa tohum veriyi üretir."""
    if not os.path.exists(CACHE_FILE):
        return generate_seed_data()
    try:
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not data:
            return generate_seed_data()
        return data
    except Exception as e:
        logger.error(f"Screener önbelleği okunamadı: {e}")
        return generate_seed_data()

def update_screener_cache():
    """
    Arka planda Yahoo Finance üzerinden rasyoları ve fiyat geçmişlerini çekerek
    önbelleği (screener_cache.json) asenkron olarak günceller.
    """
    global _updating
    with _update_lock:
        if _updating:
            logger.info("Screener güncellemesi zaten çalışıyor.")
            return False
        _updating = True
        
    def worker():
        global _updating
        logger.info("Screener önbellek güncellemesi arka planda başlatıldı...")
        try:
            data = get_screener_data()
            
            # En çok işlem gören hisseleri önceliklendir (hızlı test ve güncelleme için)
            top_syms = sources.BIST_CORE[:40]
            
            for sym in top_syms:
                try:
                    # 1. Tarihçe Çek ve Getirileri Hesapla
                    sym_is = sym + ".IS"
                    t = data_fetcher.Ticker(sym_is)
                    h = t.history(period="1y", interval="1d")
                    
                    if h is not None and len(h) >= 2:
                        close = h["Close"]
                        # Günlük
                        ret_1d = (close.iloc[-1] / close.iloc[-2] - 1) * 100
                        data[sym]["ret_1d"] = round(float(ret_1d), 2)
                        # Haftalık (5 bar)
                        if len(h) >= 6:
                            ret_1w = (close.iloc[-1] / close.iloc[-6] - 1) * 100
                            data[sym]["ret_1w"] = round(float(ret_1w), 2)
                        # Aylık (20 bar)
                        if len(h) >= 21:
                            ret_1m = (close.iloc[-1] / close.iloc[-21] - 1) * 100
                            data[sym]["ret_1m"] = round(float(ret_1m), 2)
                        # Yıllık
                        ret_1y = (close.iloc[-1] / close.iloc[0] - 1) * 100
                        data[sym]["ret_1y"] = round(float(ret_1y), 2)
                    
                    # 2. Temel Analiz ve Değerleme Verilerini Çek
                    inf = t.info
                    if inf:
                        # Rasyoları güncelle
                        mc = inf.get("marketCap")
                        ev = inf.get("enterpriseValue")
                        pe = inf.get("trailingPE")
                        pb = inf.get("priceToBook")
                        roe = inf.get("returnOnEquity")
                        
                        if mc:
                            data[sym]["market_cap"] = round(float(mc) / 1_000_000_000, 2)
                        if ev:
                            data[sym]["ev"] = round(float(ev) / 1_000_000_000, 2)
                        if pe:
                            data[sym]["pe"] = round(float(pe), 2)
                        if pb:
                            data[sym]["pb"] = round(float(pb), 2)
                        if roe:
                            data[sym]["roe"] = round(float(roe) * 100, 2)
                            # ROIC = ROE * 0.75 (BIST borç oranıyla yaklaşık modelleme)
                            data[sym]["roic"] = round(float(roe) * 75, 2)
                        
                        # Diğer yfinance rasyoları
                        ev_rev = inf.get("enterpriseToRevenue")
                        ev_eb = inf.get("enterpriseToEbitda")
                        if ev_rev:
                            data[sym]["ev_sales"] = round(float(ev_rev), 2)
                        if ev_eb:
                            data[sym]["ev_ebitda"] = round(float(ev_eb), 2)
                            
                        # Büyümeler
                        eg = inf.get("earningsQuarterlyGrowth") or inf.get("revenueGrowth")
                        if eg:
                            data[sym]["earn_growth"] = round(float(eg) * 100, 2)
                            
                        # Yapay Zeka Değerlendirmesini Yeniden Hesapla
                        report_data = fundamental_advisor.generate_fundamental_report(sym, data[sym])
                        data[sym]["score"] = report_data["score"]
                        data[sym]["recommendation"] = report_data["recommendation"]
                        data[sym]["recommendation_color"] = report_data["color"]
                        data[sym]["report"] = report_data["report"]
                            
                except Exception as sym_e:
                    logger.warning(f"Screener update failed for symbol {sym}: {sym_e}")
                    continue
            
            # Güncellenmiş veriyi kaydet
            with open(CACHE_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
            logger.info("Screener önbellek güncellemesi başarıyla tamamlandı.")
        except Exception as e:
            logger.error(f"Screener önbellek güncellemesi hata verdi: {e}")
        finally:
            with _update_lock:
                _updating = False
                
    threading.Thread(target=worker, daemon=True).start()
    return True
