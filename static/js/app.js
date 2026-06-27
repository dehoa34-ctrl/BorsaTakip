/** 
 * BorsaTakip AI - Frontend Logic
 * Handles real-time API fetches and charting with Lightweight Charts.
 */

let chart;
let candleSeries;
let currentSymbol = 'THYAO.IS';
let currentPeriod = '1y';
let currentInterval = '1d';

document.addEventListener('DOMContentLoaded', () => {
    initChart();
    loadWatchlist();
    
    // UI Selectors
    const searchBtn = document.getElementById('search-btn');
    const searchInput = document.getElementById('symbol-search');
    
    searchBtn.addEventListener('click', () => {
        const symbol = searchInput.value.trim().toUpperCase();
        if (symbol) fetchTickerData(symbol, currentPeriod, currentInterval);
    });

    searchInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') {
            const symbol = searchInput.value.trim().toUpperCase();
            if (symbol) fetchTickerData(symbol, currentPeriod, currentInterval);
        }
    });

    // Nav Items
    const navItems = document.querySelectorAll('.nav-item');
    const newsModal = document.getElementById('news-modal');
    const closeModal = document.querySelector('.close-modal');

    navItems.forEach(item => {
        item.addEventListener('click', () => {
            navItems.forEach(n => n.classList.remove('active'));
            item.classList.add('active');
            
            if (item.id === 'btn-watchlist') {
                alert('İzleme Listesi modülü yapım aşamasında.');
            } else if (item.id === 'btn-news') {
                fetchTickerNews(currentSymbol);
                newsModal.style.display = 'block';
            }
        });
    });

    closeModal.onclick = () => newsModal.style.display = 'none';
    window.onclick = (e) => { if (e.target == newsModal) newsModal.style.display = 'none'; };

    // Chart Controls (1G, 1H, 1A)
    const chartControls = document.querySelectorAll('.chart-controls span');
    chartControls.forEach(control => {
        control.addEventListener('click', (e) => {
            chartControls.forEach(c => c.classList.remove('active'));
            e.target.classList.add('active');
            
            const text = e.target.innerText;
            if (text === '1G') {
                currentPeriod = '5d';      // intraday: son günler 5dk mum
                currentInterval = '5m';
            } else if (text === '1H') {
                currentPeriod = '1mo';
                currentInterval = '15m';
            } else if (text === '1A') {
                currentPeriod = '3mo';     // günlük mum, 3 ay
                currentInterval = '1d';
            } else if (text === '6A') {
                currentPeriod = '6mo';     // günlük mum, 6 ay
                currentInterval = '1d';
            } else if (text === '1Y') {
                currentPeriod = '1y';      // günlük mum, 1 yıl
                currentInterval = '1d';
            } else if (text === '5Y') {
                currentPeriod = '5y';      // haftalık mum, 5 yıl
                currentInterval = '1wk';
            } else if (text === 'TÜM') {
                currentPeriod = 'max';     // aylık mum — TÜM geçmiş okunur şekilde sığar
                currentInterval = '1mo';
            }
            fetchTickerData(currentSymbol, currentPeriod, currentInterval);
        });
    });

    // Default load
    fetchTickerData(currentSymbol, currentPeriod, currentInterval);
});

/**
 * Initialize Lightweight Chart
 */
function initChart() {
    const chartElement = document.getElementById('main-chart');
    if (!chartElement) return;

    // Remove placeholder so chart spans perfectly
    chartElement.innerHTML = '';

    chart = LightweightCharts.createChart(chartElement, {
        width: chartElement.clientWidth,
        height: chartElement.clientHeight,
        layout: {
            backgroundColor: 'transparent',
            textColor: '#94a3b8',
            fontSize: 12,
            fontFamily: "'Inter', sans-serif",
        },
        grid: {
            vertLines: { color: 'rgba(255, 255, 255, 0.05)' },
            horzLines: { color: 'rgba(255, 255, 255, 0.05)' },
        },
        crosshair: {
            mode: LightweightCharts.CrosshairMode.Normal,
        },
        rightPriceScale: {
            borderColor: 'rgba(255, 255, 255, 0.1)',
            // Logaritmik: BIST'te enflasyonla nominal fiyat çok büyüdüğü için
            // uzun geçmişte yüzdesel hareketler orantılı/okunur görünür.
            mode: LightweightCharts.PriceScaleMode.Logarithmic,
        },
        timeScale: {
            borderColor: 'rgba(255, 255, 255, 0.1)',
            timeVisible: true,
            secondsVisible: false,
        },
    });

    candleSeries = chart.addCandlestickSeries({
        upColor: '#10b981',
        downColor: '#ef4444',
        borderDownColor: '#ef4444',
        borderUpColor: '#10b981',
        wickDownColor: '#ef4444',
        wickUpColor: '#10b981',
    });

    // Handle Resize — hem pencere hem KONTEYNER boyutu değişince düzelt
    const doResize = () => {
        const w = chartElement.clientWidth, h = chartElement.clientHeight;
        if (w > 0 && h > 0) chart.resize(w, h);
    };
    window.addEventListener('resize', doResize);
    // Konteyner (grid/CSS/sekme) değişince grafik kendini boyutlandırsın
    if (window.ResizeObserver) {
        new ResizeObserver(doResize).observe(chartElement);
    }
    // İlk düzgün boyutlanma için bir sonraki frame'de tekrar dene
    requestAnimationFrame(doResize);
}

