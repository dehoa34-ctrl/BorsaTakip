"""
news_engine.py — Haber/KAP zekâsı: kategorize + Türkçe duygu + geçmiş fiyat tepkisi.

Felsefe (kullanıcının isteği):
    "B hissesine KAP'ta bir haber düştü; aynı tip haber geçmişte geldiğinde hisse
     ne yaptı?" → Bunu bir İSTATİSTİK olarak veriyoruz (sonraki 1/3/5 günde ortalama
     % hareket, isabet oranı, örnek sayısı). Tek bir habere 'al/sat' demek yerine
     geçmiş davranıştan bir OLASILIK üretiyoruz.

Veri kaynağı bağımsızdır: kategorize/duygu/tepki motoru, başlık + tarih içeren
HERHANGİ bir bildirim listesiyle çalışır (RSS, yfinance, ileride KAP scraper).
"""

import re
import unicodedata
import pandas as pd


# ─────────────────────────────────────────────────────────────────────────────
#  Metin normalleştirme (TR karakter + küçük harf)
# ─────────────────────────────────────────────────────────────────────────────
def _norm(text):
    if not text:
        return ""
    t = text.lower()
    t = (t.replace("ı", "i").replace("ş", "s").replace("ğ", "g")
           .replace("ü", "u").replace("ö", "o").replace("ç", "c"))
    t = unicodedata.normalize("NFKD", t)
    t = "".join(c for c in t if not unicodedata.combining(c))
    return t


# ─────────────────────────────────────────────────────────────────────────────
#  KAP-benzeri kategoriler — (kategori, varsayılan eğilim, anahtar kelimeler)
#  eğilim: +1 pozitif, 0 nötr, -1 negatif (kısa vadeli tipik etki)
# ─────────────────────────────────────────────────────────────────────────────
CATEGORIES = [
    ("Bedelsiz Sermaye Artırımı", +1, ["bedelsiz"]),
    ("Bedelli Sermaye Artırımı", -1, ["bedelli"]),
    ("Sermaye Artırımı", 0, ["sermaye artirimi", "sermaye art"]),
    ("Temettü / Kâr Payı", +1, ["temettu", "kar payi", "kâr payi", "kar dagitim"]),
    ("Pay Geri Alım", +1, ["geri alim", "geri alin", "geri alinmas", "geri alinan", "pay geri", "geri alim programi"]),
    # Negatif yüksek-öncelikli (pozitif operasyonel kategorilerden ÖNCE eşleşsin)
    ("Geri Çağırma / Üretim Durdurma", -1, ["geri cagir", "uretim durdur", "faaliyet durdur", "uretime ara"]),
    ("Hukuki / Dava / Ceza", -1, ["dava", "ceza", "sorusturma", "tazminat", "icra", "haciz", "konkordato", "iflas", "temerrut", "fesih", "el konuldu", "kayyum", "tedbir"]),
    ("İhale / Sözleşme / Sipariş", +1, ["ihale", "sozlesme", "siparis", "anlasma imzal", "yeni is", "is ilisk"]),
    ("Ortaklık / İş Birliği", +1, ["is birligi", "isbirligi", "stratejik ortaklik", "ortak girisim", "konsorsiyum"]),
    ("Birleşme / Devralma", +1, ["birlesme", "devral", "satin alma", "satin aldi", "iktisap", "hisse devri", "pay devri"]),
    ("Yatırım / Kapasite / Tesis", +1, ["yatirim", "kapasite", "tesis", "fabrika", "uretim hatti", "ges ", "santral", "yatirim tesvik"]),
    ("Ürün / Ruhsat / Lisans", +1, ["ruhsat", "lisans", "patent", "tip onayi", "ce belge", "sertifika", "yeni urun", "izin aldi"]),
    ("Halka Arz", +1, ["halka arz", "borsada islem gormeye basla", "ek satis", "fiyat tespit"]),
    ("Kredi Notu / Derecelendirme", 0, ["kredi notu", "derecelendirme", "rating", "not teyit", "gorunum"]),
    ("Analist / Hedef Fiyat", 0, ["hedef fiyat", "tavsiye", "yukseltti", "dusurdu", "model portfoy", "arastirma"]),
    ("Finansal Tablo / Bilanço", 0, ["finansal rapor", "finansal tablo", "bilanco", "faaliyet raporu", "net donem kari", "net donem zarari", "ceyrek sonuc"]),
    ("Pay Bazında Devre Kesici", 0, ["devre kesici", "bistech"]),
    ("Genel Kurul", 0, ["genel kurul"]),
    ("Yönetim / Atama / İstifa", 0, ["atama", "istifa", "yonetim kurulu uyesi", "genel mudur", "murahhas"]),
    ("Esas Sözleşme", 0, ["esas sozlesme"]),
    ("Bağımsız Denetim", 0, ["bagimsiz denetim", "denetim kurulus"]),
    ("Kredi / Tahvil / Bono", 0, ["tahvil", "bono", "kredi", "ihrac", "finansman bonosu", "kira sertifika"]),
    ("Sermaye Piyasası Aracı İşlemi", 0, ["pay disinda sermaye piyasasi araci", "geri alim islem"]),
    ("Özel Durum Açıklaması", 0, ["ozel durum"]),
]

