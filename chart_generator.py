import requests
from datetime import datetime, timedelta
import os
import logging

logger = logging.getLogger(__name__)

class ChartGenerator:
    def __init__(self):
        self.alpha_vantage_key = os.getenv('ALPHA_VANTAGE_API_KEY')
        self.twelve_data_key = os.getenv('TWELVE_DATA_API_KEY')
    
    def get_stock_data(self, ticker, period='30d'):
        """Get stock price data for chart"""
        try:
            logger.debug(f"Getting chart data for {ticker} period {period}")
            logger.debug(f"Twelve Data key: {'SET' if self.twelve_data_key else 'NOT SET'} (length: {len(self.twelve_data_key) if self.twelve_data_key else 0})")
            logger.debug(f"Alpha Vantage key: {'SET' if self.alpha_vantage_key else 'NOT SET'} (length: {len(self.alpha_vantage_key) if self.alpha_vantage_key else 0})")
            
            # Try Twelve Data first (more reliable for charts)
            if self.twelve_data_key and self.twelve_data_key != 'your_twelve_data_api_key':
                logger.debug(f"Trying Twelve Data API for {ticker}")
                data = self._get_twelve_data_prices(ticker, period)
                if data:
                    logger.debug(f"Twelve Data returned data for {ticker}")
                    return data
                else:
                    logger.debug(f"Twelve Data returned no data for {ticker}")
                    
            if self.alpha_vantage_key and self.alpha_vantage_key != 'your-alpha-vantage-api-key':
                logger.debug(f"Trying Alpha Vantage API for {ticker}")
                data = self._get_alpha_vantage_prices(ticker, period)
                if data:
                    logger.debug(f"Alpha Vantage returned data for {ticker}")
                    return data
                else:
                    logger.debug(f"Alpha Vantage returned no data for {ticker}")
                    
            logger.warning(f"No valid chart API keys configured for {ticker}")
            return None
        except Exception as e:
            logger.error(f"Chart data error for {ticker}: {e}")
            return None
    
    def _get_twelve_data_prices(self, ticker, period='30d'):
        """Get price data from Twelve Data"""
        # Map periods to outputsize
        period_map = {
            '7d': 7, '30d': 30, '90d': 90, 
            '1y': 365, '2y': 730
        }
        outputsize = period_map.get(period, 30)
        
        url = "https://api.twelvedata.com/time_series"
        params = {
            'symbol': ticker,
            'interval': '1day',
            'outputsize': outputsize,
            'apikey': self.twelve_data_key
        }
        
        logger.debug(f"Twelve Data chart API call: {url} with params: {params}")
        response = requests.get(url, params=params, timeout=15)
        logger.debug(f"Twelve Data chart response status: {response.status_code}")
        
        if response.status_code != 200:
            return None
            
        data = response.json()
        logger.debug(f"Twelve Data chart response keys: {list(data.keys()) if isinstance(data, dict) else 'Not a dict'}")
        
        if 'values' in data and data['values']:
            logger.debug(f"Twelve Data found {len(data['values'])} data points")
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
        elif 'code' in data and data['code'] == 429:
            logger.warning(f"Twelve Data rate limit exceeded: {data.get('message', '')}")
        elif 'status' in data and data['status'] == 'error':
            logger.warning(f"Twelve Data error: {data.get('message', '')}")
        
        return None
    
    def _get_alpha_vantage_prices(self, ticker, period='30d'):
        """Get price data from Alpha Vantage"""
        # Map periods to days
        period_map = {
            '7d': 7, '30d': 30, '90d': 90, 
            '1y': 365, '2y': 730
        }
        days = period_map.get(period, 30)
        
        url = "https://www.alphavantage.co/query"
        params = {
            'function': 'TIME_SERIES_DAILY',
            'symbol': ticker,
            'apikey': self.alpha_vantage_key,
            'outputsize': 'full' if days > 100 else 'compact'
        }
        
        logger.debug(f"Alpha Vantage chart API call: {url} with params: {params}")
        response = requests.get(url, params=params, timeout=15)
        logger.debug(f"Alpha Vantage chart response status: {response.status_code}")
        
        if response.status_code != 200:
            return None
            
        data = response.json()
        logger.debug(f"Alpha Vantage chart response keys: {list(data.keys()) if isinstance(data, dict) else 'Not a dict'}")
        
        if 'Time Series (Daily)' in data:
            time_series = data['Time Series (Daily)']
            logger.debug(f"Alpha Vantage found {len(time_series)} total data points, using last {days}")
            dates = sorted(list(time_series.keys()))[-days:]  # Last N days
            prices = [float(time_series[date]['4. close']) for date in dates]
            
            return {
                'dates': dates,
                'prices': prices,
                'current_price': prices[-1] if prices else 0,
                'change': ((prices[-1] - prices[0]) / prices[0] * 100) if len(prices) > 1 else 0
            }
        elif 'Information' in data:
            logger.warning(f"Alpha Vantage quota/limit: {data['Information']}")
        
        return None
    

    
    def generate_chart_config(self, ticker, period='30d'):
        """Generate Chart.js configuration"""
        logger.debug(f"Generating chart config for {ticker} period {period}")
        data = self.get_stock_data(ticker, period)
        
        if not data:
            logger.error(f"No stock data returned for {ticker} in generate_chart_config")
            return None
            
        logger.debug(f"Stock data found: {len(data.get('dates', []))} data points")
        
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