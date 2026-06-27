/**
 * technical.js — investing.com tarzı "Konsensüs + Olasılık" teknik analiz görünümü.
 *
 * Tek bir AL/SAT yerine ~24 göstergenin oy birliğini kadranlar, tablolar ve
 * bir "Yükseliş Olasılığı %" çubuğu olarak gösterir.
 */

let techPeriod = '6mo';
let techInterval = '1d';
let techSymbol = null;

// Eylem etiketi → renk
const ACTION_COLORS = {
    'Güçlü Al': '#16a34a',
    'Al': '#22c55e',
    'Nötr': '#94a3b8',
    'Sat': '#f97316',
    'Güçlü Sat': '#ef4444',
    'Aşırı Alış': '#ef4444',
    'Aşırı Satış': '#22c55e',
    'Yüksek Hareketli': '#94a3b8',
    'Düşük Hareketli': '#94a3b8',
};

function techActionClass(action) {
    if (action === 'Al' || action === 'Güçlü Al' || action === 'Aşırı Satış') return 'tag-buy';
    if (action === 'Sat' || action === 'Güçlü Sat' || action === 'Aşırı Alış') return 'tag-sell';
    return 'tag-neutral';
}

/* ── Timeframe butonları ──────────────────────────────────────────────── */
document.addEventListener('DOMContentLoaded', () => {
    const tf = document.getElementById('tech-timeframes');
    if (tf) {
        tf.querySelectorAll('button').forEach(btn => {
            btn.addEventListener('click', () => {
                tf.querySelectorAll('button').forEach(b => b.classList.remove('active'));
                btn.classList.add('active');
                techPeriod = btn.dataset.period;
                techInterval = btn.dataset.interval;
                if (techSymbol) loadTechnical(techSymbol);
            });
        });
    }
});

/* ── Veri çek ─────────────────────────────────────────────────────────── */
async function loadTechnical(symbol) {
    if (!symbol) return;
    techSymbol = symbol;
    const content = document.getElementById('tech-content');
    document.getElementById('tech-symbol').innerText = symbol;
    content.innerHTML = '<div class="tech-empty glass-card"><span class="loading-small">Konsensüs hesaplanıyor...</span></div>';

    try {
        const res = await fetch(`/api/technical/${symbol}?period=${techPeriod}&interval=${techInterval}`);
        if (!res.ok) throw new Error('Veri alınamadı');
        const data = await res.json();
        if (!data.ok) {
            content.innerHTML = `<div class="tech-empty glass-card">${data.message || 'Yetersiz veri.'}</div>`;
            return;
        }
        renderTechnical(data);
        loadFlow(symbol);   // Hacim & Likidite göstergelerini de getir
    } catch (err) {
        console.error(err);
        content.innerHTML = `<div class="tech-empty glass-card">Analiz yüklenemedi: ${symbol}. Geçerli bir sembol deneyin.</div>`;
    }
}

/* ── Hacim & Likidite (Akıllı Para) ───────────────────────────────────── */
async function loadFlow(symbol) {
    const host = document.getElementById('flow-section');
    if (!host) return;
    host.innerHTML = '<div class="tech-empty glass-card"><span class="loading-small">Hacim/akıllı para hesaplanıyor...</span></div>';
    try {
        const res = await fetch(`/api/flow/${symbol}?period=${techPeriod}&interval=${techInterval}`);
        const d = await res.json();
        // Bayat yanıt koruması: bu sırada başka sembole geçildiyse render etme
        if (symbol !== techSymbol) return;
        if (!d.ok) { host.innerHTML = ''; return; }
        renderFlow(d, host);
    } catch (e) { host.innerHTML = ''; }
}

function flowActClass(a) {
    if (/Giriş|Akümülasyon|Kurumsal Alım|Üstü/.test(a)) return 'tag-buy';
    if (/Çıkış|Dağıtım|Kurumsal Satım|Altı|Aşırı Alış/.test(a)) return 'tag-sell';
    return 'tag-neutral';
}

