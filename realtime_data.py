import requests
import os
from datetime import datetime
import json
import logging

logger = logging.getLogger(__name__)

class RealtimeDataProvider:
    def __init__(self):
        self.alpha_vantage_key = os.getenv('ALPHA_VANTAGE_API_KEY')
        self.twelve_data_key = os.getenv('TWELVE_DATA_API_KEY')
        self.alpaca_key = os.getenv('ALPACA_API_KEY')
        self.alpaca_secret = os.getenv('ALPACA_SECRET_KEY')
    
    def get_realtime_quote(self, ticker):
        """Get real-time quote data with fallbacks"""
        try:
            # Try Alpaca first
            if self.alpaca_key and self.alpaca_secret:
                quote = self._get_alpaca_quote(ticker)
                if quote:
                    return quote
                logger.debug(f"Alpaca failed for {ticker}, trying fallback")
            
            # Fallback to Alpha Vantage
            if self.alpha_vantage_key:
                quote = self._get_alpha_vantage_quote(ticker)
                if quote:
                    return quote
            
            # Fallback to Twelve Data
            if self.twelve_data_key:
                quote = self._get_twelve_data_quote(ticker)
                if quote:
                    return quote
            
            logger.debug(f"No quote data available for {ticker}")
            return None
        except Exception as e:
            logger.error(f"Realtime data error for {ticker}: {e}")
            return None
    
    def _get_alpha_vantage_quote(self, ticker):
        """Get quote from Alpha Vantage"""
        # Import here to avoid circular import
        from app import check_api_quota, increment_api_usage
        
        if not check_api_quota('alpha_vantage_realtime'):
            logger.warning("Alpha Vantage realtime quota exceeded")
            return None
            
        url = "https://www.alphavantage.co/query"
        params = {
            'function': 'GLOBAL_QUOTE',
            'symbol': ticker,
            'apikey': self.alpha_vantage_key
        }
        
        response = requests.get(url, params=params, timeout=10)
        increment_api_usage('alpha_vantage_realtime')
        data = response.json()
        
        if 'Global Quote' in data:
            quote = data['Global Quote']
            return {
                'symbol': quote.get('01. symbol', ticker),
                'price': float(quote.get('05. price', 0)),
                'change': float(quote.get('09. change', 0)),
                'change_percent': quote.get('10. change percent', '0%').replace('%', ''),
                'volume': int(quote.get('06. volume', 0)),
                'timestamp': datetime.now().isoformat(),
                'source': 'Alpha Vantage'
            }
        
        return None
    
    def _get_twelve_data_quote(self, ticker):
        """Get quote from Twelve Data"""
        # Import here to avoid circular import
        from app import check_api_quota, increment_api_usage
        
        if not check_api_quota('twelve_data_realtime'):
            logger.warning("Twelve Data realtime quota exceeded")
            return None
            
        url = "https://api.twelvedata.com/quote"
        params = {
            'symbol': ticker,
            'apikey': self.twelve_data_key
        }
        
        response = requests.get(url, params=params, timeout=10)
        increment_api_usage('twelve_data_realtime')
        data = response.json()
        
        if 'close' in data:
            return {
                'symbol': data.get('symbol', ticker),
                'price': float(data.get('close', 0)),
                'change': float(data.get('change', 0)),
                'change_percent': data.get('percent_change', '0'),
                'volume': int(data.get('volume', 0)),
                'timestamp': datetime.now().isoformat(),
                'source': 'Twelve Data'
            }
        
        return None
    
    def _get_alpaca_quote(self, ticker):
        """Get real-time quote from Alpaca Markets"""
        import base64
        
        # Alpaca API headers
        credentials = base64.b64encode(f"{self.alpaca_key}:{self.alpaca_secret}".encode()).decode()
        headers = {
            'Authorization': f'Basic {credentials}',
            'Content-Type': 'application/json'
        }
        
        # Get latest quote
        url = f"https://data.alpaca.markets/v2/stocks/{ticker}/quotes/latest"
        
        logger.debug(f"Alpaca quote API call: {url}")
        response = requests.get(url, headers=headers, timeout=10)
        logger.debug(f"Alpaca quote response status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            
            if 'quote' in data:
                quote = data['quote']
                
                # Check if required fields exist
                if 'bid_price' not in quote or 'ask_price' not in quote:
                    logger.debug(f"Missing bid/ask data for {ticker}")
                    return None
                
                # Get previous close for change calculation
                prev_close = self._get_alpaca_prev_close(ticker, headers)
                current_price = (quote['bid_price'] + quote['ask_price']) / 2
                
                change = current_price - prev_close if prev_close else 0
                change_percent = (change / prev_close * 100) if prev_close else 0
                
                return {
                    'symbol': ticker,
                    'price': current_price,
                    'change': change,
                    'change_percent': f"{change_percent:.2f}",
                    'volume': quote.get('bid_size', 0) + quote.get('ask_size', 0),
                    'bid': quote['bid_price'],
                    'ask': quote['ask_price'],
                    'spread': quote['ask_price'] - quote['bid_price'],
                    'timestamp': quote['timestamp'],
                    'source': 'Alpaca Markets'
                }
        
        return None
    
    def _get_alpaca_prev_close(self, ticker, headers):
        """Get previous close price from Alpaca"""
        try:
            from datetime import datetime, timedelta
            
            # Get yesterday's date
            yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
            
            url = f"https://data.alpaca.markets/v2/stocks/{ticker}/bars"
            params = {
                'start': yesterday,
                'end': yesterday,
                'timeframe': '1Day'
            }
            
            logger.debug(f"Alpaca prev close API call: {url} with params: {params}")
            response = requests.get(url, headers=headers, params=params, timeout=10)
            logger.debug(f"Alpaca prev close response status: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                if 'bars' in data and data['bars']:
                    return data['bars'][0]['close']
            
            return None
        except:
            return None
    
    def get_alpaca_market_data(self, ticker):
        """Get comprehensive market data from Alpaca"""
        try:
            if not (self.alpaca_key and self.alpaca_secret):
                return None
                
            import base64
            credentials = base64.b64encode(f"{self.alpaca_key}:{self.alpaca_secret}".encode()).decode()
            headers = {
                'Authorization': f'Basic {credentials}',
                'Content-Type': 'application/json'
            }
            
            # Get latest bars (OHLCV data)
            url = f"https://data.alpaca.markets/v2/stocks/{ticker}/bars/latest"
            
            logger.debug(f"Alpaca bars API call: {url}")
            response = requests.get(url, headers=headers, timeout=10)
            logger.debug(f"Alpaca bars response status: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                
                if 'bar' in data:
                    bar = data['bar']
                    return {
                        'open': bar['open'],
                        'high': bar['high'],
                        'low': bar['low'],
                        'close': bar['close'],
                        'volume': bar['volume'],
                        'vwap': bar.get('vwap', 0),
                        'timestamp': bar['timestamp'],
                        'source': 'Alpaca Markets'
                    }
            
            return None
        except Exception as e:
            logger.error(f"Alpaca market data error for {ticker}: {e}")
            return None
    
    def get_multiple_quotes(self, tickers):
        """Get quotes for multiple tickers"""
        quotes = {}
        try:
            for ticker in tickers:
                quote = self.get_realtime_quote(ticker)
                if quote:
                    quotes[ticker] = quote
        except Exception as e:
            logger.error(f"Error getting multiple quotes: {e}")
        return quotes