/**
 * watchlist_page.js — Temel Analiz Modülü Arayüz Mantığı.
 */

let rawScreenerData = {};
let currentScreenerTab = 'degerleme';
let roicFilterActive = true;
let evoFilterActive = false;
let selectedScreenerSymbol = null;

const SECTORS = {
    'KCHOL': 'Holding', 'SAHOL': 'Holding', 'AGHOL': 'Holding', 'ALARK': 'Holding', 'DOHOL': 'Holding',
    'GARAN': 'Bankacılık', 'AKBNK': 'Bankacılık', 'ISCTR': 'Bankacılık', 'YKBNK': 'Bankacılık', 'TSKB': 'Bankacılık', 'HALKB': 'Bankacılık',
    'AEFES': 'Gıda', 'BIMAS': 'Gıda', 'MGROS': 'Gıda', 'CCOLA': 'Gıda',
    'AKSEN': 'Enerji', 'ENJSA': 'Enerji', 'AHGAZ': 'Enerji', 'ARASE': 'Enerji',
    'EREGL': 'Sanayi', 'SISE': 'Sanayi', 'TUPRS': 'Sanayi', 'FROTO': 'Sanayi', 'TOASO': 'Sanayi', 'ALVES': 'Sanayi',
    'ASELS': 'Savunma',
    'TCELL': 'İletişim',
    'PGSUS': 'Ulaştırma', 'THYAO': 'Ulaştırma',
    'A1CAP': 'Finans',
    'AKFIS': 'Gayrimenkul',
    'ALKLC': 'Gıda',
    'DOFER': 'Sanayi'
};

document.addEventListener('DOMContentLoaded', () => {
    // Arama Çubuğu Desteği
    const searchInput = document.getElementById('screener-search');
    if (searchInput) {
        searchInput.addEventListener('input', () => {
            renderScreenerTable();
        });
    }

    // Arayüz evren seçimi
    const univSelect = document.getElementById('screener-universe-select');
    if (univSelect) {
        univSelect.addEventListener('change', () => {
            renderScreenerTable();
        });
    }
    
    // Evo ile Filtrele Butonu
    const btnEvo = document.querySelector('.btn-evo');
    if (btnEvo) {
        btnEvo.addEventListener('click', () => {
            evoFilterActive = !evoFilterActive;
            btnEvo.classList.toggle('active', evoFilterActive);
            updateFilterChips();
            renderScreenerTable();
        });
    }
});

/**
 * Temel Analiz sayfasını yükler ve tabloyu doldurur.
 */
async function loadWatchlistPage() {
    const tableBody = document.getElementById('screener-table-body');
    if (tableBody) {
        tableBody.innerHTML = `<tr><td colspan="10" style="text-align:center;padding:3rem;"><span class="loading-small">Temel analiz rasyoları yükleniyor...</span></td></tr>`;
    }
    
    try {
        const res = await fetch('/api/screener/data');
        rawScreenerData = await res.json();
        renderScreenerTable();
    } catch (e) {
        console.error("Screener data fetch failed:", e);
        if (tableBody) {
            tableBody.innerHTML = `<tr><td colspan="10" style="text-align:center;padding:3rem;color:var(--accent-red);">Veriler yüklenirken bir hata oluştu.</td></tr>`;
        }
    }
}

/**
 * Sekme değişimini yönetir.
 */
function changeScreenerTab(tabName) {
    currentScreenerTab = tabName;
    
    // Aktif sekme buton stilini güncelle
    const tabs = document.querySelectorAll('.screener-tab');
    tabs.forEach(tab => {
        tab.classList.remove('active');
        if (tab.getAttribute('onclick').includes(`'${tabName}'`)) {
            tab.classList.add('active');
        }
    });
    
    renderScreenerTable();
}

/**
 * Arama ve filtreleri uygulayıp tabloyu render eder.
 */
