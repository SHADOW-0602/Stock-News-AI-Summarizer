class StockNewsApp {
    constructor() {
        this.currentTicker = null;
        this.chartListenersSet = false;
        this.init();
    }

    init() {
        this.bindEvents();
        this.loadTickers();
        this.loadMarketWidget();
    }

    async loadMarketWidget() {
        try {
            const response = await fetch('/api/market-status');
            if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
            const data = await response.json();

            const widget = document.getElementById('market-widget');
            if (data.market) {
                const statusClass = data.market.is_open ? 'open' : 'closed';
                const statusText = data.market.is_open ? 'OPEN' : 'CLOSED';

                widget.innerHTML = `
                    <div class="market-status ${statusClass}">
                        <div class="status-indicator"></div>
                        <span class="status-text">Market ${statusText}</span>
                    </div>
                `;
            }
        } catch (error) {
            console.error('Market widget error:', error);
            document.getElementById('market-widget').innerHTML = '<div class="market-error">Market data unavailable</div>';
        }
    }

    bindEvents() {
        // Add ticker functionality
        document.getElementById('add-ticker-btn').addEventListener('click', () => {
            this.addTicker();
        });

        document.getElementById('ticker-input').addEventListener('keypress', (e) => {
            if (e.key === 'Enter') {
                this.addTicker();
            }
        });

        // Refresh button
        document.getElementById('refresh-btn').addEventListener('click', () => {
            if (this.currentTicker) {
                this.refreshTicker(this.currentTicker);
            }
        });

        // Chart toggle button
        document.getElementById('chart-toggle-btn').addEventListener('click', () => {
            if (this.currentTicker) {
                this.toggleChart(this.currentTicker);
            }
        });
    }

    async loadTickers() {
        try {
            const response = await fetch('/api/tickers');
            if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
            const tickers = await response.json();

            if (Array.isArray(tickers)) {
                this.displayTickers(tickers);
            } else {
                console.error('Invalid tickers response:', tickers);
                this.displayTickers([]);
            }
        } catch (error) {
            console.error('Error loading tickers:', error);
            this.displayTickers([]);
        }
    }

    displayTickers(tickers) {
        const tickerList = document.getElementById('ticker-list');

        if (!tickers || tickers.length === 0) {
            tickerList.innerHTML = `
                <div class="no-tickers">
                    <div class="no-tickers-title">No tickers added yet</div>
                    <div class="no-tickers-subtitle">Add your first stock ticker above to get started</div>
                    <div class="no-tickers-examples">
                        <strong>Examples:</strong> AAPL, TSLA, MSFT, GOOGL
                    </div>
                </div>
            `;
            return;
        }

        tickerList.innerHTML = tickers.map(ticker =>
            `<div class="ticker-item" data-ticker="${ticker}" onclick="app.selectTicker('${ticker}')">
                ${ticker}
                <span class="remove-ticker" onclick="event.stopPropagation(); app.removeTicker('${ticker}')" title="Remove ticker">×</span>
            </div>`
        ).join('');
    }

    async addTicker() {
        const input = document.getElementById('ticker-input');
        const ticker = input.value.trim().toUpperCase();

        if (!ticker) {
            alert('Please enter a ticker symbol');
            return;
        }

        if (!/^[A-Z]{1,10}$/.test(ticker)) {
            alert('Please enter a valid ticker symbol (letters only, max 10 characters)');
            return;
        }

        try {
            const response = await fetch('/api/tickers', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ ticker })
            });

            const result = await response.json();

            if (response.ok) {
                input.value = '';
                this.loadTickers();
                this.showMessage(`${ticker} added successfully!`, 'success');
            } else {
                this.showMessage(result.error || 'Failed to add ticker', 'error');
            }
        } catch (error) {
            console.error('Error adding ticker:', error);
            this.showMessage('Failed to add ticker', 'error');
        }
    }

    async selectTicker(ticker) {
        document.querySelectorAll('.ticker-item').forEach(item => {
            item.classList.remove('active');
        });
        document.querySelector(`[data-ticker="${ticker}"]`).classList.add('active');

        this.currentTicker = ticker;
        document.getElementById('current-ticker').textContent = `${ticker} - Daily Summary`;

        const refreshBtn = document.getElementById('refresh-btn');
        const chartBtn = document.getElementById('chart-toggle-btn');
        refreshBtn.style.display = 'block';
        chartBtn.style.display = 'block';
        refreshBtn.innerHTML = '🤖 Generate';
        refreshBtn.disabled = false;
        refreshBtn.classList.remove('loading');

        this.hideChart();
        document.getElementById('sources-section').style.display = 'none';
        document.getElementById('history-section').style.display = 'none';

        document.getElementById('summary-content').innerHTML =
            '<div class="loading-container"><div class="loading-spinner"></div><div class="loading-text">Loading summary...</div></div>';

        try {
            const response = await fetch(`/api/summary/${ticker}`);
            if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
            const data = await response.json();

            if (data.company_logo) {
                console.log(`Logo found for ${ticker}: ${data.company_logo}`);
                document.getElementById('current-ticker').innerHTML = `
                    <img src="${data.company_logo}" alt="${ticker} logo" class="company-logo" onerror="console.log('Logo failed to load: ${data.company_logo}'); this.style.display='none'"> 
                    ${ticker} - Daily Summary
                `;
            } else {
                console.log(`No logo found for ${ticker}`);
                document.getElementById('current-ticker').textContent = `${ticker} - Daily Summary`;
            }

            this.displaySummary(data);
        } catch (error) {
            console.error('Error loading summary:', error);
            document.getElementById('summary-content').innerHTML =
                '<div class="error-message">Failed to load summary</div>';
            refreshBtn.innerHTML = '🤖 Generate';
            refreshBtn.disabled = false;
            refreshBtn.classList.remove('loading');
        }
    }

    displaySummary(data) {
        const summaryContent = document.getElementById('summary-content');
        const sourcesSection = document.getElementById('sources-section');
        const historySection = document.getElementById('history-section');

        if (!data.current_summary) {
            summaryContent.innerHTML = `
                <div class="error-message">
                    <h3>No summary available</h3>
                    <p>Click the Generate button for a new summary for this ticker.</p>
                </div>
            `;
            sourcesSection.style.display = 'none';
            historySection.style.display = 'none';
            return;
        }

        const summary = data.current_summary;

        let mlAnalysisHtml = '';
        if (data.ml_analysis) {
            const ml = data.ml_analysis;
            mlAnalysisHtml = `
                <div class="future-predictions-box">
                    <div class="predictions-header">
                        <span class="predictions-icon">🔮</span>
                        <strong>Future Predictions</strong>
                    </div>
                    <div class="predictions-content">
            `;

            if (ml.price_forecast) {
                const forecast = ml.price_forecast;
                const changeClass = forecast.change_percent >= 0 ? 'positive' : 'negative';
                mlAnalysisHtml += `
                    <div class="prediction-section">
                        <div class="prediction-label">📈 Price Forecast (${forecast.timeframe})</div>
                        <div class="price-prediction">
                            <span class="current-price">$${forecast.current_price}</span>
                            <span class="arrow">→</span>
                            <span class="predicted-price">$${forecast.predicted_price}</span>
                            <span class="price-change ${changeClass}">
                                ${forecast.change_percent >= 0 ? '+' : ''}${forecast.change_percent}%
                            </span>
                        </div>
                        <div class="prediction-meta">Model: ${forecast.model_used.toUpperCase()} | Confidence: ${forecast.confidence}</div>
                    </div>
                `;
            }

            if (ml.sentiment) {
                const sentiment = ml.sentiment;
                const sentimentClass = sentiment.sentiment.toLowerCase();
                mlAnalysisHtml += `
                    <div class="prediction-section">
                        <div class="prediction-label">💭 Market Sentiment</div>
                        <div class="sentiment-prediction">
                            <span class="sentiment-score ${sentimentClass}">${sentiment.sentiment}</span>
                            <span class="sentiment-value">(${sentiment.score})</span>
                        </div>
                        <div class="prediction-meta">Based on ${sentiment.articles_analyzed} articles | Confidence: ${sentiment.confidence}</div>
                    </div>
                `;
            }

            mlAnalysisHtml += '</div></div>';
        }

        summaryContent.innerHTML = `
            <div class="summary-date">
                <strong>Last Updated:</strong> ${new Date(summary.date).toLocaleDateString()}
            </div>
            ${mlAnalysisHtml}
            <div class="summary-text">${this.formatSummary(summary.summary)}</div>
            ${summary.what_changed && summary.what_changed.trim() !== '' &&
                summary.what_changed !== 'No material developments identified.' &&
                summary.what_changed !== 'API quota exceeded - manual review recommended.' &&
                summary.what_changed !== 'Unable to determine changes due to API error.' ? `
                <div class="what-changed-box">
                    <div class="what-changed-header">
                        <span class="change-icon">📊</span>
                        <strong>What Changed Today</strong>
                    </div>
                    <div class="what-changed-content">${summary.what_changed}</div>
                </div>
            ` : ''}
            ${summary.risk_factors && summary.risk_factors.trim() !== '' &&
                summary.risk_factors !== 'Unable to generate risk analysis.' &&
                summary.risk_factors !== 'Risk analysis unavailable - API quota exceeded.' &&
                summary.risk_factors !== 'Risk analysis unavailable due to API error.' &&
                summary.risk_factors !== 'undefined' ? `
                <div class="risk-factors-box">
                    <div class="risk-factors-header">
                        <span class="risk-icon">⚠️</span>
                        <strong>Risk Factors</strong>
                    </div>
                    <div class="risk-factors-content">${summary.risk_factors}</div>
                </div>
            ` : ''}
        `;

        if (summary.articles_used && summary.articles_used.length > 0) {
            const sourcesList = document.getElementById('sources-list');
            sourcesSection.style.display = 'block';
            sourcesList.innerHTML = summary.articles_used.map(article => `
                <div class="source-item">
                    <div class="source-name">${article.source}</div>
                    <div class="source-title">${article.title}</div>
                    <a href="${article.url}" class="source-url" target="_blank">Read more</a>
                </div>
            `).join('');
        } else {
            sourcesSection.style.display = 'none';
        }

        if (data.history && data.history.length > 0) {
            const historyList = document.getElementById('history-list');
            historySection.style.display = 'block';
            historyList.innerHTML = data.history.map(item => `
                <div class="history-item">
                    <div class="history-date">${new Date(item.date).toLocaleDateString()}</div>
                    <div class="history-change">${item.what_changed}</div>
                </div>
            `).join('');
        } else {
            historySection.style.display = 'none';
        }
    }

    formatSummary(summary) {
        return summary.replace(/\n/g, '<br>').replace(/(\*\*.*?\*\*)/g, '<strong>$1</strong>').replace(/\*\*/g, '');
    }

    async refreshTicker(ticker) {
        const refreshBtn = document.getElementById('refresh-btn');
        refreshBtn.innerHTML = '<span class="spinner"></span> Generating...';
        refreshBtn.disabled = true;
        refreshBtn.classList.add('loading');

        try {
            const response = await fetch(`/api/refresh/${ticker}`);
            const result = await response.json();

            if (response.ok) {
                this.showMessage(`${ticker} refreshed successfully!`, 'success');
                this.selectTicker(ticker);
            } else {
                this.showMessage(result.error || 'Failed to refresh ticker', 'error');
                refreshBtn.innerHTML = '🤖 Generate';
                refreshBtn.disabled = false;
                refreshBtn.classList.remove('loading');
            }
        } catch (error) {
            console.error('Error refreshing ticker:', error);
            this.showMessage('Failed to refresh ticker', 'error');
            refreshBtn.innerHTML = '🤖 Generate';
            refreshBtn.disabled = false;
            refreshBtn.classList.remove('loading');
        }
    }

    async toggleChart(ticker) {
        const chartWrapper = document.getElementById('chart-wrapper');
        const summaryContent = document.getElementById('summary-content');
        const chartBtn = document.getElementById('chart-toggle-btn');

        if (chartWrapper.style.display === 'block') {
            chartWrapper.style.display = 'none';
            summaryContent.style.display = 'block';
            chartBtn.innerHTML = '📊 Chart';
        } else {
            chartWrapper.style.display = 'block';
            summaryContent.style.display = 'none';
            chartBtn.innerHTML = '📝 Summary';
            this.loadChart(ticker, '7d');
        }
    }

    async loadChart(ticker, period) {
        try {
            const response = await fetch(`/api/chart/${ticker}/${period}`);
            if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
            const data = await response.json();

            const ctx = document.getElementById('stock-chart').getContext('2d');
            if (this.chart) this.chart.destroy();

            this.chart = new Chart(ctx, {
                type: 'line',
                data: {
                    labels: data.labels,
                    datasets: [{
                        label: `${ticker} Price`,
                        data: data.values,
                        borderColor: '#00ffcc',
                        backgroundColor: 'rgba(0, 255, 204, 0.2)',
                        fill: true,
                        tension: 0.4,
                        pointRadius: 3,
                        pointBackgroundColor: '#ffffff',
                        pointBorderColor: '#00ffcc',
                        pointHoverRadius: 6,
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    scales: {
                        x: {
                            grid: { display: false },
                            ticks: { color: '#a0d4ff' }
                        },
                        y: {
                            grid: { borderColor: 'rgba(0, 255, 255, 0.1)' },
                            ticks: { color: '#a0d4ff' }
                        }
                    },
                    plugins: {
                        legend: { labels: { color: '#ffffff' } },
                        tooltip: {
                            backgroundColor: 'rgba(15, 32, 39, 0.9)',
                            titleColor: '#00ffcc',
                            bodyColor: '#ffffff',
                            borderColor: '#00ffcc',
                            borderWidth: 1
                        }
                    }
                }
            });

            if (!this.chartListenersSet) {
                document.querySelectorAll('.period-btn').forEach(btn => {
                    btn.addEventListener('click', (e) => {
                        document.querySelectorAll('.period-btn').forEach(b => b.classList.remove('active'));
                        e.target.classList.add('active');
                        this.loadChart(ticker, e.target.dataset.period);
                    });
                });
                this.chartListenersSet = true;
            }
        } catch (error) {
            console.error('Error loading chart:', error);
            document.getElementById('chart-wrapper').innerHTML = '<div class="error-message">Failed to load chart</div>';
        }
    }

    hideChart() {
        document.getElementById('chart-wrapper').style.display = 'none';
        document.getElementById('summary-content').style.display = 'block';
        document.getElementById('chart-toggle-btn').innerHTML = '📊 Chart';
    }

    async removeTicker(ticker) {
        // Add removing animation
        const tickerElement = document.querySelector(`[data-ticker="${ticker}"]`);
        if (tickerElement) {
            tickerElement.classList.add('removing');
        }

        try {
            const response = await fetch(`/api/tickers/${ticker}`, {
                method: 'DELETE'
            });

            if (response.ok) {
                // Wait for animation to complete
                setTimeout(() => {
                    this.loadTickers();
                    if (this.currentTicker === ticker) {
                        this.currentTicker = null;
                        document.getElementById('current-ticker').textContent = 'Select a ticker to view summary';
                        document.getElementById('summary-content').innerHTML = '';
                        document.getElementById('sources-section').style.display = 'none';
                        document.getElementById('history-section').style.display = 'none';
                        document.getElementById('refresh-btn').style.display = 'none';
                        document.getElementById('chart-toggle-btn').style.display = 'none';
                    }
                }, 150);
                this.showMessage(`${ticker} removed successfully!`, 'success');
            } else {
                // Remove animation class if failed
                if (tickerElement) tickerElement.classList.remove('removing');
                const result = await response.json();
                this.showMessage(result.error || 'Failed to remove ticker', 'error');
            }
        } catch (error) {
            // Remove animation class if failed
            if (tickerElement) tickerElement.classList.remove('removing');
            console.error('Error removing ticker:', error);
            this.showMessage('Failed to remove ticker', 'error');
        }
    }

    showMessage(message, type) {
        const messageDiv = document.createElement('div');
        messageDiv.className = `message ${type}`;
        messageDiv.textContent = message;
        messageDiv.style.position = 'fixed';
        messageDiv.style.top = '20px';
        messageDiv.style.right = '20px';
        messageDiv.style.padding = '15px 25px';
        messageDiv.style.borderRadius = '8px';
        messageDiv.style.zIndex = '1000';
        messageDiv.style.color = '#fff';
        messageDiv.style.background = type === 'success' ? 'linear-gradient(45deg, #00ffcc, #00b4db)' : 'linear-gradient(45deg, #ff6b6b, #e74c3c)';
        messageDiv.style.boxShadow = '0 4px 15px rgba(0,0,0,0.3)';
        messageDiv.style.animation = 'slideIn 0.2s ease-out';
        document.body.appendChild(messageDiv);

        setTimeout(() => {
            messageDiv.style.transition = 'opacity 0.2s ease';
            messageDiv.style.opacity = '0';
            setTimeout(() => messageDiv.remove(), 200);
        }, 2500);
    }
}

// Add CSS animations
const style = document.createElement('style');
style.textContent = `
    @keyframes slideIn {
        from { transform: translateX(100%); opacity: 0; }
        to { transform: translateX(0); opacity: 1; }
    }
    
    @keyframes slideOut {
        from { transform: translateX(0); opacity: 1; }
        to { transform: translateX(100%); opacity: 0; }
    }
    
    .summary-text {
        line-height: 1.8;
        color: #d0efff;
    }
    
    .summary-text h4 {
        color: #00ffcc;
        margin: 20px 0 10px 0;
        font-size: 1.2rem;
        font-weight: 600;
        border-bottom: 1px solid rgba(0, 255, 255, 0.2);
        padding-bottom: 5px;
    }
    
    .summary-text ul {
        margin: 10px 0;
        padding-left: 25px;
    }
    
    .summary-text li {
        margin: 8px 0;
        color: #a0d4ff;
    }
    
    .summary-text p {
        margin: 12px 0;
        text-align: justify;
    }
    
    .what-changed-box {
        background: rgba(243, 156, 18, 0.1);
        border-radius: 10px;
        padding: 18px;
        margin: 20px 0;
        box-shadow: 0 2px 8px rgba(243, 156, 18, 0.2);
        border-left: 4px solid #f39c12;
    }
    
    .what-changed-header {
        display: flex;
        align-items: center;
        margin-bottom: 12px;
        color: #f39c12;
    }
    
    .change-icon {
        margin-right: 10px;
        font-size: 20px;
    }
    
    .what-changed-content {
        color: #f39c12;
        font-weight: 500;
        line-height: 1.6;
    }
    
    .risk-factors-box {
        background: rgba(231, 76, 60, 0.1);
        border-radius: 10px;
        padding: 18px;
        margin: 20px 0;
        box-shadow: 0 2px 8px rgba(231, 76, 60, 0.2);
        border-left: 4px solid #ff6b6b;
    }
    
    .risk-factors-header {
        display: flex;
        align-items: center;
        margin-bottom: 12px;
        color: #ff6b6b;
    }
    
    .risk-icon {
        margin-right: 10px;
        font-size: 20px;
    }
    
    .risk-factors-content {
        color: #ff6b6b;
        font-weight: 500;
        line-height: 1.6;
    }
    
    .remove-ticker {
        float: right;
        color: #ff6b6b;
        font-weight: bold;
        cursor: pointer;
        padding: 4px 8px;
        border-radius: 4px;
        font-size: 16px;
        line-height: 1;
        transition: all 0.1s ease;
    }
    
    .remove-ticker:hover {
        background: #ff6b6b;
        color: white;
    }
    
    .ticker-item {
        position: relative;
        padding-right: 35px;
        transition: all 0.15s ease;
        animation: tickerSlideIn 0.2s ease-out;
    }
    
    .ticker-item.removing {
        animation: tickerSlideOut 0.15s ease-in forwards;
    }
    
    @keyframes tickerSlideIn {
        from {
            opacity: 0;
            transform: translateX(-20px);
        }
        to {
            opacity: 1;
            transform: translateX(0);
        }
    }
    
    @keyframes tickerSlideOut {
        from {
            opacity: 1;
            transform: translateX(0);
        }
        to {
            opacity: 0;
            transform: translateX(-20px);
        }
    }
    
    .header-buttons {
        display: flex;
        gap: 15px;
        align-items: center;
    }
    
    .summary-date {
        background: rgba(255,255,255,0.05);
        padding: 10px 15px;
        border-radius: 6px;
        margin-bottom: 20px;
        font-size: 1rem;
        color: #a0d4ff;
    }
    
    .no-tickers {
        text-align: center;
        color: #a0d4ff;
        padding: 25px;
        background: rgba(255,255,255,0.05);
        border-radius: 10px;
        margin: 15px 0;
    }
    
    .no-tickers-title {
        font-size: 1.2rem;
        font-weight: 600;
        color: #ffffff;
        margin-bottom: 10px;
    }
    
    .no-tickers-subtitle {
        font-size: 1rem;
        color: #a0d4ff;
        margin-bottom: 15px;
    }
    
    .no-tickers-examples {
        font-size: 0.9rem;
        color: #a0d4ff;
        background: rgba(255,255,255,0.05);
        padding: 10px;
        border-radius: 6px;
        border-left: 4px solid #00ffcc;
    }
    
    .spinner {
        display: inline-block;
        width: 14px;
        height: 14px;
        border: 3px solid #ffffff;
        border-radius: 50%;
        border-top-color: transparent;
        animation: spin 1s ease-in-out infinite;
    }
    
    @keyframes spin {
        to { transform: rotate(360deg); }
    }
    
    .loading-container {
        text-align: center;
        padding: 50px 20px;
        color: #a0d4ff;
    }
    
    .loading-spinner {
        width: 50px;
        height: 50px;
        border: 5px solid rgba(255,255,255,0.1);
        border-top: 5px solid #00ffcc;
        border-radius: 50%;
        animation: spin 1s linear infinite;
        margin: 0 auto 25px;
    }
    
    .loading-text {
        font-size: 1.2rem;
        font-weight: 600;
        margin-bottom: 10px;
        color: #ffffff;
    }
    
    .loading-subtext {
        font-size: 1rem;
        color: #a0d4ff;
    }
    
    #refresh-btn.loading {
        background: linear-gradient(45deg, #95a5a6, #7f8c8d) !important;
        cursor: not-allowed;
    }
    
    #refresh-btn:disabled {
        background: linear-gradient(45deg, #95a5a6, #7f8c8d) !important;
        cursor: not-allowed;
        opacity: 0.7;
    }
    
    .ticker-wrapper {
        overflow: hidden !important;
        border-top: 2px solid #00ffcc;
        border-bottom: 2px solid #00ffcc;
        padding: 1.2rem 0;
        margin: 25px 0;
        user-select: none;
        background: rgba(15, 32, 39, 0.8);
        color: white;
        position: relative;
        z-index: 1000;
        width: 100%;
        display: block !important;
        visibility: visible !important;
        height: auto !important;
    }
    
    .ticker {
        display: flex;
        gap: 2.5rem;
        animation: scroll 30s linear infinite;
        min-width: max-content;
        list-style: none;
        margin: 0;
        padding: 0;
    }
    
    .ticker-wrapper:hover .ticker {
        animation-play-state: paused;
    }
    
    .ticker li {
        display: flex;
        align-items: center;
        font-weight: bold;
        white-space: nowrap;
    }
    
    .symbol {
        margin-right: 0.5rem;
        color: #d0efff;
        font-size: 1rem;
    }
    
    .price {
        margin: 0 0.5rem;
        color: #f39c12;
        font-size: 1rem;
    }
    
    .change.plus {
        color: #2ecc71;
    }
    
    .change.minus {
        color: #ff6b6b;
    }
    
    .change.plus::before {
        content: "▲ ";
    }
    
    .change.minus::before {
        content: "▼ ";
    }
    
    @keyframes scroll {
        0% { transform: translateX(0); }
        100% { transform: translateX(calc(-50% - 2.5rem)); }
    }
    
    .usage-section {
        background: rgba(255,255,255,0.05);
        border-radius: 10px;
        padding: 20px;
        margin-bottom: 25px;
    }
    
    .usage-refresh-btn {
        background: linear-gradient(45deg, #00ffcc, #00b4db);
        color: #0f2027;
        border: none;
        border-radius: 6px;
        padding: 6px 12px;
        cursor: pointer;
        font-size: 0.9rem;
        margin-left: 15px;
        transition: all 0.3s ease;
    }
    
    .usage-refresh-btn:hover {
        transform: translateY(-2px);
        box-shadow: 0 0 10px rgba(0, 255, 204, 0.3);
    }
    
    .usage-category {
        margin: 15px 0 8px 0;
        color: #ffffff;
        font-size: 1rem;
    }
    
    .usage-item {
        display: flex;
        align-items: center;
        margin: 10px 0;
        padding: 8px;
        border-radius: 6px;
    }
    
    .usage-item.safe {
        background: rgba(46, 204, 113, 0.1);
    }
    
    .usage-item.warning {
        background: rgba(243, 156, 18, 0.1);
    }
    
    .usage-item.danger {
        background: rgba(231, 76, 60, 0.1);
    }
    
    .api-name {
        width: 130px;
        font-size: 0.9rem;
        font-weight: 500;
        color: #d0efff;
    }
    
    .usage-bar {
        flex: 1;
        height: 10px;
        background: rgba(255,255,255,0.1);
        border-radius: 5px;
        margin: 0 15px;
        overflow: hidden;
    }
    
    .usage-fill {
        height: 100%;
        background: #00ffcc;
        transition: width 0.4s ease;
    }
    
    .usage-item.warning .usage-fill {
        background: #f39c12;
    }
    
    .usage-item.danger .usage-fill {
        background: #ff6b6b;
    }
    
    .usage-text {
        font-size: 0.85rem;
        color: #a0d4ff;
        min-width: 70px;
        text-align: right;
    }
    
    .future-predictions-box {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        border-radius: 15px;
        padding: 20px;
        margin: 25px 0;
        color: #ffffff;
        box-shadow: 0 8px 25px rgba(102, 126, 234, 0.3);
        border: 1px solid rgba(0, 255, 255, 0.1);
    }
    
    .predictions-header {
        display: flex;
        align-items: center;
        margin-bottom: 18px;
        font-size: 1.2rem;
        font-weight: 600;
        border-bottom: 1px solid rgba(255, 255, 255, 0.2);
        padding-bottom: 10px;
    }
    
    .predictions-icon {
        margin-right: 12px;
        font-size: 1.5rem;
    }
    
    .prediction-section {
        margin-bottom: 18px;
    }
    
    .prediction-section:last-child {
        margin-bottom: 0;
    }
    
    .prediction-label {
        font-size: 1rem;
        font-weight: 500;
        margin-bottom: 10px;
        opacity: 0.9;
    }
    
    .price-prediction {
        display: flex;
        align-items: center;
        gap: 15px;
        margin-bottom: 8px;
        font-size: 1.1rem;
        font-weight: 600;
    }
    
    .arrow {
        font-size: 1.2rem;
        opacity: 0.8;
    }
    
    .price-change.positive {
        color: #2ecc71;
        font-weight: 700;
    }
    
    .price-change.negative {
        color: #ff6b6b;
        font-weight: 700;
    }
    
    .sentiment-prediction {
        display: flex;
        align-items: center;
        gap: 10px;
        margin-bottom: 8px;
        font-size: 1.1rem;
    }
    
    .sentiment-score {
        font-weight: 600;
        padding: 6px 12px;
        border-radius: 6px;
        background: rgba(255, 255, 255, 0.2);
    }
    
    .sentiment-score.bullish {
        background: rgba(46, 204, 113, 0.3);
    }
    
    .sentiment-score.bearish {
        background: rgba(231, 76, 60, 0.3);
    }
    
    .sentiment-score.neutral {
        background: rgba(243, 156, 18, 0.3);
    }
    
    .sentiment-value {
        font-size: 0.9rem;
        opacity: 0.8;
    }
    
    .prediction-meta {
        font-size: 0.85rem;
        opacity: 0.7;
        font-style: italic;
    }
    
    /* Entity Highlighting Styles */
    .highlight-financial {
        background: linear-gradient(120deg, #2ecc71, #27ae60);
        color: white;
        padding: 3px 6px;
        border-radius: 4px;
        font-weight: 600;
        font-size: 0.95rem;
    }
    
    .highlight-percentage {
        background: linear-gradient(120deg, #ff6b6b, #e74c3c);
        color: white;
        padding: 3px 6px;
        border-radius: 4px;
        font-weight: 600;
    }
    
    .highlight-number {
        background: linear-gradient(120deg, #00ffcc, #00b4db);
        color: white;
        padding: 3px 6px;
        border-radius: 4px;
        font-weight: 600;
    }
    
    .highlight-quarter {
        background: linear-gradient(120deg, #9b59b6, #8e44ad);
        color: white;
        padding: 3px 6px;
        border-radius: 4px;
        font-weight: 600;
        font-size: 0.9rem;
    }
    
    .highlight-term {
        background: linear-gradient(120deg, #f39c12, #e67e22);
        color: white;
        padding: 3px 6px;
        border-radius: 4px;
        font-weight: 600;
        text-transform: uppercase;
        font-size: 0.85rem;
    }
    
    .highlight-ticker {
        background: linear-gradient(120deg, #34495e, #2c3e50);
        color: white;
        padding: 3px 6px;
        border-radius: 4px;
        font-weight: 700;
        font-family: 'Courier New', monospace;
        font-size: 0.9rem;
        letter-spacing: 0.5px;
    }
    
    .highlight-financial:hover,
    .highlight-percentage:hover,
    .highlight-number:hover,
    .highlight-quarter:hover,
    .highlight-term:hover,
    .highlight-ticker:hover {
        transform: scale(1.05);
        box-shadow: 0 2px 8px rgba(0,0,0,0.3);
        transition: all 0.2s ease;
    }
    
    .company-logo {
        width: 48px;
        height: 48px;
        margin-right: 12px;
        vertical-align: middle;
        border-radius: 6px;
        object-fit: contain;
        display: inline-block;
        background: rgba(255,255,255,0.05);
        border: 1px solid rgba(0, 255, 255, 0.2);
    }
    
    .market-status {
        display: flex;
        align-items: center;
        gap: 10px;
    }
    
    .market-status.open .status-indicator {
        background: #2ecc71;
        box-shadow: 0 0 10px #2ecc71;
    }
    
    .market-status.closed .status-indicator {
        background: #ff6b6b;
        box-shadow: 0 0 10px #ff6b6b;
    }
    
    .status-text {
        font-weight: 600;
        color: #ffffff;
    }
    
    .market-error {
        color: #ff6b6b;
        font-size: 0.9rem;
    }
`;
document.head.appendChild(style);

// Initialize the app
document.addEventListener('DOMContentLoaded', () => {
    const app = new StockNewsApp();
    window.app = app;
});