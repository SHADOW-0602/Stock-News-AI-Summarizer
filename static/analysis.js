// Global variables
let chartInstance = null;
let financialData = {};
let newsData = [];
let currentNewsPage = 1;
let totalNewsPages = 1;
let currentFinancialView = 'table';

// Load stock basic info
async function loadStockInfo() {
    try {
        // Load company logo
        const logoResponse = await fetch(`/api/logo/${ticker}`);
        if (logoResponse.ok) {
            const logoData = await logoResponse.json();
            if (logoData.image) {
                document.getElementById('stock-logo').innerHTML =
                    `<img src="${logoData.image}" alt="${ticker}" style="width: 100%; height: 100%; object-fit: contain; border-radius: 8px;">`;
            }
            if (logoData.name) {
                document.getElementById('company-name').textContent = logoData.name;
            }
        }

        // Load current price
        const priceResponse = await fetch(`/api/price/${ticker}`);
        if (priceResponse.ok) {
            const priceData = await priceResponse.json();
            document.getElementById('current-price').textContent = `$${priceData.price.toFixed(2)}`;

            const changeElement = document.getElementById('price-change');
            const change = priceData.change;
            const changePercent = priceData.changePercent;

            changeElement.textContent = `${change >= 0 ? '+' : ''}${change.toFixed(2)} (${changePercent.toFixed(2)}%)`;
            changeElement.className = `price-change ${change >= 0 ? 'positive' : 'negative'}`;
        }
    } catch (error) {
        console.error('Error loading stock info:', error);
    }
}

// Chart Tab Functions
async function loadChartData() {
    try {
        console.log(`Loading chart data for ${ticker} with timeframe ${currentTimeframe}`);
        const response = await fetch(`/api/chart-data/${ticker}?period=${currentTimeframe}`);

        if (!response.ok) {
            throw new Error(`API request failed with status ${response.status}`);
        }

        const responseText = await response.text();
        console.log('Raw response:', responseText.substring(0, 200));

        let data;
        try {
            data = JSON.parse(responseText);
        } catch (jsonError) {
            console.error('JSON parsing error:', jsonError);
            console.error('Response text:', responseText.substring(0, 500));
            throw new Error(`Invalid JSON response: ${jsonError.message}`);
        }

        console.log('Chart data received:', data);
        if (data.error) {
            throw new Error(data.error);
        }

        if (!data.prices || data.prices.length === 0) {
            throw new Error('No price data available');
        }

        // Validate price data for NaN values
        const validPrices = data.prices.filter(price => {
            return price.open != null && price.high != null &&
                price.low != null && price.close != null &&
                !isNaN(price.open) && !isNaN(price.high) &&
                !isNaN(price.low) && !isNaN(price.close);
        });

        if (validPrices.length === 0) {
            throw new Error('All price data contains invalid values');
        }

        data.prices = validPrices;
        renderCandlestickChart(data);
        await updateChartStats(data);

        // Show data source info
        const sourceInfo = document.getElementById('chart-source-info');
        if (sourceInfo) {
            sourceInfo.textContent = `Data source: ${data.source || 'Unknown'}`;
        }

    } catch (error) {
        console.error('Error loading chart data:', error);
        console.log('Falling back to sample data');
        const sampleData = generateSampleChartData();
        renderCandlestickChart(sampleData);
        updateChartStats(sampleData);

        // Show error info
        const sourceInfo = document.getElementById('chart-source-info');
        if (sourceInfo) {
            sourceInfo.textContent = `Error: ${error.message} - Using sample data`;
        }
    }
}

function generateSampleChartData() {
    const prices = [];
    let basePrice = 150 + Math.random() * 100;
    const now = new Date();

    for (let i = 30; i >= 0; i--) {
        const date = new Date(now.getTime() - i * 24 * 60 * 60 * 1000);
        const change = (Math.random() - 0.5) * 10;
        basePrice += change;

        prices.push({
            date: date.toISOString(),
            close: basePrice,
            volume: Math.floor(Math.random() * 2000000) + 500000
        });
    }

    return { prices, marketCap: '$50.2B' };
}

function renderChart(data) {
    const ctx = document.getElementById('candlestick-chart').getContext('2d');

    if (chartInstance) {
        chartInstance.destroy();
    }

    const priceData = data.prices.map(item => ({
        x: new Date(item.date),
        y: item.close
    }));

    const datasets = [{
        label: `${ticker} Price`,
        data: priceData,
        borderColor: '#00d4ff',
        backgroundColor: 'rgba(0, 212, 255, 0.1)',
        borderWidth: 2,
        fill: true,
        tension: 0.1
    }];

    chartInstance = new Chart(ctx, {
        type: 'line',
        data: { datasets },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                x: {
                    type: 'time',
                    time: { unit: 'day' },
                    grid: { color: 'rgba(255, 255, 255, 0.1)' },
                    ticks: { color: '#cccccc' }
                },
                y: {
                    grid: { color: 'rgba(255, 255, 255, 0.1)' },
                    ticks: {
                        color: '#cccccc',
                        callback: function (value) {
                            return '$' + value.toFixed(2);
                        }
                    }
                }
            },
            plugins: {
                legend: {
                    labels: { color: '#cccccc' }
                }
            }
        }
    });
}

function renderCandlestickChart(data) {
    if (chartInstance) {
        chartInstance.destroy();
    }

    if (!data || !data.prices || data.prices.length === 0) {
        data = generateSampleChartData();
    }

    // Prepare candlestick data
    const candlestickData = data.prices.map(item => {
        return {
            x: new Date(item.date).getTime(),
            y: [item.open, item.high, item.low, item.close]
        };
    });

    // Prepare volume data
    const volumeData = data.prices.map(item => {
        return {
            x: new Date(item.date).getTime(),
            y: item.volume || 0
        };
    });

    const options = {
        series: [{
            name: 'Price',
            type: 'candlestick',
            data: candlestickData
        }, {
            name: 'Volume',
            type: 'column',
            data: volumeData,
            yAxisIndex: 1
        }],
        chart: {
            type: 'candlestick',
            height: 400,
            background: 'transparent',
            toolbar: {
                show: true,
                tools: {
                    download: true,
                    selection: true,
                    zoom: true,
                    zoomin: true,
                    zoomout: true,
                    pan: true,
                    reset: true
                }
            },
            zoom: {
                enabled: true,
                type: 'x',
                autoScaleYaxis: true
            }
        },
        theme: {
            mode: 'dark'
        },
        title: {
            text: `${ticker} Stock Price`,
            align: 'left',
            style: {
                color: '#ffffff'
            }
        },
        xaxis: {
            type: 'datetime',
            labels: {
                style: {
                    colors: '#cccccc'
                }
            },
            axisBorder: {
                color: '#333'
            },
            axisTicks: {
                color: '#333'
            }
        },
        yaxis: [{
            tooltip: {
                enabled: true
            },
            labels: {
                style: {
                    colors: '#cccccc'
                },
                formatter: function (val) {
                    return '$' + val.toFixed(2);
                }
            }
        }, {
            opposite: true,
            tooltip: {
                enabled: true
            },
            labels: {
                style: {
                    colors: '#cccccc'
                },
                formatter: function (val) {
                    return formatNumber(val);
                }
            }
        }],
        grid: {
            borderColor: '#333',
            strokeDashArray: 3
        },
        plotOptions: {
            candlestick: {
                colors: {
                    upward: '#00d4ff',
                    downward: '#ff6b6b'
                }
            },
            bar: {
                columnWidth: '80%'
            }
        },
        tooltip: {
            theme: 'dark'
        },
        rangeSelector: {
            enabled: true,
            buttons: [
                { text: '1D', timePeriod: 1, timeUnit: 'day' },
                { text: '5D', timePeriod: 5, timeUnit: 'day' },
                { text: '1M', timePeriod: 1, timeUnit: 'month' },
                { text: '3M', timePeriod: 3, timeUnit: 'month' },
                { text: '6M', timePeriod: 6, timeUnit: 'month' },
                { text: '1Y', timePeriod: 1, timeUnit: 'year' },
                { text: 'All', timePeriod: 'all' }
            ]
        }
    };

    chartInstance = new ApexCharts(document.querySelector('#candlestick-chart'), options);
    chartInstance.render();

    console.log('ApexCharts candlestick chart rendered successfully');
}