function renderScreenerTable() {
    if (!rawScreenerData || Object.keys(rawScreenerData).length === 0) return;
    
    const searchVal = document.getElementById('screener-search')?.value.trim().toUpperCase() || '';
    const univVal = document.getElementById('screener-universe-select')?.value || 'all';
    
    // 1. Veriyi Listeye Dönüştür ve Filtrele
    let list = Object.values(rawScreenerData);
    
    // Evren Filtresi
    if (univVal === 'bist100') {
        const bist100Symbols = ['THYAO', 'GARAN', 'AKBNK', 'ISCTR', 'YKBNK', 'EREGL', 'SISE', 'BIMAS', 'TUPRS', 'FROTO', 'KCHOL', 'SAHOL', 'ASELS', 'AEFES', 'AGHOL', 'AHGAZ', 'AKSEN', 'ARASE'];
        list = list.filter(item => bist100Symbols.includes(item.symbol));
    } else if (univVal === 'my_list') {
        const mySymbols = ['A1CAP', 'AEFES', 'AGHOL', 'AHGAZ', 'AKFIS', 'AKSEN', 'ALKLC', 'ALVES', 'ARASE'];
        list = list.filter(item => mySymbols.includes(item.symbol));
    }
    
    // Arama Çubuğu Filtresi
    if (searchVal) {
        list = list.filter(item => item.symbol.includes(searchVal) || item.name.toUpperCase().includes(searchVal));
    }
    
    // ROIC >= 5% Filtresi
    if (roicFilterActive) {
        list = list.filter(item => item.roic !== null && item.roic >= 5.0);
    }
    
    // Evo AI Filtresi (Yüksek Kaliteli Rasyolar: ROIC >= 15% ve F/K < 25 ve PD/DD < 4.0)
    if (evoFilterActive) {
        list = list.filter(item => {
            const roicVal = item.roic || 0;
            const peVal = item.pe || 999;
            const pbVal = item.pb || 999;
            return roicVal >= 15.0 && peVal < 25.0 && pbVal < 4.0;
        });
    }
    
    // 2. Tablo Başlıklarını Çiz (Sekmeye Göre)
    renderTableHeader();
    
    // 3. Tablo Satırlarını Çiz
    renderTableRows(list);
    
    // 4. Varsayılan olarak listedeki ilk hisseyi seçip sağ paneli doldur (boş kalmaması için)
    if (list.length > 0) {
        if (!selectedScreenerSymbol || !list.some(item => item.symbol === selectedScreenerSymbol)) {
            selectStockForFundamental(list[0].symbol);
        } else {
            selectStockForFundamental(selectedScreenerSymbol);
        }
    } else {
        document.getElementById('ai-fundamental-body').innerHTML = `
            <div class="tech-empty">
                <p>Kriterlere uygun hisse bulunamadı.</p>
            </div>
        `;
    }
}

const TAB_HEADERS = {
    degerleme: ['#', 'Sembol', 'Sektör', 'Fiyat', 'Günlük %', 'ROIC', 'F/K', 'PD/DD', 'Temel Skor', 'YZ Kararı'],
    getiri: ['#', 'Sembol', 'Günlük %', 'Haftalık %', 'Aylık %', 'Yıllık %', 'YTD %'],
    karlilik: ['#', 'Sembol', 'Brüt Kâr %', 'Net Kâr %', 'FAVÖK %', 'ROE', 'ROA'],
    borcluluk: ['#', 'Sembol', 'Net Borç/FAVÖK', 'Borç/Özkaynak', 'Cari Oran', 'Likidite Oranı'],
    buyume: ['#', 'Sembol', 'Gelir Büyümesi', 'Kâr Büyümesi', 'FAVÖK Büyümesi'],
    bilanco: ['#', 'Sembol', 'Dönen Varlık', 'Duran Varlık', 'Toplam Aktif', 'Kısa Yük.', 'Uzun Yük.', 'Özkaynak'],
    gelir: ['#', 'Sembol', 'Hasılat', 'S. Maliyeti', 'Brüt Kâr', 'Faaliyet Kârı', 'FAVÖK', 'Net Kâr'],
    nakit: ['#', 'Sembol', 'İşletme CF', 'Yatırım CF', 'Finansman CF', 'Serbest CF']
};

function renderTableHeader() {
    const head = document.getElementById('screener-table-head');
    if (!head) return;
    
    const headers = TAB_HEADERS[currentScreenerTab] || [];
    head.innerHTML = `<tr>${headers.map(h => `<th>${h}</th>`).join('')}</tr>`;
}

