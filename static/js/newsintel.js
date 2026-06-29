/**
 * newsintel.js — Haber Zekâsı + BIST Tarama.
 *  - Hisse görünümü: bildirimleri kategorize + duygu + "aynı tip haber geçmişte ne yaptı"
 *  - Tarama görünümü: arşivdeki pozitif/negatif haber akışı (scalp)
 */

let niSymbol = null;
let niTab = 'symbol';

function niSentClass(s) {
    if (s && s.indexOf('Pozitif') >= 0) return 'tag-buy';
    if (s && s.indexOf('Negatif') >= 0) return 'tag-sell';
    return 'tag-neutral';
}

document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('.ni-tab').forEach(tab => {
        tab.addEventListener('click', () => {
            document.querySelectorAll('.ni-tab').forEach(t => t.classList.remove('active'));
            tab.classList.add('active');
            niTab = tab.dataset.nitab;
            document.getElementById('ni-symbol-view').style.display = niTab === 'symbol' ? '' : 'none';
            document.getElementById('ni-scanner-view').style.display = niTab === 'scanner' ? '' : 'none';
            if (niTab === 'scanner') loadScanner();
            else if (niSymbol) loadNewsIntel(niSymbol);
        });
    });
});

async function loadNewsIntel(symbol) {
    if (!symbol) return;
    niSymbol = symbol;
    if (niTab === 'scanner') { loadScanner(); return; }
    const view = document.getElementById('ni-symbol-view');
    view.innerHTML = '<div class="tech-empty glass-card"><span class="loading-small">Haberler kategorize ediliyor, geçmiş tepki hesaplanıyor...</span></div>';
    try {
        const res = await fetch(`/api/news-intel/${symbol}`);
        const data = await res.json();
        if (!data.ok) throw new Error();
        renderNewsIntel(data);
    } catch (e) {
        view.innerHTML = `<div class="tech-empty glass-card">Haber zekâsı yüklenemedi: ${symbol}.</div>`;
    }
}

function reactionCard(cat, res) {
    const cell = (s) => {
        if (!s || s.n === 0) return '<td class="num muted">-</td><td class="num muted">-</td>';
        const c = s.avg > 0 ? '#22c55e' : (s.avg < 0 ? '#ef4444' : '#94a3b8');
        return `<td class="num" style="color:${c}">${s.avg > 0 ? '+' : ''}${s.avg}%</td><td class="num">${s.win_rate}%</td>`;
    };
    const st = res.stats;
    const n = st.r3.n || st.r1.n || st.r5.n;
    return `
    <div class="tech-table-card glass-card">
        <div class="tech-table-head">
            <h3>${cat}</h3>
            <span class="tt-summary tag tag-neutral">${n} örnek</span>
        </div>
        <table class="tech-table">
            <thead><tr><th>Ufuk</th><th class="num">Ort. Getiri</th><th class="num">İsabet</th></tr></thead>
            <tbody>
                <tr><td>Sonraki 1 gün</td>${cell(st.r1)}</tr>
                <tr><td>Sonraki 3 gün</td>${cell(st.r3)}</tr>
                <tr><td>Sonraki 5 gün</td>${cell(st.r5)}</tr>
            </tbody>
        </table>
        <div class="tt-foot">Bu tip haber geçmişte geldiğinde hissenin ortalama hareketi ve pozitif kapatma oranı.</div>
    </div>`;
}

function newsRow(item) {
    return `
    <div class="ni-news-row glass-card">
        <div class="ni-news-main">
            <span class="tag ${niSentClass(item.sentiment)}">${item.sentiment}</span>
            <span class="ni-cat">${item.category}</span>
            <span class="ni-title">${item.title}</span>
        </div>
        <div class="ni-news-meta">
            <span>${item.date || '—'}</span>
            <span>${item.source || ''}</span>
            ${item.url ? `<a href="${item.url}" target="_blank">aç ↗</a>` : ''}
        </div>
    </div>`;
}

function mlCard(ml) {
    if (!ml || !ml.ok) return '';
    const p = ml.impact_prob;
    const color = p >= 55 ? '#ef4444' : (p >= 40 ? '#f59e0b' : '#22c55e');
    const leanTxt = ml.direction_lean === 'yukarı' ? '▲ yukarı' : (ml.direction_lean === 'aşağı' ? '▼ aşağı' : '◆ belirsiz');
    return `
    <div class="ml-card glass-card">
        <div class="ml-left">
            <h3>🤖 YZ Olay Etkisi Modeli</h3>
            <p class="prob-sub">En güncel bildirim için 3 işlem gününde <b>büyük hareket (|getiri| > %${ml.big_move_pct})</b> olma olasılığı. ${ml.note}</p>
            <div class="ml-lean">Duygu temelli yön ipucu: <b>${leanTxt}</b></div>
            ${ml.category_model ? `<div class="ml-cat">📁 Kategori-özel model (<b>${ml.category_model.category}</b>): %${ml.category_model.prob} ${ml.category_model.target === 'impact' ? 'etki' : 'yükseliş'} · doğruluk(AUC) ${ml.category_model.cv_auc}</div>` : ''}
        </div>
        <div class="ml-gauge" style="color:${color}">
            <div class="ml-pct">%${p}</div>
            <div class="ml-label">${ml.label}</div>
        </div>
    </div>`;
}