/**
 * Fetch and Update Ticker Data
 */
async function fetchTickerData(symbol, period='1mo', interval='1d') {
    currentSymbol = symbol;
    currentPeriod = period;
    currentInterval = interval;
    
    console.log(`Fetching data for ${symbol} (${period}, ${interval})...`);
    try {
        // Show loading state or header
        const tickerHeader = document.getElementById('ticker-header');
        tickerHeader.style.display = 'flex';
        tickerHeader.style.opacity = '0.5';

        // 1. Fetch Info & Signals with given period/interval
        const infoRes = await fetch(`/api/ticker/${symbol}?period=${period}&interval=${interval}`);
        if (!infoRes.ok) throw new Error('Symbol not found');
        const infoData = await infoRes.json();

        // 2. Fetch History for Chart
        const histRes = await fetch(`/api/history/${symbol}?period=${period}&interval=${interval}`);
        const histData = await histRes.json();

        updateUI(infoData);
        updateChart(histData);

        // Teknik Analiz sekmesi açıksa onu da güncelle
        const techSection = document.getElementById('section-technical');
        if (techSection && techSection.style.display !== 'none' && typeof loadTechnical === 'function') {
            loadTechnical(symbol);
        }
        // Mum Formasyonları sekmesi açıksa onu da güncelle
        const cndSection = document.getElementById('section-candles');
        if (cndSection && cndSection.style.display !== 'none' && typeof loadCandles === 'function') {
            loadCandles(symbol);
        }
        // Haber Zekâsı sekmesi açıksa onu da güncelle
        const niSection = document.getElementById('section-newsintel');
        if (niSection && niSection.style.display !== 'none' && typeof loadNewsIntel === 'function') {
            loadNewsIntel(symbol);
        }

        tickerHeader.style.opacity = '1';
    } catch (err) {
        console.error(err);
        alert(`Sembol bulunamadı: ${symbol}. Lütfen geçerli bir sembol girin (Örn: THYAO.IS, AKBNK.IS, AAPL, NVDA)`);
        const tickerHeader = document.getElementById('ticker-header');
        if (tickerHeader) tickerHeader.style.opacity = '1';
    }
}

/**
 * Fetch and Display News
 */
async function fetchTickerNews(symbol) {
    const container = document.getElementById('news-container');
    container.innerHTML = '<div class="loading-small">Haberler taranıyor...</div>';
    
    try {
        const res = await fetch(`/api/news/${symbol}`);
        const news = await res.json();
        
        container.innerHTML = '';
        if (!news || news.length === 0) {
            container.innerHTML = '<p>Bu sembol için güncel haber bulunamadı.</p>';
            return;
        }

        news.forEach(item => {
            const card = document.createElement('div');
            card.className = 'news-card';
            card.innerHTML = `
                <span class="source">${item.publisher} | ${new Date(item.providerPublishTime * 1000).toLocaleTimeString()}</span>
                <h4>${item.title}</h4>
                <a href="${item.link}" target="_blank">Devamını Oku &rarr;</a>
            `;
            container.appendChild(card);
        });
    } catch (err) {
        container.innerHTML = '<p>Haberler yüklenirken bir hata oluştu.</p>';
    }
}

/**
 * Update UI Elements with API data
 */
