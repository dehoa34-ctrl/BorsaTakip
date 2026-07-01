"""
data_fetcher.py — Yahoo Finance API Fallback / Backup Katmanı.
yfinance kütüphanesi çöktüğünde veya engellendiğinde doğrudan Yahoo Finance 
HTTP endpoint'lerini (v8/chart ve v10/quoteSummary) sorgulayarak kesintisiz çalışmayı sağlar.
"""

import logging
import pandas as pd
import numpy as np
import yfinance as yf
import httpx
import urllib.request
import json
import time
import os
import pickle

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5"
}

# Pre-load 5-year BIST price cache once on import
_PRICE_CACHE_5Y = {}
try:
    _dir_path = os.path.dirname(os.path.abspath(__file__))
    _cache_path = os.path.join(_dir_path, "price_cache_5y.pkl")
    if os.path.exists(_cache_path):
        with open(_cache_path, "rb") as _f:
            _PRICE_CACHE_5Y = pickle.load(_f)
        logger.info(f"Loaded {len(_PRICE_CACHE_5Y)} cached BIST tickers from price_cache_5y.pkl")
    else:
        logger.warning(f"price_cache_5y.pkl not found at {_cache_path}")
except Exception as _e:
    logger.warning(f"Failed to load price_cache_5y.pkl: {_e}")

def _cache_is_fresh(max_age_days=1):
    """Örnek bir sembole bakarak önbelleğin ne kadar güncel olduğunu kontrol eder."""
    if not _PRICE_CACHE_5Y:
        return False
    try:
        sample = next(iter(_PRICE_CACHE_5Y.values()))
        if sample is None or sample.empty:
            return False
        last_date = sample.index[-1]
        if getattr(last_date, "tzinfo", None) is not None:
            last_date = last_date.tz_localize(None)
        age_days = (pd.Timestamp.now().normalize() - last_date.normalize()).days
        return age_days <= max_age_days
    except Exception:
        return False


def initialize_cache(force=False):
    """
    BIST tickers verilerini toplu halde yf.download ile indirip diske kaydeder.
    force=False iken: önbellek DOLU ve GÜNCEL (≤1 gün) ise atlanır.
    force=True (periyodik yenileme) iken: her zaman yeniden indirir — böylece
    uzun süre çalışan sunucularda 'ultimate fallback' asla haftalarca bayat kalmaz.
    """
    global _PRICE_CACHE_5Y
    cache_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "price_cache_5y.pkl")

    if not force and len(_PRICE_CACHE_5Y) > 50 and _cache_is_fresh():
        return

    logger.info("BIST önbelleği boş/eksik/bayat. Toplu indirme (batch download) başlatılıyor...")
    
    try:
        import sources
        # Tüm BIST sembollerini hazırla
        symbols = [s + ".IS" for s in sources.BIST_CORE]
        
        # 50'şerli gruplara böl (Yahoo rate limit yememek için en güvenli ve hızlı yol)
        batch_size = 50
        batches = [symbols[i:i + batch_size] for i in range(0, len(symbols), batch_size)]
        
        new_cache = {}
        for idx, batch in enumerate(batches):
            logger.info(f"BIST veri paketi indiriliyor ({idx+1}/{len(batches)})...")
            try:
                # Toplu indir (6 aylık veri teknik analiz için yeterlidir)
                df = yf.download(batch, period="6mo", interval="1d", progress=False)
                if df is not None and not df.empty:
                    for sym in batch:
                        clean_sym = sym.replace(".IS", "")
                        # Ticker'ın sütunları mevcut mu kontrol et
                        if "Close" in df and sym in df["Close"].columns:
                            try:
                                # Tekil DataFrame oluştur
                                ticker_df = pd.DataFrame({
                                    "Open": df["Open"][sym],
                                    "High": df["High"][sym],
                                    "Low": df["Low"][sym],
                                    "Close": df["Close"][sym],
                                    "Volume": df["Volume"][sym]
                                })
                                # Sadece Close değeri dolu olan satırları tut
                                ticker_df = ticker_df.dropna(subset=["Close"])
                                if not ticker_df.empty:
                                    new_cache[clean_sym] = ticker_df
                            except Exception as parse_e:
                                logger.debug(f"Failed to parse batch data for {sym}: {parse_e}")
            except Exception as batch_e:
                logger.warning(f"Batch {idx+1} download failed: {batch_e}")
                
        if new_cache:
            _PRICE_CACHE_5Y.update(new_cache)
            with open(cache_path, "wb") as f:
                pickle.dump(_PRICE_CACHE_5Y, f)
            logger.info(f"BIST önbelleği başarıyla oluşturuldu ve diske kaydedildi. Toplam {len(_PRICE_CACHE_5Y)} hisse.")
        else:
            logger.warning("Toplu indirme başarısız oldu veya hiçbir veri çekilemedi.")
    except Exception as e:
        logger.error(f"Önbellek ilklendirme hatası: {e}")

