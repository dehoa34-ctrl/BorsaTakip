// kap_history.js — TEK tarih aralığı için KAP bildirimlerini çek.
// Kanıtlanmış desen: tek sayfa yükleme + tek "Ara" tıklaması; request
// interception ile giden gerçek isteğin fromDate/toDate'i istenen aralıkla
// değiştirilir (WAF gerçek app isteği görür).
//
// Kullanım: node kap_history.js <fromDate> <toDate>   (YYYY-MM-DD)
// Çıktı: stdout JSON { ok, count, rows:[{symbol,date,time,title,category_kap,url}] }
const puppeteer = require('puppeteer');
const log = (...a) => console.error(...a);

(async () => {
  const from = process.argv[2];
  const to = process.argv[3];
  if (!from || !to) { process.stdout.write(JSON.stringify({ ok: false, error: 'fromDate toDate gerekli' })); return; }

  const browser = await puppeteer.launch({ headless: 'new', args: ['--no-sandbox', '--disable-setuid-sandbox', '--lang=tr-TR'] });
  const page = await browser.newPage();
  await page.setUserAgent('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36');

  await page.setRequestInterception(true);
  page.on('request', (req) => {
    if (req.url().includes('byCriteria') && req.method() === 'POST' && req.postData()) {
      try {
        const j = JSON.parse(req.postData());
        j.fromDate = from; j.toDate = to;
        return req.continue({ postData: JSON.stringify(j) });
      } catch (e) {}
    }
    req.continue();
  });

  const rows = new Map();
  let batch = -1;
  page.on('response', async (res) => {
    if (!res.url().includes('byCriteria')) return;
    try {
      const j = await res.json();
      const arr = Array.isArray(j) ? j : (j.content || j.data || []);
      batch = arr.length;
      for (const d of arr) {
        const sym = (d.stockCodes || d.relatedStocks || '').toString().split(/[,;]/)[0].trim();
        if (!sym) continue;
        const [dt, tm] = (d.publishDate || '').toString().trim().split(' ');
        const subj = (d.subject || d.summary || d.disclosureCategory || '').toString().trim();
        rows.set(String(d.disclosureIndex) + sym, {
          symbol: sym.toUpperCase(), date: dt || '', time: tm || '',
          title: subj || (d.kapTitle || ''),
          category_kap: (d.disclosureCategory || '').toString().trim(),
          url: d.disclosureIndex ? `https://www.kap.org.tr/tr/Bildirim/${d.disclosureIndex}` : '',
        });
      }
    } catch (e) {}
  });

  await page.goto('https://www.kap.org.tr/tr/bildirim-sorgu', { waitUntil: 'domcontentloaded', timeout: 45000 }).catch(e => log('NAV', e.message));
  await new Promise(r => setTimeout(r, 4800));

  async function clickAra() {
    const h = await page.evaluateHandle(() => [...document.querySelectorAll('button,a,span,input')].find(e => /^(ara|sorgula)$/i.test((e.innerText || e.value || '').trim())) || null);
    const el = h.asElement();
    if (el) { try { await el.click(); } catch (e) { await page.evaluate(b => b.click(), el); } return true; }
    return false;
  }

  // 3 denemeye kadar: Ara tıkla, yanıt gelene kadar bekle; gelmezse tekrar dene.
  for (let attempt = 0; attempt < 3 && batch < 0; attempt++) {
    if (attempt > 0) { log(`yeniden deneme ${attempt}`); await new Promise(r => setTimeout(r, 1500)); }
    const ok = await clickAra();
    if (!ok) break;
    for (let k = 0; k < 14 && batch < 0; k++) await new Promise(r => setTimeout(r, 1200));
  }
  await new Promise(r => setTimeout(r, 1200));

  const out = [...rows.values()];
  log(`${from}..${to}: batch=${batch} benzersiz=${out.length}`);
  process.stdout.write(JSON.stringify({ ok: out.length > 0, count: out.length, rows: out }));
  await browser.close();
})();
