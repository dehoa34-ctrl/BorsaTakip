"""
sources.py — Bildirim/haber kaynakları + arşiv (SQLite).

Tasarım: kaynak BAĞIMSIZ. Bugün çalışan kaynaklar (yfinance haberleri) + ileride
takılacak KAP scraper aynı arayüzü kullanır:  fetch_*  →  [{symbol,date,title,source,url}]

Arşiv (news_archive.db): ingest edilen her bildirim kategorize+duygu ile saklanır;
geçmiş-tepki motoru buradan "aynı tip haber geçmişte ne yaptı" sorgusunu besler.
Arşiv zamanla doldukça istatistik güçlenir.
"""

import os
import sqlite3
import time
from datetime import datetime, timedelta

from news_engine import classify_item

DB_PATH = os.environ.get("NEWS_DB_PATH", "news_archive.db")


# ─────────────────────────────────────────────────────────────────────────────
#  BIST sembol evreni — bist_tickers.txt'ten yüklenir (~550), yoksa çekirdek liste.
#  .IS uzantısı yfinance içindir. İdealgo formatı:  IMKBH'SEMBOL
# ─────────────────────────────────────────────────────────────────────────────
IDEAL_PREFIX = "IMKBH'"
_TICKERS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bist_tickers.txt")

_FALLBACK = [
    "THYAO", "GARAN", "AKBNK", "ISCTR", "YKBNK", "ASELS", "KCHOL", "SAHOL", "EREGL",
    "BIMAS", "SISE", "TUPRS", "FROTO", "TOASO", "TCELL", "TTKOM", "PGSUS", "KOZAL",
    "EKGYO", "ALARK", "MGROS", "DOHOL", "TKFEN", "AEFES", "CCOLA", "ULKER", "ASTOR",
]


def _parse_ticker_line(line):
    """Hem düz 'AKBNK' hem İdealgo 'IMKBH'AKBNK' satırını sembole çevirir."""
    s = line.strip()
    if not s:
        return None
    if "'" in s:                      # IMKBH'AKBNK → AKBNK
        s = s.split("'")[-1]
    s = s.upper()
    return s if s.isalnum() and s.isascii() else None


def _load_universe():
    try:
        with open(_TICKERS_FILE, encoding="utf-8") as f:
            syms = [t for t in (_parse_ticker_line(l) for l in f) if t]
        if syms:
            # benzersiz + sıra koru
            seen, out = set(), []
            for s in syms:
                if s not in seen:
                    seen.add(s); out.append(s)
            return out
    except Exception:
        pass
    return list(_FALLBACK)


BIST_CORE = _load_universe()


def bist_symbols(suffix=".IS"):
    return [s + suffix for s in BIST_CORE]


def to_ideal_format(symbols, prefix=None):
    """Sembol listesini İdealgo TXT formatına çevirir:  IMKBH'SEMBOL veya PREFIX'SEMBOL (satır satır)."""
    if prefix is None:
        pfx = IDEAL_PREFIX
    else:
        pfx = prefix + "'" if not prefix.endswith("'") else prefix
    lines = []
    for s in symbols:
        s = s.replace(".IS", "").upper().strip()
        if s:
            lines.append(pfx + s)
    return "\n".join(lines) + "\n"


# ─────────────────────────────────────────────────────────────────────────────
#  Arşiv (SQLite)
# ─────────────────────────────────────────────────────────────────────────────
def _conn():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    return c


def init_db():
    with _conn() as c:
        c.execute("""
            CREATE TABLE IF NOT EXISTS disclosures (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT, date TEXT, time TEXT, title TEXT,
                category TEXT, bias INTEGER, sentiment TEXT, score INTEGER,
                source TEXT, url TEXT,
                UNIQUE(symbol, date, title)
            )
        """)


