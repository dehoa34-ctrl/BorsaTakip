// kap_scraper.js — KAP bildirimlerini gerçek tarayıcı + gerçek "Ara" tıklamasıyla çek.
// Uygulamanın KENDİ XHR'ını yakalar (WAF'ı aşmanın en gerçekçi yolu).
// Başarılıysa stdout'a JSON basar: [{symbol,date,time,title,url}]
//
// Kullanım: node kap_scraper.js   (opsiyonel: HEADFUL=1 görünür mod)
const puppeteer = require('puppeteer');

const log = (...a) => console.error(...a);   // teşhis stderr'e
const TIMEOUT = 50000;

(async () => {
  const browser = await puppeteer.launch({
    headless: process.env.HEADFUL ? false : 'new',
    args: ['--no-sandbox', '--disable-setuid-sandbox', '--lang=tr-TR'],
  });
  const page = await browser.newPage();
  await page.setUserAgent('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36');
  await page.setViewport({ width: 1366, height: 900 });

  let captured = null;
  page.on('response', async (res) => {
    const url = res.url();
    if (!url.includes('/api/') || /menu|footer|about/.test(url)) return;
    const ct = res.headers()['content-type'] || '';
    if (!ct.includes('json')) return;
    try {
      const j = await res.json();
      const arr = Array.isArray(j) ? j : (j.content || j.data || j.disclosureList || j.disclosures || []);
      if (Array.isArray(arr) && arr.length && typeof arr[0] === 'object') {
        const k = Object.keys(arr[0]).join(',').toLowerCase();
        if (/title|disclosure|stockcode|kaptitle|basic|companyname|memberoid/.test(k)) {
          captured = { url, arr };
          log('>>> XHR yakalandı:', url, 'n=', arr.length, 'keys=', Object.keys(arr[0]).join(','));
        }
      }
    } catch (e) {}
  });

  try {
    await page.goto('https://www.kap.org.tr/tr/bildirim-sorgu', { waitUntil: 'domcontentloaded', timeout: TIMEOUT });
  } catch (e) { log('NAV', e.message); }
  await new Promise(r => setTimeout(r, 4500));

  // "Ara" / "Sorgula" submit butonunu bul ve GERÇEK tıkla (Puppeteer click → trusted event)
  const handle = await page.evaluateHandle(() => {
    const all = [...document.querySelectorAll('button, a, [role="button"], input[type="submit"], span')];
    // tam "Ara" ya da "Sorgula"/"Listele"
    return all.find(e => {
      const t = (e.innerText || e.value || '').trim();
      return /^(ara|sorgula|listele)$/i.test(t);
    }) || null;
  });
  const el = handle.asElement();
  if (el) {
    log('Ara butonu bulundu, tıklanıyor...');
    try { await el.click(); } catch (e) { await page.evaluate(b => b.click(), el); }
  } else {
    log('Ara butonu bulunamadı.');
  }

  // XHR + render için bekle
  for (let i = 0; i < 12 && !captured; i++) {
    await new Promise(r => setTimeout(r, 1500));
  }

  let rows = [];
  if (captured) {
    if (captured.arr[0]) log('RAW örnek:', JSON.stringify({
      stockCodes: captured.arr[0].stockCodes, kapTitle: captured.arr[0].kapTitle,
      disclosureCategory: captured.arr[0].disclosureCategory, subject: captured.arr[0].subject,
      summary: captured.arr[0].summary, publishDate: captured.arr[0].publishDate,
    }));
    rows = captured.arr.map(d => {
      const sym = (d.stockCodes || d.relatedStocks || '').toString().split(/[,;]/)[0].trim();
      // Anlamlı başlık: konu/özet/kategori (kategorize+duygu için)
      const subj = (d.subject || d.summary || d.disclosureCategory || '').toString().trim();
      const cat = (d.disclosureCategory || '').toString().trim();
      const pub = (d.publishDate || '').toString().trim();   // "25.06.2026 18:53:37"
      const parts = pub.split(' ');
      const dateStr = parts[0] || '';   // 25.06.2026
      const timeStr = parts[1] || '';
      return {
        symbol: sym,
        company: (d.kapTitle || '').toString().trim(),
        date: dateStr,
        time: timeStr,
        title: subj || cat || (d.kapTitle || ''),
        category_kap: cat,
        url: d.disclosureIndex ? `https://www.kap.org.tr/tr/Bildirim/${d.disclosureIndex}` : '',
      };
    }).filter(r => r.symbol);
  } else {
    // DOM fallback: render edilmiş bildirim satırlarını oku
    rows = await page.evaluate(() => {
      const out = [];
      const rowsEl = document.querySelectorAll('a[href*="/Bildirim/"], [class*="notification"], table tbody tr');
      rowsEl.forEach(e => {
        const t = (e.innerText || '').replace(/\s+/g, ' ').trim();
        if (t && t.length > 8) out.push({ raw: t, url: e.href || '' });
      });
      return out.slice(0, 60);
    });
  }

  log('Sonuç satır:', rows.length, '| kaynak:', captured ? 'XHR' : 'DOM');
  process.stdout.write(JSON.stringify({ ok: rows.length > 0, source: captured ? 'xhr' : 'dom', rows }, null, 2));
  await browser.close();
})();