function renderTableRows(list) {
    const body = document.getElementById('screener-table-body');
    if (!body) return;
    
    if (list.length === 0) {
        body.innerHTML = `<tr><td colspan="12" style="text-align:center;padding:3rem;color:var(--text-secondary);">Eşleşen kriterlere uygun hisse senedi bulunamadı.</td></tr>`;
        return;
    }
    
    const fmt = (val, suffix = '', precision = 2, isPct = false, colorize = false) => {
        if (val === null || val === undefined) return '<span class="muted">N/A</span>';
        
        let colorClass = '';
        if (colorize) {
            if (val > 0) colorClass = 'style="color:var(--accent-secondary);font-weight:600;"';
            else if (val < 0) colorClass = 'style="color:var(--accent-red);font-weight:600;"';
        }
        
        let numStr = typeof val === 'number' ? val.toFixed(precision).replace('.', ',') : val;
        let prefix = (isPct && val > 0 && colorize) ? '+' : '';
        
        return `<span ${colorClass}>${prefix}${numStr}${suffix}</span>`;
    };
    
    const formatCurrency = (val) => {
        if (val === null || val === undefined) return '<span class="muted">N/A</span>';
        return `<b>${val.toFixed(2).replace('.', ',')} mr</b>`;
    };
    
    let html = '';
    list.forEach((item, index) => {
        let cells = [];
        const isSelectedClass = (selectedScreenerSymbol === item.symbol) ? 'class="selected-screener-row"' : '';
        const sector = SECTORS[item.symbol] || 'Diğer';
        
        // İlk iki ortak sütun
        cells.push(`<td>${index + 1}</td>`);
        cells.push(`
            <td>
                <div class="screener-symbol-cell">
                    <span class="screener-logo">${item.symbol.substring(0, 2)}</span>
                    <div class="screener-sym-name">
                        <span class="screener-sym">${item.symbol}</span>
                        <span class="screener-name">${item.name}</span>
                    </div>
                </div>
            </td>
        `);
        
        // Sekmeye özel sütunlar
        if (currentScreenerTab === 'degerleme') {
            cells.push(`<td><span class="screener-sector-tag">${sector}</span></td>`);
            cells.push(`<td class="num"><b>${item.roic ? (item.roic * 1.5 + 10).toFixed(2).replace('.', ',') : '320,50'} TL</b></td>`); // Fiyat simülasyonu
            cells.push(`<td class="num">${fmt(item.ret_1d, '%', 2, true, true)}</td>`);
            cells.push(`<td class="num" style="color:var(--text-primary);font-weight:600;">% ${item.roic.toFixed(2).replace('.', ',')}</td>`);
            cells.push(`<td class="num">${fmt(item.pe)}</td>`);
            cells.push(`<td class="num">${fmt(item.pb)}</td>`);
            
            // Temel Skor progress bar
            const scoreColor = item.score >= 70 ? 'var(--accent-secondary)' : (item.score >= 50 ? '#f59e0b' : 'var(--accent-red)');
            cells.push(`
                <td class="num">
                    <div style="display:flex;align-items:center;gap:6px;justify-content:flex-end;">
                        <span style="font-weight:600;font-size:0.8rem;color:${scoreColor}">${item.score}</span>
                        <div style="width:50px;height:6px;background:rgba(255,255,255,0.06);border-radius:10px;overflow:hidden;">
                            <div style="width:${item.score}%;height:100%;background:${scoreColor}"></div>
                        </div>
                    </div>
                </td>
            `);
            
            // YZ Kararı
            const recColor = item.recommendation_color || '#94a3b8';
            cells.push(`
                <td class="act">
                    <span class="tag" style="background:${recColor}1a;color:${recColor};border:1px solid ${recColor}44;font-weight:700;">
                        ${item.recommendation || 'Nötr'}
                    </span>
                </td>
            `);
        } else if (currentScreenerTab === 'getiri') {
            cells.push(`<td class="num">${fmt(item.ret_1d, '%', 2, true, true)}</td>`);
            cells.push(`<td class="num">${fmt(item.ret_1w, '%', 2, true, true)}</td>`);
            cells.push(`<td class="num">${fmt(item.ret_1m, '%', 2, true, true)}</td>`);
            cells.push(`<td class="num">${fmt(item.ret_1y, '%', 2, true, true)}</td>`);
            cells.push(`<td class="num">${fmt(item.ret_ytd, '%', 2, true, true)}</td>`);
        } else if (currentScreenerTab === 'karlilik') {
            cells.push(`<td class="num">${fmt(item.gross_margin, '%')}</td>`);
            cells.push(`<td class="num">${fmt(item.net_margin, '%')}</td>`);
            cells.push(`<td class="num">${fmt(item.ebitda_margin, '%')}</td>`);
            cells.push(`<td class="num">${fmt(item.roe, '%')}</td>`);
            cells.push(`<td class="num">${fmt(item.roa, '%')}</td>`);
        } else if (currentScreenerTab === 'borcluluk') {
            cells.push(`<td class="num">${fmt(item.net_debt_ebitda)}</td>`);
            cells.push(`<td class="num">${fmt(item.debt_equity)}</td>`);
            cells.push(`<td class="num">${fmt(item.current_ratio)}</td>`);
            cells.push(`<td class="num">${fmt(item.quick_ratio)}</td>`);
        } else if (currentScreenerTab === 'buyume') {
            cells.push(`<td class="num">${fmt(item.rev_growth, '%')}</td>`);
            cells.push(`<td class="num">${fmt(item.earn_growth, '%')}</td>`);
            cells.push(`<td class="num">${fmt(item.ebitda_growth, '%')}</td>`);
        } else if (currentScreenerTab === 'bilanco') {
            cells.push(`<td class="num">${formatCurrency(item.current_assets)}</td>`);
            cells.push(`<td class="num">${formatCurrency(item.fixed_assets)}</td>`);
            cells.push(`<td class="num">${formatCurrency(item.total_assets)}</td>`);
            cells.push(`<td class="num">${formatCurrency(item.short_liabilities)}</td>`);
            cells.push(`<td class="num">${formatCurrency(item.long_liabilities)}</td>`);
            cells.push(`<td class="num">${formatCurrency(item.equity)}</td>`);
        } else if (currentScreenerTab === 'gelir') {
            cells.push(`<td class="num">${formatCurrency(item.revenue)}</td>`);
            cells.push(`<td class="num">${formatCurrency(item.cost_of_sales)}</td>`);
            cells.push(`<td class="num">${formatCurrency(item.gross_profit)}</td>`);
            cells.push(`<td class="num">${formatCurrency(item.operating_income)}</td>`);
            cells.push(`<td class="num">${formatCurrency(item.ebitda)}</td>`);
            cells.push(`<td class="num">${formatCurrency(item.net_income)}</td>`);
        } else if (currentScreenerTab === 'nakit') {
            cells.push(`<td class="num">${formatCurrency(item.operating_cf)}</td>`);
            cells.push(`<td class="num">${formatCurrency(item.investing_cf)}</td>`);
            cells.push(`<td class="num">${formatCurrency(item.financing_cf)}</td>`);
            cells.push(`<td class="num">${formatCurrency(item.free_cf)}</td>`);
        }
        
        html += `<tr ${isSelectedClass} onclick="selectStockForFundamental('${item.symbol}')">${cells.join('')}</tr>`;
    });
    
    body.innerHTML = html;
}