function generateSampleChartData() {
    console.log('Generating sample chart data');
    const prices = [];
    let basePrice = 150 + Math.random() * 100;
    const now = new Date();

    for (let i = 60; i >= 0; i--) {
        const date = new Date(now.getTime() - i * 24 * 60 * 60 * 1000);
        const change = (Math.random() - 0.5) * 10;
        basePrice = Math.max(10, basePrice + change); // Ensure price stays positive

        prices.push({
            date: date.toISOString().split('T')[0], // YYYY-MM-DD format
            open: Math.max(10, basePrice - Math.random() * 2),
            high: basePrice + Math.random() * 5,
            low: Math.max(5, basePrice - Math.random() * 5),
            close: basePrice,
            volume: Math.floor(Math.random() * 2000000) + 500000
        });
    }

    console.log(`Generated ${prices.length} sample price points`);
    return {
        prices,
        marketCap: '$50.2B',
        source: 'Sample Data (Demo Mode)'
    };
}

async function updateChartStats(data) {
    // Get real stock metrics from Yahoo Finance
    try {
        const response = await fetch(`/api/stock-metrics/${ticker}`);
        if (response.ok) {
            const metrics = await response.json();

            document.getElementById('week-52-high').textContent =
                metrics.week_52_high ? `$${metrics.week_52_high.toFixed(2)}` : '--';
            document.getElementById('week-52-low').textContent =
                metrics.week_52_low ? `$${metrics.week_52_low.toFixed(2)}` : '--';
            document.getElementById('avg-volume').textContent =
                metrics.avg_volume || '--';
        } else {
            // Fallback to chart data if API fails
            const prices = data.prices.map(p => p.close);
            const volumes = data.prices.map(p => p.volume);

            document.getElementById('week-52-high').textContent = `$${Math.max(...prices).toFixed(2)}`;
            document.getElementById('week-52-low').textContent = `$${Math.min(...prices).toFixed(2)}`;
            document.getElementById('avg-volume').textContent = formatNumber(volumes.reduce((a, b) => a + b, 0) / volumes.length);
        }
    } catch (error) {
        console.error('Error fetching stock metrics:', error);
        // Fallback to chart data
        const prices = data.prices.map(p => p.close);
        const volumes = data.prices.map(p => p.volume);

        document.getElementById('week-52-high').textContent = `$${Math.max(...prices).toFixed(2)}`;
        document.getElementById('week-52-low').textContent = `$${Math.min(...prices).toFixed(2)}`;
        document.getElementById('avg-volume').textContent = formatNumber(volumes.reduce((a, b) => a + b, 0) / volumes.length);
    }

    // Market cap from chart data
    document.getElementById('market-cap').textContent = data.marketCap || '--';
}

// News Tab Functions


async function loadNewsData() {
    try {
        const response = await fetch(`/api/summary/${ticker}`);
        if (!response.ok) throw new Error('Failed to load news data');

        const data = await response.json();

        // Update analyst commentary
        if (data.current_summary) {
            const beautifiedSummary = beautifySummary(data.current_summary.summary);
            document.getElementById('analyst-summary').innerHTML = beautifiedSummary;

            // Better date formatting for last updated
            let lastUpdated = new Date().toLocaleDateString();
            if (data.current_summary.created_at || data.current_summary.date) {
                try {
                    const date = new Date(data.current_summary.created_at || data.current_summary.date);
                    if (!isNaN(date.getTime())) {
                        lastUpdated = date.toLocaleDateString();
                    }
                } catch (e) {
                    lastUpdated = new Date().toLocaleDateString();
                }
            }
            document.getElementById('last-updated').textContent = `Last updated: ${lastUpdated}`;

            // Update what changed section
            if (data.current_summary.what_changed) {
                const whatChangedElement = document.getElementById('what-changed-timeline');
                if (whatChangedElement) {
                    const whatChangedContent = decodeHtmlEntities(data.current_summary.what_changed);
                    whatChangedElement.innerHTML = `<div class="timeline-item"><div class="timeline-date">Today</div><div class="timeline-content">${whatChangedContent}</div></div>`;
                    whatChangedElement.classList.add('collapsed');
                }
            }
        } else {
            document.getElementById('analyst-summary').innerHTML = 'Loading AI analysis...';
            document.getElementById('last-updated').textContent = `Last updated: ${new Date().toLocaleDateString()}`;

            // Show loading for what changed section
            const whatChangedElement = document.getElementById('what-changed-timeline');
            if (whatChangedElement) {
                whatChangedElement.innerHTML = '<p style="color: #666; text-align: center; padding: 1rem;">Loading recent changes...</p>';
            }
        }



        // Display 7-day "what changed" history including today
        let historyData = [];
        if (data.current_summary && data.current_summary.what_changed) {
            historyData.push({
                date: data.current_summary.date || new Date().toISOString().split('T')[0],
                what_changed: data.current_summary.what_changed
            });
        }
        if (data.history && data.history.length > 0) {
            historyData = historyData.concat(data.history.slice(0, 6));
        }
        if (historyData.length > 0) {
            renderWhatChangedTimeline(historyData);
        }

        // Load news articles with pagination
        await loadNewsArticles(1);
    } catch (error) {
        console.error('Error loading news data:', error);
        document.getElementById('analyst-summary').innerHTML = 'Unable to load analyst commentary';
    }
}

async function loadNewsArticles(page = 1) {
    try {
        const response = await fetch(`/api/news/${ticker}?page=${page}&per_page=10`);
        if (!response.ok) throw new Error('Failed to load news articles');

        const data = await response.json();
        currentNewsPage = data.pagination.page;
        totalNewsPages = data.pagination.pages;

        renderNewsList(data.articles, data.pagination, data.sources);
        renderNewsPagination(data.pagination);

    } catch (error) {
        console.error('Error loading news articles:', error);
        document.getElementById('news-list').innerHTML =
            '<div style="text-align: center; color: #666; padding: 2rem;">Error loading news articles</div>';
    }
}

