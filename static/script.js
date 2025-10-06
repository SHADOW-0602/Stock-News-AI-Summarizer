class StockNewsApp {
    constructor() {
        this.currentTicker = null;
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
            const data = await response.json();
            
            const widget = document.getElementById('market-widget');
            if (data.market) {
                const statusClass = data.market.is_open ? 'open' : 'closed';
                const statusText = data.market.is_open ? 'OPEN' : 'CLOSED';
                
                let html = `
                    <div class="market-status ${statusClass}">
                        <div class="status-indicator"></div>
                        <span class="status-text">Market ${statusText}</span>
                    </div>
                `;
                

                
                widget.innerHTML = html;
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
            console.log('Fetching tickers...');
            const response = await fetch('/api/tickers');
            console.log('Response status:', response.status);
            
            const tickers = await response.json();
            console.log('Tickers received:', tickers);
            
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
            tickerList.innerHTML = '<div class="no-tickers">No tickers added yet</div>';
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
        // Update UI
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
        
        // Show loading animation
        document.getElementById('summary-content').innerHTML =
            '<div class="loading-container"><div class="loading-spinner"></div><div class="loading-text">Loading summary...</div></div>';

        try {
            const response = await fetch(`/api/summary/${ticker}`);
            const data = await response.json();
            
            // Update header with logo if available
            console.log('Logo data:', data.company_logo);
            if (data.company_logo) {
                document.getElementById('current-ticker').innerHTML = `<img src="${data.company_logo}" alt="${ticker} logo" class="company-logo" onerror="console.log('Logo failed to load: ${data.company_logo}')"> ${ticker} - Daily Summary`;
            }
            
            this.displaySummary(data);
        } catch (error) {
            console.error('Error loading summary:', error);
            document.getElementById('summary-content').innerHTML =
                '<div class="error-message">Failed to load summary</div>';
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
        
        // Display ML analysis if available
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
        
        // Display main summary
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

        // Display sources
        if (summary.articles_used && summary.articles_used.length > 0) {
            const sourcesList = document.getElementById('sources-list');
            sourcesList.innerHTML = summary.articles_used.map(article => `
                <div class="source-item">
                    <div class="source-name">${article.source}</div>
                    <div class="source-title">${article.title}</div>
                    <a href="${article.url}" target="_blank" class="source-url">
                        ${this.truncateUrl(article.url)}
                    </a>
                </div>
            `).join('');
            sourcesSection.style.display = 'block';
        } else {
            sourcesSection.style.display = 'none';
        }

        // Display history
        if (data.history && data.history.length > 0) {
            const historyList = document.getElementById('history-list');
            historyList.innerHTML = data.history.map(item => `
                <div class="history-item">
                    <div class="history-date">${new Date(item.date).toLocaleDateString()}</div>
                    <div class="history-change">${item.what_changed}</div>
                </div>
            `).join('');
            historySection.style.display = 'block';
        } else {
            historySection.style.display = 'none';
        }
    }

    highlightEntities(text) {
        // Highlight key financial entities and terms
        let highlighted = text;
        
        // Financial amounts: $1.2B, $500M, $50K
        highlighted = highlighted.replace(/\$[\d,]+\.?\d*[BMK]?/g, '<span class="highlight-financial">$&</span>');
        
        // Percentages: 15%, 2.5%
        highlighted = highlighted.replace(/\b\d+\.?\d*%/g, '<span class="highlight-percentage">$&</span>');
        
        // Large numbers: 1.5B, 500M, 50K
        highlighted = highlighted.replace(/\b\d+\.?\d*[BMK]\b/g, '<span class="highlight-number">$&</span>');
        
        // Quarters: Q3 2024, Q1 2025
        highlighted = highlighted.replace(/\bQ[1-4]\s+\d{4}/g, '<span class="highlight-quarter">$&</span>');
        
        // Important financial terms
        const terms = ['earnings', 'revenue', 'profit', 'loss', 'guidance', 'outlook', 'acquisition', 'merger', 'partnership', 'IPO', 'dividend', 'buyback', 'FDA', 'approval'];
        terms.forEach(term => {
            const regex = new RegExp(`\\b${term}\\b`, 'gi');
            highlighted = highlighted.replace(regex, '<span class="highlight-term">$&</span>');
        });
        
        // Ticker symbols (2-5 uppercase letters)
        highlighted = highlighted.replace(/\b[A-Z]{2,5}\b/g, '<span class="highlight-ticker">$&</span>');
        
        return highlighted;
    }
    
    formatSummary(text) {
        // Enhanced formatting with entity highlighting
        let formatted = this.highlightEntities(text)
            // Remove "What Changed Today" and "Risk Factors" sections from main summary
            .replace(/\*\*WHAT CHANGED TODAY\*\*[\s\S]*?(?=\n\n|\*\*|$)/gi, '')
            .replace(/WHAT CHANGED TODAY[\s\S]*?(?=\n\n|\*\*|$)/gi, '')
            .replace(/\*\*What Changed Today\*\*[\s\S]*?(?=\n\n|\*\*|$)/gi, '')
            .replace(/\*\*RISK FACTORS\*\*[\s\S]*?(?=\n\n|\*\*|$)/gi, '')
            .replace(/RISK FACTORS[\s\S]*?(?=\n\n|\*\*|$)/gi, '')
            .replace(/\*\*Risk Factors\*\*[\s\S]*?(?=\n\n|\*\*|$)/gi, '')
            // Format headers (but preserve remaining content)
            .replace(/\*\*(.*?)\*\*/g, '<h4>$1</h4>')
            // Clean up any remaining "What Changed" fragments
            .replace(/<h4>What Changed Today<\/h4>/gi, '')
            .replace(/<h4>WHAT CHANGED TODAY<\/h4>/gi, '')
            // Clean up empty bullet points and asterisks
            .replace(/^\s*\*\s*$/gm, '')
            .replace(/^\s*[•·-]\s*$/gm, '')
            // Format bullet points with content
            .replace(/^\s*\*\s+(.+)$/gm, '<li>$1</li>')
            .replace(/^\s*[•·-]\s+(.+)$/gm, '<li>$1</li>')
            // Clean up multiple line breaks
            .replace(/\n{3,}/g, '\n\n')
            // Format paragraphs
            .replace(/\n\n/g, '</p><p>')
            .replace(/\n/g, '<br>')
            // Wrap in paragraphs
            .replace(/^/, '<p>')
            .replace(/$/, '</p>')
            // Clean up list formatting
            .replace(/(<li>.*?<\/li>)/gs, '<ul>$1</ul>')
            .replace(/<\/ul>\s*<ul>/g, '')
            // Clean up empty elements
            .replace(/<p>\s*<\/p>/g, '')
            .replace(/<p>\s*<br>\s*<\/p>/g, '')
            .replace(/<li>\s*<\/li>/g, '')
            .replace(/<ul>\s*<\/ul>/g, '')
            // Clean up empty headers
            .replace(/<h4>\s*<\/h4>/g, '')
            // Remove standalone asterisks and bullets
            .replace(/<p>\s*[\*•·-]\s*<\/p>/g, '')
            // Remove headers followed immediately by another header (empty sections)
            .replace(/<h4>([^<]+)<\/h4>\s*<h4>/g, '<h4>')
            // Remove headers at the end with no content
            .replace(/<h4>([^<]+)<\/h4>\s*<\/p>\s*$/g, '</p>');
        
        return formatted;
    }

    truncateUrl(url) {
        if (url.length > 50) {
            return url.substring(0, 47) + '...';
        }
        return url;
    }

    async refreshTicker(ticker) {
        const refreshBtn = document.getElementById('refresh-btn');
        const originalText = refreshBtn.textContent;
        const summaryContent = document.getElementById('summary-content');

        // Show loading animation
        refreshBtn.innerHTML = '<span class="spinner"></span> Generating...';
        refreshBtn.disabled = true;
        refreshBtn.classList.add('loading');
        
        // Show loading in summary area and load chart
        summaryContent.innerHTML = `
            <div class="loading-container">
                <div class="loading-spinner"></div>
                <div class="loading-text">Generating AI summary...</div>
                <div class="loading-subtext">This may take 30-60 seconds</div>
            </div>
        `;
        
        // Load and show chart during generation
        this.loadChart(ticker);

        try {
            const response = await fetch(`/api/refresh/${ticker}`);
            const result = await response.json();

            if (response.ok) {
                this.showMessage('Summary generated successfully!', 'success');
                // Reload the summary after processing completes
                this.selectTicker(ticker);
            } else {
                this.showMessage(result.error || 'Failed to refresh', 'error');
                summaryContent.innerHTML = `<div class="error-message">Failed to generate summary: ${result.error}</div>`;
            }
        } catch (error) {
            console.error('Error refreshing ticker:', error);
            this.showMessage('Failed to generate summary', 'error');
            summaryContent.innerHTML = '<div class="error-message">Failed to generate summary</div>';
        } finally {
            // Only reset button if there was an error
            // Success case resets via selectTicker
            if (!response || !response.ok) {
                refreshBtn.innerHTML = originalText;
                refreshBtn.disabled = false;
                refreshBtn.classList.remove('loading');
            }
        }
    }

    showMessage(message, type) {
        // Create and show a temporary message
        const messageDiv = document.createElement('div');
        messageDiv.className = `message ${type}`;
        messageDiv.textContent = message;
        messageDiv.style.cssText = `
            position: fixed;
            top: 20px;
            right: 20px;
            padding: 15px 20px;
            border-radius: 8px;
            color: white;
            font-weight: bold;
            z-index: 1000;
            animation: slideIn 0.3s ease;
            background: ${type === 'success' ? '#27ae60' : '#e74c3c'};
        `;

        document.body.appendChild(messageDiv);

        setTimeout(() => {
            messageDiv.style.animation = 'slideOut 0.3s ease';
            setTimeout(() => {
                document.body.removeChild(messageDiv);
            }, 300);
        }, 3000);
    }

    async checkCacheStatus() {
        const checkBtn = document.getElementById('check-cache-btn');
        const statusContent = document.getElementById('cache-status-content');
        
        checkBtn.textContent = 'Checking...';
        checkBtn.disabled = true;
        
        try {
            const response = await fetch('/api/cache-status');
            const status = await response.json();
            
            let statusHtml = `
                <div class="cache-info">
                    <div class="cache-item">
                        <strong>Cache Type:</strong> ${status.cache_type}
                    </div>
                    <div class="cache-item">
                        <strong>Connection:</strong> 
                        <span class="status-${status.connection_test ? 'success' : 'error'}">
                            ${status.connection_test ? '✅ Working' : '❌ Failed'}
                        </span>
                    </div>
                    <div class="cache-item">
                        <strong>Test Result:</strong> ${status.test_result || 'N/A'}
                    </div>
                    ${status.upstash_configured ? 
                        '<div class="cache-item"><strong>Upstash:</strong> <span class="status-success">✅ Configured</span></div>' : 
                        '<div class="cache-item"><strong>Upstash:</strong> <span class="status-error">❌ Not configured</span></div>'
                    }
                    ${status.cache_durations ? `
                        <div class="cache-item">
                            <strong>News Cache TTL:</strong> ${status.cache_durations.news_cache}
                        </div>
                        <div class="cache-item">
                            <strong>Summary Cache TTL:</strong> ${status.cache_durations.summary_cache}
                        </div>
                    ` : ''}
                </div>
            `;
            
            statusContent.innerHTML = statusHtml;
            
        } catch (error) {
            statusContent.innerHTML = `<div class="cache-error">Error checking cache: ${error.message}</div>`;
        } finally {
            checkBtn.textContent = 'Check';
            checkBtn.disabled = false;
        }
    }

    async loadChart(ticker, period = '30d') {
        try {
            const chartContainer = document.getElementById('chart-container');
            const chartTitle = document.getElementById('chart-title');
            const chartStats = document.getElementById('chart-stats');
            
            chartContainer.style.display = 'block';
            
            // Update period buttons
            document.querySelectorAll('.period-btn').forEach(btn => {
                btn.classList.remove('active');
                if (btn.dataset.period === period) {
                    btn.classList.add('active');
                }
            });
            
            // Set up period button listeners
            document.querySelectorAll('.period-btn').forEach(btn => {
                btn.onclick = () => this.loadChart(ticker, btn.dataset.period);
            });
            
            const periodLabels = {'7d': '7 Day', '30d': '30 Day', '90d': '90 Day', '1y': '1 Year', '2y': '2 Year'};
            chartTitle.textContent = `${ticker} - ${periodLabels[period]} Trend`;
            chartStats.innerHTML = '<div class="loading-container"><div class="loading-spinner"></div><div class="loading-text">Loading chart...</div></div>';
            
            const response = await fetch(`/api/chart/${ticker}/${period}`);
            
            if (!response.ok) {
                // Hide chart if no data available
                chartContainer.style.display = 'none';
                return;
            }
            
            const chartConfig = await response.json();
            
            if (chartConfig.data) {
                // Update stats
                const stats = chartConfig.stats;
                const changeClass = stats.change_percent >= 0 ? 'positive' : 'negative';
                chartStats.innerHTML = `
                    <div class="price-stat">
                        <span class="current-price">$${stats.current_price.toFixed(2)}</span>
                        <span class="price-change ${changeClass}">
                            ${stats.change_percent >= 0 ? '+' : ''}${stats.change_percent.toFixed(2)}%
                        </span>
                    </div>
                `;
                
                // Create chart
                const ctx = document.getElementById('price-chart').getContext('2d');
                
                // Destroy existing chart if it exists
                if (window.stockChart) {
                    window.stockChart.destroy();
                }
                
                // Fix callback function for Chart.js
                chartConfig.options.scales.y.ticks.callback = function(value) {
                    return '$' + value.toFixed(2);
                };
                
                window.stockChart = new Chart(ctx, chartConfig);
            } else {
                chartContainer.style.display = 'none';
            }
        } catch (error) {
            console.error('Chart loading error:', error);
            document.getElementById('chart-container').style.display = 'none';
        }
    }

    hideChart() {
        document.getElementById('chart-container').style.display = 'none';
        if (window.stockChart) {
            window.stockChart.destroy();
            window.stockChart = null;
        }
    }

    toggleChart(ticker) {
        const chartContainer = document.getElementById('chart-container');
        const isVisible = chartContainer.style.display !== 'none';
        
        if (isVisible) {
            this.hideChart();
        } else {
            this.loadChart(ticker);
        }
    }



    async removeTicker(ticker) {
        if (!confirm(`Remove ${ticker} from watchlist?`)) {
            return;
        }

        try {
            const response = await fetch(`/api/tickers/${ticker}`, {
                method: 'DELETE'
            });

            const result = await response.json();

            if (response.ok) {
                this.showMessage(`${ticker} removed successfully!`, 'success');
                this.loadTickers();


                // Clear summary if this ticker was selected
                if (this.currentTicker === ticker) {
                    document.getElementById('summary-content').innerHTML =
                        '<div class="welcome-message"><h3>Select a ticker to view summary</h3></div>';
                    document.getElementById('current-ticker').textContent = 'Select a ticker to view summary';
                    document.getElementById('refresh-btn').style.display = 'none';
                    document.getElementById('chart-toggle-btn').style.display = 'none';
                    document.getElementById('sources-section').style.display = 'none';
                    document.getElementById('history-section').style.display = 'none';
                    this.hideChart();
                    this.currentTicker = null;
                }
            } else {
                this.showMessage(result.error || 'Failed to remove ticker', 'error');
            }
        } catch (error) {
            console.error('Error removing ticker:', error);
            this.showMessage('Failed to remove ticker', 'error');
        }
    }
    
    async loadUsageStats() {
        try {
            const response = await fetch('/api/debug/apis');
            const data = await response.json();
            this.displayUsageStats(data);
        } catch (error) {
            console.error('Usage stats error:', error);
            document.getElementById('usage-content').innerHTML = '<div class="error">Failed to load usage</div>';
        }
    }
    
    displayUsageStats(data) {
        const usageContent = document.getElementById('usage-content');
        
        let html = '<div class="usage-stats">';
        
        if (data.usage) {
            html += '<div class="usage-category"><strong>API Usage:</strong></div>';
            Object.entries(data.usage).forEach(([api, info]) => {
                if (api !== 'alpha_vantage_realtime' && api !== 'twelve_data_realtime') {
                    const limit = data.limits[api] || 1000;
                    const used = info.calls || 0;
                    const percentage = Math.round((used / limit) * 100);
                    const statusClass = percentage > 80 ? 'danger' : percentage > 60 ? 'warning' : 'safe';
                    
                    html += `
                        <div class="usage-item ${statusClass}">
                            <span class="api-name">${api}</span>
                            <div class="usage-bar"><div class="usage-fill" style="width: ${percentage}%"></div></div>
                            <span class="usage-text">${used}/${limit}</span>
                        </div>
                    `;
                }
            });
        }
        
        html += '</div>';
        usageContent.innerHTML = html;
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
        line-height: 1.6;
        color: #2c3e50;
    }
    
    .summary-text h4 {
        color: #27ae60;
        margin: 20px 0 10px 0;
        font-size: 16px;
        font-weight: 600;
        border-bottom: 2px solid #ecf0f1;
        padding-bottom: 5px;
    }
    
    .summary-text ul {
        margin: 10px 0;
        padding-left: 20px;
    }
    
    .summary-text li {
        margin: 8px 0;
        color: #34495e;
    }
    
    .summary-text p {
        margin: 12px 0;
        text-align: justify;
    }
    
    .what-changed-box {
        background: linear-gradient(135deg, #f39c12, #f1c40f);
        border-radius: 8px;
        padding: 16px;
        margin: 20px 0;
        box-shadow: 0 2px 8px rgba(243, 156, 18, 0.2);
        border-left: 4px solid #e67e22;
    }
    
    .what-changed-header {
        display: flex;
        align-items: center;
        margin-bottom: 10px;
        color: #2c3e50;
    }
    
    .change-icon {
        margin-right: 8px;
        font-size: 18px;
    }
    
    .what-changed-content {
        color: #2c3e50;
        font-weight: 500;
        line-height: 1.5;
    }
    
    .remove-ticker {
        float: right;
        color: #e74c3c;
        font-weight: bold;
        cursor: pointer;
        padding: 2px 6px;
        border-radius: 3px;
        font-size: 16px;
        line-height: 1;
    }
    
    .remove-ticker:hover {
        background: #e74c3c;
        color: white;
    }
    
    .ticker-item {
        position: relative;
        padding-right: 30px;
    }
    
    .header-buttons {
        display: flex;
        gap: 10px;
        align-items: center;
    }
    
    .chart-toggle-btn {
        background: #3498db;
        color: white;
        border: none;
        border-radius: 6px;
        padding: 8px 12px;
        cursor: pointer;
        font-size: 14px;
        font-weight: 500;
        transition: all 0.2s ease;
        display: flex;
        align-items: center;
        gap: 5px;
    }
    
    .chart-toggle-btn:hover {
        background: #2980b9;
        transform: scale(1.05);
    }
    
    .summary-date {
        background: #ecf0f1;
        padding: 8px 12px;
        border-radius: 4px;
        margin-bottom: 16px;
        font-size: 14px;
        color: #7f8c8d;
    }
    
    .no-tickers {
        text-align: center;
        color: #7f8c8d;
        font-style: italic;
        padding: 20px;
    }
    
    .spinner {
        display: inline-block;
        width: 12px;
        height: 12px;
        border: 2px solid #ffffff;
        border-radius: 50%;
        border-top-color: transparent;
        animation: spin 1s ease-in-out infinite;
    }
    
    @keyframes spin {
        to { transform: rotate(360deg); }
    }
    
    .loading-container {
        text-align: center;
        padding: 40px 20px;
        color: #7f8c8d;
    }
    
    .loading-spinner {
        width: 40px;
        height: 40px;
        border: 4px solid #ecf0f1;
        border-top: 4px solid #3498db;
        border-radius: 50%;
        animation: spin 1s linear infinite;
        margin: 0 auto 20px;
    }
    
    .loading-text {
        font-size: 18px;
        font-weight: 600;
        margin-bottom: 8px;
        color: #2c3e50;
    }
    
    .loading-subtext {
        font-size: 14px;
        color: #95a5a6;
    }
    
    #refresh-btn.loading {
        background: #95a5a6 !important;
        cursor: not-allowed;
    }
    
    #refresh-btn:disabled {
        background: #95a5a6 !important;
        cursor: not-allowed;
        opacity: 0.7;
    }
    
    .ticker-wrapper {
        overflow: hidden !important;
        border-top: 2px solid #3498db;
        border-bottom: 2px solid #3498db;
        padding: 1rem 0;
        margin: 20px 0;
        user-select: none;
        background: #2c3e50;
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
        gap: 2rem;
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
        color: #ecf0f1;
        font-size: 14px;
    }
    
    .price {
        margin: 0 0.5rem;
        color: #f39c12;
        font-size: 14px;
    }
    
    .change.plus {
        color: #27ae60;
    }
    
    .change.minus {
        color: #e74c3c;
    }
    
    .change.plus::before {
        content: "▲ ";
    }
    
    .change.minus::before {
        content: "▼ ";
    }
    
    @keyframes scroll {
        0% {
            transform: translateX(0);
        }
        100% {
            transform: translateX(calc(-50% - 2rem));
        }
    }
    
    .usage-section {
        background: #f8f9fa;
        border-radius: 8px;
        padding: 15px;
        margin-bottom: 20px;
    }
    
    .usage-refresh-btn {
        background: #3498db;
        color: white;
        border: none;
        border-radius: 4px;
        padding: 4px 8px;
        cursor: pointer;
        font-size: 12px;
        margin-left: 10px;
    }
    
    .usage-category {
        margin: 10px 0 5px 0;
        color: #2c3e50;
        font-size: 14px;
    }
    
    .usage-item {
        display: flex;
        align-items: center;
        margin: 8px 0;
        padding: 5px;
        border-radius: 4px;
    }
    
    .usage-item.safe { background: #d5f4e6; }
    .usage-item.warning { background: #fef9e7; }
    .usage-item.danger { background: #fadbd8; }
    
    .api-name {
        width: 120px;
        font-size: 12px;
        font-weight: 500;
    }
    
    .usage-bar {
        flex: 1;
        height: 8px;
        background: #ecf0f1;
        border-radius: 4px;
        margin: 0 10px;
        overflow: hidden;
    }
    
    .usage-fill {
        height: 100%;
        background: #3498db;
        transition: width 0.3s ease;
    }
    
    .usage-item.warning .usage-fill { background: #f39c12; }
    .usage-item.danger .usage-fill { background: #e74c3c; }
    
    .usage-text {
        font-size: 11px;
        color: #7f8c8d;
        min-width: 60px;
        text-align: right;
    }
    
    .future-predictions-box {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        border-radius: 12px;
        padding: 18px;
        margin: 20px 0;
        color: white;
        box-shadow: 0 6px 20px rgba(102, 126, 234, 0.3);
    }
    
    .predictions-header {
        display: flex;
        align-items: center;
        margin-bottom: 16px;
        font-size: 16px;
        font-weight: 600;
        border-bottom: 1px solid rgba(255, 255, 255, 0.2);
        padding-bottom: 8px;
    }
    
    .predictions-icon {
        margin-right: 10px;
        font-size: 18px;
    }
    
    .prediction-section {
        margin-bottom: 16px;
    }
    
    .prediction-section:last-child {
        margin-bottom: 0;
    }
    
    .prediction-label {
        font-size: 13px;
        font-weight: 500;
        margin-bottom: 8px;
        opacity: 0.9;
    }
    
    .price-prediction {
        display: flex;
        align-items: center;
        gap: 12px;
        margin-bottom: 6px;
        font-size: 15px;
        font-weight: 600;
    }
    
    .arrow {
        font-size: 18px;
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
        gap: 8px;
        margin-bottom: 6px;
        font-size: 15px;
    }
    
    .sentiment-score {
        font-weight: 600;
        padding: 4px 8px;
        border-radius: 4px;
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
        font-size: 13px;
        opacity: 0.8;
    }
    
    .prediction-meta {
        font-size: 11px;
        opacity: 0.7;
        font-style: italic;
    }
    
    /* Entity Highlighting Styles */
    .highlight-financial {
        background: linear-gradient(120deg, #2ecc71, #27ae60);
        color: white;
        padding: 2px 4px;
        border-radius: 3px;
        font-weight: 600;
        font-size: 0.95em;
    }
    
    .highlight-percentage {
        background: linear-gradient(120deg, #e74c3c, #c0392b);
        color: white;
        padding: 2px 4px;
        border-radius: 3px;
        font-weight: 600;
    }
    
    .highlight-number {
        background: linear-gradient(120deg, #3498db, #2980b9);
        color: white;
        padding: 2px 4px;
        border-radius: 3px;
        font-weight: 600;
    }
    
    .highlight-quarter {
        background: linear-gradient(120deg, #9b59b6, #8e44ad);
        color: white;
        padding: 2px 4px;
        border-radius: 3px;
        font-weight: 600;
        font-size: 0.9em;
    }
    
    .highlight-term {
        background: linear-gradient(120deg, #f39c12, #e67e22);
        color: white;
        padding: 2px 4px;
        border-radius: 3px;
        font-weight: 600;
        text-transform: uppercase;
        font-size: 0.85em;
    }
    
    .highlight-ticker {
        background: linear-gradient(120deg, #34495e, #2c3e50);
        color: white;
        padding: 2px 4px;
        border-radius: 3px;
        font-weight: 700;
        font-family: 'Courier New', monospace;
        font-size: 0.9em;
        letter-spacing: 0.5px;
    }
    
    /* Hover effects for highlights */
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
        background: #f0f0f0;
        border: 1px solid #ddd;
    }
    
    .market-widget {
        display: flex;
        align-items: center;
        gap: 20px;
        font-size: 14px;
    }
    
    .market-status {
        display: flex;
        align-items: center;
        gap: 8px;
    }
    
    .market-status.open .status-indicator {
        width: 8px;
        height: 8px;
        background: #27ae60;
        border-radius: 50%;
        animation: pulse 2s infinite;
    }
    
    .market-status.closed .status-indicator {
        width: 8px;
        height: 8px;
        background: #e74c3c;
        border-radius: 50%;
    }
    
    .status-text {
        font-weight: 600;
        color: #2c3e50;
    }
    

    

    
    @keyframes pulse {
        0% { opacity: 1; }
        50% { opacity: 0.5; }
        100% { opacity: 1; }
    }
`;
document.head.appendChild(style);

// Initialize the app after DOM loads
document.addEventListener('DOMContentLoaded', () => {
    const app = new StockNewsApp();
    window.app = app; // Make globally accessible
});