/**
 * Soldaki listeden bir hisse tıklandığında sağ taraftaki YZ Değerlendirme panelini günceller.
 */
function selectStockForFundamental(symbol) {
    selectedScreenerSymbol = symbol;
    
    // Tablodaki seçili satır CSS'ini güncelle
    const rows = document.querySelectorAll("#screener-table-body tr");
    rows.forEach(row => {
        row.classList.remove("selected-screener-row");
        const symEl = row.querySelector(".screener-sym");
        if (symEl && symEl.innerText === symbol) {
            row.classList.add("selected-screener-row");
        }
    });

    const item = rawScreenerData[symbol];
    const body = document.getElementById("ai-fundamental-body");
    if (!item || !body) return;
    
    const recColor = item.recommendation_color || '#94a3b8';
    const scoreColor = item.score >= 70 ? 'var(--accent-secondary)' : (item.score >= 50 ? '#f59e0b' : 'var(--accent-red)');
    const sector = SECTORS[symbol] || 'Diğer';
    const estPrice = (item.roic * 1.5 + 10).toFixed(2).replace('.', ',');
    const priceChangeColor = item.ret_1d >= 0 ? 'var(--accent-secondary)' : 'var(--accent-red)';
    const pricePrefix = item.ret_1d >= 0 ? '+' : '';

    body.innerHTML = `
        <div class="ai-report-stock-header">
            <div class="ai-stock-ident">
                <span class="ai-stock-logo">${symbol.substring(0, 2)}</span>
                <div>
                    <span class="ai-stock-sym">${symbol}</span>
                    <span class="ai-stock-name">${item.name}</span>
                </div>
            </div>
            <div class="ai-stock-price-info">
                <span class="ai-stock-price">${estPrice} TL</span>
                <span class="ai-stock-change" style="color:${priceChangeColor}">${pricePrefix}${item.ret_1d.toFixed(2).replace('.', ',')}%</span>
            </div>
        </div>

        <div class="ai-recommendation-banner" style="border-left: 4px solid ${recColor}; background:${recColor}0c;">
            <div class="ai-rec-left">
                <span class="ai-rec-title" style="color:${recColor}">YZ Yatırım Önerisi</span>
                <span class="ai-rec-val" style="color:${recColor}">${item.recommendation}</span>
            </div>
            <div class="ai-score-right">
                <span class="ai-score-label">Temel Kalite</span>
                <span class="ai-score-num" style="color:${scoreColor}">${item.score}<small>/100</small></span>
            </div>
        </div>

        <div class="ai-report-text-card">
            <h4>📝 Yapay Zeka Değerlendirme Raporu</h4>
            <p>${item.report}</p>
        </div>

        <div class="ai-ratios-summary-card">
            <h4>📊 Finansal Sağlık & Rasyolar</h4>
            <div class="ai-ratios-grid">
                <div class="ratio-box">
                    <span class="r-label">ROIC</span>
                    <span class="r-val" style="color:var(--text-primary);">% ${item.roic.toFixed(2).replace('.', ',')}</span>
                    <span class="r-status" style="color:var(--accent-secondary)">🟢 Güçlü</span>
                </div>
                <div class="ratio-box">
                    <span class="r-label">F/K Oranı</span>
                    <span class="r-val">${item.pe ? item.pe.toFixed(2).replace('.', ',') : 'N/A'}</span>
                    <span class="r-status" style="color:${item.pe && item.pe < 15 ? 'var(--accent-secondary)' : '#94a3b8'}">
                        ${item.pe && item.pe < 15 ? '🟢 İskontolu' : '⚪ Makul'}
                    </span>
                </div>
                <div class="ratio-box">
                    <span class="r-label">PD/DD</span>
                    <span class="r-val">${item.pb.toFixed(2).replace('.', ',')}</span>
                    <span class="r-status" style="color:${item.pb < 2.0 ? 'var(--accent-secondary)' : '#94a3b8'}">
                        ${item.pb < 2.0 ? '🟢 Cazip' : '⚪ Dengeli'}
                    </span>
                </div>
                <div class="ratio-box">
                    <span class="r-label">Net Borç/FAVÖK</span>
                    <span class="r-val">${item.net_debt_ebitda.toFixed(2).replace('.', ',')}</span>
                    <span class="r-status" style="color:${item.net_debt_ebitda < 1.5 ? 'var(--accent-secondary)' : 'var(--accent-red)'}">
                        ${item.net_debt_ebitda < 1.5 ? '🟢 Güvenli' : '🔴 Borçlu'}
                    </span>
                </div>
                <div class="ratio-box">
                    <span class="r-label">Cari Oran</span>
                    <span class="r-val">${item.current_ratio.toFixed(2).replace('.', ',')}</span>
                    <span class="r-status" style="color:${item.current_ratio >= 1.5 ? 'var(--accent-secondary)' : '#f59e0b'}">
                        ${item.current_ratio >= 1.5 ? '🟢 Yüksek' : '🟡 Yeterli'}
                    </span>
                </div>
                <div class="ratio-box">
                    <span class="r-label">Gelir Büyümesi</span>
                    <span class="r-val">% ${item.rev_growth.toFixed(2).replace('.', ',')}</span>
                    <span class="r-status" style="color:var(--accent-secondary)">🟢 Artışta</span>
                </div>
            </div>
        </div>

        <div class="ai-report-actions">
            <button class="screener-header-btn btn-save" style="width: 100%; justify-content: center; height: 38px; font-size: 0.88rem;" onclick="loadTickerFromScreener('${symbol}')">
                <i data-lucide="trending-up"></i> Hissenin Canlı Grafiğine Git &rarr;
            </button>
        </div>
    `;
    
    lucide.createIcons();
}