function renderNewsList(articles, pagination, sources) {
    const newsList = document.getElementById('news-list');

    if (!articles || articles.length === 0) {
        newsList.innerHTML = '<div style="text-align: center; color: #666; padding: 2rem;">No recent news available</div>';
        return;
    }

    console.log(`Page ${pagination.page}/${pagination.pages}: Displaying ${articles.length} of ${pagination.total} total articles`);
    console.log('Available sources:', Object.keys(sources).join(', '));

    // Add pagination info header
    const paginationInfo = `
        <div class="news-pagination-info">
            <span>Showing ${articles.length} articles (Page ${pagination.page} of ${pagination.pages})</span>
            <span>${pagination.total} total articles from ${Object.keys(sources).length} sources</span>
        </div>
    `;

    const articlesHTML = articles.map(article => {
        const title = decodeHtmlEntities(article.title || 'No title');
        const content = decodeHtmlEntities(article.content || article.summary || '').substring(0, 200) + '...';

        // Use the actual source name, with fallback to 'Financial News' only if truly empty
        let source = article.source;
        if (!source || source.trim() === '' || source === 'Unknown') {
            source = 'Financial News';
        }

        // Better date handling
        let formattedDate = 'Recently';
        if (article.date) {
            try {
                const date = new Date(article.date);
                if (!isNaN(date.getTime())) {
                    const now = new Date();
                    const diffTime = Math.abs(now - date);
                    const diffDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24));

                    if (diffDays === 1) {
                        formattedDate = 'Today';
                    } else if (diffDays === 2) {
                        formattedDate = 'Yesterday';
                    } else if (diffDays <= 7) {
                        formattedDate = `${diffDays - 1} days ago`;
                    } else {
                        formattedDate = date.toLocaleDateString();
                    }
                }
            } catch (e) {
                formattedDate = 'Recently';
            }
        }

        return `
            <div class="news-item">
                <h4>${title}</h4>
                <div class="news-url">
                    <a href="${article.url}" target="_blank" rel="noopener">${article.url}</a>
                </div>
                <div class="news-meta">
                    <span>${source}</span>
                    <span>${formattedDate}</span>
                </div>
            </div>
        `;
    }).join('');

    newsList.innerHTML = paginationInfo + articlesHTML;
}

function renderNewsPagination(pagination) {
    const paginationContainer = document.getElementById('news-pagination');
    if (!paginationContainer) {
        // Create pagination container if it doesn't exist
        const container = document.createElement('div');
        container.id = 'news-pagination';
        container.className = 'news-pagination';
        document.getElementById('news-list').parentNode.appendChild(container);
    }

    if (pagination.pages <= 1) {
        document.getElementById('news-pagination').innerHTML = '';
        return;
    }

    let paginationHTML = '<div class="pagination-controls">';

    // Previous button
    if (pagination.page > 1) {
        paginationHTML += `<button class="pagination-btn" onclick="loadNewsArticles(${pagination.page - 1})">← Previous</button>`;
    }

    // Page numbers
    const startPage = Math.max(1, pagination.page - 2);
    const endPage = Math.min(pagination.pages, pagination.page + 2);

    if (startPage > 1) {
        paginationHTML += `<button class="pagination-btn" onclick="loadNewsArticles(1)">1</button>`;
        if (startPage > 2) {
            paginationHTML += '<span class="pagination-ellipsis">...</span>';
        }
    }

    for (let i = startPage; i <= endPage; i++) {
        const isActive = i === pagination.page ? 'active' : '';
        paginationHTML += `<button class="pagination-btn ${isActive}" onclick="loadNewsArticles(${i})">${i}</button>`;
    }

    if (endPage < pagination.pages) {
        if (endPage < pagination.pages - 1) {
            paginationHTML += '<span class="pagination-ellipsis">...</span>';
        }
        paginationHTML += `<button class="pagination-btn" onclick="loadNewsArticles(${pagination.pages})">${pagination.pages}</button>`;
    }

    // Next button
    if (pagination.page < pagination.pages) {
        paginationHTML += `<button class="pagination-btn" onclick="loadNewsArticles(${pagination.page + 1})">Next →</button>`;
    }

    paginationHTML += '</div>';

    document.getElementById('news-pagination').innerHTML = paginationHTML;
}

function renderWhatChangedTimeline(history) {
    const timelineContainer = document.getElementById('what-changed-timeline');
    if (!timelineContainer) return;

    if (!history || history.length === 0) {
        timelineContainer.innerHTML = '<p style="color: #666; text-align: center; padding: 1rem;">No recent changes tracked</p>';
        return;
    }

    // Filter out duplicate what_changed content
    const uniqueHistory = [];
    const seenContent = new Set();

    for (const item of history.slice(0, 7)) {
        const whatChanged = item.what_changed || 'No changes recorded';
        const contentKey = whatChanged.substring(0, 100); // Use first 100 chars as key

        if (!seenContent.has(contentKey)) {
            seenContent.add(contentKey);
            uniqueHistory.push(item);
        }
    }

    if (uniqueHistory.length === 0) {
        timelineContainer.innerHTML = '<p style="color: #666; text-align: center; padding: 1rem;">No unique changes found</p>';
        return;
    }

    const timelineHTML = uniqueHistory.map((item, index) => {
        const date = new Date(item.date || item.created_at);
        const today = new Date();
        const diffTime = today.getTime() - date.getTime();
        const diffDays = Math.floor(diffTime / (1000 * 60 * 60 * 24));

        let dayLabel;
        if (diffDays === 0) {
            dayLabel = `Today (${date.toLocaleDateString()})`;
        } else if (diffDays === 1) {
            dayLabel = `Yesterday (${date.toLocaleDateString()})`;
        } else {
            dayLabel = `${diffDays} days ago (${date.toLocaleDateString()})`;
        }

        const whatChanged = decodeHtmlEntities(item.what_changed || 'No changes recorded');
        const shortContent = whatChanged.length > 150 ? whatChanged.substring(0, 150) + '...' : whatChanged;

        return `
            <div class="timeline-item" title="${whatChanged.replace(/"/g, '&quot;')}">
                <div class="timeline-date">${dayLabel}</div>
                <div class="timeline-content">${shortContent}</div>
            </div>
        `;
    }).join('');

    timelineContainer.innerHTML = timelineHTML;
}

function categorizeArticle(title, content) {
    return 'general';
}