function renderFlow(d, host) {
    const mf = d.money_flow;
    const mfColor = mf.score > 0.35 ? '#22c55e' : (mf.score < -0.35 ? '#ef4444' : '#94a3b8');
    const rows = d.items.map(i => `
        <tr><td>${i.name}</td><td class="num">${i.value ?? '-'}</td>
        <td class="act"><span class="tag ${flowActClass(i.action)}">${i.action}</span></td>
        <td class="scan-detail">${i.desc}</td></tr>`).join('');

    let warn = '';
    if (d.trap) {
        warn += `<div class="flow-warn trap"><b>⚠️ ${d.trap.type} (Risk: ${d.trap.risk})</b><br>${d.trap.note}</div>`;
    }
    if (d.divergence) {
        const good = /Gizli Alım/.test(d.divergence.type);
        warn += `<div class="flow-warn ${good ? 'pos' : 'neg'}"><b>${good ? '🟢' : '🔴'} ${d.divergence.type}</b><br>${d.divergence.note}</div>`;
    }

    host.innerHTML = `
        <h3 class="cnd-section-title">💧 Hacim ve Likidite Göstergeleri (Akıllı Para)</h3>
        <div class="flow-banner glass-card" style="border-left:4px solid ${mfColor}">
            <div><span class="flow-label" style="color:${mfColor}">${mf.label}</span>
            <span class="prob-sub">PGC verisi yerine para akışını matematiksel simüle eder (MFI·OBV·CMF·POC). Klasik fiyat indikatörünün kandırdığı yeri yakalar.</span></div>
            <div class="flow-score" style="color:${mfColor}">CMF ${mf.cmf} · MFI ${mf.mfi}</div>
        </div>
        ${warn}
        <div class="tech-table-card glass-card">
            <table class="tech-table">
                <thead><tr><th>Gösterge</th><th class="num">Değer</th><th class="act">Yorum</th><th>Açıklama</th></tr></thead>
                <tbody>${rows}</tbody>
            </table>
        </div>`;
}

/* ── SVG yarım daire kadran ───────────────────────────────────────────── */
function gaugeSVG(score, label) {
    // score: -1 (Güçlü Sat) .. +1 (Güçlü Al)
    const cx = 110, cy = 110, r = 90;
    // İğne açısı: 180° (sol) → 0° (sağ)
    const t = (score + 1) / 2;                 // 0..1
    const angle = Math.PI * (1 - t);           // PI (sol) → 0 (sağ)
    const nx = cx + (r - 18) * Math.cos(angle);
    const ny = cy - (r - 18) * Math.sin(angle);

    // 5 renkli yay segmenti
    const segs = [
        { from: 180, to: 144, color: '#ef4444' },  // Güçlü Sat
        { from: 144, to: 108, color: '#f97316' },  // Sat
        { from: 108, to: 72,  color: '#64748b' },   // Nötr
        { from: 72,  to: 36,  color: '#22c55e' },   // Al
        { from: 36,  to: 0,   color: '#16a34a' },   // Güçlü Al
    ];
    const arc = (a1, a2, color) => {
        const p = (deg) => {
            const rad = Math.PI * deg / 180;
            return [cx + r * Math.cos(rad), cy - r * Math.sin(rad)];
        };
        const [x1, y1] = p(a1), [x2, y2] = p(a2);
        return `<path d="M ${x1} ${y1} A ${r} ${r} 0 0 1 ${x2} ${y2}"
                fill="none" stroke="${color}" stroke-width="16" stroke-linecap="butt"/>`;
    };
    const color = ACTION_COLORS[label] || '#94a3b8';

    return `
    <svg viewBox="0 0 220 150" class="gauge-svg">
        ${segs.map(s => arc(s.from, s.to, s.color)).join('')}
        <text x="14" y="138" class="gauge-edge gauge-sell">Güçlü Sat</text>
        <text x="206" y="138" class="gauge-edge gauge-buy" text-anchor="end">Güçlü Al</text>
        <line x1="${cx}" y1="${cy}" x2="${nx}" y2="${ny}" stroke="${color}" stroke-width="4" stroke-linecap="round"/>
        <circle cx="${cx}" cy="${cy}" r="7" fill="${color}"/>
    </svg>`;
}

function gaugeCard(title, group) {
    const color = ACTION_COLORS[group.action] || '#94a3b8';
    return `
    <div class="gauge-card glass-card">
        <div class="gauge-title">${title}</div>
        ${gaugeSVG(group.score, group.action)}
        <div class="gauge-label" style="background:${color}1a;color:${color};border:1px solid ${color}55;">${group.action}</div>
        <div class="gauge-counts">
            <span class="gc buy">Al: ${group.buy}</span>
            <span class="gc neutral">Nötr: ${group.neutral}</span>
            <span class="gc sell">Sat: ${group.sell}</span>
        </div>
    </div>`;
}

/* ── Olasılık çubuğu ──────────────────────────────────────────────────── */
function probabilityBlock(s) {
    const bull = s.bull_prob, bear = s.bear_prob;
    return `
    <div class="prob-card glass-card">
        <div class="prob-head">
            <div>
                <h3>Konsensüs Olasılığı</h3>
                <p class="prob-sub">${s.total_indicators} bağımsız göstergenin oy birliğinden hesaplandı —
                tek bir indikatör manipüle edilse bile sonuç çok az değişir.</p>
            </div>
            <div class="prob-pct" style="color:${bull >= 50 ? '#22c55e' : '#ef4444'}">
                ${bull >= 50 ? '▲' : '▼'} %${bull >= 50 ? bull : bear}
                <small>${bull >= 50 ? 'Yükseliş' : 'Düşüş'} olasılığı</small>
            </div>
        </div>
        <div class="prob-bar">
            <div class="prob-fill-bull" style="width:${bull}%">${bull > 12 ? '%' + bull + ' Al' : ''}</div>
            <div class="prob-fill-bear" style="width:${bear}%">${bear > 12 ? '%' + bear + ' Sat' : ''}</div>
        </div>
    </div>`;
}