function updateUI(data) {
    document.getElementById('selected-symbol').innerText = data.symbol;
    document.getElementById('current-price').innerText = `${data.price.toLocaleString()} `;
    
    const changeEl = document.getElementById('price-change');
    changeEl.innerText = `${data.change > 0 ? '+' : ''}${data.change} (${data.change_percent}%)`;
    changeEl.className = `price-change ${data.change >= 0 ? 'positive' : 'negative'}`;

    // Signal Updates
    const signalBadge = document.getElementById('signal-text');
    const signalMsg = document.getElementById('signal-message');
    const aiInsight = document.getElementById('ai-insight');

    signalBadge.innerText = data.analysis.signal;
    signalBadge.style.borderColor = data.analysis.color;
    signalBadge.style.color = data.analysis.color;
    signalMsg.innerText = data.analysis.message;

    // AI Insight — ML modeli + akıllı para karakteri (if/else yerine)
    const ml = data.ml;
    if (ml) {
        let html = `<b>🤖 ML Güven Skoru:</b> %${ml.ml_confidence} — ${ml.label}<br>`;
        html += `<span style="color:#94a3b8;font-size:0.82rem">${ml.note}</span><br>`;
        if (ml.flow_character) html += `<b>💧 Akıllı Para:</b> ${ml.flow_character}<br>`;
        if (ml.trap) html += `<span style="color:#fcd34d">⚠️ ${ml.trap.type} (Risk: ${ml.trap.risk}) — ${ml.trap.note}</span><br>`;
        if (ml.divergence) {
            const good = /Gizli Alım/.test(ml.divergence.type);
            html += `<span style="color:${good ? '#86efac' : '#fca5a5'}">${good ? '🟢' : '🔴'} ${ml.divergence.type}</span>`;
        }
        aiInsight.innerHTML = html;
    } else {
        aiInsight.innerText = data.analysis.insight || "Analiz bekleniyor...";
    }

    // Confidence Bar — ML hareketlilik olasılığı (yön değil)
    const confidenceBar = document.querySelector('.progress');
    const confVal = ml ? ml.ml_confidence : data.analysis.confidence;
    if (confidenceBar && confVal !== undefined) {
        confidenceBar.style.width = `${confVal}%`;
        const confText = document.querySelector('.ai-confidence span');
        if (confText) confText.innerText = ml ? `Büyük Hareket Olasılığı: %${confVal}` : `Güven Oranı: %${confVal}`;
    }

    // Temel Analiz + Birleşik Görüş (Tuzak Filtresi / Onay Mekanizması)
    renderFundamentals(data.fundamentals, data.final_view);

    // Stats
    document.getElementById('stat-rsi').innerText = data.analysis.rsi || '---';
    document.getElementById('stat-sma').innerText = `${data.analysis.sma50 || '--'}`;
}

/**
 * Temel Analiz rasyoları + Birleşik Görüş kartı
 */
function renderFundamentals(f, fv) {
    const card = document.getElementById('fundamental-card');
    if (!card) return;
    if (!f) { card.style.display = 'none'; return; }
    card.style.display = '';

    const toneColor = { warn: '#fcd34d', strong: '#22c55e', ok: '#86efac', mixed: '#94a3b8', neutral: '#94a3b8' };
    const vEl = document.getElementById('final-verdict');
    if (fv && fv.verdict) {
        const c = toneColor[fv.tone] || '#94a3b8';
        vEl.innerHTML = `<div class="verdict-badge" style="background:${c}1a;color:${c};border:1px solid ${c}55">${fv.verdict}</div>
            ${fv.note ? `<p class="verdict-note">${fv.note}</p>` : ''}`;
    } else { vEl.innerHTML = ''; }

    const q = f.quality || {};
    const fmt = (v, suf = '') => (v === null || v === undefined) ? '<span class="muted">N/A</span>' : `${v}${suf}`;
    const rows = [
        ['Çeyreklik Büyüme (FAVÖK)', fmt(f.favok_growth, '%')],
        ['Net Borç / FAVÖK', fmt(f.net_debt_ebitda)],
        ['Özsermaye Kârlılığı (ROE)', fmt(f.roe, '%')],
        ['F/K', fmt(f.pe)],
        ['PD/DD', fmt(f.pb)],
        ['Net YP Poz. / Özsermaye', fmt(f.fx_position_equity)],
    ];
    document.getElementById('fundamental-ratios').innerHTML = `
        <div class="fund-quality">Temel Kalite: <b>${q.label || '—'}</b>${q.score !== null && q.score !== undefined ? ` (${q.score})` : ''}</div>
        <table class="fund-table">${rows.map(r => `<tr><td>${r[0]}</td><td class="num">${r[1]}</td></tr>`).join('')}</table>`;
}