# Arka planda çalıştır (sunucu açılışını bloklamaz) + periyodik yenile.
# Not: eskiden bu önbellek YALNIZCA boşken bir kez dolduruluyordu ve sonra
# process ömrü boyunca hiç yenilenmiyordu — uzun süre açık kalan bir sunucuda
# 'ultimate fallback' haftalarca bayat kalabiliyordu (yanlış/eski fiyat riski).
def _cache_refresh_loop():
    import threading
    initialize_cache()  # açılışta bir kez (boş/bayatsa doldurur)
    while True:
        time.sleep(12 * 3600)  # 12 saatte bir tazele
        try:
            initialize_cache(force=True)
        except Exception as e:
            logger.warning(f"Periyodik önbellek yenileme hatası: {e}")

def _async_init_cache():
    import threading
    threading.Thread(target=_cache_refresh_loop, daemon=True).start()

_async_init_cache()

_yahoo_blocked_until = 0.0

def is_yahoo_blocked() -> bool:
    global _yahoo_blocked_until
    return time.time() < _yahoo_blocked_until

def mark_yahoo_blocked():
    global _yahoo_blocked_until
    # Block live requests for the next 5 minutes
    _yahoo_blocked_until = time.time() + 300.0
    logger.warning("Yahoo Finance rate limit or block detected. Disabling live requests for 5 minutes and using cache fallback.")

def get_yahoo_cookie_and_crumb():
    """Yahoo Finance quoteSummary API'si için gereken çerez (cookie) ve kırıntı (crumb) değerlerini çeker."""
    if is_yahoo_blocked():
        return None, None
    try:
        # 1. Cookie almak için fc.yahoo.com'a git
        resp = httpx.get("https://fc.yahoo.com", headers=HEADERS, follow_redirects=True, timeout=5)
        if resp.status_code == 429:
            mark_yahoo_blocked()
            return None, None
        cookies = resp.cookies
        
        # 2. Crumb almak için getcrumb API'sini sorgula
        crumb_resp = httpx.get("https://query1.finance.yahoo.com/v1/test/getcrumb", headers=HEADERS, cookies=cookies, timeout=5)
        if crumb_resp.status_code == 429:
            mark_yahoo_blocked()
            return None, None
        crumb = crumb_resp.text.strip()
        return cookies, crumb
    except Exception as e:
        logger.debug(f"Failed to fetch Yahoo cookie/crumb: {e}")
        if "429" in str(e) or "too many requests" in str(e).lower():
            mark_yahoo_blocked()
        return None, None

def fetch_history_http(symbol: str, period: str = "6mo", interval: str = "1d") -> pd.DataFrame:
    """Doğrudan Yahoo Finance Chart API'sini sorgulayarak tarihçe verisi çeker (yfinance yedeği)."""
    if is_yahoo_blocked():
        return pd.DataFrame()
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
    params = {"range": period, "interval": interval}
    
    try:
        with httpx.Client(headers=HEADERS, timeout=15.0) as client:
            resp = client.get(url, params=params)
            if resp.status_code == 429:
                mark_yahoo_blocked()
                return pd.DataFrame()
            resp.raise_for_status()
            data = resp.json()
    except Exception as e:
        logger.debug(f"HTTPX history fetch failed: {e}. Trying urllib...")
        if "429" in str(e) or "too many requests" in str(e).lower():
            mark_yahoo_blocked()
            return pd.DataFrame()
        try:
            full_url = f"{url}?range={period}&interval={interval}"
            req = urllib.request.Request(full_url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=15) as response:
                data = json.loads(response.read().decode('utf-8'))
        except Exception as ex:
            logger.debug(f"Urllib history fetch failed: {ex}")
            if "429" in str(ex) or "too many requests" in str(ex).lower():
                mark_yahoo_blocked()
            return pd.DataFrame()

    try:
        result = data["chart"]["result"][0]
        timestamps = result["timestamp"]
        indicators = result["indicators"]["quote"][0]
        
        o = indicators.get("open", [])
        h = indicators.get("high", [])
        l = indicators.get("low", [])
        c = indicators.get("close", [])
        v = indicators.get("volume", [])
        
        length = len(timestamps)
        o = o + [np.nan] * (length - len(o))
        h = h + [np.nan] * (length - len(h))
        l = l + [np.nan] * (length - len(l))
        c = c + [np.nan] * (length - len(c))
        v = v + [0] * (length - len(v))
        
        df = pd.DataFrame({
            "Open": o,
            "High": h,
            "Low": l,
            "Close": c,
            "Volume": v
        }, index=pd.to_datetime(timestamps, unit="s"))
        
        df.index.name = "Date"
        df.index = df.index.tz_localize(None)
        df = df.dropna(subset=["Close"])
        return df
    except Exception as parse_err:
        logger.debug(f"Failed to parse Yahoo chart JSON: {parse_err}")
        return pd.DataFrame()