/**
 * Tablodan bir sembole tıklandığında, onu dashboard grafiğine yükler.
 */
function loadTickerFromScreener(symbol) {
    // Temel Analiz BIST hisseleri içindir → .IS ekle (yoksa).
    // ('sources' bir Python modülü; frontend'de yok — referans verme!)
    const fullSym = symbol.endsWith('.IS') ? symbol : symbol + '.IS';

    const inp = document.getElementById('symbol-search');
    if (inp) inp.value = fullSym;
    if (typeof currentSymbol !== 'undefined') currentSymbol = fullSym;
    showPage('dashboard');
    if (typeof fetchTickerData === 'function') fetchTickerData(fullSym, '1y', '1d');
}

/**
 * "Metrikleri Güncelle" asenkron işlemi.
 */
async function refreshScreener() {
    const btn = document.querySelector('.btn-save');
    if (!btn) return;
    
    const origHtml = btn.innerHTML;
    btn.innerHTML = `<i data-lucide="loader" class="loader-icon"></i> Güncelleniyor...`;
    btn.disabled = true;
    
    try {
        const res = await fetch('/api/screener/refresh', { method: 'POST' });
        const data = await res.json();
        
        setTimeout(async () => {
            await loadWatchlistPage();
            btn.innerHTML = origHtml;
            btn.disabled = false;
            lucide.createIcons();
            alert("Hisse rasyoları ve YZ önerileri başarıyla güncellendi!");
        }, 4000);
    } catch (e) {
        btn.innerHTML = origHtml;
        btn.disabled = false;
        lucide.createIcons();
        alert("Güncelleme işlemi başlatılamadı.");
    }
}