/**
 * Refresh Chart Data
 */
function updateChart(data) {
    if (data && data.length > 0) {
        // Geçersiz/sıfır fiyatlı eski mumları ele (log ölçek 0'ı kabul etmez)
        const clean = data.filter(d => d.close > 0 && d.open > 0 && d.high > 0 && d.low > 0);
        candleSeries.setData(clean);
        chart.timeScale().fitContent();
    }
}

/**
 * Sayfa/sekme geçişi (Bot Paneli kaldırıldı — sistem yalnızca borsa).
 */
function showPage(page) {
    document.querySelectorAll('.nav-item').forEach(el => el.classList.remove('active'));
    document.getElementById('btn-' + page)?.classList.add('active');

    const dashboard = document.querySelector('.dashboard');
    const technical = document.getElementById('section-technical');
    const candles = document.getElementById('section-candles');
    const newsintel = document.getElementById('section-newsintel');
    const scanSec = document.getElementById('section-scan');

    if (dashboard) dashboard.style.display = 'none';
    if (technical) technical.style.display = 'none';
    if (candles) candles.style.display = 'none';
    if (newsintel) newsintel.style.display = 'none';
    if (scanSec) scanSec.style.display = 'none';

    const sym = (typeof currentSymbol !== 'undefined') ? currentSymbol : 'THYAO.IS';

    if (page === 'technical') {
        if (technical) technical.style.display = '';
        if (typeof loadTechnical === 'function') loadTechnical(sym);
    } else if (page === 'candles') {
        if (candles) candles.style.display = '';
        if (typeof loadCandles === 'function') loadCandles(sym);
    } else if (page === 'newsintel') {
        if (newsintel) newsintel.style.display = '';
        if (typeof loadNewsIntel === 'function') loadNewsIntel(sym);
    } else if (page === 'scan') {
        if (scanSec) scanSec.style.display = '';
        if (typeof initScanTab === 'function') initScanTab();
    } else {
        if (dashboard) dashboard.style.display = '';
    }
}

/**
 * İzleme listesi — sadece Türk (BIST) ve ABD hisseleri (kripto kaldırıldı).
 */
function loadWatchlist() {
    const list = [
        // 🇹🇷 BIST
        { sym: 'THYAO.IS', cat: 'bist' },
        { sym: 'GARAN.IS', cat: 'bist' },
        { sym: 'ASELS.IS', cat: 'bist' },
        { sym: 'AKBNK.IS', cat: 'bist' },
        { sym: 'EREGL.IS', cat: 'bist' },
        { sym: 'SISE.IS', cat: 'bist' },
        { sym: 'KCHOL.IS', cat: 'bist' },
        { sym: 'BIMAS.IS', cat: 'bist' },
        { sym: 'TUPRS.IS', cat: 'bist' },
        { sym: 'FROTO.IS', cat: 'bist' },
        // 🇺🇸 ABD
        { sym: 'AAPL', cat: 'us' },
        { sym: 'MSFT', cat: 'us' },
        { sym: 'NVDA', cat: 'us' },
        { sym: 'TSLA', cat: 'us' },
        { sym: 'AMZN', cat: 'us' },
        { sym: 'GOOGL', cat: 'us' },
        { sym: 'META', cat: 'us' },
        { sym: 'AMD', cat: 'us' }
    ];

    const bistContainer = document.getElementById('watchlist-bist');
    const usContainer = document.getElementById('watchlist-us');

    if (bistContainer) bistContainer.innerHTML = '';
    if (usContainer) usContainer.innerHTML = '';

    list.forEach(item => {
        const div = document.createElement('div');
        div.className = 'watchlist-card';
        div.innerHTML = `
            <span class="sym">${item.sym.replace('.IS', '')}</span>
            <span class="price">Canlı</span>
        `;
        div.onclick = () => {
            document.getElementById('symbol-search').value = item.sym;
            fetchTickerData(item.sym, currentPeriod, currentInterval);
        };

        if (item.cat === 'bist' && bistContainer) bistContainer.appendChild(div);
        if (item.cat === 'us' && usContainer) usContainer.appendChild(div);
    });
}