def fetch_info_http(symbol: str) -> dict:
    """Doğrudan Yahoo Finance quoteSummary API'sini sorgulayarak hisse bilgilerini çeker (yfinance.Ticker.info yedeği)."""
    if is_yahoo_blocked():
        return {}
    # Cookie ve crumb al
    cookies, crumb = get_yahoo_cookie_and_crumb()
    
    modules = "financialData,defaultKeyStatistics,summaryDetail,price"
    url = f"https://query2.finance.yahoo.com/v10/finance/quoteSummary/{symbol}"
    params = {"modules": modules}
    if crumb:
        params["crumb"] = crumb
        
    try:
        with httpx.Client(headers=HEADERS, cookies=cookies, timeout=15.0) as client:
            resp = client.get(url, params=params)
            if resp.status_code == 429:
                mark_yahoo_blocked()
                return {}
            resp.raise_for_status()
            data = resp.json()
    except Exception as e:
        logger.debug(f"HTTPX info fetch failed: {e}. Attempting direct HTTP fallback...")
        if "429" in str(e) or "too many requests" in str(e).lower():
            mark_yahoo_blocked()
        return {}

    try:
        summary = data["quoteSummary"]["result"][0]
        
        fin = summary.get("financialData", {})
        stats = summary.get("defaultKeyStatistics", {})
        detail = summary.get("summaryDetail", {})
        price_info = summary.get("price", {})
        
        def val(d, key):
            if key in d and isinstance(d[key], dict):
                return d[key].get("raw")
            return d.get(key)
        
        info = {
            "shortName": price_info.get("shortName") or price_info.get("longName") or symbol,
            "totalDebt": val(fin, "totalDebt"),
            "totalCash": val(fin, "totalCash"),
            "ebitda": val(fin, "ebitda"),
            "earningsQuarterlyGrowth": val(fin, "earningsQuarterlyGrowth"),
            "revenueGrowth": val(fin, "revenueGrowth"),
            "returnOnEquity": val(fin, "returnOnEquity"),
            "trailingPE": val(stats, "trailingPE") or val(detail, "trailingPE"),
            "priceToBook": val(stats, "priceToBook") or val(detail, "priceToBook"),
            "floatShares": val(stats, "floatShares"),
            "sharesOutstanding": val(stats, "sharesOutstanding"),
        }
        return info
    except Exception as parse_err:
        logger.debug(f"Failed to parse quoteSummary JSON for {symbol}: {parse_err}")
        return {}

# ── Ana API Sarmalayıcı Sınıf ──

