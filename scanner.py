"""
scanner.py — BIST evreni üzerinde kriterli formasyon/teknik tarama.

İdealgo'daki "formasyon tarama" mantığı: bir kritere uyan hisseleri bul, listele,
ve İdealgo'ya geri yüklenebilir TXT (IMKBH'SEMBOL) olarak dışa aktar.
"""

import concurrent.futures as cf
import json
import os
import time
import data_fetcher
import sources
import fundamentals as fund
import flow
from technical import get_technical_analysis
from candles import scan_candles

# ── Kısa süreli tarama önbelleği + ölü sembol kayıt defteri ─────────────────
# Amaç: aynı oturumda arka arkaya yapılan taramalarda (ör. eşik değerini
# değiştirip yeniden tarama) her seferinde Yahoo'ya tekrar istek atmayı
# önlemek (429/rate-limit riskini azaltır → "bayat fallback fiyatı" hatasını
# önler) ve hiç veri vermeyen (delisted/sukuk/varlık kiralama vb.) sembolleri
# tekrar tekrar sorgulamayı atlamak (tarama hızını korur).
_HIST_CACHE = {}          # sym -> (fetched_at, df)
_HIST_TTL = 900           # 15 dk — bir oturum içindeki tekrar taramalar için yeterli
_DEAD_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dead_symbols.json")
_DEAD_TTL = 30 * 24 * 3600  # 30 gün sonra tekrar dene (belki listelenmiştir)
_dead_cache = None


def _load_dead():
    global _dead_cache
    if _dead_cache is None:
        try:
            with open(_DEAD_FILE, "r", encoding="utf-8") as f:
                _dead_cache = json.load(f)
        except Exception:
            _dead_cache = {}
    return _dead_cache


def _save_dead():
    try:
        with open(_DEAD_FILE, "w", encoding="utf-8") as f:
            json.dump(_dead_cache or {}, f)
    except Exception:
        pass


def _dead_backoff_seconds(fails):
    """
    Kademeli bekleme: tek seferlik hata çoğunlukla geçici rate-limit'tir
    (ör. KOZAL gibi gerçek/büyük bir hisse bile anlık 429 yiyebilir) —
    bunu 30 gün karantinaya almak yanlış olur. Israrlı (3+) hata olursa
    gerçekten sembol geçersizdir (delisted/sukuk/VKŞ vb.) ve uzun süre atlanır.
    """
    if fails <= 1:
        return 3600            # 1. hata: 1 saat sonra tekrar dene
    if fails == 2:
        return 6 * 3600        # 2. hata: 6 saat sonra tekrar dene
    return _DEAD_TTL            # 3+ hata: gerçekten ölü kabul et (30 gün)


def _fetch(sym):
    now = time.time()

    # 1) Kısa süreli başarı önbelleği
    cached = _HIST_CACHE.get(sym)
    if cached and (now - cached[0]) < _HIST_TTL:
        return cached[1]

    # 2) Ölü sembol kaydı — tekrar tekrar boşuna ağ isteği atmayı önler
    dead = _load_dead()
    d = dead.get(sym)
    if d and (now - d.get("last_try", 0)) < _dead_backoff_seconds(d.get("fails", 1)):
        return None

    try:
        # data_fetcher üzerinden yedekli tarihçe çeker
        h = data_fetcher.Ticker(sym + ".IS").history(period="6mo", interval="1d")
        if h is None or len(h) < 30:
            dead[sym] = {"last_try": now, "fails": (d.get("fails", 0) if d else 0) + 1}
            _save_dead()
            return None
        _HIST_CACHE[sym] = (now, h)
        if sym in dead:
            del dead[sym]   # kendini iyileştir: artık veri veriyor
            _save_dead()
        return h
    except Exception:
        dead[sym] = {"last_try": now, "fails": (d.get("fails", 0) if d else 0) + 1}
        _save_dead()
        return None

def _rsi_of(tech):
    for it in tech["oscillators"]["items"]:
        if it["name"] == "RSI(14)":
            return it["value"]
    return None

