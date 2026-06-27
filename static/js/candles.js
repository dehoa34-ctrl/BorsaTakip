/**
 * candles.js — Mum (candlestick) formasyonları tarama görünümü.
 * Tek bir sembol için boğa/ayı/kararsız price-action desenlerini listeler.
 */

let cndPeriod = '3mo';
let cndInterval = '1d';
let cndSymbol = null;

const CND_COLORS = { 'Boğa': '#22c55e', 'Ayı': '#ef4444', 'Kararsız': '#94a3b8' };

function cndTypeClass(t) {
    if (t === 'Boğa') return 'tag-buy';
    if (t === 'Ayı') return 'tag-sell';
    return 'tag-neutral';
}
function cndIcon(t) {
    if (t === 'Boğa') return '▲';
    if (t === 'Ayı') return '▼';
    return '◆';
}

document.addEventListener('DOMContentLoaded', () => {
    const tf = document.getElementById('cnd-timeframes');
    if (tf) {
        tf.querySelectorAll('button').forEach(btn => {
            btn.addEventListener('click', () => {
                tf.querySelectorAll('button').forEach(b => b.classList.remove('active'));
                btn.classList.add('active');
                cndPeriod = btn.dataset.period;
                cndInterval = btn.dataset.interval;
                if (cndSymbol) loadCandles(cndSymbol);
            });
        });
    }
});

async function loadCandles(symbol) {
    if (!symbol) return;
    cndSymbol = symbol;
    document.getElementById('cnd-symbol').innerText = symbol;
    const content = document.getElementById('cnd-content');
    content.innerHTML = '<div class="tech-empty glass-card"><span class="loading-small">Mum formasyonları taranıyor...</span></div>';

    try {
        const res = await fetch(`/api/candles/${symbol}?period=${cndPeriod}&interval=${cndInterval}`);
        if (!res.ok) throw new Error('Veri alınamadı');
        const data = await res.json();
        if (!data.ok) {
            content.innerHTML = `<div class="tech-empty glass-card">${data.message || 'Yetersiz veri.'}</div>`;
            return;
        }
        renderCandles(data);
    } catch (err) {
        console.error(err);
        content.innerHTML = `<div class="tech-empty glass-card">Tarama yüklenemedi: ${symbol}.</div>`;
    }
}

function patternCard(p, big) {
    const color = CND_COLORS[p.type] || '#94a3b8';
    return `
    <div class="pattern-card glass-card ${big ? 'big' : ''}" style="border-left:4px solid ${color}">
        <div class="pc-head">
            <span class="pc-name">${cndIcon(p.type)} ${p.name}</span>
            <span class="tag ${cndTypeClass(p.type)}">${p.type}</span>
        </div>
        <div class="pc-meta">
            <span class="pc-date">${p.date}</span>
            <span class="pc-rel">Güvenilirlik: ${p.reliability}</span>
        </div>
        <p class="pc-desc">${p.desc}</p>
    </div>`;
}

function renderCandles(data) {
    document.getElementById('cnd-symbol').innerText = data.symbol;
    document.getElementById('cnd-price').innerText = (data.price || 0).toLocaleString();

    const bias = data.summary.bias;
    const bEl = document.getElementById('cnd-bias');
    const bc = CND_COLORS[bias] || '#94a3b8';
    bEl.innerText = `${cndIcon(bias)} ${bias} eğilimi`;
    bEl.style.cssText = `background:${bc}1a;color:${bc};border:1px solid ${bc}55;padding:4px 12px;border-radius:8px;font-weight:600;font-size:0.85rem;`;

    const s = data.summary;
    const latestHtml = data.latest.length
        ? data.latest.map(p => patternCard(p, true)).join('')
        : `<div class="tech-empty glass-card">Son mumda belirgin bir formasyon yok. Aşağıda son ${cndPeriod} içindeki formasyonlar listeleniyor.</div>`;

    const historyHtml = data.history.length
        ? data.history.map(p => patternCard(p, false)).join('')
        : '<div class="tech-empty glass-card">Bu dönemde formasyon bulunamadı.</div>';

    document.getElementById('cnd-content').innerHTML = `
        <div class="cnd-summary glass-card">
            <div class="cs-item"><span class="cs-num" style="color:#22c55e">${s.bullish}</span><span>Boğa</span></div>
            <div class="cs-item"><span class="cs-num" style="color:#ef4444">${s.bearish}</span><span>Ayı</span></div>
            <div class="cs-item"><span class="cs-num" style="color:#94a3b8">${s.neutral}</span><span>Kararsız</span></div>
            <div class="cs-note">Son dönemdeki formasyon dağılımı. Bunlar tek başına emir değil; teyit için trend ve hacimle birlikte değerlendirin.</div>
        </div>

        <h3 class="cnd-section-title">🔥 Son Mumdaki Formasyon</h3>
        <div class="pattern-grid">${latestHtml}</div>

        <h3 class="cnd-section-title">📜 Geçmiş Formasyonlar (yeniden eskiye)</h3>
        <div class="pattern-grid">${historyHtml}</div>
    `;
}
