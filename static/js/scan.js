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
        ['70', '%70+'], ['80', '%80+'], ['60', '%60+'], ['90', '%90+'],
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

    const est = limit === 0 ? '~550 hisse (1-2 dk sürebilir)' : `${limit} hisse`;
    content.innerHTML = `<div class="tech-empty glass-card"><span class="loading-small">Taranıyor: ${est}...</span></div>`;

    try {
        const res = await fetch(`/api/scan?ctype=${ctype}&cval=${encodeURIComponent(cval)}&limit=${limit}`);
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
                <p class="prob-sub">${data.scanned} hisse tarandı (evren: ${data.universe_total}). Aşağıdaki listeyi İdealgo'ya geri yüklenebilir TXT olarak indirebilirsin.</p>
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
    // Eşleşen sembolleri doğrudan biçimlet (yeniden taramaya gerek yok)
    const syms = scanLastMatches.map(x => x.symbol).join(',');
    const cval = scanLastCval || 'Güçlü Al';
    const ctype = document.getElementById('scan-ctype').value;
    const url = `/api/scan/export?symbols=${encodeURIComponent(syms)}&cval=${encodeURIComponent(cval)}&ctype=${encodeURIComponent(ctype)}`;
    // İndirmeyi tetikle
    const a = document.createElement('a');
    a.href = url;
    a.download = 'idealgo_tarama.txt';
    document.body.appendChild(a);
    a.click();
    a.remove();
}
