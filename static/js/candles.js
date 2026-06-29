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

function valBadge(v) {
    if (!v) return '';
    const strong = v.score >= 50, weak = v.score < 20;
    const c = strong ? '#22c55e' : (weak ? '#ef4444' : '#f59e0b');
    const icon = strong ? '✅' : (weak ? '⚠️' : '◐');
    return `<span class="val-badge" style="background:${c}1a;color:${c};border:1px solid ${c}55">${icon} ${v.verdict}</span>`;
}

function valDetail(v) {
    if (!v) return '';
    const volC = v.volume_ok ? '#22c55e' : '#ef4444';
    let html = `<div class="pc-val">
        <span style="color:${volC}">Hacim ×${v.vol_ratio} ${v.volume_ok ? '✓ (≥1.5)' : '✗ (zayıf)'}</span>
        <span style="color:${v.trend_ok ? '#22c55e' : '#ef4444'}">Konum ${v.trend_ok ? '✓' : '✗'} (5g %${v.prior_ret5})</span>`;
    if (v.poc_signal) html += `<span class="pc-poc">📊 ${v.poc_signal}</span>`;
    html += `</div>`;
    return html;
}

function patternCard(p, big) {
    const color = CND_COLORS[p.type] || '#94a3b8';
    const v = p.validation;
    return `
    <div class="pattern-card glass-card ${big ? 'big' : ''}" style="border-left:4px solid ${color}">
        <div class="pc-head">
            <span class="pc-name">${cndIcon(p.type)} ${p.name}</span>
            <span class="tag ${cndTypeClass(p.type)}">${p.type}</span>
        </div>
        <div class="pc-meta">
            <span class="pc-date">${p.date}</span>
            ${valBadge(v)}
        </div>
        ${valDetail(v)}
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
            <div class="cs-item"><span class="cs-num" style="color:#3b82f6">${s.validated ?? 0}</span><span>✅ Doğrulanmış</span></div>
            <div class="cs-note"><b>Doğrulama:</b> formasyonlar hacim (≥1.5× ort.), trend/konum ve POC ile süzülür. Hacimsiz formasyonlar "Zayıf/Şüpheli" işaretlenir — robot tuzaklarını ayıklamak için. Sadece <b>✅ Doğrulandı</b> olanlar güvenilirdir.</div>
        </div>

        <h3 class="cnd-section-title">🔥 Son Mumdaki Formasyon</h3>
        <div class="pattern-grid">${latestHtml}</div>

        <h3 class="cnd-section-title">📜 Geçmiş Formasyonlar (yeniden eskiye)</h3>
        <div class="pattern-grid">${historyHtml}</div>
    `;
}
