/**
 * scan.js — Formasyon Tarama + İdealgo TXT dışa aktarma.
 * Kritere göre BIST evrenini tarar, eşleşenleri listeler, IMKBH'… TXT indirir.
 */

let scanLastMatches = [];
let scanLastCval = '';
let scanInited = false;

// Kriter türüne göre değer seçenekleri
const SCAN_VALUES = {
    teknik: [
        ['Güçlü Al', 'Güçlü Al'], ['Al', 'Al'], ['Nötr', 'Nötr'],
        ['Sat', 'Sat'], ['Güçlü Sat', 'Güçlü Sat'],
    ],
    mum: [
        ['boga', 'Boğa dönüşü (son mum)'], ['ayi', 'Ayı dönüşü (son mum)'],
        ['Yutan', 'Yutan (Engulfing)'], ['Çekiç', 'Çekiç (Hammer)'],
        ['Yıldız', 'Yıldız (Star)'], ['Doji', 'Doji'],
    ],
    rsi: [
        ['asiri_satim', 'Aşırı Satım (RSI ≤ 30)'],
        ['asiri_alim', 'Aşırı Alım (RSI ≥ 70)'],
    ],
    olasilik: [
        ['30', '%30+'], ['40', '%40+'], ['50', '%50+'], ['60', '%60+'],
        ['70', '%70+'], ['80', '%80+'], ['90', '%90+'],
    ],
};

function fillScanValues() {
    const ctype = document.getElementById('scan-ctype').value;
    const sel = document.getElementById('scan-cval');
    sel.innerHTML = SCAN_VALUES[ctype].map(([v, l]) => `<option value="${v}">${l}</option>`).join('');
}

function initScanTab() {
    if (scanInited) return;
    scanInited = true;
    fillScanValues();
    document.getElementById('scan-ctype').addEventListener('change', fillScanValues);
    document.getElementById('scan-run').addEventListener('click', runScan);
    document.getElementById('scan-export').addEventListener('click', exportScan);
}

async function runScan() {
    const ctype = document.getElementById('scan-ctype').value;
    const cval = document.getElementById('scan-cval').value;
    const limit = parseInt(document.getElementById('scan-limit').value || '0', 10);
    const content = document.getElementById('scan-content');
    const exportBtn = document.getElementById('scan-export');
    exportBtn.disabled = true;

    const est = limit === 0 ? '~800 hisse (birkaç dk sürebilir)' : `${limit} hisse`;
    content.innerHTML = `<div class="tech-empty glass-card"><span class="loading-small">Taranıyor: ${est}...</span></div>`;

    // Ön filtreleme parametrelerini topla
    const vol_limit_toggle = document.getElementById('filter-vol-limit-toggle').checked;
    const vol_limit_val = document.getElementById('filter-vol-limit-val').value;
    
    const fdo_toggle = document.getElementById('filter-fdo-toggle').checked;
    const fdo_min = document.getElementById('filter-fdo-min').value;
    const fdo_max = document.getElementById('filter-fdo-max').value;
    
    const roe_toggle = document.getElementById('filter-roe-toggle').checked;
    const roe_min = document.getElementById('filter-roe-min').value;
    const roe_max = document.getElementById('filter-roe-max').value;
    
    const indicators_toggle = document.getElementById('filter-indicators-toggle').checked;
    const mfi_period = document.getElementById('filter-mfi-period').value;
    const obv_trend = document.getElementById('filter-obv-trend').value;
    
    const min_prob_toggle = document.getElementById('filter-min-prob-toggle').checked;
    const min_prob = document.getElementById('filter-min-prob').value;
    
    const karanlik_oda_toggle = document.getElementById('filter-karanlik-oda-toggle').checked;
    const karanlik_oda_val = document.getElementById('filter-karanlik-oda-val').value;
    
    const vol_z_toggle = document.getElementById('filter-vol-z-toggle').checked;
    const vol_z_val = document.getElementById('filter-vol-z-val').value;
    
    const silkeleme_toggle = document.getElementById('filter-silkeleme-toggle').checked;
    const silkeleme_val = document.getElementById('filter-silkeleme-val').value;

    let url = `/api/scan?ctype=${ctype}&cval=${encodeURIComponent(cval)}&limit=${limit}`;
    url += `&vol_limit_toggle=${vol_limit_toggle}&vol_limit_val=${vol_limit_val}`;
    url += `&fdo_toggle=${fdo_toggle}&fdo_min=${fdo_min}&fdo_max=${fdo_max}`;
    url += `&roe_toggle=${roe_toggle}&roe_min=${roe_min}&roe_max=${roe_max}`;
    url += `&indicators_toggle=${indicators_toggle}&mfi_period=${mfi_period}&obv_trend=${obv_trend}`;
    url += `&min_prob_toggle=${min_prob_toggle}&min_prob=${min_prob}`;
    url += `&karanlik_oda_toggle=${karanlik_oda_toggle}&karanlik_oda_val=${karanlik_oda_val}`;
    url += `&vol_z_toggle=${vol_z_toggle}&vol_z_val=${vol_z_val}`;
    url += `&silkeleme_toggle=${silkeleme_toggle}&silkeleme_val=${silkeleme_val}`;

    try {
        const res = await fetch(url);
        const data = await res.json();
        scanLastMatches = data.matches || [];
        scanLastCval = cval;
        renderScanResults(data);
        exportBtn.disabled = scanLastMatches.length === 0;
    } catch (e) {
        content.innerHTML = '<div class="tech-empty glass-card">Tarama başarısız oldu.</div>';
    }
}

function renderScanResults(data) {
    const m = data.matches || [];
    const rows = m.map(x => `
        <tr>
            <td><b>${x.symbol}</b></td>
            <td>${x.price ?? ''}</td>
            <td>${x.label}</td>
            <td class="scan-detail">${x.detail || ''}</td>
        </tr>`).join('');

    document.getElementById('scan-content').innerHTML = `
        <div class="scan-result-head glass-card">
            <div>
                <h2>${data.count} eşleşme</h2>
                <p class="prob-sub">${data.scanned} hisse tarandı (evren: ${data.universe_total}). "İdealgo TXT" ile İdealgo'ya geri yüklenebilir <b>IMKBH'SEMBOL</b> biçiminde dışa aktarılır.</p>
            </div>
            <div class="scan-chips">${m.map(x => `<span class="scan-chip">${x.symbol}</span>`).join('')}</div>
        </div>
        ${m.length ? `
        <div class="tech-table-card glass-card">
            <table class="tech-table">
                <thead><tr><th>Sembol</th><th>Fiyat</th><th>Sonuç</th><th>Detay</th></tr></thead>
                <tbody>${rows}</tbody>
            </table>
        </div>` : '<div class="tech-empty glass-card">Bu kritere uyan hisse bulunamadı.</div>'}
    `;
}

function exportScan() {
    if (!scanLastMatches.length) return;
    // İdealgo formatı: IMKBH'SEMBOL (başka format İdealgo tarafından tanınmaz)
    const lines = scanLastMatches.map(x => `IMKBH'${x.symbol.replace('.IS', '')}`);
    const txt = lines.join('\r\n') + '\r\n';
    const blob = new Blob([txt], { type: 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'idealgo_tarama.txt';
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
}