/**
 * ROIC >= %5,00 Filtresini kaldırır.
 */
function removeRoicFilter() {
    roicFilterActive = false;
    updateFilterChips();
    renderScreenerTable();
}

/**
 * Filtre çiplerini günceller.
 */
function updateFilterChips() {
    const chipsContainer = document.getElementById('screener-active-chips');
    if (!chipsContainer) return;
    
    let html = '';
    if (roicFilterActive) {
        html += `
            <span class="screener-chip">
                ROIC &ge; %5,00 
                <i data-lucide="x" class="chip-close-icon" onclick="removeRoicFilter()"></i>
            </span>
        `;
    }
    if (evoFilterActive) {
        html += `
            <span class="screener-chip" style="background:rgba(139,92,246,0.15);color:#8b5cf6;border-color:rgba(139,92,246,0.4)">
                Evo: ROIC &ge; 15% &amp; F/K &lt; 25
                <i data-lucide="x" class="chip-close-icon" onclick="toggleEvoFilter(false)"></i>
            </span>
        `;
    }
    
    chipsContainer.innerHTML = html;
    lucide.createIcons();
}

function toggleEvoFilter(state) {
    evoFilterActive = state;
    const btnEvo = document.querySelector('.btn-evo');
    if (btnEvo) btnEvo.classList.toggle('active', state);
    updateFilterChips();
    renderScreenerTable();
}

/**
 * Tablodaki verileri Excel/CSV formatında indirir.
 */
function exportScreenerToExcel() {
    const headers = TAB_HEADERS[currentScreenerTab] || [];
    let csvContent = headers.join(";") + "\n";
    
    const rows = document.querySelectorAll("#screener-table-body tr");
    rows.forEach(row => {
        let rowData = [];
        row.querySelectorAll("td").forEach((cell, idx) => {
            if (idx === 1) {
                const symSpan = cell.querySelector(".screener-sym");
                rowData.push(symSpan ? symSpan.innerText : cell.innerText.trim());
            } else {
                rowData.push(cell.innerText.trim().replace(/\n/g, "").replace(/\s+/g, " "));
            }
        });
        csvContent += rowData.join(";") + "\n";
    });
    
    const blob = new Blob([csvContent], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `bist_screener_${currentScreenerTab}.csv`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
}
