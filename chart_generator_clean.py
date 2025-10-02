import requests
import os

class ChartGenerator:
    def __init__(self):
        self.alpha_vantage_key = os.getenv('ALPHA_VANTAGE_API_KEY')
        self.twelve_data_key = os.getenv('TWELVE_DATA_API_KEY')
    
    def get_stock_data(self, ticker, period='30d'):
        """Get stock price data for chart"""
        try:
            # Try Twelve Data first (more reliable for charts)
            if self.twelve_data_key:
                return self._get_twelve_data_prices(ticker, period)
            elif self.alpha_vantage_key:
                return self._get_alpha_vantage_prices(ticker, period)
            else:
                return None
        except Exception as e:
            print(f"Chart data error for {ticker}: {e}")
            return None
    
    def _get_twelve_data_prices(self, ticker, period='30d'):
        """Get price data from Twelve Data"""
        period_map = {'7d': 7, '30d': 30, '90d': 90, '1y': 365, '2y': 730}
        outputsize = period_map.get(period, 30)
        
        url = "https://api.twelvedata.com/time_series"
        params = {
            'symbol': ticker,
            'interval': '1day',
            'outputsize': outputsize,
            'apikey': self.twelve_data_key
        }
        
        response = requests.get(url, params=params, timeout=10)
        data = response.json()
        
        if 'values' in data:
            prices = []
            dates = []
            for item in data['values']:
                dates.append(item['datetime'])
                prices.append(float(item['close']))
            
            # Reverse to get chronological order
            dates.reverse()
            prices.reverse()
            
            return {
                'dates': dates,
                'prices': prices,
                'current_price': prices[-1] if prices else 0,
                'change': ((prices[-1] - prices[0]) / prices[0] * 100) if len(prices) > 1 else 0
            }
        
        return None
    
    def _get_alpha_vantage_prices(self, ticker, period='30d'):
        """Get price data from Alpha Vantage"""
        period_map = {'7d': 7, '30d': 30, '90d': 90, '1y': 365, '2y': 730}
        days = period_map.get(period, 30)
        
        url = "https://www.alphavantage.co/query"
        params = {
            'function': 'TIME_SERIES_DAILY',
            'symbol': ticker,
            'apikey': self.alpha_vantage_key,
            'outputsize': 'full' if days > 100 else 'compact'
        }
        
        response = requests.get(url, params=params, timeout=10)
        data = response.json()
        
        if 'Time Series (Daily)' in data:
            time_series = data['Time Series (Daily)']
            dates = sorted(list(time_series.keys()))[-days:]
            prices = [float(time_series[date]['4. close']) for date in dates]
            
            return {
                'dates': dates,
                'prices': prices,
                'current_price': prices[-1] if prices else 0,
                'change': ((prices[-1] - prices[0]) / prices[0] * 100) if len(prices) > 1 else 0
            }
        
        return None
    
    def generate_chart_config(self, ticker, period='30d'):
        """Generate Chart.js configuration"""
        data = self.get_stock_data(ticker, period)
        
        if not data:
            return None
        
        # Determine trend color
        trend_color = '#27ae60' if data['change'] >= 0 else '#e74c3c'
        
        config = {
            'type': 'line',
            'data': {
                'labels': data['dates'],
                'datasets': [{
                    'label': f'{ticker} Price',
                    'data': data['prices'],
                    'borderColor': trend_color,
                    'backgroundColor': f"{trend_color}20",
                    'borderWidth': 3,
                    'fill': True,
                    'tension': 0.4,
                    'pointRadius': 0,
                    'pointHoverRadius': 6
                }]
            },
            'options': {
                'responsive': True,
                'maintainAspectRatio': False,
                'plugins': {
                    'legend': {
                        'display': False
                    },
                    'tooltip': {
                        'mode': 'index',
                        'intersect': False,
                        'backgroundColor': 'rgba(0,0,0,0.8)',
                        'titleColor': '#fff',
                        'bodyColor': '#fff',
                        'borderColor': trend_color,
                        'borderWidth': 1
                    }
                },
                'scales': {
                    'x': {
                        'display': True,
                        'grid': {
                            'display': False
                        },
                        'ticks': {
                            'maxTicksLimit': 6,
                            'color': '#7f8c8d'
                        }
                    },
                    'y': {
                        'display': True,
                        'grid': {
                            'color': 'rgba(127,140,141,0.1)'
                        },
                        'ticks': {
                            'color': '#7f8c8d',
                            'callback': 'function(value) { return "$" + value.toFixed(2); }'
                        }
                    }
                },
                'interaction': {
                    'intersect': False,
                    'mode': 'index'
                }
            },
            'stats': {
                'current_price': data['current_price'],
                'change_percent': data['change'],
                'trend_color': trend_color
            }
        }
        
        return config