class Ticker:
    """yfinance.Ticker sınıfının drop-in yedeği."""
    def __init__(self, symbol: str):
        # Gerçek drop-in: sembolü OLDUĞU GİBİ kullan (yf.Ticker gibi).
        # Otomatik .IS ekleme YOK — ABD hisseleri (AAPL, NVDA) bozulmasın.
        # BIST için çağıran taraf zaten ".IS" ekliyor.
        self.raw_symbol = symbol.upper()
        self.symbol = self.raw_symbol
        self._info = None
        self._news = None

    def history(self, period: str = "6mo", interval: str = "1d") -> pd.DataFrame:
        try:
            t = yf.Ticker(self.symbol)
            df = t.history(period=period, interval=interval)
            if df is not None and not df.empty:
                df.index = df.index.tz_localize(None)
                return df
            logger.warning(f"yfinance.Ticker.history returned empty for {self.symbol}, falling back to HTTP API...")
        except Exception as e:
            logger.warning(f"yfinance.Ticker.history failed for {self.symbol}: {e}, falling back to HTTP API...")
            
        df_fallback = fetch_history_http(self.symbol, period, interval)
        if df_fallback is not None and not df_fallback.empty:
            return df_fallback

        # Ultimate fallback: local cache C:\Users\canbi\OneDrive\Masaüstü\projeler\BorsaTakip\price_cache_5y.pkl
        # ÖNEMLİ: bu önbellek yalnızca process başlarken BİR KEZ diskten okunur ve
        # kendini asla otomatik yenilemez. Uzun süre çalışan bir sunucuda günler/haftalar
        # eskiyebilir (özellikle bedelsiz sermaye artırımı gibi kurumsal işlemlerden sonra
        # fiyat ölçeği tamamen değişir). Bu yüzden "güncel fiyat" gibi sunmadan önce
        # tazelik kontrolü yapılır — çok eskiyse yanlış fiyat göstermek yerine boş dönülür.
        clean_symbol = self.symbol.replace(".IS", "")
        if clean_symbol in _PRICE_CACHE_5Y:
            cached_df = _PRICE_CACHE_5Y[clean_symbol]
            if cached_df is not None and not cached_df.empty:
                df = cached_df.copy()
                if df.index.tz is not None:
                    df.index = df.index.tz_localize(None)
                last_bar_age_days = (pd.Timestamp.now().normalize() - df.index[-1].normalize()).days
                if last_bar_age_days > 4:
                    logger.warning(
                        f"{self.symbol} için yerel önbellek çok bayat "
                        f"({last_bar_age_days} gün) — YANLIŞ fiyat göstermemek için boş dönülüyor."
                    )
                    return pd.DataFrame()
                logger.info(f"Yahoo Finance failed for {self.symbol}. Falling back to local cache "
                            f"(son bar {last_bar_age_days} gün önce).")
                try:
                    if period == "1mo":
                        start_date = df.index[-1] - pd.Timedelta(days=30)
                        df = df[df.index >= start_date]
                    elif period == "3mo":
                        start_date = df.index[-1] - pd.Timedelta(days=90)
                        df = df[df.index >= start_date]
                    elif period == "6mo":
                        start_date = df.index[-1] - pd.Timedelta(days=180)
                        df = df[df.index >= start_date]
                    elif period == "1y":
                        start_date = df.index[-1] - pd.Timedelta(days=365)
                        df = df[df.index >= start_date]
                except Exception as filter_err:
                    logger.warning(f"Failed to slice cached df for {self.symbol}: {filter_err}")
                return df
        return pd.DataFrame()

    @property
    def info(self) -> dict:
        if self._info is not None:
            return self._info
            
        try:
            t = yf.Ticker(self.symbol)
            inf = t.info
            if inf and isinstance(inf, dict) and "shortName" in inf:
                # FDO için floatShares/sharesOutstanding ekle
                if "floatShares" not in inf:
                    fallback_info = fetch_info_http(self.symbol)
                    inf["floatShares"] = fallback_info.get("floatShares")
                    inf["sharesOutstanding"] = fallback_info.get("sharesOutstanding")
                self._info = inf
                return self._info
            logger.warning(f"yfinance.Ticker.info returned invalid for {self.symbol}, falling back to HTTP API...")
        except Exception as e:
            logger.warning(f"yfinance.Ticker.info failed for {self.symbol}: {e}, falling back to HTTP API...")
            
        self._info = fetch_info_http(self.symbol)
        if self._info and isinstance(self._info, dict) and len(self._info) > 0:
            return self._info

        # Ultimate fallback: local screener_cache.json
        try:
            clean_symbol = self.symbol.replace(".IS", "")
            import screener
            screener_data = screener.get_screener_data()
            if clean_symbol in screener_data:
                logger.info(f"Yahoo Finance info failed for {self.symbol}. Falling back to screener cache.")
                sc = screener_data[clean_symbol]
                self._info = {
                    "shortName": sc.get("name") or clean_symbol,
                    "longName": sc.get("name") or clean_symbol,
                    "marketCap": int(sc.get("market_cap") * 1_000_000_000) if sc.get("market_cap") else None,
                    "enterpriseValue": int(sc.get("ev") * 1_000_000_000) if sc.get("ev") else None,
                    "trailingPE": sc.get("pe"),
                    "priceToBook": sc.get("pb"),
                    "returnOnEquity": sc.get("roe") / 100.0 if sc.get("roe") else None,
                    "floatShares": sc.get("floatShares"),
                    "sharesOutstanding": sc.get("sharesOutstanding"),
                }
                return self._info
        except Exception as cache_err:
            logger.warning(f"Screener cache fallback failed for {self.symbol}: {cache_err}")
        return {}

    @property
    def news(self) -> list:
        if self._news is not None:
            return self._news
            
        try:
            t = yf.Ticker(self.symbol)
            n = t.news
            if n:
                self._news = n
                return self._news
        except Exception as e:
            logger.warning(f"yfinance.Ticker.news failed for {self.symbol}: {e}")
            
        url = f"https://query2.finance.yahoo.com/v10/finance/quoteSummary/{self.symbol}?modules=news"
        try:
            with httpx.Client(headers=HEADERS, timeout=10.0) as client:
                resp = client.get(url)
                if resp.status_code == 200:
                    data = resp.json()
                    raw_news = data.get("quoteSummary", {}).get("result", [{}])[0].get("news", [])
                    self._news = raw_news
                    return self._news
        except Exception:
            pass
            
        self._news = []
        return self._news