# ─────────────────────────────────────────────────────────────────────────────
#  Türkçe finansal duygu sözlüğü (kelime → ağırlık)
# ─────────────────────────────────────────────────────────────────────────────
POSITIVE = {
    # kârlılık / büyüme
    "rekor": 2, "rekor kar": 3, "rekor ciro": 2, "kar artisi": 2, "karlilik": 1,
    "kar marji": 1, "net kar": 1, "buyume": 1, "ciro artisi": 2, "favok artisi": 2,
    "guclu finansal": 2, "beklenti uzeri": 2, "tahmin uzeri": 2,
    # ticari / operasyonel
    "ihracat": 1, "ihracat artti": 2, "yeni siparis": 2, "yeni musteri": 1,
    "ihale kazan": 3, "ihaleyi kazan": 3, "sozlesme imzal": 2, "sozlesme kazan": 2,
    "anlasma": 1, "stratejik ortaklik": 2, "is birligi": 1, "yeni pazar": 2,
    "yeni urun": 1, "lansman": 1, "kapasite artis": 2, "yeni tesis": 2, "fabrika acti": 2,
    # sermaye / temettu
    "bedelsiz": 2, "temettu": 2, "temettu artir": 3, "kar payi": 2, "kar dagitim": 2,
    "geri alim": 2, "geri alin": 2, "geri alim programi": 3, "yatirim": 1,
    "halka arz talep": 2, "tahsisli": 1,
    # izin / onay / kalite
    "tesvik": 1, "tesvik belgesi": 2, "izin aldi": 2, "ruhsat": 1, "ruhsat aldi": 2,
    "onayland": 1, "lisans aldi": 2, "patent": 1, "belge aldi": 1, "sertifika aldi": 1,
    "satin aldi": 1, "devraldi": 1, "iktisap etti": 1,
    # finansal saglik / analist
    "borc kapatti": 2, "borc azaltti": 1, "kredi notu yukse": 2, "not artir": 2,
    "hedefi yukseltti": 2, "hedef fiyat yukse": 2, "tavsiye al": 2, "primli": 1,
    "guclu": 1, "olumlu": 1, "artti": 1, "yukseldi": 1, "kazandi": 2, "odul": 1,
    "basari": 1, "imzalandi": 1, "tamamlandi": 1, "gecti": 1,
}
NEGATIVE = {
    # zarar / kriz
    "zarar": 2, "zarar acikla": 3, "kar uyarisi": 3, "net zarar": 2, "iflas": 3,
    "iflas erteleme": 3, "konkordato": 3, "temerrut": 2, "odeme guclugu": 2,
    "nakit sikinti": 2, "likidite": 1,
    # hukuki / ceza
    "dava": 1, "dava acildi": 2, "ceza": 2, "ceza kesildi": 2, "vergi cezasi": 2,
    "idari para cezasi": 2, "sorusturma": 2, "sorusturma acildi": 2, "el konuldu": 3,
    "kayyum": 3, "haciz": 2, "icra": 1, "icra takibi": 2, "rehin": 1, "tazminat": 1,
    # operasyonel sorun
    "grev": 1, "lokavt": 1, "hasar": 1, "yangin": 2, "kaza": 1, "uretim durdu": 2,
    "uretim durdur": 2, "faaliyet durdu": 2, "tedarik sorun": 2, "arz sorun": 1,
    "geri cagir": 2, "kapatma": 2, "lisans iptal": 3, "ruhsat iptal": 3,
    # sermaye / temettu olumsuz
    "sermaye azalt": 2, "bedelli": 1, "temettu iptal": 2, "temettu erteleme": 2,
    "halka arz iptal": 2, "kredi notu dusur": 2, "not indir": 2,
    # analist / fiyat
    "fesih": 2, "iptal": 1, "gecikme": 1, "hedefi dusurdu": 2, "hedef fiyat dusur": 2,
    "tavsiye sat": 2, "satis baskisi": 1, "geriledi": 1, "dustu": 1, "azaldi": 1,
    "kuculdu": 1, "daraldi": 1, "uyari": 1, "risk": 1, "olumsuz": 2, "ertelendi": 1,
}


