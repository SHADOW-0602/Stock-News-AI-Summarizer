// Financial Charts Module
class FinancialCharts {
    constructor() {
        this.charts = {};
    }

    async fetchAndRenderYahooCharts(ticker) {
        try {
            document.getElementById('financial-data').innerHTML = 
                '<div style="text-align: center; color: #666; padding: 2rem;">Loading Yahoo Finance data...</div>';
            
            const response = await fetch(`/api/yahoo-financials/${ticker}`);
            const data = await response.json();
            
            if (!response.ok || data.error) {
                throw new Error(data.error || 'Failed to fetch data');
            }
            
            this.renderYahooCharts(data, ticker);
        } catch (error) {
            console.error('Yahoo Finance error:', error);
            document.getElementById('financial-data').innerHTML = 
                `<div style="text-align: center; color: #666; padding: 2rem;">
                    Yahoo Finance Error: ${error.message}
                </div>`;
        }
    }

    processFinancialData(data) {
        console.log('Processing financial data:', data.length, 'items');
        
        // Extract all available financial metrics
        const allMetrics = this.extractAllMetrics(data);
        console.log('Available metrics:', Object.keys(allMetrics));
        
        return allMetrics;
    }

    calculateTTM(data) {
        const ttmPoints = [];
        for (let i = 3; i < data.length; i++) {
            const last4Quarters = data.slice(i-3, i+1);
            const ttmRevenue = last4Quarters.reduce((sum, item) => {
                const financialData = typeof item.data === 'string' ? JSON.parse(item.data) : item.data;
                const revenue = financialData.totalRevenue || financialData.revenue || financialData.totalOperatingRevenues || 0;
                return sum + revenue;
            }, 0);
            
            if (ttmRevenue > 0) {
                ttmPoints.push({
                    date: data[i].fiscal_date,
                    value: ttmRevenue / 1e9 // Convert to billions
                });
            }
        }
        return ttmPoints;
    }

    extractDatabaseMetrics(data) {
        console.log('Extracting metrics from', data.length, 'database items');
        const metrics = {};
        
        data.forEach((item, index) => {
            try {
                const financialData = typeof item.data === 'string' ? JSON.parse(item.data) : item.data;
                console.log(`Item ${index}:`, Object.keys(financialData));
                
                // Extract ANY numeric field > 1000
                Object.keys(financialData).forEach(key => {
                    const value = financialData[key];
                    if (typeof value === 'number' && !isNaN(value) && Math.abs(value) > 1000) {
                        if (!metrics[key]) metrics[key] = [];
                        metrics[key].push({
                            date: item.fiscal_date,
                            value: Math.abs(value) / 1e6, // Convert to millions
                            period: item.period,
                            type: item.statement_type
                        });
                    }
                });
            } catch (e) {
                console.error('Error processing financial data item:', e, item);
            }
        });
        
        // Sort metrics and keep ones with at least 1 data point
        Object.keys(metrics).forEach(key => {
            metrics[key].sort((a, b) => new Date(a.date) - new Date(b.date));
            if (metrics[key].length === 0) delete metrics[key];
        });
        
        console.log('Final metrics:', Object.keys(metrics));
        return metrics;
    }

    calculateYoYGrowth(data) {
        const growthPoints = [];
        for (let i = 4; i < data.length; i++) {
            const current = data[i];
            const yearAgo = data[i-4];
            
            const currentData = typeof current.data === 'string' ? JSON.parse(current.data) : current.data;
            const yearAgoData = typeof yearAgo.data === 'string' ? JSON.parse(yearAgo.data) : yearAgo.data;
            
            const currentRevenue = currentData.totalRevenue || 0;
            const yearAgoRevenue = yearAgoData.totalRevenue || 0;
            
            if (yearAgoRevenue !== 0) {
                const growth = ((currentRevenue - yearAgoRevenue) / yearAgoRevenue) * 100;
                growthPoints.push({
                    date: current.fiscal_date,
                    value: growth
                });
            }
        }
        return growthPoints;
    }

    renderYahooCharts(data, ticker) {
        const container = document.getElementById('financial-data');
        const charts = [];
        
        if (data.price_history && data.price_history.length > 0) {
            charts.push({ name: 'Stock Price History', data: data.price_history, id: 'price-chart' });
        }
        
        if (data.annual_revenue && data.annual_revenue.length > 0) {
            charts.push({ name: 'Annual Revenue', data: data.annual_revenue, id: 'revenue-chart' });
        }
        
        if (data.yoy_growth && data.yoy_growth.length > 0) {
            charts.push({ name: 'YoY Revenue Growth', data: data.yoy_growth, id: 'yoy-chart' });
        }
        
        console.log('Available chart data:', {
            price_history: data.price_history?.length || 0,
            annual_revenue: data.annual_revenue?.length || 0,
            yoy_growth: data.yoy_growth?.length || 0
        });
        
        if (charts.length === 0) {
            container.innerHTML = '<div style="text-align: center; color: #666; padding: 2rem;">No chart data available from Yahoo Finance</div>';
            return;
        }
        
        console.log(`Rendering ${charts.length} charts:`, charts.map(c => c.name));
        
        const companyInfo = data.company_info || {};
        let chartsHTML = charts.map(chart => `
            <div class="chart-section">
                <h4>${chart.name} (${chart.data.length} data points)</h4>
                <div id="${chart.id}" class="financial-chart"></div>
            </div>
        `).join('');
        
        container.innerHTML = `
            <div class="financial-charts-container">
                <div class="company-info">
                    <h3>${companyInfo.name || ticker}</h3>
                    <p>Sector: ${companyInfo.sector || 'Unknown'} | Market Cap: ${this.formatValue(companyInfo.market_cap || 0)}</p>
                </div>
                ${chartsHTML}
            </div>
        `;
        
        setTimeout(() => {
            charts.forEach(chart => {
                console.log(`Rendering chart: ${chart.name} with ${chart.data.length} data points`);
                this.renderChart(chart.data, chart.name, chart.id);
            });
        }, 100);
    }
    