function decodeHtmlEntities(text) {
    if (!text) return '';
    const textarea = document.createElement('textarea');
    textarea.innerHTML = text;
    let decoded = textarea.value;
    // Additional decoding for common HTML entities
    decoded = decoded.replace(/&amp;/g, '&')
        .replace(/&lt;/g, '<')
        .replace(/&gt;/g, '>')
        .replace(/&quot;/g, '"')
        .replace(/&#39;/g, "'")
        .replace(/&nbsp;/g, ' ');
    return decoded;
}

function beautifySummary(summary) {
    if (!summary) return '';

    let beautified = summary
        // Convert **text** to bold
        .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
        // Convert bullet points to proper list items
        .replace(/^• (.+)$/gm, '<li>$1</li>')
        // Highlight financial metrics with yellow background
        .replace(/(\$[0-9,]+(?:\.[0-9]+)?[BMK]?)/g, '<mark class="highlight">$1</mark>')
        // Highlight percentages
        .replace(/([+-]?[0-9]+(?:\.[0-9]+)?%)/g, '<mark class="highlight">$1</mark>')
        // Highlight price targets and levels
        .replace(/(\$[0-9]+(?:\.[0-9]+)?(?:\s*-\s*\$[0-9]+(?:\.[0-9]+)?)?)/g, '<mark class="highlight">$1</mark>')
        // Convert line breaks to paragraphs
        .replace(/\n\n/g, '</p><p>')
        .replace(/\n/g, '<br>');

    // Wrap in paragraph tags if not already wrapped
    if (!beautified.startsWith('<p>')) {
        beautified = '<p>' + beautified + '</p>';
    }

    // Wrap consecutive list items in ul tags
    beautified = beautified.replace(/(<li>.*?<\/li>)/gs, (match) => {
        return '<ul>' + match + '</ul>';
    });

    return beautified;
}

// Financial Statements Tab Functions
async function loadFinancialData() {
    try {
        const response = await fetch(`/api/financials/${ticker}`);
        if (!response.ok) throw new Error('Failed to load financial data');

        const data = await response.json();
        console.log('Financial API response:', data);

        // Extract the actual financial statements from the API response
        const statements = data.stored_statements || data.statements || [];
        financialData.allStatements = statements;

        // Update UI availability
        updateFinancialAvailability(statements);

        // Cache filtered data
        financialData[`${currentStatement}_${currentPeriod}`] = statements;

        if (currentFinancialView === 'table') {
            renderFinancialTable(statements);
        } else {
            renderFinancialCharts(statements);
        }
    } catch (error) {
        console.error('Error loading financial data:', error);
        document.getElementById('financial-data').innerHTML =
            '<div style="text-align: center; color: #666; padding: 2rem;">Financial data unavailable</div>';
    }
}

function updateFinancialAvailability(statements) {
    // Check availability for each statement type and period
    const statementTypes = ['income', 'balance', 'cashflow'];
    const periods = ['quarterly', 'annual'];

    statementTypes.forEach(type => {
        const btn = document.querySelector(`[data-statement="${type}"]`);
        if (btn) {
            const hasData = statements.some(s => s.statement_type === type);
            btn.style.opacity = hasData ? '1' : '0.5';
            btn.disabled = !hasData;
            if (!hasData) btn.title = `No ${type} data available`;
        }
    });

    periods.forEach(period => {
        const btn = document.querySelector(`[data-period="${period}"]`);
        if (btn) {
            const hasData = statements.some(s => s.period === period);
            btn.style.opacity = hasData ? '1' : '0.5';
            btn.disabled = !hasData;
            if (!hasData) btn.title = `No ${period} data available`;
        }
    });
}

function updateStatementAvailability() {
    if (!financialData.allStatements) return;
    const hasData = financialData.allStatements.some(s =>
        s.statement_type === currentStatement && s.period === currentPeriod
    );
    if (!hasData) {
        // Find first available period for this statement
        const availablePeriod = financialData.allStatements.find(s =>
            s.statement_type === currentStatement
        )?.period;
        if (availablePeriod) {
            currentPeriod = availablePeriod;
            document.querySelector(`[data-period="${availablePeriod}"]`).click();
        }
    }
}

function updatePeriodAvailability() {
    if (!financialData.allStatements) return;
    const hasData = financialData.allStatements.some(s =>
        s.statement_type === currentStatement && s.period === currentPeriod
    );
    if (!hasData) {
        // Find first available statement for this period
        const availableStatement = financialData.allStatements.find(s =>
            s.period === currentPeriod
        )?.statement_type;
        if (availableStatement) {
            currentStatement = availableStatement;
            document.querySelector(`[data-statement="${availableStatement}"]`).click();
        }
    }
}



function renderFinancialTable(data) {
    const container = document.getElementById('financial-data');
    const showChanges = true;

    console.log('Rendering financial table with data:', data);

    if (!data || data.length === 0) {
        container.innerHTML = '<div style="text-align: center; color: #666; padding: 2rem;">No financial data available</div>';
        return;
    }

    if (data.error) {
        container.innerHTML = `
            <div style="text-align: center; padding: 2rem;">
                <div style="color: #ef4444; margin-bottom: 1rem; font-weight: 600;">⚠️ ${data.error}</div>
                <div style="color: #666; font-size: 0.9rem;">${data.message || 'Please try a different ticker or check back later.'}</div>
            </div>
        `;
        return;
    }

    // Filter data by current statement type and period
    let filteredData = data.filter(item =>
        item.statement_type === currentStatement &&
        item.period === currentPeriod
    );

    if (filteredData.length === 0) {
        container.innerHTML = `<div style="text-align: center; color: #666; padding: 2rem;">No ${currentStatement} ${currentPeriod} data available</div>`;
        return;
    }

    // Sort by fiscal date (most recent first)
    filteredData.sort((a, b) => new Date(b.fiscal_date) - new Date(a.fiscal_date));

    // Extract financial data from each record
    const reports = filteredData.map(item => {
        const financialData = typeof item.data === 'string' ? JSON.parse(item.data) : item.data;
        return {
            ...financialData,
            fiscalDateEnding: item.fiscal_date
        };
    });

    if (reports.length === 0) {
        container.innerHTML = '<div style="text-align: center; color: #666; padding: 2rem;">No financial reports found</div>';
        return;
    }

    // Get metrics that have data in ALL reports to avoid empty columns
    const firstReport = reports[0];
    const potentialMetrics = Object.keys(firstReport).filter(key =>
        !['fiscalDateEnding', 'reportedCurrency', 'symbol'].includes(key)
    );

    const metrics = potentialMetrics.filter(metric => {
        // Only include metrics that have at least one non-empty value across all reports
        return reports.some(report => {
            const value = report[metric];
            return value !== null && value !== 'None' && value !== undefined && value !== '' && value !== 0;
        });
    });

    if (metrics.length === 0) {
        container.innerHTML = '<div style="text-align: center; color: #666; padding: 2rem;">No valid financial metrics found</div>';
        return;
    }

    // Filter out periods that have no data for any metric
    const periodsWithData = [];
    const reportsWithData = [];

    reports.forEach((report, index) => {
        const hasData = metrics.some(metric => {
            const value = report[metric];
            return value !== null && value !== 'None' && value !== undefined && value !== '' && !isNaN(parseFloat(value));
        });

        if (hasData) {
            periodsWithData.push(report.fiscalDateEnding ? report.fiscalDateEnding.substring(0, 7) : 'Unknown');
            reportsWithData.push(report);
        }
    });

    let tableHTML = `
        <div style="margin-bottom: 1rem; color: #ccc; font-size: 0.9rem;">
            Showing ${currentStatement} statements (${currentPeriod}) - ${periodsWithData.length} periods
        </div>
        <table class="financial-table">
            <thead>
                <tr>
                    <th>Metric</th>
                    ${periodsWithData.map(period => `<th>${period}</th>`).join('')}
                    ${currentPeriod === 'quarterly' ? '<th>TTM</th>' : ''}
                </tr>
            </thead>
            <tbody>
    `;

    // Define important financial metrics in order of priority
    const priorityMetrics = [
        'totalRevenue', 'revenue', 'totalOperatingRevenues',
        'netIncome', 'netIncomeFromContinuingOps', 'netIncomeCommonStockholders',
        'grossProfit', 'operatingIncome', 'ebit', 'ebitda',
        'totalAssets', 'totalStockholderEquity', 'totalDebt',
        'operatingCashFlow', 'freeCashFlow', 'capitalExpenditures',
        'eps', 'dilutedEPS', 'basicEPS'
    ];

    // Get available metrics in priority order
    const availableMetrics = priorityMetrics.filter(metric => metrics.includes(metric));
    const otherMetrics = metrics.filter(metric => !priorityMetrics.includes(metric));
    const importantMetrics = [...availableMetrics, ...otherMetrics].slice(0, 15);

    importantMetrics.forEach(metric => {
        const values = reportsWithData.map(report => {
            const value = report[metric];
            if (value === null || value === undefined || value === 'None' || value === '') {
                return null;
            }
            const numValue = parseFloat(value);
            return isNaN(numValue) || numValue === 0 ? null : numValue;
        });

        // Skip metrics where all values are null in periods with data
        if (values.every(v => v === null)) return;

        // Calculate TTM value - for annual data, hide TTM column since it would be same as latest year
        let ttmValue = '--';
        if (currentPeriod === 'quarterly' && values.length >= 4) {
            const last4Quarters = values.slice(0, 4).filter(v => v !== null);
            if (last4Quarters.length === 4) {
                ttmValue = formatFinancialNumber(last4Quarters.reduce((sum, val) => sum + val, 0));
            }
        }

        // Calculate change between periods
        const latestChange = values.length > 1 && values[1] !== null && values[0] !== null && values[1] !== 0 ?
            ((values[0] - values[1]) / Math.abs(values[1]) * 100).toFixed(1) : '--';

        tableHTML += `
            <tr>
                <td><strong>${formatMetricName(metric)}</strong><br><small style="color: #666;">YoY Growth</small></td>
                ${values.map((value, index) => {
            let changeHtml = '';
            if (index === 0 && values.length > 1 && values[1] !== null && value !== null && values[1] !== 0) {
                // First column: compare with next period (previous year)
                const change = ((value - values[1]) / Math.abs(values[1]) * 100).toFixed(1);
                changeHtml = `<div class="yoy-change ${change >= 0 ? 'positive' : 'negative'}">${change >= 0 ? '+' : ''}${change}%</div>`;
            } else if (index > 0 && index < values.length - 1 && values[index + 1] !== null && value !== null && values[index + 1] !== 0) {
                // Other columns: compare with next period (previous year)
                const change = ((value - values[index + 1]) / Math.abs(values[index + 1]) * 100).toFixed(1);
                changeHtml = `<div class="yoy-change ${change >= 0 ? 'positive' : 'negative'}">${change >= 0 ? '+' : ''}${change}%</div>`;
            }
            return `<td>
                                <div>${value === null || value === 0 ? '--' : formatFinancialNumber(value)}</div>
                                ${changeHtml}
                            </td>`;
        }).join('')}
                ${currentPeriod === 'quarterly' ? `<td class="${ttmValue !== '--' ? 'positive' : 'negative'}">${ttmValue}</td>` : ''}
            </tr>
        `;
    });

    tableHTML += '</tbody></table>';
    container.innerHTML = tableHTML;
}

function renderFinancialCharts(data) {
    console.log(`Rendering charts for ${currentStatement} ${currentPeriod}`);

    // Filter data by current statement type and period
    let filteredData = data.filter(item =>
        item.statement_type === currentStatement &&
        item.period === currentPeriod
    );

    if (filteredData.length === 0) {
        document.getElementById('financial-data').innerHTML =
            `<div style="text-align: center; color: #666; padding: 2rem;">No ${currentStatement} ${currentPeriod} chart data available</div>`;
        return;
    }

    // Extract financial data and create charts based on statement type
    const reports = filteredData.map(item => {
        const financialData = typeof item.data === 'string' ? JSON.parse(item.data) : item.data;
        return {
            ...financialData,
            fiscalDate: item.fiscal_date
        };
    }).sort((a, b) => new Date(a.fiscalDate) - new Date(b.fiscalDate));

    // Get all available metrics from the data and find the best matches
    const allMetrics = new Set();
    reports.forEach(report => {
        Object.keys(report).forEach(key => {
            if (key !== 'fiscalDate' && key !== 'fiscalDateEnding') {
                allMetrics.add(key);
            }
        });
    });

    console.log('Available metrics:', Array.from(allMetrics));

    // Define flexible metric patterns based on statement type
    let metricPatterns = [];
    if (currentStatement === 'income') {
        metricPatterns = [
            ['Total Revenue', 'totalRevenue', 'revenue', 'Revenue'],
            ['Net Income', 'netIncome', 'Net Income Common Stockholders'],
            ['Gross Profit', 'grossProfit', 'Gross Profit'],
            ['Operating Income', 'operatingIncome', 'Operating Income']
        ];
    } else if (currentStatement === 'balance') {
        metricPatterns = [
            ['Total Assets', 'totalAssets', 'Total Assets'],
            ['Total Stockholder Equity', 'totalStockholderEquity', 'Stockholders Equity', 'Total Equity Gross Minority Interest'],
            ['Total Debt', 'totalDebt', 'Total Debt', 'Net Debt'],
            ['Total Current Assets', 'totalCurrentAssets', 'Current Assets']
        ];
    } else if (currentStatement === 'cashflow') {
        metricPatterns = [
            ['Operating Cash Flow', 'operatingCashFlow', 'Operating Cash Flow', 'Cash Flow From Continuing Operating Activities'],
            ['Free Cash Flow', 'freeCashFlow', 'Free Cash Flow'],
            ['Capital Expenditures', 'capitalExpenditures', 'Capital Expenditure'],
            ['Net Cash Flow', 'netCashFlow', 'Changes In Cash']
        ];
    }

    // Find actual metrics that match our patterns
    const metricsToChart = [];
    metricPatterns.forEach(patterns => {
        for (const pattern of patterns) {
            if (allMetrics.has(pattern)) {
                metricsToChart.push(pattern);
                break;
            }
        }
    });

    // Filter metrics that actually exist in the data with valid values
    const availableMetrics = metricsToChart.filter(metric =>
        reports.some(report => {
            const value = report[metric];
            return value !== null && value !== undefined && value !== 0 && value !== 'None' && !isNaN(parseFloat(value));
        })
    );

    console.log('Metrics to chart:', metricsToChart);
    console.log('Available metrics with data:', availableMetrics);

    if (availableMetrics.length === 0) {
        document.getElementById('financial-data').innerHTML =
            `<div style="text-align: center; color: #666; padding: 2rem;">No chartable metrics found for ${currentStatement}</div>`;
        return;
    }

    // Create chart HTML
    const chartHTML = `
        <div style="margin-bottom: 1rem; color: #ccc; font-size: 0.9rem;">
            ${currentStatement.charAt(0).toUpperCase() + currentStatement.slice(1)} Statement Charts (${currentPeriod})
        </div>
        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 2rem;">
            ${availableMetrics.map(metric => `
                <div style="background: rgba(255, 255, 255, 0.03); border-radius: 8px; padding: 1rem;">
                    <h4 style="color: #00d4ff; margin-bottom: 1rem;">${formatMetricName(metric)}</h4>
                    <div style="height: 300px;"><canvas id="chart-${metric}"></canvas></div>
                </div>
            `).join('')}
        </div>
    `;

    document.getElementById('financial-data').innerHTML = chartHTML;

    // Wait for DOM to update, then create charts
    setTimeout(() => {
        availableMetrics.forEach(metric => {
            const canvas = document.getElementById(`chart-${metric}`);
            if (!canvas) {
                console.error(`Canvas not found for metric: ${metric}`);
                return;
            }

            const ctx = canvas.getContext('2d');
            const chartData = reports.map(report => {
                const value = parseFloat(report[metric]);
                return {
                    x: report.fiscalDate,
                    y: isNaN(value) ? 0 : value
                };
            }).filter(point => point.y !== 0);

            if (chartData.length === 0) {
                console.log(`No valid data for ${metric}`);
                return;
            }

            try {
                new Chart(ctx, {
                    type: 'line',
                    data: {
                        labels: chartData.map(point => point.x),
                        datasets: [{
                            label: formatMetricName(metric),
                            data: chartData.map(point => point.y),
                            borderColor: '#00d4ff',
                            backgroundColor: 'rgba(0, 212, 255, 0.1)',
                            borderWidth: 2,
                            fill: true,
                            tension: 0.1
                        }]
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        layout: {
                            padding: 10
                        },
                        scales: {
                            x: {
                                grid: { color: 'rgba(255, 255, 255, 0.1)' },
                                ticks: { color: '#cccccc' }
                            },
                            y: {
                                grid: { color: 'rgba(255, 255, 255, 0.1)' },
                                ticks: {
                                    color: '#cccccc',
                                    callback: function (value) {
                                        return formatFinancialNumber(value);
                                    }
                                }
                            }
                        },
                        plugins: {
                            legend: {
                                labels: { color: '#cccccc' }
                            }
                        }
                    }
                });
                console.log(`Chart created successfully for ${metric}`);
            } catch (error) {
                console.error(`Error creating chart for ${metric}:`, error);
            }
        });
    }, 100);
}

// Trade Ideas Tab Functions
async function loadTradeIdeas() {
    try {
        const response = await fetch(`/api/trade-ideas/${ticker}`);
        if (response.ok) {
            const ideas = await response.json();
            renderTradeIdeas(ideas);
            setTimeout(initPexelsImages, 100);
        }
    } catch (error) {
        console.error('Error loading trade ideas:', error);
        document.getElementById('ml-recommendations').innerHTML =
            '<div style="text-align: center; color: #666; padding: 2rem;">Error loading ML analysis</div>';
    }
}

function renderTradeIdeas(data) {
    const container = document.getElementById('ml-recommendations');

    if (!data || data.status === 'coming_soon') {
        container.innerHTML = generateMLAnalysis();
    } else if (data.status === 'real_data') {
        container.innerHTML = generateRealMLAnalysis(data);
    } else if (data.status === 'ml_generated') {
        container.innerHTML = generateAdvancedMLAnalysis(data);
    } else {
        container.innerHTML = data.recommendations.map(rec => `
            <div class="ml-recommendation">
                <h4>${rec.strategy}</h4>
                <p>${rec.description}</p>
                <div class="rec-metrics">
                    <span>Confidence: ${rec.confidence}%</span>
                    <span>Expected Return: ${rec.expectedReturn}%</span>
                </div>
            </div>
        `).join('');
    }
}

function generateAdvancedMLAnalysis(data) {
    // Handle error case when no price data is available
    if (data.status === 'error') {
        return `
            <div class="ml-dashboard">
                <div class="ml-section">
                    <h4><img src="" data-pexels="warning alert sign" alt="Warning" style="width: 24px; height: 24px; vertical-align: middle; margin-right: 8px;"> Trade Ideas Unavailable</h4>
                    <div style="text-align: center; padding: 2rem; color: #ef4444;">
                        <p><strong>Price data unavailable for ${ticker}</strong></p>
                        <p style="color: #666; margin-top: 1rem;">Unable to generate trade ideas without current price information. Please try again later or verify the ticker symbol.</p>
                    </div>
                </div>
            </div>
        `;
    }

    return `
        <div class="ml-dashboard">
            <div class="ml-section">
                <h4>🤖 Advanced ML Trade Ideas</h4>
                <div class="trade-ideas-list">
                    ${data.trade_ideas.map(idea => `
                        <div class="trade-idea-card">
                            ${idea.image ? `<div class="idea-image"><img src="${idea.image}" alt="${idea.strategy}" /></div>` : ''}
                            <div class="idea-header">
                                <span class="strategy-name">${idea.strategy}</span>
                                <span class="action-badge ${idea.action.toLowerCase().replace('/', '-')}">${idea.action}</span>
                            </div>
                            <div class="idea-content">
                                <p class="reasoning">${idea.reasoning}</p>
                                <div class="idea-metrics">
                                    <span>Confidence: ${idea.confidence}</span>
                                    <span>Timeframe: ${idea.timeframe}</span>
                                    ${idea.risk_reward ? `<span>R/R: ${idea.risk_reward}</span>` : ''}
                                </div>
                                <div class="price-levels">
                                    ${idea.entry_price ? `<span>Entry: $${parseFloat(idea.entry_price).toFixed(2)}</span>` : ''}
                                    ${idea.target_price ? `<span>Target: $${parseFloat(idea.target_price).toFixed(2)}</span>` : ''}
                                    ${idea.target_price_low ? `<span> / $${parseFloat(idea.target_price_low).toFixed(2)}</span>` : ''}
                                    ${idea.stop_loss ? `<span>Stop: $${parseFloat(idea.stop_loss).toFixed(2)}</span>` : ''}
                                </div>
                            </div>
                        </div>
                    `).join('')}
                </div>
            </div>
            
            <div class="ml-section">
                <h4>📊 ML Technical Analysis</h4>
                <div class="idea-image">
                    <img src="" data-pexels="stock market technical analysis charts" alt="Technical Analysis" />
                </div>
                <div class="ml-analysis-summary">
                    ${data.technical_analysis.ml_forecast ? `
                        <div class="forecast-item">
                            <span>ML Price Forecast:</span>
                            <span class="${data.technical_analysis.ml_forecast.change_percent >= 0 ? 'positive' : 'negative'}">
                                ${data.technical_analysis.ml_forecast.change_percent > 0 ? '+' : ''}${data.technical_analysis.ml_forecast.change_percent.toFixed(1)}%
                            </span>
                        </div>
                    ` : ''}
                    ${data.technical_analysis.sentiment ? `
                        <div class="sentiment-item">
                            <span>News Sentiment:</span>
                            <span class="sentiment-${data.technical_analysis.sentiment.sentiment.toLowerCase()}">
                                ${data.technical_analysis.sentiment.sentiment} (${data.technical_analysis.sentiment.score.toFixed(2)})
                            </span>
                        </div>
                    ` : ''}
                    <div class="signal-item">
                        <span>Overall Signal:</span>
                        <span class="signal-${data.technical_analysis.overall_signal.toLowerCase()}">
                            ${data.technical_analysis.overall_signal}
                        </span>
                    </div>
                </div>
            </div>
            
            <div class="ml-section">
                <h4>⚠️ Risk Assessment</h4>
                <div class="idea-image">
                    <img src="" data-pexels="financial risk management warning" alt="Risk Assessment" />
                </div>
                <div class="risk-assessment">
                    <div class="risk-level">
                        <span class="risk-badge ${data.risk_assessment.level.toLowerCase()}">
                            ${data.risk_assessment.level} RISK
                        </span>
                    </div>
                    <p class="risk-reason">${data.risk_assessment.reason}</p>
                </div>
            </div>
            
            <div class="ml-disclaimer">
                <p><strong>Advanced ML Analysis:</strong> Based on machine learning models and sentiment analysis. Not financial advice.</p>
            </div>
        </div>
    `;
}

function generateRealMLAnalysis(data) {
    return `
        <div class="ml-dashboard">
            <div class="ml-section">
                <h4>📊 Technical Analysis (Real Data)</h4>
                <div class="technical-signals">
                    ${data.technical_signals.map(signal => `
                        <div class="signal-item">
                            <span class="signal-name">${signal.name}</span>
                            <span class="signal-value">${signal.value}</span>
                            <span class="signal-indicator ${signal.signal.toLowerCase()}">${signal.signal}</span>
                        </div>
                        <div class="signal-reason">${signal.reason}</div>
                    `).join('')}
                </div>
            </div>
            
            <div class="ml-section">
                <h4>💰 Current Price Data</h4>
                <div class="price-info">
                    <div class="price-item">
                        <span>Current Price:</span>
                        <span>$${data.current_price ? data.current_price.toFixed(2) : '--'}</span>
                    </div>
                    <div class="price-item">
                        <span>Daily Change:</span>
                        <span class="${data.price_change >= 0 ? 'positive' : 'negative'}">
                            ${data.price_change ? data.price_change.toFixed(2) + '%' : '--'}
                        </span>
                    </div>
                </div>
            </div>
            
            <div class="ml-section">
                <h4>⚠️ Risk Assessment</h4>
                <div class="risk-metrics">
                    <div class="risk-item">
                        <span>Risk Level:</span>
                        <span class="risk-badge ${data.risk_level.toLowerCase()}">${data.risk_level}</span>
                    </div>
                </div>
            </div>
            
            <div class="ml-section recommendation-section">
                <h4>🎯 Technical Recommendation</h4>
                <div class="recommendation-card">
                    <div class="rec-header">
                        <span class="rec-action ${data.recommendation.toLowerCase()}">${data.recommendation}</span>
                        <span class="confidence-score">${data.confidence}% Confidence</span>
                    </div>
                    <p class="rec-reasoning">
                        Based on real technical indicators: ${data.technical_signals.length} signals analyzed.
                    </p>
                </div>
            </div>
            
            <div class="ml-disclaimer">
                <p><strong>Real Data:</strong> Based on Alpha Vantage technical indicators. Not financial advice.</p>
            </div>
        </div>
    `;
}

function generateMLAnalysis() {
    const technicalSignals = [
        { name: 'RSI (14)', value: Math.floor(Math.random() * 40) + 30, signal: 'NEUTRAL' },
        { name: 'MACD', value: (Math.random() - 0.5) * 2, signal: Math.random() > 0.5 ? 'BULLISH' : 'BEARISH' },
        { name: 'Moving Average', value: Math.random() > 0.6 ? 'ABOVE' : 'BELOW', signal: Math.random() > 0.5 ? 'BULLISH' : 'BEARISH' }
    ];

    const sentimentScore = Math.floor(Math.random() * 40) + 30;
    const riskLevel = ['LOW', 'MEDIUM', 'HIGH'][Math.floor(Math.random() * 3)];
    const recommendation = ['BUY', 'HOLD', 'SELL'][Math.floor(Math.random() * 3)];

    return `
        <div class="ml-dashboard">
            <div class="ml-section">
                <h4>📊 Technical Analysis</h4>
                <div class="technical-signals">
                    ${technicalSignals.map(signal => `
                        <div class="signal-item">
                            <span class="signal-name">${signal.name}</span>
                            <span class="signal-value">${typeof signal.value === 'number' ? signal.value.toFixed(2) : signal.value}</span>
                            <span class="signal-indicator ${signal.signal.toLowerCase()}">${signal.signal}</span>
                        </div>
                    `).join('')}
                </div>
            </div>
            
            <div class="ml-section">
                <h4>🧠 Sentiment Analysis</h4>
                <div class="sentiment-gauge">
                    <div class="gauge-container">
                        <div class="gauge-fill" style="width: ${sentimentScore}%"></div>
                    </div>
                    <span class="sentiment-score">${sentimentScore}/100</span>
                </div>
                <p class="sentiment-text">${sentimentScore > 60 ? 'Positive market sentiment detected' : sentimentScore > 40 ? 'Neutral market sentiment' : 'Negative market sentiment detected'}</p>
            </div>
            
            <div class="ml-section">
                <h4>⚠️ Risk Assessment</h4>
                <div class="risk-metrics">
                    <div class="risk-item">
                        <span>Risk Level:</span>
                        <span class="risk-badge ${riskLevel.toLowerCase()}">${riskLevel}</span>
                    </div>
                    <div class="risk-item">
                        <span>Volatility:</span>
                        <span>${(Math.random() * 30 + 10).toFixed(1)}%</span>
                    </div>
                    <div class="risk-item">
                        <span>Beta:</span>
                        <span>${(Math.random() * 1.5 + 0.5).toFixed(2)}</span>
                    </div>
                </div>
            </div>
            
            <div class="ml-section recommendation-section">
                <h4>🎯 ML Recommendation</h4>
                <div class="recommendation-card">
                    <div class="rec-header">
                        <span class="rec-action ${recommendation.toLowerCase()}">${recommendation}</span>
                        <span class="confidence-score">${Math.floor(Math.random() * 30) + 60}% Confidence</span>
                    </div>
                    <p class="rec-reasoning">
                        ${recommendation === 'BUY' ? 'Technical indicators suggest upward momentum with positive sentiment support.' :
            recommendation === 'SELL' ? 'Risk factors and negative sentiment indicate potential downside.' :
                'Mixed signals suggest maintaining current position until clearer trend emerges.'}
                    </p>
                    <div class="price-targets">
                        <span>Entry: $${(Math.random() * 20 + 90).toFixed(2)}</span>
                        <span>Target: $${(Math.random() * 50 + 100).toFixed(2)}</span>
                        <span>Stop: $${(Math.random() * 30 + 80).toFixed(2)}</span>
                    </div>
                </div>
            </div>
            
            <div class="ml-disclaimer">
                <p><strong>Disclaimer:</strong> This is a simulated ML analysis for demonstration. Not financial advice.</p>
            </div>
        </div>
    `;
}

// Add CSS for pagination and ML trade ideas
const style = document.createElement('style');
style.textContent = `
    .trade-ideas-list {
        display: flex;
        flex-direction: column;
        gap: 1rem;
    }
    .trade-idea-card {
        background: rgba(255, 255, 255, 0.03);
        border-radius: 8px;
        padding: 1rem;
        border-left: 4px solid #00d4ff;
        position: relative;
        overflow: hidden;
    }
    .idea-image {
        width: 100%;
        height: 120px;
        margin-bottom: 1rem;
        border-radius: 6px;
        overflow: hidden;
    }
    .idea-image img {
        width: 100%;
        height: 100%;
        object-fit: cover;
        opacity: 0.8;
    }
    .idea-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 0.5rem;
    }
    .strategy-name {
        font-weight: 600;
        color: #00d4ff;
    }
    .action-badge {
        padding: 0.2rem 0.6rem;
        border-radius: 12px;
        font-size: 0.8rem;
        font-weight: 600;
    }
    .action-badge.buy { background: rgba(34, 197, 94, 0.2); color: #22c55e; }
    .action-badge.sell-short { background: rgba(239, 68, 68, 0.2); color: #ef4444; }
    .action-badge.hold { background: rgba(156, 163, 175, 0.2); color: #9ca3af; }
    .action-badge.straddle { background: rgba(251, 191, 36, 0.2); color: #fbbf24; }
    .action-badge.wait-avoid { background: rgba(156, 163, 175, 0.2); color: #9ca3af; }
    .reasoning {
        margin: 0.5rem 0;
        font-size: 0.9rem;
        line-height: 1.4;
    }
    .idea-metrics, .price-levels {
        display: flex;
        gap: 1rem;
        font-size: 0.8rem;
        color: #ccc;
        margin-top: 0.5rem;
    }
    .ml-analysis-summary {
        display: flex;
        flex-direction: column;
        gap: 0.5rem;
    }
    .forecast-item, .sentiment-item, .signal-item {
        display: flex;
        justify-content: space-between;
        align-items: center;
        padding: 0.5rem;
        background: rgba(255, 255, 255, 0.03);
        border-radius: 4px;
    }
    .sentiment-bullish { color: #22c55e; }
    .sentiment-bearish { color: #ef4444; }
    .sentiment-neutral { color: #9ca3af; }
    .signal-bullish { color: #22c55e; }
    .signal-bearish { color: #ef4444; }
    .signal-neutral { color: #9ca3af; }
    .risk-assessment {
        text-align: center;
    }
    .risk-level {
        margin-bottom: 0.5rem;
    }
    .risk-reason {
        font-size: 0.9rem;
        color: #ccc;
    }
    .signal-reason {
        font-size: 0.8rem;
        color: #888;
        margin-left: 1rem;
        margin-bottom: 0.5rem;
    }
    .price-info {
        display: flex;
        flex-direction: column;
        gap: 0.5rem;
    }
    .price-item {
        display: flex;
        justify-content: space-between;
        align-items: center;
    }
    .positive {
        color: #22c55e;
    }
    .negative {
        color: #ef4444;
    }
    .news-pagination-info {
        display: flex;
        justify-content: space-between;
        align-items: center;
        padding: 1rem;
        background: rgba(255, 255, 255, 0.03);
        border-radius: 8px;
        margin-bottom: 1rem;
        font-size: 0.9rem;
        color: #ccc;
    }
    .news-pagination {
        margin-top: 2rem;
    }
    .timeline-item {
        margin-bottom: 1.5rem;
        padding-bottom: 1rem;
        border-bottom: 1px solid rgba(255, 255, 255, 0.1);
    }
    .timeline-item:last-child {
        border-bottom: none;
        margin-bottom: 0;
    }
    .timeline-date {
        font-weight: 600;
        color: #00d4ff;
        margin-bottom: 0.5rem;
        font-size: 0.9rem;
    }
    .timeline-content {
        line-height: 1.5;
        color: #ccc;
    }
    .timeline-item {
        cursor: help;
        padding: 0.75rem;
        border-radius: 8px;
        transition: all 0.3s ease;
        position: relative;
    }
    .timeline-item:hover {
        background: rgba(0, 212, 255, 0.1);
        border-left: 3px solid #00d4ff;
        transform: translateX(5px);
        box-shadow: 0 4px 12px rgba(0, 212, 255, 0.2);
    }
    .timeline-item:hover .timeline-date {
        color: #ffffff;
        font-weight: 700;
    }
    .timeline-item:hover .timeline-content {
        color: #ffffff;
    }
    .pagination-controls {
        display: flex;
        justify-content: center;
        align-items: center;
        gap: 0.5rem;
        flex-wrap: wrap;
    }
    .pagination-btn {
        padding: 0.5rem 1rem;
        background: rgba(255, 255, 255, 0.1);
        border: 1px solid rgba(255, 255, 255, 0.2);
        border-radius: 6px;
        color: #ccc;
        cursor: pointer;
        transition: all 0.2s ease;
        font-size: 0.9rem;
    }
    .pagination-btn:hover {
        background: rgba(0, 212, 255, 0.2);
        border-color: #00d4ff;
        color: #00d4ff;
    }
    .pagination-btn.active {
        background: #00d4ff;
        border-color: #00d4ff;
        color: #000;
        font-weight: 600;
    }
    .pagination-btn:disabled {
        opacity: 0.5;
        cursor: not-allowed;
    }
    .pagination-ellipsis {
        color: #666;
        padding: 0.5rem;
    }
`;
document.head.appendChild(style);

// Load Pexels images
async function loadPexelsImage(query, imgElement) {
    try {
        const response = await fetch(`/api/pexels-image?query=${encodeURIComponent(query)}`);
        if (response.ok) {
            const data = await response.json();
            if (data.image) {
                imgElement.src = data.image;
            }
        }
    } catch (error) {
        console.log('Pexels image load failed:', error);
    }
}

// Initialize Pexels images
function initPexelsImages() {
    document.querySelectorAll('[data-pexels]').forEach(img => {
        const query = img.getAttribute('data-pexels');
        loadPexelsImage(query, img);
    });
}

// Event Listeners
document.addEventListener('DOMContentLoaded', () => {
    initPexelsImages();
    // Timeframe selector
    document.querySelectorAll('.timeframe-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('.timeframe-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            currentTimeframe = btn.dataset.period;
            loadChartData();
        });
    });

    // Statement selector with availability check
    document.querySelectorAll('.statement-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('.statement-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            currentStatement = btn.dataset.statement;
            updateStatementAvailability();
            loadFinancialData();
        });
    });

    // Period selector with availability check
    document.querySelectorAll('.period-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('.period-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            currentPeriod = btn.dataset.period;
            updatePeriodAvailability();
            loadFinancialData();
        });
    });



    // View selector
    document.querySelectorAll('.view-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('.view-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            currentFinancialView = btn.dataset.view;

            const statements = financialData.allStatements || financialData[`${currentStatement}_${currentPeriod}`] || [];
            if (currentFinancialView === 'table') {
                renderFinancialTable(statements);
            } else {
                renderFinancialCharts(statements);
            }
        });
    });







    // Refresh analysis
    document.getElementById('refresh-analysis').addEventListener('click', async () => {
        const btn = document.getElementById('refresh-analysis');
        btn.textContent = '🔄 Refreshing...';
        btn.disabled = true;

        try {
            const response = await fetch(`/api/refresh/${ticker}`);
            if (response.ok) {
                await loadNewsData();
            } else {
                console.error('Refresh failed:', await response.text());
            }
        } catch (error) {
            console.error('Error refreshing analysis:', error);
        } finally {
            btn.textContent = '🔄 Refresh Analysis';
            btn.disabled = false;
        }
    });

    // Refresh chart
    document.getElementById('refresh-chart').addEventListener('click', async () => {
        const btn = document.getElementById('refresh-chart');
        btn.textContent = '🔄 Refreshing...';
        btn.disabled = true;

        try {
            // Clear chart cache by adding timestamp
            const response = await fetch(`/api/chart-data/${ticker}?period=${currentTimeframe}&refresh=${Date.now()}`);
            if (response.ok) {
                const data = await response.json();
                renderCandlestickChart(data);
                updateChartStats(data);
            } else {
                console.error('Chart refresh failed:', await response.text());
            }
        } catch (error) {
            console.error('Error refreshing chart:', error);
        } finally {
            btn.textContent = '🔄 Refresh';
            btn.disabled = false;
        }
    });

    // Make loadNewsArticles globally available
    window.loadNewsArticles = loadNewsArticles;
});

// Utility Functions
function formatNumber(num) {
    if (num >= 1e9) return (num / 1e9).toFixed(1) + 'B';
    if (num >= 1e6) return (num / 1e6).toFixed(1) + 'M';
    if (num >= 1e3) return (num / 1e3).toFixed(1) + 'K';
    return num.toFixed(0);
}

function formatFinancialNumber(num) {
    if (Math.abs(num) >= 1e9) return '$' + (num / 1e9).toFixed(2) + 'B';
    if (Math.abs(num) >= 1e6) return '$' + (num / 1e6).toFixed(2) + 'M';
    if (Math.abs(num) >= 1e3) return '$' + (num / 1e3).toFixed(2) + 'K';
    return '$' + num.toFixed(2);
}

function formatMetricName(metric) {
    return metric.replace(/([A-Z])/g, ' $1')
        .replace(/^./, str => str.toUpperCase())
        .trim();
}