def ingest(items):
    """items: [{symbol,date,title,source?,url?,time?}] → kategorize+duygu ile arşivle."""
    init_db()
    n = 0
    with _conn() as c:
        for it in items:
            cls = classify_item(it.get("title", ""))
            try:
                c.execute(
                    "INSERT OR IGNORE INTO disclosures "
                    "(symbol,date,time,title,category,bias,sentiment,score,source,url) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (it.get("symbol", ""), it.get("date", ""), it.get("time", ""),
                     it.get("title", ""), cls["category"], cls["category_bias"],
                     cls["sentiment"]["label"], cls["sentiment"]["score"],
                     it.get("source", ""), it.get("url", "")),
                )
                n += c.total_changes and 1 or 0
            except Exception:
                pass
    return n


def get_history(symbol, category=None, limit=200):
    init_db()
    sym = symbol.replace(".IS", "")
    q = "SELECT * FROM disclosures WHERE (symbol=? OR symbol=?)"
    args = [sym, symbol]
    if category:
        q += " AND category=?"
        args.append(category)
    q += " ORDER BY date DESC LIMIT ?"
    args.append(limit)
    with _conn() as c:
        return [dict(r) for r in c.execute(q, args).fetchall()]


def recent_all(limit=80):
    init_db()
    with _conn() as c:
        return [dict(r) for r in c.execute(
            "SELECT * FROM disclosures ORDER BY date DESC, id DESC LIMIT ?", (limit,)
        ).fetchall()]


# ─────────────────────────────────────────────────────────────────────────────
#  Canlı kaynaklar
# ─────────────────────────────────────────────────────────────────────────────
def fetch_symbol_news(symbol):
    """yfinance haber akışı (bazı semboller için doludur). → ortak format."""
    out = []
    try:
        import yfinance as yf
        for item in (yf.Ticker(symbol).news or [])[:15]:
            ts = item.get("providerPublishTime")
            d = datetime.fromtimestamp(ts).strftime("%Y-%m-%d") if ts else ""
            out.append({
                "symbol": symbol.replace(".IS", ""),
                "date": d,
                "title": item.get("title", ""),
                "source": item.get("publisher", "yfinance"),
                "url": item.get("link", ""),
            })
    except Exception:
        pass
    return out


_KAP_CACHE = {"ts": 0, "rows": []}
_KAP_TTL = int(os.environ.get("KAP_TTL", "600"))   # saniye (10 dk)
_SCRAPER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "kap_scraper.js")


def _conv_date(d):
    """'25.06.2026' → '2026-06-25'."""
    d = (d or "").strip()
    if "." in d:
        p = d.split(".")
        if len(p) == 3:
            return f"{p[2]}-{p[1].zfill(2)}-{p[0].zfill(2)}"
    return d


def fetch_kap_disclosures(symbols=None, force=False):
    """
    KAP bildirimlerini Puppeteer scraper (kap_scraper.js) ile çeker.
    Gerçek 'Ara' tıklamasıyla uygulamanın kendi XHR'ını yakalar (WAF'ı aşar).
    Sonuç ~10 dk önbelleğe alınır (scrape ~40sn sürdüğü için). Arşive de yazılır.
    """
    import subprocess
    import json as _json

    now = time.time()
    if not force and (now - _KAP_CACHE["ts"] < _KAP_TTL) and _KAP_CACHE["rows"]:
        rows = _KAP_CACHE["rows"]
    else:
        if not os.path.exists(_SCRAPER):
            return []
        try:
            proc = subprocess.run(
                ["node", _SCRAPER], capture_output=True, text=True,
                timeout=110, cwd=os.path.dirname(_SCRAPER), encoding="utf-8",
            )
            data = _json.loads(proc.stdout or "{}")
            raw = data.get("rows", []) if data.get("ok") else []
        except Exception:
            raw = []
        rows = []
        for r in raw:
            rows.append({
                "symbol": (r.get("symbol") or "").upper(),
                "date": _conv_date(r.get("date")),
                "time": r.get("time", ""),
                "title": r.get("title", ""),
                "source": "KAP",
                "url": r.get("url", ""),
            })
        if rows:
            _KAP_CACHE["rows"] = rows
            _KAP_CACHE["ts"] = now
            ingest(rows)   # arşive yaz (kategorize+duygu otomatik)

    if symbols:
        want = {s.replace(".IS", "").upper() for s in symbols}
        return [r for r in rows if r["symbol"] in want]
    return rows