/* ── Osilatör tablosu ─────────────────────────────────────────────────── */
function oscTable(osc) {
    const rows = osc.items.map(i => `
        <tr>
            <td>${i.name}</td>
            <td class="num">${i.value}</td>
            <td class="act"><span class="tag ${techActionClass(i.action)}">${i.action}</span></td>
        </tr>`).join('');
    return `
    <div class="tech-table-card glass-card">
        <div class="tech-table-head">
            <h3>Teknik Göstergeler</h3>
            <span class="tt-summary tag ${techActionClass(osc.action)}">${osc.action}</span>
        </div>
        <table class="tech-table">
            <thead><tr><th>İsim</th><th class="num">Değer</th><th class="act">Hareket</th></tr></thead>
            <tbody>${rows}</tbody>
        </table>
        <div class="tt-foot">Al: ${osc.buy} &nbsp;·&nbsp; Nötr: ${osc.neutral} &nbsp;·&nbsp; Sat: ${osc.sell}</div>
    </div>`;
}

/* ── Hareketli ortalama tablosu ───────────────────────────────────────── */
function maTable(ma) {
    const rows = ma.items.map(i => `
        <tr>
            <td>${i.name}</td>
            <td class="num">${i.simple.value}</td>
            <td class="act"><span class="tag ${techActionClass(i.simple.action)}">${i.simple.action}</span></td>
            <td class="num">${i.exp.value}</td>
            <td class="act"><span class="tag ${techActionClass(i.exp.action)}">${i.exp.action}</span></td>
        </tr>`).join('');
    return `
    <div class="tech-table-card glass-card">
        <div class="tech-table-head">
            <h3>Hareketli Ortalamalar</h3>
            <span class="tt-summary tag ${techActionClass(ma.action)}">${ma.action}</span>
        </div>
        <table class="tech-table">
            <thead><tr><th>İsim</th><th class="num">Basit</th><th class="act"></th><th class="num">Üssel</th><th class="act"></th></tr></thead>
            <tbody>${rows}</tbody>
        </table>
        <div class="tt-foot">Al: ${ma.buy} &nbsp;·&nbsp; Nötr: ${ma.neutral} &nbsp;·&nbsp; Sat: ${ma.sell}</div>
    </div>`;
}

/* ── Pivot tablosu ────────────────────────────────────────────────────── */
function pivotTable(pivots) {
    const cell = v => (v === null || v === undefined) ? '<td class="num muted">-</td>' : `<td class="num">${v}</td>`;
    const rows = pivots.map(p => `
        <tr>
            <td>${p.name}</td>
            ${cell(p.s3)}${cell(p.s2)}${cell(p.s1)}
            <td class="num pivot-col">${p.pivot}</td>
            ${cell(p.r1)}${cell(p.r2)}${cell(p.r3)}
        </tr>`).join('');
    return `
    <div class="tech-table-card glass-card wide">
        <div class="tech-table-head"><h3>Pivot Noktaları</h3></div>
        <table class="tech-table pivot-table">
            <thead><tr>
                <th>İsim</th><th class="num">3. Destek</th><th class="num">2. Destek</th><th class="num">1. Destek</th>
                <th class="num pivot-col">Pivot</th><th class="num">1. Direnç</th><th class="num">2. Direnç</th><th class="num">3. Direnç</th>
            </tr></thead>
            <tbody>${rows}</tbody>
        </table>
    </div>`;
}

/* ── Ana render ───────────────────────────────────────────────────────── */
function renderTechnical(data) {
    // Başlık fiyat/değişim
    document.getElementById('tech-symbol').innerText = data.symbol;
    document.getElementById('tech-price').innerText = (data.price || 0).toLocaleString();
    const ch = document.getElementById('tech-change');
    const cp = data.change_percent || 0;
    ch.innerText = `${data.change > 0 ? '+' : ''}${data.change} (${cp}%)`;
    ch.className = `price-change ${cp >= 0 ? 'positive' : 'negative'}`;

    const content = document.getElementById('tech-content');
    content.innerHTML = `
        ${probabilityBlock(data.summary)}
        <div class="gauge-row">
            ${gaugeCard('Teknik Göstergeler', data.oscillators)}
            ${gaugeCard('Özet', data.summary)}
            ${gaugeCard('Hareketli Ortalama', data.moving_averages)}
        </div>
        <div class="tech-tables-row">
            ${oscTable(data.oscillators)}
            ${maTable(data.moving_averages)}
        </div>
        ${pivotTable(data.pivots)}
    `;
}