    formatMetricName(metric) {
        return metric.replace(/([A-Z])/g, ' $1')
                    .replace(/^./, str => str.toUpperCase())
                    .trim();
    }

    renderChart(data, chartName, chartId) {
        const isPrice = chartName.includes('Price');
        const isGrowth = chartName.includes('Growth');
        
        // Simple data validation
        const values = data.map(point => point.value).filter(val => 
            typeof val === 'number' && !isNaN(val) && isFinite(val)
        );
        const dates = data.map(point => point.date);
        
        if (values.length === 0) {
            document.querySelector(`#${chartId}`).innerHTML = 
                '<div style="text-align: center; color: #666; padding: 2rem;">No valid data</div>';
            return;
        }
        
        const options = {
            series: [{ name: chartName, data: values }],
            chart: { type: isPrice ? 'line' : 'column', height: 300 },
            xaxis: { categories: dates },
            theme: { mode: 'dark' },
            colors: [isPrice ? '#00d4ff' : '#4A90E2']
        };
        
        if (isPrice) {
            options.stroke = { curve: 'smooth', width: 2 };
        }

        const chartElement = document.querySelector(`#${chartId}`);
        if (chartElement) {
            console.log('Chart.js available:', typeof Chart);
            
            if (typeof Chart !== 'undefined') {
                chartElement.innerHTML = `<div style="height: 250px; padding: 15px; background: #1a1a1a; border-radius: 8px;"><canvas id="${chartId}-canvas"></canvas></div>`;
                const canvas = document.getElementById(`${chartId}-canvas`);
                
                new Chart(canvas, {
                    type: isPrice ? 'line' : 'bar',
                    data: {
                        labels: dates.map(d => d.slice(0, 7)),
                        datasets: [{
                            label: chartName,
                            data: values,
                            backgroundColor: isGrowth ? values.map(v => v >= 0 ? '#28a745' : '#dc3545') : 'rgba(74, 144, 226, 0.8)',
                            borderColor: isPrice ? '#00d4ff' : '#4A90E2',
                            borderWidth: isPrice ? 2 : 1
                        }]
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        plugins: { 
                            legend: { display: false },
                            tooltip: {
                                callbacks: {
                                    label: function(context) {
                                        const value = context.parsed.y;
                                        if (isPrice) return `$${value.toFixed(2)}`;
                                        if (isGrowth) return `${value.toFixed(1)}%`;
                                        return `$${(value/1e9).toFixed(1)}B`;
                                    }
                                }
                            }
                        },
                        scales: {
                            y: {
                                ticks: {
                                    callback: function(value) {
                                        if (isPrice) return `$${value.toFixed(0)}`;
                                        if (isGrowth) return `${value.toFixed(0)}%`;
                                        return `$${(value/1e9).toFixed(1)}B`;
                                    },
                                    color: '#ccc'
                                },
                                grid: { color: '#333' }
                            },
                            x: {
                                ticks: { color: '#ccc' },
                                grid: { color: '#333' }
                            }
                        }
                    }
                });
                console.log(`${chartName} Chart.js rendered`);
            } else {
                chartElement.innerHTML = `<div style="padding: 20px; background: #2a2a2a; color: #fff;">${chartName}: ${values.join(', ')}</div>`;
            }
        }
    }
    
    formatValue(val) {
        if (Math.abs(val) >= 1e9) return `$${(val/1e9).toFixed(1)}B`;
        if (Math.abs(val) >= 1e6) return `$${(val/1e6).toFixed(1)}M`;
        return `$${val.toFixed(0)}`;
    }
    
    applyZoom(period) {
        const today = new Date();
        let fromDate;
        
        switch(period) {
            case '1Y':
                fromDate = new Date(today.getFullYear() - 1, today.getMonth(), today.getDate());
                break;
            case '2Y':
                fromDate = new Date(today.getFullYear() - 2, today.getMonth(), today.getDate());
                break;
            case '3Y':
                fromDate = new Date(today.getFullYear() - 3, today.getMonth(), today.getDate());
                break;
            case '5Y':
                fromDate = new Date(today.getFullYear() - 5, today.getMonth(), today.getDate());
                break;
            default:
                fromDate = new Date(today.getFullYear() - 10, today.getMonth(), today.getDate());
        }
        
        document.getElementById('chart-from-date').value = fromDate.toISOString().split('T')[0];
        document.getElementById('chart-to-date').value = today.toISOString().split('T')[0];
        
        // Update all charts with new date range
        Object.values(this.charts).forEach(chart => {
            if (chart && chart.updateOptions) {
                chart.updateOptions({
                    xaxis: {
                        min: fromDate.getTime(),
                        max: today.getTime()
                    }
                });
            }
        });
    }
}

// Global instance
const financialCharts = new FinancialCharts();