_HIST_SCRAPER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "kap_history.js")


def _week_ranges(weeks, start_week=0):
    """Bugünden geriye haftalık (from,to) YYYY-MM-DD aralıkları (start_week kadar atla)."""
    from datetime import datetime, timedelta
    today = datetime.now()
    out = []
    for i in range(start_week, start_week + weeks):
        end = today - timedelta(days=i * 7)
        start = today - timedelta(days=(i + 1) * 7 - 1)
        out.append((start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")))
    return out


def fetch_kap_history(weeks=8, progress=None, start_week=0):
    """
    KAP GEÇMİŞ arşivini haftalık aralıklarla (her aralık ayrı process) toplu çeker
    ve arşive kategorize+duygu ile yazar. Geçmiş-tepki motorunu gerçek KAP
    geçmişiyle besler. ~ (weeks × 9sn) sürer.
    """
    import subprocess
    import json as _json

    if not os.path.exists(_HIST_SCRAPER):
        return {"ok": False, "ingested": 0, "fetched": 0}

    seen = set()
    all_rows = []
    range_stats = []
    ranges = _week_ranges(weeks, start_week=start_week)
    for i, (frm, to) in enumerate(ranges):
        # Throttle azaltmak için aralıklar arasına kısa bekleme
        if i > 0:
            time.sleep(4)
        data = {}
        # Boş dönerse 1 kez daha dene (throttle/transient)
        for attempt in range(2):
            try:
                proc = subprocess.run(
                    ["node", _HIST_SCRAPER, frm, to], capture_output=True, text=True,
                    timeout=120, cwd=os.path.dirname(_HIST_SCRAPER), encoding="utf-8",
                )
                data = _json.loads(proc.stdout or "{}")
            except Exception as e:
                data = {"ok": False, "_err": str(e)[:80]}
            if data.get("ok") and data.get("rows"):
                break
            if attempt == 0:
                time.sleep(6)
        if not data.get("ok"):
            range_stats.append({"range": f"{frm}..{to}", "error": data.get("_err", "boş")})
            continue
        batch = []
        for r in (data.get("rows", []) if data.get("ok") else []):
            sym = (r.get("symbol") or "").upper()
            key = (r.get("url") or "") + sym
            if not sym or key in seen:
                continue
            seen.add(key)
            batch.append({
                "symbol": sym, "date": _conv_date(r.get("date")), "time": r.get("time", ""),
                "title": r.get("title", ""), "source": "KAP", "url": r.get("url", ""),
            })
        # Her aralığı HEMEN arşive yaz (timeout'ta kısmi ilerleme korunur)
        ingest(batch)
        all_rows.extend(batch)
        range_stats.append({"range": f"{frm}..{to}", "new": len(batch)})
        if progress:
            progress(frm, to, len(batch))

    return {"ok": True, "fetched": len(all_rows), "ingested": len(all_rows), "ranges": range_stats}


# ─────────────────────────────────────────────────────────────────────────────
#  Örnek arşiv tohumu — geçmiş-tepki görünümünü GERÇEK fiyatla göstermek için.
#  Olaylar 'örnek' kaynaklı; tarihler geçmişe yayılmış. Fiyat tepkisi gerçektir.
# ─────────────────────────────────────────────────────────────────────────────
def purge_demo():
    """Eski 'örnek arşiv' (demo) satırlarını siler — sistem yalnızca gerçek KAP verisiyle çalışır."""
    init_db()
    with _conn() as c:
        c.execute("DELETE FROM disclosures WHERE source='örnek arşiv'")
        return c.total_changes