function renderNewsIntel(data) {
    const reacts = Object.entries(data.reactions || {});
    const reactHtml = reacts.length
        ? `<div class="tech-tables-row">${reacts.map(([c, r]) => reactionCard(c, r)).join('')}</div>`
        : `<div class="tech-empty glass-card">Bu sembol için yeterli geçmiş bildirim arşivi yok. KAP kaynağı bağlandığında "aynı tip haber geçmişte ne yaptı" istatistiği otomatik dolacak.</div>`;

    const recent = data.recent || [];
    const newsHtml = recent.length
        ? recent.map(newsRow).join('')
        : '<div class="tech-empty glass-card">Bu sembol için arşivde/akışta bildirim yok (KAP bağlanınca dolacak).</div>';

    document.getElementById('ni-symbol-view').innerHTML = `
        <div class="ni-head glass-card">
            <div>
                <h2>${data.symbol} — Haber Zekâsı</h2>
                <p class="prob-sub">Bildirimler kategorize + Türkçe duygu ile etiketlenir; geçmiş benzer haberlerde fiyatın ne yaptığı istatistik olarak verilir.</p>
            </div>
            <div class="ni-counts">
                <span style="color:#22c55e">▲ ${data.counts.pozitif} pozitif</span>
                <span style="color:#ef4444">▼ ${data.counts.negatif} negatif</span>
                <span>Σ ${data.counts.total}</span>
            </div>
        </div>

        ${mlCard(data.ml)}

        <h3 class="cnd-section-title">📈 Geçmiş Tepki — "Aynı tip haber geldiğinde hisse ne yaptı?"</h3>
        ${reactHtml}

        <h3 class="cnd-section-title">📰 Bildirim Akışı (kategorize + duygu)</h3>
        ${newsHtml}
    `;
}

async function refreshKap() {
    const btn = document.getElementById('kap-refresh-btn');
    if (btn) { btn.disabled = true; btn.innerText = '⏳ KAP çekiliyor (~40sn)...'; }
    try {
        const res = await fetch('/api/kap/refresh');
        const d = await res.json();
        if (btn) btn.innerText = `✅ ${d.fetched} bildirim`;
    } catch (e) {
        if (btn) btn.innerText = '⚠️ Hata';
    }
    setTimeout(loadScanner, 800);
}

async function backfillKap() {
    const btn = document.getElementById('kap-hist-btn');
    if (btn) { btn.disabled = true; btn.innerText = '⏳ Geçmiş çekiliyor (~1dk)...'; }
    try {
        const res = await fetch('/api/kap/history?weeks=4');
        const d = await res.json();
        if (btn) btn.innerText = `✅ ${d.ingested} yeni kayıt`;
    } catch (e) {
        if (btn) btn.innerText = '⚠️ Hata';
    }
    setTimeout(loadScanner, 1000);
}

async function loadScanner() {
    const view = document.getElementById('ni-scanner-view');
    view.innerHTML = '<div class="tech-empty glass-card"><span class="loading-small">BIST haber akışı taranıyor...</span></div>';
    try {
        const res = await fetch('/api/scanner');
        const data = await res.json();
        renderScanner(data);
    } catch (e) {
        view.innerHTML = '<div class="tech-empty glass-card">Tarama yüklenemedi.</div>';
    }
}

function scanCol(title, items, color) {
    const rows = items.length
        ? items.map(i => `
            <div class="scan-row" style="cursor: pointer;" onclick="loadTickerFromNewsIntel('${i.symbol}')">
                <span class="scan-sym">${i.symbol}</span>
                <span class="tag ${niSentClass(i.sentiment)}">${i.sentiment}</span>
                <span class="scan-cat">${i.category}</span>
                <span class="scan-date">${i.date || ''}</span>
            </div>`).join('')
        : '<div class="scan-empty">Akışta kayıt yok.</div>';
    return `
    <div class="tech-table-card glass-card">
        <div class="tech-table-head"><h3 style="color:${color}">${title}</h3><span class="tt-summary tag tag-neutral">${items.length}</span></div>
        <div class="scan-list">${rows}</div>
    </div>`;
}

function renderScanner(data) {
    document.getElementById('ni-scanner-view').innerHTML = `
        <div class="ni-head glass-card">
            <div>
                <h2>📡 BIST Haber Tarama (Scalp)</h2>
                <p class="prob-sub">${data.universe} hisselik evrende KAP bildirimleri duyguya göre süzülür. "KAP Yenile" canlı bildirimleri çeker (~40sn).</p>
            </div>
            <div class="ni-scan-actions">
                <div class="ni-counts">
                    <span style="color:#22c55e">▲ ${data.counts.pozitif}</span>
                    <span style="color:#ef4444">▼ ${data.counts.negatif}</span>
                    <span>Σ ${data.counts.toplam}</span>
                </div>
                <div class="kap-btn-row">
                    <button class="search-btn" id="kap-refresh-btn" onclick="refreshKap()">🔄 KAP Yenile</button>
                    <button class="search-btn kap-hist-btn" id="kap-hist-btn" onclick="backfillKap()">📚 Geçmiş Çek (4 hf)</button>
                </div>
            </div>
        </div>
        <div class="tech-tables-row">
            ${scanCol('🟢 Pozitif Akış', data.pozitif, '#22c55e')}
            ${scanCol('🔴 Negatif Akış', data.negatif, '#ef4444')}
        </div>
    `;
}

/**
 * Haber Akışından (Scalp) hisseye tıklandığında Dashboard grafiğini yükler.
 */
function loadTickerFromNewsIntel(symbol) {
    let fullSym = symbol.toUpperCase().trim();
    if (!fullSym.endsWith('.IS') && fullSym.length <= 5) {
        fullSym = fullSym + '.IS';
    }
    const searchInput = document.getElementById('symbol-search');
    if (searchInput) {
        searchInput.value = fullSym;
    }
    showPage('dashboard');
    if (typeof fetchTickerData === 'function') {
        fetchTickerData(fullSym, '1y', '1d');
    }
}