# ─────────────────────────────────────────────────────────────────────────────
#  Kategorize + duygu
# ─────────────────────────────────────────────────────────────────────────────
def categorize(title):
    n = _norm(title)
    for cat, bias, kws in CATEGORIES:
        if any(k in n for k in kws):
            return cat, bias
    return "Genel Bilgi", 0


def sentiment(title, category_bias=0):
    n = _norm(title)
    score = category_bias
    hits = []
    for w, wt in POSITIVE.items():
        if w in n:
            score += wt; hits.append("+" + w)
    for w, wt in NEGATIVE.items():
        if w in n:
            score -= wt; hits.append("-" + w)
    if score >= 2:
        label = "Pozitif"
    elif score <= -2:
        label = "Negatif"
    elif score == 1:
        label = "Hafif Pozitif"
    elif score == -1:
        label = "Hafif Negatif"
    else:
        label = "Nötr"
    return {"label": label, "score": score, "signals": hits[:6]}


def classify_item(title):
    """Tek bir başlık için kategori + duygu."""
    cat, bias = categorize(title)
    sent = sentiment(title, bias)
    return {"category": cat, "category_bias": bias, "sentiment": sent}


# ─────────────────────────────────────────────────────────────────────────────
#  Geçmiş fiyat tepkisi (yfinance günlük veri üzerinde)
# ─────────────────────────────────────────────────────────────────────────────
def price_reaction(price_df, event_date, horizons=(1, 3, 5)):
    """
    Bir olay tarihinden sonra fiyat ne yaptı? event_date'teki (veya sonraki ilk
    işlem günü) kapanışa göre +1/+3/+5 işlem günü getirisi (%).
    price_df: yfinance history (DatetimeIndex, 'Close').
    """
    if price_df is None or price_df.empty:
        return None
    idx = price_df.index
    ed = pd.Timestamp(event_date)
    if idx.tz is not None:
        ed = ed.tz_localize(idx.tz) if ed.tzinfo is None else ed.tz_convert(idx.tz)
    # event_date'te veya sonrasındaki ilk işlem gününü bul
    pos = idx.searchsorted(ed)
    if pos >= len(idx):
        return None
    base = float(price_df["Close"].iloc[pos])
    out = {"base_date": str(idx[pos].date()), "base_price": round(base, 2)}
    for h in horizons:
        j = pos + h
        if j < len(idx) and base:
            out[f"r{h}"] = round((float(price_df["Close"].iloc[j]) - base) / base * 100, 2)
        else:
            out[f"r{h}"] = None
    return out


def analyze_category_reaction(price_df, events, horizons=(1, 3, 5)):
    """
    Aynı kategorideki geçmiş olayların ortalama fiyat tepkisi.
    events: [{'date': 'YYYY-MM-DD', 'title': ...}, ...]
    Dönüş: her ufuk için ortalama %, isabet oranı (pozitif kapanış), örnek sayısı.
    """
    per_h = {h: [] for h in horizons}
    samples = []
    for ev in events:
        rc = price_reaction(price_df, ev["date"], horizons)
        if not rc:
            continue
        row = {"date": ev.get("date"), "title": ev.get("title", ""), **{f"r{h}": rc.get(f"r{h}") for h in horizons}}
        samples.append(row)
        for h in horizons:
            v = rc.get(f"r{h}")
            if v is not None:
                per_h[h].append(v)

    stats = {}
    for h in horizons:
        vals = per_h[h]
        if vals:
            wins = sum(1 for v in vals if v > 0)
            stats[f"r{h}"] = {
                "avg": round(sum(vals) / len(vals), 2),
                "win_rate": round(100 * wins / len(vals), 1),
                "n": len(vals),
            }
        else:
            stats[f"r{h}"] = {"avg": None, "win_rate": None, "n": 0}
    return {"stats": stats, "samples": samples}
