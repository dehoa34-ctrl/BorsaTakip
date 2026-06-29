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

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5"
}

def get_yahoo_cookie_and_crumb():
    """Yahoo Finance quoteSummary API'si için gereken çerez (cookie) ve kırıntı (crumb) değerlerini çeker."""
    try:
        # 1. Cookie almak için fc.yahoo.com'a git
        resp = httpx.get("https://fc.yahoo.com", headers=HEADERS, follow_redirects=True, timeout=5)
        cookies = resp.cookies
        
        # 2. Crumb almak için getcrumb API'sini sorgula
        crumb_resp = httpx.get("https://query1.finance.yahoo.com/v1/test/getcrumb", headers=HEADERS, cookies=cookies, timeout=5)
        crumb = crumb_resp.text.strip()
        return cookies, crumb
    except Exception as e:
        logger.warning(f"Failed to fetch Yahoo cookie/crumb: {e}")
        return None, None

def fetch_history_http(symbol: str, period: str = "6mo", interval: str = "1d") -> pd.DataFrame:
    """Doğrudan Yahoo Finance Chart API'sini sorgulayarak tarihçe verisi çeker (yfinance yedeği)."""
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
    params = {"range": period, "interval": interval}
    
    try:
        with httpx.Client(headers=HEADERS, timeout=15.0) as client:
            resp = client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()
    except Exception as e:
        logger.warning(f"HTTPX history fetch failed: {e}. Trying urllib...")
        try:
            full_url = f"{url}?range={period}&interval={interval}"
            req = urllib.request.Request(full_url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=15) as response:
                data = json.loads(response.read().decode('utf-8'))
        except Exception as ex:
            logger.error(f"Urllib history fetch failed: {ex}")
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
        logger.error(f"Failed to parse Yahoo chart JSON: {parse_err}")
        return pd.DataFrame()

def fetch_info_http(symbol: str) -> dict:
    """Doğrudan Yahoo Finance quoteSummary API'sini sorgulayarak hisse bilgilerini çeker (yfinance.Ticker.info yedeği)."""
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
            resp.raise_for_status()
            data = resp.json()
    except Exception as e:
        logger.warning(f"HTTPX info fetch failed: {e}. Attempting direct HTTP fallback...")
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
        logger.error(f"Failed to parse quoteSummary JSON for {symbol}: {parse_err}")
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
            
        return fetch_history_http(self.symbol, period, interval)

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
        return self._info

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