def _apply_pre_filters(sym, h, filters):
    """
    Kullanıcının belirlediği Sağ Panel kriterlerine göre hisseyi ön filtrelemeden geçirir.
    Eğer filtreyi geçemezse False döner ve hisse elenir.
    """
    # 1) Dinamik Aylık Hacim Sınırı (TL)
    if filters.get("vol_limit_toggle"):
        # Son 20 günlük toplam işlem hacmini (Fiyat * Hacim) hesapla
        if len(h) >= 20:
            vol_20 = h.iloc[-20:]
            monthly_vol_tl = float((vol_20["Close"] * vol_20["Volume"]).sum())
        else:
            monthly_vol_tl = float((h["Close"] * h["Volume"]).sum())
            
        limit_val = float(filters.get("vol_limit_val", 500000000.0))
        if monthly_vol_tl < limit_val:
            return False

    # 2) ROE ve FDO filtreleri (Fundamentals)
    if filters.get("roe_toggle") or filters.get("fdo_toggle"):
        f = fund.get_fundamentals(sym)
        
        # ROE filtrelemesi (% min - % max)
        if filters.get("roe_toggle"):
            roe = f.get("roe")
            if roe is not None:
                roe_min = float(filters.get("roe_min", 5.0))
                roe_max = float(filters.get("roe_max", 75.0))
                if roe < roe_min or roe > roe_max:
                    return False
            else:
                return False  # Veri yoksa elenir
                
        # FDO (Fiili Dolaşım Oranı) filtrelemesi (% min - % max)
        if filters.get("fdo_toggle"):
            fdo = f.get("fdo")
            if fdo is not None:
                fdo_min = float(filters.get("fdo_min", 15.0))
                fdo_max = float(filters.get("fdo_max", 55.0))
                if fdo < fdo_min or fdo > fdo_max:
                    return False
            else:
                return False

    # 3) Volume Z-Score (> 2.5 veya dinamik limit)
    if filters.get("vol_z_toggle"):
        vol = h["Volume"]
        if len(vol) >= 11:
            win = vol.iloc[-11:-1]  # son 10 gün (bugün hariç)
            v_mean = float(win.mean())
            v_std = float(win.std())
            v_today = float(vol.iloc[-1])
            vol_z = ((v_today - v_mean) / v_std) if v_std else 0.0
            z_limit = float(filters.get("vol_z_val", 2.5))
            if vol_z < z_limit:
                return False
        else:
            return False

    # 4) Hacimsiz Silkeleme Kontrolü (Divergence)
    if filters.get("silkeleme_toggle"):
        last_row = h.iloc[-1]
        # Eğer hisse bugün düşüşteyse (kırmızı mum)
        if last_row["Close"] < last_row["Open"]:
            vol = h["Volume"]
            avg_vol_20 = float(vol.iloc[-21:-1].mean()) if len(vol) >= 21 else float(vol.mean())
            vol_today = float(vol.iloc[-1])
            silkeleme_limit = float(filters.get("silkeleme_val", 30.0)) / 100.0
            
            # Kırmızı mumda hacim son 20 gün ortalamasının %30'unun (silkeleme_limit) altında mı?
            is_dry = vol_today < (avg_vol_20 * silkeleme_limit)
            if not is_dry:
                # Yüksek hacimli düşüş mal çıkışıdır (dağıtım), ön elemede elenir
                return False

    # 5) Dinamik İndikatör Ayarları (OBV Trend & MFI)
    if filters.get("indicators_toggle"):
        # OBV Trend Gün Sayısına göre kümülatif hacim eğimini kontrol et
        obv_trend_days = int(filters.get("obv_trend", 10))
        obv_series = flow.obv(h)
        slope = flow._slope(obv_series, obv_trend_days)
        if slope <= 0.0:
            # OBV eğimi negatif veya yataysa akümülasyon yoktur, elenir
            return False

    # 6) Yükseliş Olasılığı (AI Score / Teknik Konsensüs)
    if filters.get("min_prob_toggle"):
        t = get_technical_analysis(h, sym, "1d")
        if t.get("ok"):
            prob = t["summary"]["bull_prob"]
            p_limit = float(filters.get("min_prob", 30.0))
            if prob < p_limit:
                return False
        else:
            return False

    # 7) Karanlık Oda Hacim Oranı (> %15 veya dinamik limit)
    if filters.get("karanlik_oda_toggle"):
        try:
            t_intraday = data_fetcher.Ticker(sym + ".IS")
            df_5m = t_intraday.history(period="1d", interval="5m")
            if df_5m is not None and not df_5m.empty:
                # 17:50 - 18:05 arası karanlık oda seansı
                closing_vol = df_5m[
                    ((df_5m.index.hour == 17) & (df_5m.index.minute >= 50)) | (df_5m.index.hour == 18)
                ]["Volume"].sum()
                total_vol = df_5m["Volume"].sum()
                ratio = (closing_vol / total_vol) * 100 if total_vol > 0 else 0.0
                k_limit = float(filters.get("karanlik_oda_val", 15.0))
                if ratio < k_limit:
                    return False
            else:
                return False
        except Exception:
            return False

    return True

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
                    # Doğrulama skorunu da gösterelim
                    val_str = pats[0].get("validation", {}).get("verdict", "Nötr")
                    score_str = pats[0].get("validation", {}).get("score", 0)
                    return {"symbol": sym, "label": ", ".join(p["name"] for p in pats),
                            "detail": f"{target} ({val_str} Skor:{score_str})", "price": c["price"]}
            else:
                pats = [p for p in latest if cval.lower() in p["name"].lower()]
                if pats:
                    val_str = pats[0].get("validation", {}).get("verdict", "Nötr")
                    score_str = pats[0].get("validation", {}).get("score", 0)
                    return {"symbol": sym, "label": ", ".join(p["name"] for p in pats),
                            "detail": f"{pats[0]['type']} ({val_str} Skor:{score_str})", "price": c["price"]}
    except Exception:
        return None
    return None

def scan_universe(ctype, cval, symbols=None, limit=None, max_workers=10, filters=None):
    syms = symbols if symbols else sources.BIST_CORE
    if limit:
        syms = syms[:limit]

    def work(sym):
        h = _fetch(sym)
        if h is None:
            return None
        # Sağ Panel Ön Filtreleme (Pre-filtering)
        if filters:
            try:
                if not _apply_pre_filters(sym, h, filters):
                    return None
            except Exception:
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
