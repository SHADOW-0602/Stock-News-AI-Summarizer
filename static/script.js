class StockNewsApp {
    constructor() {
        this.currentTicker = null;
        this.init();
    }

    init() {
        this.bindEvents();
        this.loadTickers();
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
    }

    async loadTickers() {
        try {
            const response = await fetch('/api/tickers');
            const tickers = await response.json();
            this.displayTickers(tickers);
        } catch (error) {
            console.error('Error loading tickers:', error);
            document.getElementById('ticker-list').innerHTML = 
                '<div class="error-message">Failed to load tickers</div>';
        }
    }

    displayTickers(tickers) {
        const tickerList = document.getElementById('ticker-list');
        
        if (tickers.length === 0) {
            tickerList.innerHTML = '<div class="loading">No tickers added yet</div>';
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
        document.getElementById('refresh-btn').style.display = 'block';

        // Show loading
        document.getElementById('summary-content').innerHTML = 
            '<div class="loading">Loading summary...</div>';

        try {
            const response = await fetch(`/api/summary/${ticker}`);
            const data = await response.json();
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
                    <p>Click the refresh button to generate a new summary for this ticker.</p>
                </div>
            `;
            sourcesSection.style.display = 'none';
            historySection.style.display = 'none';
            return;
        }

        const summary = data.current_summary;
        
        // Display main summary
        summaryContent.innerHTML = `
            <div class="summary-date">
                <strong>Last Updated:</strong> ${new Date(summary.date).toLocaleDateString()}
            </div>
            <div class="summary-text">${this.formatSummary(summary.summary)}</div>
            ${summary.what_changed ? `
                <div class="what-changed">
                    <h4>🔄 What Changed Today</h4>
                    <p>${summary.what_changed}</p>
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

    formatSummary(text) {
        // Basic formatting for better readability
        return text
            .replace(/\n\n/g, '</p><p>')
            .replace(/\n/g, '<br>')
            .replace(/^/, '<p>')
            .replace(/$/, '</p>')
            .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
            .replace(/\*(.*?)\*/g, '<em>$1</em>');
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
        
        refreshBtn.textContent = '⏳ Generating...';
        refreshBtn.disabled = true;

        try {
            const response = await fetch(`/api/refresh/${ticker}`);
            const result = await response.json();

            if (response.ok) {
                this.showMessage('Summary generated successfully!', 'success');
                // Reload the summary after processing completes
                setTimeout(() => {
                    this.selectTicker(ticker);
                }, 3000);
            } else {
                this.showMessage(result.error || 'Failed to refresh', 'error');
            }
        } catch (error) {
            console.error('Error refreshing ticker:', error);
            this.showMessage('Failed to generate summary', 'error');
        } finally {
            refreshBtn.textContent = originalText;
            refreshBtn.disabled = false;
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
                    document.getElementById('sources-section').style.display = 'none';
                    document.getElementById('history-section').style.display = 'none';
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
`;
document.head.appendChild(style);

// Initialize the app
const app = new StockNewsApp();