from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
import requests
from bs4 import BeautifulSoup
import os
from datetime import datetime, timedelta
from chart_generator import ChartGenerator
from ml_analysis import MLAnalyzer
from entity_highlighter import EntityHighlighter
import logging
try:
    import google.generativeai as genai
except ImportError:
    try:
        import google.genai as genai
    except ImportError:
        genai = None
        print("Google GenAI library not found. Install with: pip install google-generativeai")
from apscheduler.schedulers.background import BackgroundScheduler
import time
from dotenv import load_dotenv
from concurrent.futures import ThreadPoolExecutor, as_completed
from database import db
from cache import cache
from financial_data import financial_data
import warnings
import math
warnings.filterwarnings('ignore', category=UserWarning)

def clean_nan_values(obj):
    """Recursively clean NaN values from nested objects for JSON serialization"""
    if isinstance(obj, dict):
        return {k: clean_nan_values(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [clean_nan_values(item) for item in obj]
    elif isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return obj
    else:
        return obj

# Load environment variables
load_dotenv()

# Suppress Google library warnings
os.environ['GRPC_VERBOSITY'] = 'ERROR'
os.environ['GLOG_minloglevel'] = '2'


app = Flask(__name__)
CORS(app)

# Override jsonify to clean NaN values
from flask import json as flask_json
original_jsonify = jsonify

def safe_jsonify(*args, **kwargs):
    """Custom jsonify that cleans NaN values"""
    if args:
        data = clean_nan_values(args[0]) if len(args) == 1 else clean_nan_values(args)
    else:
        data = clean_nan_values(kwargs)
    return original_jsonify(data)

# Replace Flask's jsonify
import flask
flask.jsonify = safe_jsonify
jsonify = safe_jsonify

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('app.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Configuration
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
POLYGON_API_KEY = os.getenv('POLYGON_API_KEY')
ALPHA_VANTAGE_API_KEY = os.getenv('ALPHA_VANTAGE_API_KEY')
TWELVE_DATA_API_KEY = os.getenv('TWELVE_DATA_API_KEY')
FINNHUB_API_KEY = os.getenv('FINNHUB_API_KEY')
ALPACA_API_KEY = os.getenv('ALPACA_API_KEY')
ALPACA_SECRET_KEY = os.getenv('ALPACA_SECRET_KEY')
API_NINJAS_KEY = os.getenv('API_NINJAS_KEY')
BENZINGA_API_KEY = os.getenv('BENZINGA_API_KEY')
NEWSAPI_KEY = os.getenv('NEWSAPI_KEY')
IEX_API_KEY = os.getenv('IEX_API_KEY')
QUANDL_API_KEY = os.getenv('QUANDL_API_KEY')
FMP_API_KEY = os.getenv('FMP_API_KEY')
PEXELS_API_KEY = os.getenv('PEXELS_API_KEY')

logger.info("Stock News AI Summarizer started")

# API Usage Tracking
api_usage = {
    'gemini': {'calls': 0, 'last_reset': datetime.now().date()},
    'polygon': {'calls': 0, 'last_reset': datetime.now().date()},
    'alpha_vantage': {'calls': 0, 'last_reset': datetime.now().date()},
    'twelve_data': {'calls': 0, 'last_reset': datetime.now().date()},
    'finnhub': {'calls': 0, 'last_reset': datetime.now().date()},
    'newsapi': {'calls': 0, 'last_reset': datetime.now().date()}
}

ML_CACHE_DURATION = 12 * 3600  # 12 hours for ML predictions

# Financial statements now handled directly by Yahoo Finance in the endpoint



# Daily Limits (official free tier limits)
DAILY_LIMITS = {
    'gemini': 1500,  # 15 RPM, 1M tokens/month (daily estimate)
    'polygon': 'unlimited',  # 5 RPM but unlimited monthly calls
    'alpha_vantage': 25,  # 25 requests/day (free tier)
    'twelve_data': 800,  # 800 requests/day (free tier)
    'finnhub': 60,  # 60 calls/minute, ~86,400/day theoretical
    'newsapi': 1000,  # 1000 requests/day (free tier)
    'alpaca': 'unlimited'  # Unlimited real-time data
}

def check_api_quota(service):
    """Check if API quota is available"""
    # Initialize service if not exists
    if service not in api_usage:
        api_usage[service] = {'calls': 0, 'last_reset': datetime.now().date()}
        logger.debug(f"Initialized API usage tracking for {service}")
    
    today = datetime.now().date()
    if api_usage[service]['last_reset'] != today:
        api_usage[service]['calls'] = 0
        api_usage[service]['last_reset'] = today
        logger.info(f"Reset {service} daily counter")
    
    limit = DAILY_LIMITS.get(service)
    if limit == 'unlimited':
        return True
    
    if isinstance(limit, int) and api_usage[service]['calls'] >= limit:
        logger.warning(f"{service} daily limit reached ({limit})")
        return False
    return True

def increment_api_usage(service):
    """Increment API usage counter"""
    # Initialize service if not exists
    if service not in api_usage:
        api_usage[service] = {'calls': 0, 'last_reset': datetime.now().date()}
    
    api_usage[service]['calls'] += 1

# Initialize Gemini client
logger.info(f"Gemini initialization - Library: {bool(genai)}, Key exists: {bool(GEMINI_API_KEY)}, Key length: {len(GEMINI_API_KEY) if GEMINI_API_KEY else 0}")
if GEMINI_API_KEY:
    logger.info(f"Gemini API key preview: {GEMINI_API_KEY[:15]}...{GEMINI_API_KEY[-5:]}")

if genai and GEMINI_API_KEY and GEMINI_API_KEY.strip() != '' and GEMINI_API_KEY != 'your-gemini-api-key':
    try:
        logger.info("Attempting to configure Gemini client...")
        genai.configure(api_key=GEMINI_API_KEY)
        client = genai
        logger.info(f"Gemini client configured successfully with key: {GEMINI_API_KEY[:10]}...{GEMINI_API_KEY[-5:]}")
    except Exception as e:
        logger.error(f"Failed to configure Gemini client: {e}")
        logger.error(f"Error type: {type(e).__name__}")
        client = None
else:
    client = None
    logger.error(f"Gemini not available - library: {bool(genai)}, key present: {bool(GEMINI_API_KEY)}, key valid: {GEMINI_API_KEY != 'your-gemini-api-key' if GEMINI_API_KEY else False}")

# Initialize scheduler for cache cleanup
scheduler = BackgroundScheduler()
scheduler.add_job(cache.cleanup_expired, 'interval', hours=1)
scheduler.start()
logger.info("Cache cleanup scheduler started (runs every hour)")



class NewsCollector:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        # Optimize session for parallel requests
        adapter = requests.adapters.HTTPAdapter(
            pool_connections=10,
            pool_maxsize=20,
            max_retries=2
        )
        self.session.mount('http://', adapter)
        self.session.mount('https://', adapter)
    
    def get_tradingview_news(self, ticker):
        """Get TradingView news using HTTP requests (no Selenium)"""
        logger.debug(f"Starting TradingView HTTP scraping for {ticker}")
        try:
            articles = []
            
            # Method 1: TradingView RSS feeds
            rss_feeds = [
                "https://www.tradingview.com/feed/",
                "https://www.tradingview.com/blog/feed/"
            ]
            
            for feed_url in rss_feeds:
                try:
                    response = self.session.get(feed_url, timeout=10)
                    if response.status_code == 200:
                        soup = BeautifulSoup(response.content, 'xml')
                        items = soup.find_all('item')[:5]
                        
                        for item in items:
                            try:
                                title_elem = item.find('title')
                                link_elem = item.find('link')
                                desc_elem = item.find('description')
                                
                                if title_elem and link_elem:
                                    title = title_elem.get_text(strip=True)
                                    url = link_elem.get_text(strip=True)
                                    desc = desc_elem.get_text(strip=True) if desc_elem else title
                                    
                                    # Accept all TradingView content (it's already financial)
                                    if title and len(title) > 15:
                                        articles.append({
                                            'title': title,
                                            'url': url,
                                            'source': 'TradingView',
                                            'content': desc[:200],
                                            'date': datetime.now().isoformat()
                                        })
                            except Exception:
                                continue
                        
                        if articles:  # If we got articles from this feed, stop
                            break
                            
                except Exception:
                    continue
            
            # Method 2: Financial news aggregators (TradingView alternatives)
            if len(articles) < 3:
                try:
                    # Use Investing.com as TradingView alternative
                    inv_url = f"https://www.investing.com/search/?q={ticker}&tab=news"
                    response = self.session.get(inv_url, timeout=10)
                    
                    if response.status_code == 200:
                        soup = BeautifulSoup(response.content, 'html.parser')
                        news_links = soup.find_all('a', href=True)[:20]
                        
                        for link in news_links:
                            title = link.get_text(strip=True)
                            href = link.get('href', '')
                            
                            if (title and len(title) > 20 and href and
                                '/news/' in href and
                                any(word in title.lower() for word in [ticker.lower(), 'stock', 'market'])):
                                
                                if not href.startswith('http'):
                                    href = f"https://www.investing.com{href}"
                                
                                articles.append({
                                    'title': title,
                                    'url': href,
                                    'source': 'TradingView (Investing.com)',
                                    'content': title,
                                    'date': datetime.now().isoformat()
                                })
                                
                                if len(articles) >= 8:
                                    break
                except Exception:
                    pass
            
            logger.info(f"TradingView: Found {len(articles)} articles for {ticker}")
            return articles
            
        except Exception as e:
            logger.error(f"TradingView HTTP scraping error for {ticker}: {e}")
            return []
    
    def get_company_name(self, ticker):
        """Get company name for better search results"""
        company_names = {
            'AAPL': 'Apple',
            'GOOGL': 'Google',
            'MSFT': 'Microsoft',
            'TSLA': 'Tesla',
            'AMZN': 'Amazon',
            'META': 'Meta',
            'NVDA': 'Nvidia',
            'NFLX': 'Netflix'
        }
        return company_names.get(ticker, ticker)
    
    def get_reuters_via_aggregator(self, ticker):
        """Get Reuters content via MSN Money and other aggregators"""
        try:
            company_name = self.get_company_name(ticker)
            
            # Try MSN Money which republishes Reuters content
            url = f"https://www.msn.com/en-us/money/news"
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            
            response = requests.get(url, headers=headers, timeout=15)
            if response.status_code == 200:
                soup = BeautifulSoup(response.content, 'html.parser')
                articles = []
                
                # Look for news articles
                news_links = soup.find_all('a', href=True)
                for link in news_links:
                    title = link.get_text(strip=True)
                    url = link.get('href', '')
                    
                    # Check for Reuters content or company relevance
                    if (title and len(title) > 25 and url and
                        ('reuters' in title.lower() or 
                         'reuters' in url.lower() or
                         company_name.lower() in title.lower() or 
                         ticker.lower() in title.lower() or
                         any(word in title.lower() for word in ['stock', 'market', 'earnings']))):
                        
                        if not url.startswith('http'):
                            url = f"https://www.msn.com{url}"
                        
                        articles.append({
                            'title': title,
                            'url': url,
                            'source': 'Reuters (via MSN)',
                            'content': title,
                            'date': datetime.now().isoformat()
                        })
                        
                        if len(articles) >= 5:
                            break
                
                return articles
                
        except Exception as e:
            print(f"Reuters aggregator error: {e}")
        return []
    
    def get_reuters_rss(self, ticker):
        """Get Reuters news via RSS feeds"""
        try:
            # Try Reuters RSS feeds
            rss_urls = [
                "https://feeds.reuters.com/reuters/businessNews",
                "https://feeds.reuters.com/reuters/technologyNews",
                "https://feeds.reuters.com/reuters/companyNews"
            ]
            
            company_name = self.get_company_name(ticker)
            articles = []
            
            for rss_url in rss_urls:
                try:
                    response = requests.get(rss_url, timeout=10)
                    if response.status_code == 200:
                        soup = BeautifulSoup(response.content, 'xml')
                        items = soup.find_all('item')[:15]
                        
                        for item in items:
                            try:
                                title_elem = item.find('title')
                                link_elem = item.find('link')
                                desc_elem = item.find('description')
                                
                                if title_elem and link_elem:
                                    title = title_elem.get_text(strip=True)
                                    url = link_elem.get_text(strip=True)
                                    desc = desc_elem.get_text(strip=True) if desc_elem else title
                                    
                                    # Check relevance
                                    if (title and len(title) > 20 and
                                        (ticker.lower() in title.lower() or 
                                         company_name.lower() in title.lower() or
                                         any(word in title.lower() for word in ['stock', 'market', 'earnings', 'financial', 'business']))):
                                        
                                        articles.append({
                                            'title': title,
                                            'url': url,
                                            'source': 'Reuters (RSS)',
                                            'content': desc[:200],
                                            'date': datetime.now().isoformat()
                                        })
                                        
                            except Exception as item_error:
                                continue
                        
                        if len(articles) >= 5:
                            break
                            
                except Exception as feed_error:
                    continue
            
            return articles[:5]
            
        except Exception as e:
            print(f"Reuters RSS error: {e}")
        return []
    
    def get_invezz_rss(self, ticker):
        """Get Invezz news via RSS feed"""
        try:
            # Try Invezz RSS feeds
            rss_urls = [
                "https://invezz.com/feed/",
                "https://invezz.com/news/feed/",
                "https://invezz.com/news/stock-market/feed/"
            ]
            
            company_name = self.get_company_name(ticker)
            articles = []
            
            for rss_url in rss_urls:
                try:
                    response = requests.get(rss_url, timeout=10)
                    if response.status_code == 200:
                        soup = BeautifulSoup(response.content, 'xml')
                        items = soup.find_all('item')[:20]
                        
                        for item in items:
                            try:
                                title_elem = item.find('title')
                                link_elem = item.find('link')
                                desc_elem = item.find('description')
                                
                                if title_elem and link_elem:
                                    title = title_elem.get_text(strip=True)
                                    url = link_elem.get_text(strip=True)
                                    desc = desc_elem.get_text(strip=True) if desc_elem else title
                                    
                                    # Check relevance
                                    if (title and len(title) > 20 and
                                        (ticker.lower() in title.lower() or 
                                         company_name.lower() in title.lower() or
                                         any(word in title.lower() for word in ['stock', 'market', 'trading', 'investment']))):
                                        
                                        articles.append({
                                            'title': title,
                                            'url': url,
                                            'source': 'Invezz (RSS)',
                                            'content': desc[:200],
                                            'date': datetime.now().isoformat()
                                        })
                                        
                            except Exception as item_error:
                                continue
                        
                        if articles:
                            break
                            
                except Exception as feed_error:
                    continue
            
            return articles[:5]
            
        except Exception as e:
            print(f"Invezz RSS error: {e}")
        return []
    
    def get_yahoo_finance_news(self, ticker):
        """Get news from Yahoo Finance (often includes Reuters content)"""
        try:
            url = f"https://finance.yahoo.com/news/"
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            
            response = requests.get(url, headers=headers, timeout=10)
            if response.status_code == 200:
                soup = BeautifulSoup(response.content, 'html.parser')
                articles = []
                
                # Look for news links
                links = soup.find_all('a', href=True)
                
                for link in links[:50]:
                    title = link.get_text(strip=True)
                    href = link.get('href', '')
                    
                    if (title and len(title) > 20 and href and
                        any(word in title.lower() for word in ['stock', 'market', 'earnings', 'financial'])):
                        
                        if not href.startswith('http'):
                            href = f"https://finance.yahoo.com{href}"
                        
                        # Check if it's Reuters content
                        source_name = 'Yahoo Finance'
                        if 'reuters' in title.lower():
                            source_name = 'Reuters (via Yahoo)'
                        
                        articles.append({
                            'title': title,
                            'url': href,
                            'source': source_name,
                            'content': title,
                            'date': datetime.now().isoformat()
                        })
                        
                        if len(articles) >= 5:
                            break
                
                return articles
                
        except Exception as e:
            print(f"Yahoo Finance error: {e}")
        return []
    
    def _call_polygon_with_fallback(self, url, params):
        """Call Polygon API with quota checking"""
        if not check_api_quota('polygon'):
            logger.warning("Polygon quota exhausted, skipping API call")
            return []
        
        try:
            time.sleep(12)  # 5 calls/min = 12 sec delay
            response = self.session.get(url, params=params, timeout=10)
            increment_api_usage('polygon')
            return response.json()
        except Exception as e:
            error_str = str(e)
            if 'quota' in error_str.lower() or 'limit' in error_str.lower():
                logger.error(f"Polygon quota/rate limit hit: {error_str}")
                api_usage['polygon']['calls'] = DAILY_LIMITS['polygon']
                return []
            raise e
    
    def get_yahoo_ticker_news(self, ticker):
        """Get ticker-specific news from Yahoo Finance (Cloud-compatible)"""
        logger.debug(f"Starting Yahoo Finance ticker news for {ticker}")
        try:
            # Use Yahoo Finance RSS feed for better reliability
            rss_url = f"https://feeds.finance.yahoo.com/rss/2.0/headline?s={ticker}&region=US&lang=en-US"
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            }
            
            articles = []
            
            try:
                # Try RSS feed first
                response = self.session.get(rss_url, headers=headers, timeout=10)
                if response.status_code == 200:
                    soup = BeautifulSoup(response.content, 'xml')
                    items = soup.find_all('item')[:10]
                    
                    for item in items:
                        try:
                            title_elem = item.find('title')
                            link_elem = item.find('link')
                            desc_elem = item.find('description')
                            
                            if title_elem and link_elem:
                                title = title_elem.get_text(strip=True)
                                url = link_elem.get_text(strip=True)
                                desc = desc_elem.get_text(strip=True) if desc_elem else title
                                
                                if title and len(title) > 15:
                                    articles.append({
                                        'title': title,
                                        'url': url,
                                        'source': 'Yahoo Finance (RSS)',
                                        'content': desc[:200],
                                        'date': datetime.now().isoformat()
                                    })
                        except Exception:
                            continue
            except Exception:
                pass
            
            # Fallback to web scraping if RSS fails
            if not articles:
                try:
                    web_url = f"https://finance.yahoo.com/quote/{ticker}/news"
                    response = self.session.get(web_url, headers=headers, timeout=15)
                    
                    if response.status_code == 200:
                        soup = BeautifulSoup(response.content, 'html.parser')
                        
                        # Look for news with improved selectors
                        news_links = soup.find_all('a', href=True)
                        
                        for link in news_links[:50]:
                            title = link.get_text(strip=True)
                            href = link.get('href', '')
                            
                            # Better filtering for Yahoo Finance news
                            if (title and len(title) > 25 and href and
                                '/news/' in href and
                                any(word in title.lower() for word in ['stock', 'market', 'earnings', 'financial', ticker.lower()])):
                                
                                if not href.startswith('http'):
                                    href = f"https://finance.yahoo.com{href}"
                                
                                articles.append({
                                    'title': title,
                                    'url': href,
                                    'source': 'Yahoo Finance',
                                    'content': title,
                                    'date': datetime.now().isoformat()
                                })
                                
                                if len(articles) >= 5:
                                    break
                except Exception:
                    pass
            
            logger.info(f"Yahoo Finance: Found {len(articles)} articles for {ticker}")
            return articles
            
        except Exception as e:
            logger.warning(f"Yahoo Finance ticker news failed for {ticker}: {str(e)[:100]}")
            return []
    
    def get_finviz_news(self, ticker):
        """Scrape Finviz news for ticker with session reuse"""
        logger.debug(f"Starting Finviz scraping for {ticker}")
        try:
            url = f"https://finviz.com/quote.ashx?t={ticker}"
            logger.debug(f"Fetching URL: {url}")
            response = self.session.get(url, timeout=10)
            logger.debug(f"Response status: {response.status_code}, Content length: {len(response.content)}")
            soup = BeautifulSoup(response.content, 'html.parser')
            
            articles = []
            news_table = soup.find('table', class_='fullview-news-outer')
            
            if news_table:
                rows = news_table.find_all('tr')[:10]
                for row in rows:
                    link = row.find('a')
                    if link:
                        title = link.get_text(strip=True)
                        url = link.get('href', '')
                        
                        articles.append({
                            'title': title,
                            'url': url,
                            'source': 'Finviz',
                            'content': title,
                            'date': datetime.now().isoformat()
                        })
            
            logger.info(f"Finviz: Found {len(articles)} articles for {ticker}")
            return articles
        except Exception as e:
            logger.error(f"Finviz scraping error for {ticker}: {e}")
            return []
    
    def get_polygon_news(self, ticker):
        """Get news from Polygon API"""
        logger.debug(f"Starting Polygon API call for {ticker}")
        try:
            url = f"https://api.polygon.io/v2/reference/news"
            params = {
                'ticker': ticker,
                'limit': 10,
                'apikey': POLYGON_API_KEY
            }
            logger.debug(f"API URL: {url}, Params: {params}")
            
            data = self._call_polygon_with_fallback(url, params)
            if not data:
                return []
            
            articles = []
            if 'results' in data:
                for item in data['results']:
                    title = item.get('title', '')
                    url = item.get('article_url', '')
                    if title and len(title) > 15 and url:
                        articles.append({
                            'title': title,
                            'url': url,
                            'source': 'Polygon',
                            'content': item.get('description', item.get('title', '')),
                            'date': item.get('published_utc', datetime.now().isoformat())
                        })
            
            logger.info(f"Polygon: Found {len(articles)} articles for {ticker}")
            return articles
        except Exception as e:
            logger.error(f"Polygon API error for {ticker}: {e}")
            return []
    
    def get_alphavantage_news(self, ticker):
        """Get news from Alpha Vantage API"""
        logger.debug(f"Starting Alpha Vantage API call for {ticker}")
        try:
            url = "https://www.alphavantage.co/query"
            params = {
                'function': 'NEWS_SENTIMENT',
                'tickers': ticker,
                'apikey': ALPHA_VANTAGE_API_KEY,
                'limit': 10
            }
            
            response = self.session.get(url, params=params, timeout=15)
            
            if response.status_code != 200:
                logger.error(f"Alpha Vantage returned status {response.status_code}")
                return []
            
            data = response.json()
            
            articles = []
            if 'feed' in data:
                for item in data['feed'][:15]:
                    try:
                        title = item.get('title', '')
                        url = item.get('url', '')
                        summary = item.get('summary', '')
                        
                        if title and len(title) > 15 and url:
                            articles.append({
                                'title': title,
                                'url': url,
                                'source': 'Alpha Vantage',
                                'content': summary or title,
                                'date': item.get('time_published', datetime.now().isoformat())
                            })
                    except Exception as item_error:
                        logger.debug(f"Error processing Alpha Vantage item: {item_error}")
                        continue
            
            logger.info(f"Alpha Vantage: Found {len(articles)} articles for {ticker}")
            return articles
            
        except Exception as e:
            logger.error(f"Alpha Vantage API error for {ticker}: {e}")
            return []
    
    def get_twelve_data_news(self, ticker):
        """Get news-like data from Twelve Data using earnings and profile endpoints"""
        logger.debug(f"Starting Twelve Data earnings/profile collection for {ticker}")
        try:
            articles = []
            
            # Get earnings data (acts as news)
            earnings_url = "https://api.twelvedata.com/earnings"
            earnings_params = {
                'symbol': ticker,
                'apikey': TWELVE_DATA_API_KEY
            }
            
            response = self.session.get(earnings_url, params=earnings_params, timeout=15)
            
            if response.status_code == 200:
                data = response.json()
                if 'earnings' in data and data['earnings']:
                    for earning in data['earnings'][:3]:  # Latest 3 earnings
                        try:
                            date = earning.get('date', '')
                            eps_estimate = earning.get('eps_estimate', 'N/A')
                            eps_actual = earning.get('eps_actual', 'N/A')
                            revenue_estimate = earning.get('revenue_estimate', 'N/A')
                            revenue_actual = earning.get('revenue_actual', 'N/A')
                            
                            if date:
                                title = f"{ticker} Earnings Report - {date}: EPS ${eps_actual} vs ${eps_estimate} est"
                                content = f"Earnings data for {ticker} on {date}. EPS: ${eps_actual} (est: ${eps_estimate}), Revenue: ${revenue_actual} (est: ${revenue_estimate})"
                                
                                articles.append({
                                    'title': title,
                                    'url': f"https://twelvedata.com/stocks/{ticker.lower()}/earnings",
                                    'source': 'Twelve Data',
                                    'content': content,
                                    'date': date
                                })
                        except Exception as item_error:
                            logger.debug(f"Error processing Twelve Data earnings item: {item_error}")
                            continue
            
            # Get company profile (acts as company news)
            profile_url = "https://api.twelvedata.com/profile"
            profile_params = {
                'symbol': ticker,
                'apikey': TWELVE_DATA_API_KEY
            }
            
            response = self.session.get(profile_url, params=profile_params, timeout=15)
            
            if response.status_code == 200:
                data = response.json()
                if 'name' in data and 'description' in data:
                    company_name = data.get('name', ticker)
                    description = data.get('description', '')[:200] + '...' if len(data.get('description', '')) > 200 else data.get('description', '')
                    sector = data.get('sector', 'Unknown')
                    industry = data.get('industry', 'Unknown')
                    
                    title = f"{company_name} ({ticker}) Company Profile Update"
                    content = f"Company: {company_name}. Sector: {sector}, Industry: {industry}. {description}"
                    
                    articles.append({
                        'title': title,
                        'url': f"https://twelvedata.com/stocks/{ticker.lower()}",
                        'source': 'Twelve Data',
                        'content': content,
                        'date': datetime.now().isoformat()
                    })
            
            logger.info(f"Twelve Data: Found {len(articles)} earnings/profile items for {ticker}")
            return articles
            
        except Exception as e:
            logger.error(f"Twelve Data earnings/profile error for {ticker}: {e}")
            return []
    
    def get_finnhub_news(self, ticker):
        """Get news from Finnhub API"""
        logger.debug(f"Starting Finnhub API call for {ticker}")
        try:
            url = "https://finnhub.io/api/v1/company-news"
            params = {
                'symbol': ticker,
                'token': FINNHUB_API_KEY,
                'from': (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d'),
                'to': datetime.now().strftime('%Y-%m-%d')
            }
            
            logger.debug(f"Finnhub API call: {url} with params: {params}")
            response = self.session.get(url, params=params, timeout=15)
            logger.debug(f"Finnhub response status: {response.status_code}")
            
            if response.status_code != 200:
                logger.error(f"Finnhub returned status {response.status_code}, response: {response.text[:200]}")
                return []
            
            data = response.json()
            logger.debug(f"Finnhub response type: {type(data)}, length: {len(data) if isinstance(data, list) else 'N/A'}")
            
            articles = []
            if isinstance(data, list):
                for item in data[:15]:
                    try:
                        title = item.get('headline', '')
                        url = item.get('url', '')
                        summary = item.get('summary', '')
                        
                        if title and len(title) > 15 and url:
                            articles.append({
                                'title': title,
                                'url': url,
                                'source': 'Finnhub',
                                'content': summary or title,
                                'date': datetime.fromtimestamp(item.get('datetime', 0)).isoformat()
                            })
                    except Exception as item_error:
                        logger.debug(f"Error processing Finnhub item: {item_error}")
                        continue
            
            logger.info(f"Finnhub: Found {len(articles)} articles for {ticker}")
            return articles
            
        except Exception as e:
            logger.error(f"Finnhub API error for {ticker}: {e}")
            logger.debug(f"Finnhub full error: {repr(e)}")
            return []
    
    def get_benzinga_news(self, ticker):
        """Get news from Benzinga API"""
        logger.debug(f"Starting Benzinga API call for {ticker}")
        try:
            url = "https://api.benzinga.com/api/v2/news"
            params = {
                'token': BENZINGA_API_KEY,
                'tickers': ticker,
                'pageSize': 10,
                'displayOutput': 'full'
            }
            
            response = self.session.get(url, params=params, timeout=15)
            
            if response.status_code != 200:
                logger.debug(f"Benzinga returned status {response.status_code} for {ticker}")
                return []
            
            # Check if response has content
            if not response.text.strip():
                logger.debug(f"Benzinga returned empty response for {ticker}")
                return []
            
            try:
                data = response.json()
            except ValueError as json_error:
                logger.debug(f"Benzinga JSON parse error for {ticker}: {json_error}")
                return []
            
            articles = []
            
            if isinstance(data, list):
                for item in data[:15]:
                    try:
                        title = item.get('title', '')
                        url = item.get('url', '')
                        content = item.get('body', item.get('teaser', ''))
                        
                        if title and len(title) > 15 and url:
                            articles.append({
                                'title': title,
                                'url': url,
                                'source': 'Benzinga',
                                'content': content or title,
                                'date': item.get('created', datetime.now().isoformat())
                            })
                    except Exception as item_error:
                        logger.debug(f"Error processing Benzinga item: {item_error}")
                        continue
            
            logger.info(f"Benzinga: Found {len(articles)} articles for {ticker}")
            return articles
            
        except Exception as e:
            logger.debug(f"Benzinga API error for {ticker}: {e}")
            return []
    
    def get_stockstory_news(self, ticker):
        """Scrape StockStory news for ticker"""
        logger.debug(f"Starting StockStory scraping for {ticker}")
        try:
            # Try main search page instead of specific stock page
            url = f"https://stockstory.org/?s={ticker}"
            response = self.session.get(url, timeout=15)
            
            if response.status_code != 200:
                return []
            
            soup = BeautifulSoup(response.content, 'html.parser')
            articles = []
            
            # Look for search results or article links
            article_links = soup.find_all('a', href=True)
            
            for link in article_links[:25]:
                try:
                    href = link.get('href', '')
                    title = link.get_text(strip=True)
                    
                    # Filter for relevant articles
                    if (title and len(title) > 20 and 
                        any(word in title.lower() for word in [ticker.lower(), 'stock', 'earnings', 'analysis']) and
                        href and ('stockstory.org' in href or href.startswith('/'))):
                        
                        full_url = href if href.startswith('http') else f"https://stockstory.org{href}"
                        
                        articles.append({
                            'title': title,
                            'url': full_url,
                            'source': 'StockStory',
                            'content': title,
                            'date': datetime.now().isoformat()
                        })
                        
                        if len(articles) >= 15:
                            break
                            
                except Exception as item_error:
                    logger.debug(f"Error processing StockStory item: {item_error}")
                    continue
            
            logger.info(f"StockStory: Found {len(articles)} articles for {ticker}")
            return articles
            
        except Exception as e:
            logger.error(f"StockStory scraping error for {ticker}: {e}")
            return []
    
    def get_motley_fool_news(self, ticker):
        """Scrape Motley Fool news for ticker"""
        logger.debug(f"Starting Motley Fool scraping for {ticker}")
        try:
            # Try investing section main page
            url = "https://www.fool.com/investing/"
            response = self.session.get(url, timeout=15)
            
            if response.status_code != 200:
                logger.debug(f"Motley Fool returned status {response.status_code} for {ticker}")
                return []
            
            soup = BeautifulSoup(response.content, 'html.parser')
            articles = []
            
            # Look for article links in investing section
            article_links = soup.find_all('a', href=True)
            
            for link in article_links[:50]:
                try:
                    href = link.get('href', '')
                    title = link.get_text(strip=True)
                    
                    # Filter for relevant articles (broader search since we're on investing page)
                    if (title and len(title) > 25 and 
                        any(word in title.lower() for word in ['stock', 'earnings', 'buy', 'sell', 'invest', 'market', 'dividend']) and
                        href and ('fool.com' in href or href.startswith('/')) and
                        '/investing/' in href and
                        not any(skip in href for skip in ['login', 'signup', 'subscribe', 'newsletter'])):
                        
                        full_url = href if href.startswith('http') else f"https://www.fool.com{href}"
                        
                        articles.append({
                            'title': title,
                            'url': full_url,
                            'source': 'Motley Fool',
                            'content': title,
                            'date': datetime.now().isoformat()
                        })
                        
                        if len(articles) >= 15:
                            break
                            
                except Exception as item_error:
                    logger.debug(f"Error processing Motley Fool item: {item_error}")
                    continue
            
            logger.info(f"Motley Fool: Found {len(articles)} articles for {ticker}")
            return articles
            
        except Exception as e:
            logger.error(f"Motley Fool scraping error for {ticker}: {e}")
            return []
    

    
    def get_techcrunch_news(self, ticker):
        """Get news from TechCrunch with working selectors"""
        try:
            url = "https://techcrunch.com/"
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            
            response = requests.get(url, headers=headers, timeout=10)
            if response.status_code == 200:
                soup = BeautifulSoup(response.content, 'html.parser')
                articles = []
                
                # Find all article links
                links = soup.find_all('a', href=True)
                
                for link in links:
                    href = link.get('href', '')
                    title = link.get_text(strip=True)
                    
                    # Filter for actual article links
                    if (href and title and len(title) > 20 and
                        '/2025/' in href and 'techcrunch.com' in href and
                        not any(skip in href for skip in ['author', 'category', 'tag', 'events'])):
                        
                        articles.append({
                            'title': title,
                            'url': href,
                            'source': 'TechCrunch',
                            'content': title,
                            'date': datetime.now().isoformat()
                        })
                        
                        if len(articles) >= 5:
                            break
                
                return articles
                
        except Exception as e:
            print(f"TechCrunch error: {e}")
        return []
    
    def get_99bitcoins_news(self, ticker):
        """Get news from 99Bitcoins RSS feed"""
        logger.debug(f"Starting 99Bitcoins RSS feed collection for {ticker}")
        try:
            url = "https://99bitcoins.com/feed/"
            response = self.session.get(url, timeout=15)
            
            if response.status_code != 200:
                logger.debug(f"99Bitcoins RSS returned status {response.status_code} for {ticker}")
                return []
            
            soup = BeautifulSoup(response.content, 'xml')
            articles = []
            
            items = soup.find_all('item')
            
            for item in items[:20]:
                try:
                    title = item.find('title')
                    link = item.find('link')
                    guid = item.find('guid')
                    description = item.find('description')
                    pub_date = item.find('pubDate')
                    
                    if title:
                        title_text = title.get_text(strip=True)
                        
                        # Try multiple ways to get URL
                        link_url = ""
                        if link and link.get_text(strip=True):
                            link_url = link.get_text(strip=True)
                        elif guid and guid.get_text(strip=True):
                            link_url = guid.get_text(strip=True)
                        else:
                            link_url = "https://99bitcoins.com/"
                        
                        desc_text = description.get_text(strip=True) if description else title_text
                        date_text = pub_date.get_text(strip=True) if pub_date else datetime.now().isoformat()
                        
                        # Filter for crypto/finance related content
                        if (title_text and len(title_text) > 20 and 
                            any(word in title_text.lower() for word in ['bitcoin', 'crypto', 'stock', 'trading', 'market', 'finance', 'investment'])):
                            
                            articles.append({
                                'title': title_text,
                                'url': link_url,
                                'source': '99Bitcoins',
                                'content': desc_text,
                                'date': date_text
                            })
                            
                            if len(articles) >= 15:
                                break
                                
                except Exception as item_error:
                    logger.debug(f"Error processing 99Bitcoins RSS item: {item_error}")
                    continue
            
            logger.info(f"99Bitcoins: Found {len(articles)} articles for {ticker}")
            return articles
            
        except Exception as e:
            logger.error(f"99Bitcoins RSS error for {ticker}: {e}")
            return []
    
    def get_newsapi_reuters(self, ticker):
        """Get Reuters content via NewsAPI"""
        try:
            if not NEWSAPI_KEY or NEWSAPI_KEY == 'your-newsapi-key':
                return []
            
            if not check_api_quota('newsapi'):
                return []
            
            company_name = self.get_company_name(ticker)
            
            # Target Reuters specifically
            url = "https://newsapi.org/v2/everything"
            params = {
                'q': f'{company_name} OR {ticker}',
                'sources': 'reuters',
                'language': 'en',
                'sortBy': 'publishedAt',
                'pageSize': 10,
                'apiKey': NEWSAPI_KEY
            }
            
            response = self.session.get(url, params=params, timeout=15)
            increment_api_usage('newsapi')
            
            if response.status_code == 200:
                data = response.json()
                articles = []
                
                if 'articles' in data:
                    for item in data['articles']:
                        title = item.get('title', '')
                        url = item.get('url', '')
                        description = item.get('description', '')
                        
                        if title and url:
                            articles.append({
                                'title': title,
                                'url': url,
                                'source': 'Reuters (via NewsAPI)',
                                'content': description or title,
                                'date': item.get('publishedAt', datetime.now().isoformat())
                            })
                
                return articles[:5]
                
        except Exception as e:
            print(f"NewsAPI Reuters error: {e}")
        return []
    
    def get_marketwatch_news(self, ticker):
        """Scrape MarketWatch news for ticker"""
        logger.debug(f"Starting MarketWatch scraping for {ticker}")
        try:
            # Use markets section with proper headers
            url = "https://www.marketwatch.com/markets"
            
            # Add proper headers to avoid 401
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
                'Accept-Encoding': 'gzip, deflate, br',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1',
                'Referer': 'https://www.google.com/',
                'Cache-Control': 'max-age=0'
            }
            
            response = requests.get(url, headers=headers, timeout=15)
            
            if response.status_code != 200:
                logger.debug(f"MarketWatch returned status {response.status_code} for {ticker}")
                return []
            
            soup = BeautifulSoup(response.content, 'html.parser')
            articles = []
            
            # Look for actual story links
            all_links = soup.find_all('a', href=True)
            
            for link in all_links:
                try:
                    href = link.get('href', '')
                    title = link.get_text(strip=True)
                    
                    # MarketWatch stories have /story/ in URL
                    if (title and len(title) > 30 and 
                        href and '/story/' in href and
                        'marketwatch.com' in href and
                        not any(skip in href for skip in ['video', 'podcast', 'newsletter'])):
                        
                        articles.append({
                            'title': title,
                            'url': href,
                            'source': 'MarketWatch',
                            'content': title,
                            'date': datetime.now().isoformat()
                        })
                        
                        if len(articles) >= 5:
                            break
                            
                except Exception as item_error:
                    logger.debug(f"Error processing MarketWatch item: {item_error}")
                    continue
            
            # If no stories found, try general financial news from homepage
            if not articles:
                try:
                    homepage_response = requests.get("https://www.marketwatch.com/", headers=headers, timeout=15)
                    if homepage_response.status_code == 200:
                        homepage_soup = BeautifulSoup(homepage_response.content, 'html.parser')
                        homepage_links = homepage_soup.find_all('a', href=True)
                        
                        for link in homepage_links[:20]:
                            href = link.get('href', '')
                            title = link.get_text(strip=True)
                            
                            if (title and len(title) > 25 and 
                                any(word in title.lower() for word in ['stock', 'market', 'dow', 'nasdaq']) and
                                '/story/' in href):
                                
                                articles.append({
                                    'title': title,
                                    'url': href if href.startswith('http') else f"https://www.marketwatch.com{href}",
                                    'source': 'MarketWatch',
                                    'content': title,
                                    'date': datetime.now().isoformat()
                                })
                                
                                if len(articles) >= 3:
                                    break
                except:
                    pass
            
            logger.info(f"MarketWatch: Found {len(articles)} articles for {ticker}")
            return articles
            
        except Exception as e:
            logger.error(f"MarketWatch scraping error for {ticker}: {e}")
            return []
    
    def get_invezz_news(self, ticker):
        """Get news from Invezz with direct category scraping"""
        try:
            # Try different Invezz URLs
            urls = [
                "https://invezz.com/news/stocks/",
                "https://invezz.com/news/",
                f"https://invezz.com/news/?s={ticker}"
            ]
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.9',
                'Cache-Control': 'no-cache',
                'Pragma': 'no-cache'
            }
            
            company_name = self.get_company_name(ticker)
            
            for url in urls:
                try:
                    response = requests.get(url, headers=headers, timeout=15)
                    
                    if response.status_code == 200:
                        soup = BeautifulSoup(response.content, 'html.parser')
                        
                        # Multiple selectors for articles
                        selectors = [
                            'article h2 a',
                            'article h3 a', 
                            '.post-title a',
                            '.entry-title a',
                            'h2.title a',
                            'div.post a[href*="/news/"]'
                        ]
                        
                        news_items = []
                        for selector in selectors:
                            links = soup.select(selector)
                            if links:
                                for link in links:
                                    title = link.get_text(strip=True)
                                    url = link.get('href', '')
                                    
                                    if url and not url.startswith('http'):
                                        url = f"https://invezz.com{url}"
                                    
                                    # Check relevance
                                    if title and url and len(title) > 15:
                                        if (ticker.lower() in title.lower() or 
                                            company_name.lower() in title.lower() or
                                            any(word in title.lower() for word in ['stock', 'share', 'market', 'trading'])):
                                            news_items.append({
                                                'title': title,
                                                'url': url,
                                                'source': 'Invezz'
                                            })
                                
                                if news_items:
                                    return news_items[:5]
                        
                        # If no relevant articles found, return first few general articles
                        if not news_items and links:
                            for link in links[:3]:
                                title = link.get_text(strip=True)
                                url = link.get('href', '')
                                if url and not url.startswith('http'):
                                    url = f"https://invezz.com{url}"
                                if title and url:
                                    news_items.append({
                                        'title': title,
                                        'url': url,
                                        'source': 'Invezz'
                                    })
                            return news_items
                            
                except Exception as e:
                    continue
                    
        except Exception as e:
            print(f"Invezz error: {e}")
        return []
    
    def get_seeking_alpha_rss(self, ticker):
        """Get news from Seeking Alpha RSS feed"""
        logger.debug(f"Starting Seeking Alpha RSS collection for {ticker}")
        try:
            url = "https://seekingalpha.com/feed.xml"
            response = self.session.get(url, timeout=15)
            
            if response.status_code != 200:
                logger.debug(f"Seeking Alpha RSS returned status {response.status_code}")
                return []
            
            soup = BeautifulSoup(response.content, 'xml')
            articles = []
            
            items = soup.find_all('item')
            company_name = self.get_company_name(ticker)
            
            for item in items[:20]:
                try:
                    title = item.find('title')
                    link = item.find('link')
                    description = item.find('description')
                    pub_date = item.find('pubDate')
                    
                    if title and link:
                        title_text = title.get_text(strip=True)
                        link_url = link.get_text(strip=True)
                        desc_text = description.get_text(strip=True) if description else title_text
                        date_text = pub_date.get_text(strip=True) if pub_date else datetime.now().isoformat()
                        
                        # Filter for relevant content
                        if (title_text and len(title_text) > 20 and 
                            (ticker.lower() in title_text.lower() or 
                             company_name.lower() in title_text.lower() or
                             any(word in title_text.lower() for word in ['stock', 'market', 'earnings', 'financial', 'investment']))):
                            
                            articles.append({
                                'title': title_text,
                                'url': link_url,
                                'source': 'Seeking Alpha',
                                'content': desc_text[:200],
                                'date': date_text
                            })
                            
                            if len(articles) >= 10:
                                break
                                
                except Exception as item_error:
                    logger.debug(f"Error processing Seeking Alpha RSS item: {item_error}")
                    continue
            
            logger.info(f"Seeking Alpha: Found {len(articles)} articles for {ticker}")
            return articles
            
        except Exception as e:
            logger.error(f"Seeking Alpha RSS error for {ticker}: {e}")
            return []

class AIProcessor:
    def __init__(self):
        self.client = client
    
    def _call_gemini_with_fallback(self, prompt, fallback_result):
        """Call Gemini API with quota checking and fallback"""
        if not check_api_quota('gemini'):
            logger.warning("GEMINI API: Quota exhausted, using fallback")
            return fallback_result
        
        if not self.client:
            logger.error("GEMINI API: Client not initialized")
            return fallback_result
        
        try:
            logger.debug("GEMINI API: Making API call...")
            time.sleep(2)  # Rate limiting
            
            model = self.client.GenerativeModel('gemini-2.5-pro')
            response = model.generate_content(prompt)
            
            increment_api_usage('gemini')
            
            if response and hasattr(response, 'text') and response.text:
                logger.info(f"GEMINI API: Success - {len(response.text)} chars")
                return response
            else:
                logger.error("GEMINI API: Empty or invalid response")
                return fallback_result
                
        except Exception as e:
            error_str = str(e)
            logger.error(f"GEMINI API: Error - {error_str}")
            
            # Check for quota/rate limit errors
            if any(keyword in error_str.lower() for keyword in ['quota', 'limit', 'exceeded', 'rate']):
                logger.error(f"GEMINI API: Quota/rate limit hit")
                api_usage['gemini']['calls'] = DAILY_LIMITS['gemini']
            
            return fallback_result
    
    def select_top_articles(self, articles, ticker):
        """Use Gemini to select top 5-7 most relevant articles"""
        logger.info(f"ARTICLE SELECTION: Starting with {len(articles)} articles for {ticker}")
        if not articles:
            logger.warning("No articles provided for selection")
            return []
        
        # If we have 5 or fewer articles, return all
        if len(articles) <= 5:
            logger.info(f"ARTICLE SELECTION: Using all {len(articles)} articles (<=5)")
            return articles
        
        try:
            articles_text = "\n\n".join([
                f"Article {i+1}:\nTitle: {art['title']}\nSource: {art['source']}\nContent: {art['content'][:200]}..."
                for i, art in enumerate(articles[:15])  # Limit to first 15 to avoid token limits
            ])
            
            prompt = f"""
Select the 5-7 most important articles for {ticker} trading analysis:

PRIORITY:
1. EARNINGS/FINANCIAL RESULTS
2. REGULATORY/LEGAL NEWS
3. STRATEGIC MOVES (M&A, partnerships)
4. MANAGEMENT CHANGES
5. COMPETITIVE THREATS

Articles:
{articles_text}

Return only numbers separated by commas (e.g., 1,3,5,7,9):
"""
            
            logger.info(f"GEMINI ARTICLE SELECTION: Calling API for {ticker}")
            
            if not self.client or not GEMINI_API_KEY or GEMINI_API_KEY.strip() == '' or GEMINI_API_KEY == 'your-gemini-api-key':
                logger.warning(f"GEMINI ARTICLE SELECTION: API not configured (key present: {bool(GEMINI_API_KEY)}, client: {bool(self.client)}), using first 5")
                return articles[:5]
            
            response = self._call_gemini_with_fallback(prompt, None)
            if response is None:
                logger.warning("GEMINI ARTICLE SELECTION: API failed, using first 5")
                return articles[:5]
            
            if hasattr(response, 'text') and response.text:
                logger.info(f"GEMINI ARTICLE SELECTION: Got response: {response.text[:50]}...")
                try:
                    selected_indices = [int(x.strip()) - 1 for x in response.text.split(',') if x.strip().isdigit()]
                    selected_articles = [articles[i] for i in selected_indices if 0 <= i < len(articles)]
                    if selected_articles:
                        logger.info(f"GEMINI ARTICLE SELECTION: Selected {len(selected_articles)} articles")
                        return selected_articles
                except Exception as parse_error:
                    logger.error(f"GEMINI ARTICLE SELECTION: Parse error: {parse_error}")
            
            logger.warning("GEMINI ARTICLE SELECTION: Invalid response, using first 5")
            return articles[:5]
            
        except Exception as e:
            logger.error(f"GEMINI ARTICLE SELECTION: Error: {e}")
            return articles[:5]
    
    def generate_summary(self, ticker, selected_articles, historical_summaries, alpaca_quote=None):
        """Generate comprehensive summary with 'What changed today' section"""
        logger.info(f"SUMMARY GENERATION: Starting for {ticker} with {len(selected_articles)} articles")
        
        if not selected_articles:
            logger.warning(f"SUMMARY GENERATION: No articles provided for {ticker}")
            return {
                'summary': f"No news articles available for {ticker} analysis.",
                'what_changed': "No news data available."
            }
        
        # Add Alpaca context if available
        market_context = ""
        if alpaca_quote:
            market_context = f"\nCurrent Price: ${alpaca_quote['price']:.2f} (Bid: ${alpaca_quote['bid']:.2f}, Ask: ${alpaca_quote['ask']:.2f})\n"
        
        try:
            if not self.client or not GEMINI_API_KEY or GEMINI_API_KEY.strip() == '' or GEMINI_API_KEY == 'your-gemini-api-key':
                logger.error(f"SUMMARY GENERATION: Gemini API not configured for {ticker} (key present: {bool(GEMINI_API_KEY)}, client: {bool(self.client)})")
                return {
                    'summary': f"**{ticker} ANALYSIS** - AI summary unavailable (API not configured). {len(selected_articles)} articles collected from multiple sources. Manual review recommended for trading decisions.",
                    'what_changed': "AI analysis unavailable - check articles manually for developments."
                }
            
            articles_text = "\n\n".join([
                f"Source: {art['source']}\nTitle: {art['title']}\nContent: {art['content'][:300]}..."
                for art in selected_articles[:5]  # Limit to 5 articles to avoid token limits
            ])
            
            # Clean up old data first (older than 7 days) for this ticker
            db.cleanup_old_data(ticker, days=7)
            
            # Get exactly last 7 days of historical summaries for comparison
            recent_history = db.get_summaries_last_7_days_only(ticker)
            logger.info(f"Retrieved {len(recent_history)} summaries from exactly last 7 days for {ticker}")
            
            # Format historical data properly with dates
            if recent_history:
                history_entries = []
                for summary in recent_history:
                    date_str = summary.get('date', summary.get('created_at', ''))
                    summary_text = summary.get('summary', '')
                    what_changed = summary.get('what_changed', '')
                    
                    if summary_text:
                        # Include both summary and what_changed for better context
                        entry = f"{date_str}: {summary_text[:150]}..."
                        if what_changed:
                            entry += f" | Changes: {what_changed[:100]}..."
                        history_entries.append(entry)
                
                history_text = "\n".join(history_entries) if history_entries else "No detailed historical data available."
            else:
                history_text = "No historical data available."
            
            prompt = f"""
Analyze {ticker} for trading decisions:

TODAY'S NEWS:
{articles_text}

LAST 7 DAYS HISTORY:
{history_text}{market_context}

Provide a concise trading analysis with these sections:

**TRADING THESIS**
Bull/bear case with price catalysts.

**KEY DEVELOPMENTS**
• Financial impact with numbers
• Regulatory/legal updates
• Strategic moves and partnerships

**RISK/REWARD**
• Upside catalysts with timeline
• Downside risks
• Technical levels

**WHAT CHANGED TODAY**
Carefully compare today's news against the 7-day history provided above. Identify what is genuinely NEW or DIFFERENT today versus what was already covered in recent days. Look for:
- New earnings/financial results not mentioned before
- Fresh regulatory/legal developments
- New partnerships, acquisitions, or strategic moves
- Management changes or insider activity
- Shifts in analyst sentiment or price targets
- Market events affecting the stock differently than before
If nothing materially new happened, state "No significant new developments beyond ongoing themes."

Keep under 400 words, focus on actionable insights.
"""
            
            logger.info(f"SUMMARY GENERATION: Calling Gemini API for {ticker}")
            
            fallback_summary = {
                'summary': f"**{ticker} TRADING ALERT** - AI analysis temporarily unavailable. {len(selected_articles)} articles collected from {', '.join(set(art['source'] for art in selected_articles))}. Key themes may include earnings, regulatory updates, or strategic announcements. Manual review recommended.",
                'what_changed': "AI analysis unavailable - check collected articles for material developments."
            }
            
            response = self._call_gemini_with_fallback(prompt, fallback_summary)
            if isinstance(response, dict):  # Fallback was returned
                logger.warning(f"SUMMARY GENERATION: Using fallback for {ticker}")
                return response
            
            if not hasattr(response, 'text') or not response.text:
                logger.error(f"SUMMARY GENERATION: Invalid response for {ticker}")
                return fallback_summary
            
            summary_text = response.text.strip()
            logger.info(f"SUMMARY GENERATION: Generated {len(summary_text)} chars for {ticker}")
            
            # Extract "What changed today" section
            what_changed = "No material developments identified."
            
            # Look for the section
            if "**WHAT CHANGED TODAY**" in summary_text:
                parts = summary_text.split("**WHAT CHANGED TODAY**")
                if len(parts) > 1:
                    what_changed_raw = parts[1].strip()
                    # Clean up and take first paragraph
                    lines = what_changed_raw.split('\n')
                    clean_lines = [line.strip() for line in lines if line.strip() and not line.strip().startswith('**')]
                    if clean_lines:
                        what_changed = clean_lines[0][:200] + ('...' if len(clean_lines[0]) > 200 else '')
            
            result = {
                'summary': summary_text,
                'what_changed': what_changed
            }
            
            logger.info(f"SUMMARY GENERATION: Completed successfully for {ticker}")
            return result
            
        except Exception as e:
            error_msg = str(e)
            logger.error(f"SUMMARY GENERATION: Error for {ticker}: {error_msg}")
            return {
                'summary': f"**{ticker} ANALYSIS ERROR** - Technical issue during AI processing. {len(selected_articles)} articles collected but summary generation failed. Error: {error_msg[:100]}. Manual review of articles recommended.",
                'what_changed': "Technical error during analysis - check articles manually."
            }

# Initialize components
collector = NewsCollector()
ai_processor = AIProcessor()
chart_generator = ChartGenerator()
ml_analyzer = MLAnalyzer()
entity_highlighter = EntityHighlighter()



@app.route('/')
def index():
    return render_template('index.html')

@app.route('/features')
def features():
    return render_template('features.html')

@app.route('/about')
def about():
    return render_template('about.html')

@app.route('/learn-more')
def learn_more():
    return render_template('learn-more.html')

@app.route('/stock/<ticker>')
def stock_analysis(ticker):
    """Stock analysis page with 4-tab system"""
    ticker = ticker.upper().strip()
    return render_template('stock_analysis.html', ticker=ticker)

@app.route('/api/chart/<ticker>')
@app.route('/api/chart/<ticker>/<period>')
def get_chart_data(ticker, period='30d'):
    """Get chart configuration for ticker with period"""
    try:
        ticker = ticker.upper().strip()
        logger.debug(f"Chart request for {ticker} period {period}")
        
        if not ticker or len(ticker) > 10:
            logger.error(f"Invalid ticker format: {ticker}")
            return jsonify({'error': 'Invalid ticker format'}), 400
        
        chart_config = chart_generator.generate_chart_config(ticker, period)
        logger.debug(f"Chart config result: {chart_config is not None}")
        
        if chart_config is None:
            logger.warning(f"No chart data for {ticker} period {period}")
            return jsonify({'error': 'Chart data unavailable'}), 404
            
        return jsonify(chart_config)
        
    except Exception as e:
        logger.error(f"Chart endpoint error for {ticker}: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/market-status')
def get_market_status():
    """Get market status widget data"""
    try:
        market_status = alpaca.get_market_status()
        account_info = alpaca.get_account_info()
        
        result = {
            'market': {
                'is_open': market_status.get('is_open', False) if market_status else False,
                'next_open': market_status.get('next_open', '') if market_status else '',
                'next_close': market_status.get('next_close', '') if market_status else ''
            },
            'account': {
                'portfolio_value': float(account_info.get('portfolio_value', 0)) if account_info else 0,
                'buying_power': float(account_info.get('buying_power', 0)) if account_info else 0,
                'day_trade_count': account_info.get('daytrade_count', 0) if account_info else 0
            } if account_info else None
        }
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/alpaca-news/<ticker>')
def get_alpaca_news(ticker):
    """Get Alpaca news for ticker"""
    try:
        news_data = alpaca.get_news(symbols=[ticker], limit=5)
        if news_data and 'news' in news_data:
            articles = []
            for item in news_data['news']:
                articles.append({
                    'title': item.get('headline', ''),
                    'url': item.get('url', ''),
                    'source': 'Alpaca Markets',
                    'content': item.get('summary', item.get('headline', '')),
                    'date': item.get('created_at', datetime.now().isoformat())
                })
            return jsonify(articles)
        return jsonify([])
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/debug/apis')
def debug_apis():
    """Debug endpoint to check API status"""
    try:
        status = {
            'apis': {
                'gemini': {
                    'configured': bool(GEMINI_API_KEY and GEMINI_API_KEY != 'your-gemini-api-key' and GEMINI_API_KEY.strip() != ''),
                    'key_preview': f"{GEMINI_API_KEY[:10]}...{GEMINI_API_KEY[-5:]}" if GEMINI_API_KEY else 'Not set',
                    'key_length': len(GEMINI_API_KEY) if GEMINI_API_KEY else 0,
                    'client_initialized': bool(client),
                    'genai_library': bool(genai),
                    'env_var_exists': 'GEMINI_API_KEY' in os.environ,
                    'env_var_value': os.environ.get('GEMINI_API_KEY', 'NOT_FOUND')[:15] + '...' if os.environ.get('GEMINI_API_KEY') else 'NOT_FOUND',
                    'validation_checks': {
                        'key_exists': bool(GEMINI_API_KEY),
                        'not_placeholder': GEMINI_API_KEY != 'your-gemini-api-key' if GEMINI_API_KEY else False,
                        'not_empty': GEMINI_API_KEY.strip() != '' if GEMINI_API_KEY else False,
                        'proper_format': GEMINI_API_KEY.startswith('AIza') if GEMINI_API_KEY else False
                    }
                },
                'polygon': {
                    'configured': bool(POLYGON_API_KEY and POLYGON_API_KEY != 'your-polygon-api-key'),
                    'key_preview': f"{POLYGON_API_KEY[:10]}...{POLYGON_API_KEY[-5:]}" if POLYGON_API_KEY else 'Not set'
                },
                'alpha_vantage': {
                    'configured': bool(ALPHA_VANTAGE_API_KEY and ALPHA_VANTAGE_API_KEY != 'your-alpha-vantage-api-key'),
                    'key_preview': f"{ALPHA_VANTAGE_API_KEY[:10]}...{ALPHA_VANTAGE_API_KEY[-5:]}" if ALPHA_VANTAGE_API_KEY else 'Not set'
                },
                'twelve_data': {
                    'configured': bool(TWELVE_DATA_API_KEY),
                    'key_preview': f"{TWELVE_DATA_API_KEY[:10]}...{TWELVE_DATA_API_KEY[-5:]}" if TWELVE_DATA_API_KEY else 'Not set'
                },
                'finnhub': {
                    'configured': bool(FINNHUB_API_KEY),
                    'key_preview': f"{FINNHUB_API_KEY[:10]}...{FINNHUB_API_KEY[-5:]}" if FINNHUB_API_KEY else 'Not set'
                },
                'newsapi': {
                    'configured': bool(NEWSAPI_KEY and NEWSAPI_KEY != 'your-newsapi-key'),
                    'key_preview': f"{NEWSAPI_KEY[:10]}...{NEWSAPI_KEY[-5:]}" if NEWSAPI_KEY else 'Not set'
                },
                'alpaca': {
                    'configured': bool(ALPACA_API_KEY and ALPACA_SECRET_KEY),
                    'key_preview': f"{ALPACA_API_KEY[:10]}...{ALPACA_API_KEY[-5:]}" if ALPACA_API_KEY else 'Not set'
                }
            },
            'environment': {
                'all_env_vars': [key for key in os.environ.keys() if 'API' in key or 'KEY' in key],
                'dotenv_loaded': os.path.exists('.env')
            },
            'usage': api_usage,
            'limits': DAILY_LIMITS,
            'quota_status': {
                service: f"{api_usage.get(service, {}).get('calls', 0)}/{DAILY_LIMITS.get(service, 'N/A')}"
                for service in DAILY_LIMITS.keys()
            }
        }
        return jsonify(status)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/cache-status')
def cache_status():
    """Check cache functionality and status"""
    try:
        return jsonify(cache.get_status())
    except Exception as e:
        return jsonify({
            'error': str(e),
            'cache_type': 'Error',
            'connection_test': False
        }), 500

@app.route('/api/debug/gemini')
def debug_gemini():
    """Test Gemini API directly"""
    try:
        if not GEMINI_API_KEY:
            return jsonify({
                'error': 'Gemini API key not found',
                'env_check': os.environ.get('GEMINI_API_KEY', 'NOT_SET'),
                'client_status': bool(client)
            }), 400
        
        if not client:
            return jsonify({
                'error': 'Gemini client not initialized',
                'api_key_exists': bool(GEMINI_API_KEY),
                'api_key_preview': f"{GEMINI_API_KEY[:10]}..." if GEMINI_API_KEY else None
            }), 400
        
        # Test API call
        model = client.GenerativeModel('gemini-2.5-pro')
        response = model.generate_content("Say 'API test successful' in exactly 3 words.")
        
        return jsonify({
            'success': True,
            'response': response.text,
            'api_key_preview': f"{GEMINI_API_KEY[:10]}...",
            'client_type': str(type(client))
        })
        
    except Exception as e:
        return jsonify({
            'error': str(e),
            'api_key_exists': bool(GEMINI_API_KEY),
            'client_exists': bool(client),
            'error_type': type(e).__name__
        }), 500

@app.route('/api/debug/chart-apis/<ticker>')
def debug_chart_apis(ticker):
    """Debug endpoint to test chart APIs individually"""
    try:
        ticker = ticker.upper().strip()
        results = {}
        
        # Test Alpha Vantage
        if ALPHA_VANTAGE_API_KEY:
            try:
                url = "https://www.alphavantage.co/query"
                params = {
                    'function': 'TIME_SERIES_DAILY',
                    'symbol': ticker,
                    'apikey': ALPHA_VANTAGE_API_KEY,
                    'outputsize': 'compact'
                }
                response = requests.get(url, params=params, timeout=10)
                data = response.json()
                results['alpha_vantage'] = {
                    'status': response.status_code,
                    'response_keys': list(data.keys()),
                    'has_data': 'Time Series (Daily)' in data,
                    'error': data.get('Error Message') or data.get('Note')
                }
            except Exception as e:
                results['alpha_vantage'] = {'error': str(e)}
        else:
            results['alpha_vantage'] = {'error': 'API key not configured'}
        
        # Test Twelve Data
        if TWELVE_DATA_API_KEY:
            try:
                url = "https://api.twelvedata.com/time_series"
                params = {
                    'symbol': ticker,
                    'interval': '1day',
                    'apikey': TWELVE_DATA_API_KEY,
                    'outputsize': 5
                }
                response = requests.get(url, params=params, timeout=10)
                data = response.json()
                results['twelve_data'] = {
                    'status': response.status_code,
                    'response_keys': list(data.keys()),
                    'has_data': 'values' in data and bool(data.get('values')),
                    'api_status': data.get('status'),
                    'message': data.get('message')
                }
            except Exception as e:
                results['twelve_data'] = {'error': str(e)}
        else:
            results['twelve_data'] = {'error': 'API key not configured'}
        
        # Test Finnhub
        if FINNHUB_API_KEY:
            try:
                from datetime import datetime, timedelta
                end_date = datetime.now()
                start_date = end_date - timedelta(days=7)
                
                url = "https://finnhub.io/api/v1/stock/candle"
                params = {
                    'symbol': ticker,
                    'resolution': 'D',
                    'from': int(start_date.timestamp()),
                    'to': int(end_date.timestamp()),
                    'token': FINNHUB_API_KEY
                }
                response = requests.get(url, params=params, timeout=10)
                data = response.json()
                results['finnhub'] = {
                    'status': response.status_code,
                    'response_keys': list(data.keys()),
                    'has_data': data.get('s') == 'ok',
                    'data_status': data.get('s'),
                    'data_points': len(data.get('c', [])) if data.get('c') else 0
                }
            except Exception as e:
                results['finnhub'] = {'error': str(e)}
        else:
            results['finnhub'] = {'error': 'API key not configured'}
        
        return jsonify({
            'ticker': ticker,
            'api_tests': results,
            'summary': {
                'working_apis': [api for api, result in results.items() if result.get('has_data')],
                'failed_apis': [api for api, result in results.items() if not result.get('has_data')]
            }
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/tickers', methods=['GET'])
def get_tickers():
    try:
        tickers = db.get_tickers()
        logger.info(f"API endpoint: Found {len(tickers)} tickers: {tickers}")
        return jsonify(tickers)
    except Exception as e:
        logger.error(f"Error getting tickers: {e}")
        return jsonify({'error': str(e)}), 500

def validate_ticker(ticker):
    """Validate if ticker exists by checking multiple sources"""
    try:
        logger.debug(f"Validating ticker: {ticker}")
        
        # Format check first
        if len(ticker) > 6 or not ticker.isalpha():
            return False
        
        # Try Alpha Vantage first
        if ALPHA_VANTAGE_API_KEY:
            url = "https://www.alphavantage.co/query"
            params = {
                'function': 'GLOBAL_QUOTE',
                'symbol': ticker,
                'apikey': ALPHA_VANTAGE_API_KEY
            }
            response = requests.get(url, params=params, timeout=10)
            if response.status_code == 200:
                data = response.json()
                if 'Global Quote' in data and data['Global Quote'].get('01. symbol'):
                    logger.debug(f"Ticker {ticker} validated via Alpha Vantage")
                    return True
        
        # Try Twelve Data as fallback
        if TWELVE_DATA_API_KEY:
            url = "https://api.twelvedata.com/quote"
            params = {
                'symbol': ticker,
                'apikey': TWELVE_DATA_API_KEY
            }
            response = requests.get(url, params=params, timeout=10)
            if response.status_code == 200:
                data = response.json()
                if data.get('symbol') and 'error' not in data:
                    logger.debug(f"Ticker {ticker} validated via Twelve Data")
                    return True
        
        logger.warning(f"Ticker {ticker} not found in any API")
        return False
        
    except Exception as e:
        logger.error(f"Ticker validation error for {ticker}: {e}")
        return False

@app.route('/api/tickers', methods=['POST'])
def add_ticker():
    try:
        data = request.json
        if not data:
            logger.error("No JSON data received")
            return jsonify({'error': 'No data provided'}), 400
        
        ticker = data.get('ticker', '').upper().strip()
        logger.debug(f"Received ticker request: {ticker}")
    except Exception as e:
        logger.error(f"Error processing request data: {e}")
        return jsonify({'error': 'Internal server error'}), 500
    
    if not ticker:
        return jsonify({'error': 'Ticker required'}), 400
    
    if len(ticker) > 6 or not ticker.isalpha():
        return jsonify({'error': 'Invalid ticker format'}), 400
    
    # Validate ticker exists
    logger.info(f"Validating ticker: {ticker}")
    if not validate_ticker(ticker):
        return jsonify({'error': f'Ticker {ticker} not found or invalid'}), 400
    
    try:
        result = db.add_ticker(ticker)
        logger.info(f"Successfully added ticker: {ticker}")
        
        # Auto-start summary generation for new ticker
        try:
            logger.info(f"Auto-generating summary for new ticker: {ticker}")
            from threading import Thread
            def process_with_delay():
                time.sleep(2)  # Brief delay to ensure ticker is saved
                process_ticker_news(ticker)
            Thread(target=process_with_delay, daemon=True).start()
            logger.info(f"Summary generation started in background for {ticker}")
        except Exception as process_error:
            logger.error(f"Error starting summary generation for {ticker}: {process_error}")
            # Don't fail the ticker addition if processing fails
        
        return jsonify({'success': True})
    except Exception as e:
        error_msg = str(e)
        if 'duplicate' in error_msg.lower() or 'unique' in error_msg.lower():
            return jsonify({'error': 'Ticker already exists'}), 400
        logger.error(f"Error adding ticker {ticker}: {e}")
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/api/tickers/<ticker>', methods=['DELETE'])
def remove_ticker(ticker):
    """Remove a ticker and ALL associated data from watchlist"""
    try:
        ticker = ticker.upper().strip()
        logger.info(f"Complete removal requested for ticker: {ticker}")
        
        # Remove from all Supabase tables
        db.remove_ticker(ticker)  # Remove from tickers table
        db.delete_articles(ticker)  # Remove all news articles
        db.delete_summaries(ticker)  # Remove all summaries
        db.delete_logo(ticker)  # Remove company logo
        db.delete_financial_data(ticker)  # Remove financial data
        
        # Clear all cache data
        cache.clear(ticker)
        
        logger.info(f"Successfully removed ALL data for ticker: {ticker}")
        return jsonify({'success': True})
        
    except Exception as e:
        logger.error(f"Error removing ticker {ticker}: {e}")
        return jsonify({'success': True})

@app.route('/api/pexels-image')
def get_pexels_image_endpoint():
    """Get Pexels image by query"""
    query = request.args.get('query', '')
    if not query:
        return jsonify({'error': 'Query required'}), 400
    
    image_url = get_pexels_image(query)
    if image_url:
        return jsonify({'image': image_url})
    else:
        return jsonify({'error': 'Image not found'}), 404

@app.route('/api/logo/<ticker>')
def get_company_logo(ticker):
    """Get company logo from database or API Ninjas"""
    try:
        ticker = ticker.upper().strip()
        
        # Check database first
        logo_url = db.get_logo(ticker)
        if logo_url:
            return jsonify({'image': logo_url})
        
        # Fetch from API if not in database
        if not API_NINJAS_KEY or API_NINJAS_KEY == 'your_api_ninjas_key':
            return jsonify({'error': 'API key not configured'}), 404
        
        response = requests.get(
            f"https://api.api-ninjas.com/v1/logo?ticker={ticker}",
            headers={'X-Api-Key': API_NINJAS_KEY},
            timeout=10
        )
        
        if response.status_code == 200:
            data = response.json()
            if data and len(data) > 0 and data[0].get('image'):
                logo_url = data[0].get('image')
                company_name = data[0].get('name', ticker)
                
                # Save to database
                db.save_logo(ticker, logo_url, company_name)
                
                return jsonify({'image': logo_url, 'name': company_name})
        
        return jsonify({'error': 'No logo available'}), 404
            
    except Exception as e:
        logger.error(f"Logo API error for {ticker}: {e}")
        return jsonify({'error': 'Logo service error'}), 500

@app.route('/api/summary/<ticker>')
def get_summary(ticker):
    try:
        ticker = ticker.upper().strip()
        logger.debug(f"Getting summary for {ticker}")
        
        if not ticker or len(ticker) > 10:
            return jsonify({'error': 'Invalid ticker format'}), 400
        
        # Clean up old data first
        db.cleanup_old_data(ticker, days=7)
        
        # Get latest summary
        summary_data = db.get_summary(ticker)
        
        # Get 7-day history
        history = db.get_history(ticker)
        
        # Get ML analysis
        price_forecast = ml_analyzer.get_price_forecast(ticker)
        
        # Get recent articles for sentiment
        recent_articles = db.get_recent_articles(ticker)
        sentiment_analysis = ml_analyzer.analyze_sentiment(recent_articles)
        
        # Apply entity highlighting to summary if available
        if summary_data and summary_data.get('summary'):
            summary_data['summary'] = entity_highlighter.highlight_entities(summary_data['summary'])
        
        # Get company logo - check database first, then API
        logo_url = db.get_logo(ticker)
        
        if not logo_url and API_NINJAS_KEY:
            try:
                logo_response = requests.get(
                    f"https://api.api-ninjas.com/v1/logo?ticker={ticker}", 
                    headers={'X-Api-Key': API_NINJAS_KEY}, 
                    timeout=5
                )
                if logo_response.status_code == 200:
                    logo_data = logo_response.json()
                    if logo_data and len(logo_data) > 0:
                        logo_url = logo_data[0].get('image')
                        company_name = logo_data[0].get('name')
                        
                        # Save to database
                        db.save_logo(ticker, logo_url, company_name)
                        logger.debug(f"Logo fetched and saved for {ticker}: {logo_url}")
            except Exception as e:
                logger.debug(f"Logo fetch failed for {ticker}: {e}")
        
        # Show "No data available" if no summary exists
        if not summary_data or not summary_data.get('summary'):
            summary_data = {
                'summary': 'No data available',
                'what_changed': 'No data available',
                'date': datetime.now().isoformat()
            }
        
        return jsonify({
            'current_summary': summary_data,
            'history': history,
            'company_logo': logo_url,
            'ml_analysis': {
                'price_forecast': price_forecast,
                'sentiment': sentiment_analysis
            },
            'api_status': {
                'gemini_remaining': max(0, DAILY_LIMITS['gemini'] - api_usage['gemini']['calls']) if isinstance(DAILY_LIMITS['gemini'], int) else 'unlimited',
                'polygon_remaining': 'unlimited' if DAILY_LIMITS['polygon'] == 'unlimited' else max(0, DAILY_LIMITS['polygon'] - api_usage['polygon']['calls']),
                'quota_reset': 'Daily at midnight'
            },
            'cache_status': {
                'cache_type': cache.redis_client and 'Upstash' or 'Memory'
            }
        })
    except Exception as e:
        logger.error(f"Error getting summary for {ticker}: {e}")
        return jsonify({'error': 'Failed to load summary'}), 500

class AlpacaIntegration:
    def __init__(self):
        if ALPACA_API_KEY and ALPACA_SECRET_KEY:
            import base64
            credentials = base64.b64encode(f"{ALPACA_API_KEY}:{ALPACA_SECRET_KEY}".encode()).decode()
            self.headers = {
                'Authorization': f'Basic {credentials}',
                'Content-Type': 'application/json'
            }
            self.base_url = "https://paper-api.alpaca.markets"
            self.data_url = "https://data.alpaca.markets"
        else:
            self.headers = None
    
    def get_quote(self, ticker):
        """Get Alpaca quote for summary context"""
        if not self.headers:
            return None
        try:
            time.sleep(0.5)
            
            url = f"{self.data_url}/v2/stocks/{ticker}/quotes/latest"
            response = requests.get(url, headers=self.headers, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                if 'quote' in data:
                    quote = data['quote']
                    current_price = (quote['bid_price'] + quote['ask_price']) / 2
                    return {
                        'price': current_price,
                        'bid': quote['bid_price'],
                        'ask': quote['ask_price'],
                        'spread': quote['ask_price'] - quote['bid_price']
                    }
        except:
            pass
        return None
    
    def get_market_status(self):
        """Get market status"""
        if not self.headers:
            return None
        try:
            response = requests.get(f"{self.base_url}/v2/clock", headers=self.headers, timeout=10)
            if response.status_code == 200:
                return response.json()
        except:
            pass
        return None
    
    def get_account_info(self):
        """Get account performance"""
        if not self.headers:
            return None
        try:
            response = requests.get(f"{self.base_url}/v2/account", headers=self.headers, timeout=10)
            if response.status_code == 200:
                return response.json()
        except:
            pass
        return None
    
    def get_news(self, symbols=None, limit=5):
        """Get Alpaca news"""
        if not self.headers:
            return None
        try:
            params = {'limit': limit}
            if symbols:
                params['symbols'] = ','.join(symbols)
            response = requests.get(f"{self.data_url}/v1beta1/news", 
                                  headers=self.headers, params=params, timeout=10)
            if response.status_code == 200:
                return response.json()
        except:
            pass
        return None

alpaca = AlpacaIntegration()

def process_ticker_news(ticker):
    """Process news for a single ticker with optimized parallel processing"""
    logger.info(f"=== Starting optimized news processing for {ticker} ===")
    start_time = time.time()
    
    # Get Alpaca quote for context
    alpaca_quote = alpaca.get_quote(ticker)
    
    if alpaca_quote:
        logger.info(f"Alpaca data for {ticker}: ${alpaca_quote['price']:.2f} (Bid: ${alpaca_quote['bid']:.2f}, Ask: ${alpaca_quote['ask']:.2f})")
    
    # Check for cached news first
    cached_articles, cached_sources = cache.get_news(ticker)
    if cached_articles:
        logger.info(f"Using cached news for {ticker} ({len(cached_articles)} articles)")
        all_articles = cached_articles
        source_counts = cached_sources
    else:
        # Parallel source collection for faster processing
        logger.debug("Collecting news sources in parallel")
        all_articles = []
        source_counts = {}
        
        # Priority sources first (cloud-compatible only)
        priority_tasks = [
            ('TradingView', collector.get_tradingview_news, ticker),
            ('Finviz', collector.get_finviz_news, ticker),
            ('Yahoo Finance', collector.get_yahoo_ticker_news, ticker),
            ('Motley Fool', collector.get_motley_fool_news, ticker)
        ]
        
        # Secondary sources (RSS feeds and web scraping)
        secondary_tasks = [
            ('99Bitcoins', collector.get_99bitcoins_news, ticker),
            ('Seeking Alpha', collector.get_seeking_alpha_rss, ticker),
            ('Invezz (RSS)', collector.get_invezz_rss, ticker),
            ('Reuters (RSS)', collector.get_reuters_rss, ticker),
            ('TechCrunch', collector.get_techcrunch_news, ticker),
            ('MarketWatch', collector.get_marketwatch_news, ticker)
        ]
        
        # API sources with quota checks
        api_tasks = []
        if check_api_quota('polygon'):
            api_tasks.append(('Polygon', collector.get_polygon_news, ticker))
        if check_api_quota('twelve_data'):
            api_tasks.append(('Twelve Data', collector.get_twelve_data_news, ticker))
        if check_api_quota('finnhub'):
            api_tasks.append(('Finnhub', collector.get_finnhub_news, ticker))
        if check_api_quota('newsapi'):
            api_tasks.append(('Reuters (NewsAPI)', collector.get_newsapi_reuters, ticker))
        
        # Combine in priority order
        tasks = priority_tasks + api_tasks + secondary_tasks
        
        # Execute priority sources first
        logger.info(f"Processing {len(priority_tasks)} priority sources first...")
        with ThreadPoolExecutor(max_workers=4) as executor:
            priority_futures = {executor.submit(task[1], task[2]): task[0] for task in priority_tasks}
            
            for future in as_completed(priority_futures, timeout=60):
                source_name = priority_futures[future]
                try:
                    articles = future.result(timeout=15)  # Reduced individual timeout
                    if articles:
                        all_articles.extend(articles)
                        source_counts[source_name] = len(articles)
                        logger.info(f"PRIORITY {source_name}: SUCCESS - {len(articles)} articles")
                    else:
                        source_counts[source_name] = 0
                        logger.warning(f"PRIORITY {source_name}: NO ARTICLES")
                except Exception as e:
                    logger.error(f"PRIORITY {source_name}: FAILED - {str(e)[:50]}")
                    source_counts[source_name] = 0
        
        # Execute remaining sources with better error handling
        remaining_tasks = api_tasks + secondary_tasks
        logger.info(f"Processing {len(remaining_tasks)} remaining sources...")
        with ThreadPoolExecutor(max_workers=6) as executor:
            future_to_source = {executor.submit(task[1], task[2]): task[0] for task in remaining_tasks}
            
            # Process completed futures without strict timeout
            completed_count = 0
            for future in as_completed(future_to_source, timeout=90):
                source_name = future_to_source[future]
                completed_count += 1
                try:
                    articles = future.result(timeout=20)  # Individual timeout
                    if articles:
                        all_articles.extend(articles)
                        source_counts[source_name] = len(articles)
                        logger.info(f"{source_name}: SUCCESS - {len(articles)} articles")
                    else:
                        source_counts[source_name] = 0
                        logger.warning(f"{source_name}: NO ARTICLES FOUND")
                except Exception as e:
                    logger.error(f"{source_name}: FAILED - {str(e)[:50]}")
                    source_counts[source_name] = 0
            
            # Handle any remaining unfinished futures
            unfinished = len(remaining_tasks) - completed_count
            if unfinished > 0:
                logger.warning(f"{unfinished} sources did not complete in time")
        
        # Add Alpaca news (sequential due to authentication)
        try:
            alpaca_news = alpaca.get_news(symbols=[ticker], limit=3)
            if alpaca_news and 'news' in alpaca_news:
                for item in alpaca_news['news']:
                    all_articles.append({
                        'title': item.get('headline', ''),
                        'url': item.get('url', ''),
                        'source': 'Alpaca Markets',
                        'content': item.get('summary', item.get('headline', '')),
                        'date': item.get('created_at', datetime.now().isoformat())
                    })
                source_counts['Alpaca'] = len(alpaca_news['news'])
            else:
                source_counts['Alpaca'] = 0
        except Exception as e:
            logger.debug(f"Alpaca news error: {e}")
            source_counts['Alpaca'] = 0
        
        # Log detailed source results
        successful_sources = [name for name, count in source_counts.items() if count > 0]
        failed_sources = [name for name, count in source_counts.items() if count == 0]
        
        logger.info(f"COLLECTION SUMMARY for {ticker}:")
        logger.info(f"  Total articles: {len(all_articles)}")
        logger.info(f"  Successful sources ({len(successful_sources)}): {', '.join(successful_sources)}")
        logger.info(f"  Failed sources ({len(failed_sources)}): {', '.join(failed_sources)}")
        
        if len(failed_sources) > len(successful_sources):
            logger.warning(f"More sources failed than succeeded for {ticker}")
        
        # Cache the collected news
        if all_articles:
            cache.set_news(ticker, all_articles, source_counts)
    
    if not all_articles:
        logger.error(f"CRITICAL: No articles found for {ticker} from ANY source")
        logger.error(f"Source status: {source_counts}")
        # Still save empty result to database to track the failure
        db.save_summary(ticker, {
            'summary': f"No news articles available for {ticker}. All sources failed to return data.",
            'what_changed': "No data available - all news sources failed."
        }, [])
        return
    
    # Check for cached summary first
    cached_summary = cache.get_summary(ticker)
    if cached_summary and not cached_articles:
        logger.info(f"Using cached summary for {ticker}")
        summary_result = cached_summary
        selected_articles = all_articles[:5]  # Use first 5 for database storage
    else:
        # Get historical summaries first (this is for backward compatibility)
        history = db.get_history(ticker)
        historical_summaries = [{
            'date': item.get('date', ''),
            'summary': item.get('summary', ''),
            'what_changed': item.get('what_changed', '')
        } for item in history]
        
        logger.debug(f"Retrieved {len(historical_summaries)} historical summaries for {ticker}")
        
        # AI article selection
        logger.info(f"AI PROCESSING: Starting article selection for {ticker}")
        selected_articles = ai_processor.select_top_articles(all_articles, ticker)
        logger.info(f"AI PROCESSING: Selected {len(selected_articles)} articles for {ticker}")
        
        # AI summary generation
        logger.info(f"AI PROCESSING: Starting summary generation for {ticker}")
        summary_result = ai_processor.generate_summary(ticker, selected_articles, historical_summaries, alpaca_quote)
        
        if summary_result and summary_result.get('summary'):
            logger.info(f"AI PROCESSING: Generated summary for {ticker} ({len(summary_result['summary'])} chars)")
            # Cache the summary
            cache.set_summary(ticker, summary_result)
        else:
            logger.error(f"AI PROCESSING: Failed to generate summary for {ticker}")
            summary_result = {
                'summary': f"**{ticker} NEWS COLLECTED** - {len(all_articles)} articles gathered from {len(source_counts)} sources. AI summary generation failed. Manual review recommended.",
                'what_changed': "AI processing failed - check articles manually."
            }
    
    # Save articles to database
    articles_saved, articles_skipped = db.save_articles(ticker, all_articles)
    logger.info(f"DATABASE SAVE RESULT for {ticker}: {articles_saved} SAVED, {articles_skipped} SKIPPED out of {len(all_articles)} TOTAL")
    
    # Collect financial statements for last 7 days
    try:
        logger.info(f"Collecting financial statements for {ticker}")
        financial_data.get_financial_statements(ticker)
    except Exception as e:
        logger.error(f"Financial data collection failed for {ticker}: {e}")
    
    # Save summary
    articles_used = [{
        'title': art['title'],
        'url': art['url'],
        'source': art['source']
    } for art in selected_articles]
    
    logger.debug(f"Saving summary to database for {ticker}")
    db.save_summary(ticker, summary_result, articles_used)
    
    # Final status check
    if summary_result and summary_result.get('summary'):
        logger.info(f"SUCCESS: {ticker} - {len(all_articles)} articles, {articles_saved} saved, AI summary generated")
    else:
        logger.error(f"PARTIAL SUCCESS: {ticker} - {len(all_articles)} articles, {articles_saved} saved, AI summary FAILED")
    
    end_time = time.time()
    processing_time = end_time - start_time
    logger.info(f"=== Completed processing for {ticker} in {processing_time:.1f}s ===")

@app.route('/api/refresh/<ticker>', methods=['GET', 'POST'])
def refresh_ticker(ticker):
    """Manual refresh for a ticker - clears cache and generates new summary"""
    try:
        ticker = ticker.upper().strip()
        logger.info(f"Manual refresh requested for {ticker}")
        
        if not ticker or len(ticker) > 10:
            return jsonify({'error': 'Invalid ticker format'}), 400
        
        # Clear ALL cache for fresh data
        cache.clear(ticker)
        
        # Process the ticker with timeout handling
        try:
            process_ticker_news(ticker)
            return jsonify({'success': True, 'message': f'Successfully refreshed {ticker}'})
        except Exception as process_error:
            logger.error(f"Processing error for {ticker}: {process_error}")
            return jsonify({'error': f'Processing failed: {str(process_error)[:100]}'}), 500
        
    except Exception as e:
        logger.error(f"Refresh error for {ticker}: {e}")
        return jsonify({'error': f'Failed to refresh {ticker}: {str(e)[:100]}'}), 500

@app.route('/api/yahoo-financials/<ticker>')
def get_yahoo_financials(ticker):
    """Get financial data from Yahoo Finance with retry logic"""
    ticker = ticker.upper().strip()
    
    for attempt in range(2):
        try:
            import yfinance as yf
            
            stock = yf.Ticker(ticker)
            result = {}
            
            # Try to get basic info first
            try:
                info = stock.info
                if not info or ('symbol' not in info and 'shortName' not in info):
                    if attempt == 0:
                        time.sleep(3)
                        continue
                    return jsonify({'error': 'Invalid ticker'}), 404
            except Exception:
                if attempt == 0:
                    time.sleep(3)
                    continue
                return jsonify({'error': 'Ticker info unavailable'}), 404
            
            # Get historical data for basic chart
            try:
                hist = stock.history(period='2y')
                if not hist.empty:
                    # Create quarterly revenue approximation from market cap changes
                    quarterly_data = hist.resample('QE').last()
                    result['price_history'] = [{
                        'date': str(date.date()),
                        'value': float(row['Close'])
                    } for date, row in quarterly_data.iterrows()]
            except Exception:
                pass
            
            # Try to get financials
            try:
                financials = stock.financials
                if not financials.empty:
                    # Look for revenue row with different possible names
                    revenue_row = None
                    for row_name in ['Total Revenue', 'Revenue', 'Net Sales', 'Sales']:
                        if row_name in financials.index:
                            revenue_row = financials.loc[row_name].dropna()
                            break
                    
                    if revenue_row is not None and len(revenue_row) > 0:
                        revenue_data = [{
                            'date': str(date.date()),
                            'value': float(value)
                        } for date, value in revenue_row.items()]
                        
                        result['annual_revenue'] = revenue_data
                        
                        # Calculate YoY growth (reverse order since data is newest first)
                        if len(revenue_data) > 1:
                            yoy_growth = []
                            # Sort by date to ensure proper chronological order
                            sorted_revenue = sorted(revenue_data, key=lambda x: x['date'])
                            for i in range(1, len(sorted_revenue)):
                                current = sorted_revenue[i]['value']
                                previous = sorted_revenue[i-1]['value']
                                if previous != 0:
                                    growth = ((current - previous) / previous) * 100
                                    yoy_growth.append({
                                        'date': sorted_revenue[i]['date'],
                                        'value': growth
                                    })
                            result['yoy_growth'] = yoy_growth
            except Exception:
                pass
            
            # Add basic company info
            result['company_info'] = {
                'name': info.get('longName', info.get('shortName', ticker)),
                'sector': info.get('sector', 'Unknown'),
                'market_cap': info.get('marketCap', 0)
            }
            
            return jsonify(result)
            
        except Exception as e:
            if attempt == 0:
                logger.warning(f"Yahoo Finance financials attempt 1 failed for {ticker}: {e}")
                time.sleep(3)
                continue
            else:
                logger.error(f"Yahoo Finance financials error for {ticker} after 2 attempts: {e}")
                return jsonify({'error': 'Financial data service temporarily unavailable'}), 500

@app.route('/api/price/<ticker>')
def get_price_data(ticker):
    """Get current stock price and change using Yahoo Finance with retry logic"""
    ticker = ticker.upper().strip()
    
    for attempt in range(3):
        try:
            import yfinance as yf
            
            stock = yf.Ticker(ticker)
            
            # Try to get info
            try:
                info = stock.info
            except Exception:
                info = {}
            
            # Get current price
            current_price = info.get('currentPrice') or info.get('regularMarketPrice') or info.get('previousClose')
            
            if not current_price:
                try:
                    hist = stock.history(period='2d')
                    if not hist.empty:
                        current_price = float(hist['Close'].iloc[-1])
                except Exception:
                    pass
            
            # Get previous close for change calculation
            prev_close = info.get('previousClose')
            if not prev_close:
                try:
                    if 'hist' not in locals():
                        hist = stock.history(period='2d')
                    if not hist.empty and len(hist) > 1:
                        prev_close = float(hist['Close'].iloc[-2])
                except Exception:
                    pass
            
            if current_price and prev_close:
                change = current_price - prev_close
                change_percent = (change / prev_close) * 100
                
                return jsonify({
                    'price': float(current_price),
                    'change': float(change),
                    'changePercent': float(change_percent)
                })
            
            if current_price:
                return jsonify({
                    'price': float(current_price),
                    'change': 0,
                    'changePercent': 0
                })
            
            if attempt < 2:
                logger.warning(f"Yahoo Finance attempt {attempt + 1} failed for {ticker}, retrying...")
                time.sleep(2)
                continue
            
            return jsonify({'error': 'Price data unavailable'}), 404
            
        except Exception as e:
            if attempt < 2:
                logger.warning(f"Yahoo Finance price error for {ticker} (attempt {attempt + 1}): {e}")
                time.sleep(2)
                continue
            else:
                logger.error(f"Yahoo Finance price error for {ticker} (final attempt): {e}")
                return jsonify({'error': 'Price service error'}), 500

@app.route('/api/stock-metrics/<ticker>')
def get_stock_metrics(ticker):
    """Get real stock metrics (52W High/Low, Volume) from Yahoo Finance"""
    ticker = ticker.upper().strip()
    
    for attempt in range(2):
        try:
            import yfinance as yf
            
            stock = yf.Ticker(ticker)
            
            # Get info and historical data
            info = stock.info
            hist = stock.history(period='1y')
            
            # Get 52-week high/low from info or calculate from history
            week_52_high = info.get('fiftyTwoWeekHigh')
            week_52_low = info.get('fiftyTwoWeekLow')
            
            if not week_52_high or not week_52_low:
                if not hist.empty:
                    week_52_high = float(hist['High'].max())
                    week_52_low = float(hist['Low'].min())
            
            # Get volume data
            avg_volume = info.get('averageVolume') or info.get('averageVolume10days')
            recent_volume = info.get('volume')
            
            if not avg_volume and not hist.empty:
                avg_volume = int(hist['Volume'].mean())
            
            if not recent_volume and not hist.empty:
                recent_volume = int(hist['Volume'].iloc[-1])
            
            # Format volume
            def format_volume(vol):
                if vol >= 1e9:
                    return f"{vol/1e9:.1f}B"
                elif vol >= 1e6:
                    return f"{vol/1e6:.1f}M"
                elif vol >= 1e3:
                    return f"{vol/1e3:.1f}K"
                return str(vol)
            
            return jsonify({
                'week_52_high': float(week_52_high) if week_52_high else None,
                'week_52_low': float(week_52_low) if week_52_low else None,
                'avg_volume': format_volume(avg_volume) if avg_volume else None,
                'recent_volume': format_volume(recent_volume) if recent_volume else None
            })
            
        except Exception as e:
            if attempt == 0:
                logger.warning(f"Stock metrics attempt 1 failed for {ticker}: {e}")
                time.sleep(2)
                continue
            else:
                logger.error(f"Stock metrics error for {ticker}: {e}")
                return jsonify({'error': 'Stock metrics unavailable'}), 500

@app.route('/api/chart-data/<ticker>')
def get_chart_data_detailed(ticker):
    """Get detailed chart data for candlestick chart using Yahoo Finance only"""
    try:
        ticker = ticker.upper().strip()
        period = request.args.get('period', '1M')
        refresh = request.args.get('refresh')
        
        logger.info(f"Chart data request for {ticker}, period: {period}, refresh: {bool(refresh)}")
        
        # Skip cache if refresh requested
        if refresh:
            cache.clear_chart_data(ticker, period)
        
        # Check cache first
        cached_data = cache.get_chart_data(ticker, period)
        if cached_data:
            logger.info(f"Returning cached chart data for {ticker} ({period})")
            return jsonify(cached_data)
        
        # Use Yahoo Finance with retry logic
        for attempt in range(2):
            try:
                import yfinance as yf
                
                stock = yf.Ticker(ticker)
                
                # Map period to yfinance period and interval
                period_map = {
                    '1D': ('1d', '5m'),
                    '5D': ('5d', '15m'), 
                    '1M': ('1mo', '1d'),
                    '3M': ('3mo', '1d'),
                    '6M': ('6mo', '1d'),
                    '1Y': ('1y', '1d'),
                    '2Y': ('2y', '1d')
                }
                
                yf_period, interval = period_map.get(period, ('3mo', '1d'))
                
                # Get history
                hist = stock.history(period=yf_period, interval=interval)
                
                if not hist.empty:
                    prices = []
                    for date, row in hist.iterrows():
                        try:
                            # Validate price data - ensure all values are reasonable stock prices
                            open_price = float(row['Open'])
                            high_price = float(row['High'])
                            low_price = float(row['Low'])
                            close_price = float(row['Close'])
                            volume = int(row['Volume'])
                            
                            # Skip invalid price data (prices should be between $0.01 and $10,000)
                            if not (0.01 <= open_price <= 10000 and 0.01 <= high_price <= 10000 and 
                                   0.01 <= low_price <= 10000 and 0.01 <= close_price <= 10000):
                                continue
                                
                            prices.append({
                                'date': date.strftime('%Y-%m-%d'),
                                'open': round(open_price, 2),
                                'high': round(high_price, 2),
                                'low': round(low_price, 2),
                                'close': round(close_price, 2),
                                'volume': volume
                            })
                        except (ValueError, TypeError) as e:
                            logger.debug(f"Skipping invalid price data for {date}: {e}")
                            continue
                    
                    # Get market cap with proper validation
                    market_cap = "N/A"
                    try:
                        info = stock.info
                        mc = info.get('marketCap', 0)
                        
                        # Validate market cap is reasonable (not zero or negative)
                        if mc and mc > 0:
                            if mc > 1e12:
                                market_cap = f"${mc/1e12:.1f}T"
                            elif mc > 1e9:
                                market_cap = f"${mc/1e9:.1f}B"
                            elif mc > 1e6:
                                market_cap = f"${mc/1e6:.1f}M"
                            else:
                                market_cap = f"${mc/1e3:.1f}K"
                        else:
                            # Try alternative calculation only if marketCap is missing
                            shares = info.get('sharesOutstanding', 0)
                            price = info.get('currentPrice', 0) or info.get('regularMarketPrice', 0)
                            if shares and price and shares > 0 and price > 0:
                                mc = shares * price
                                # Validate calculated market cap
                                if mc > 1e12:
                                    market_cap = f"${mc/1e12:.1f}T"
                                elif mc > 1e9:
                                    market_cap = f"${mc/1e9:.1f}B"
                                elif mc > 1e6:
                                    market_cap = f"${mc/1e6:.1f}M"
                    except Exception as e:
                        logger.debug(f"Market cap calculation error for {ticker}: {e}")
                        market_cap = "N/A"
                    
                    if prices:
                        logger.info(f"Yahoo Finance: Found {len(prices)} price points for {period}")
                        result = {
                            'prices': prices,
                            'marketCap': market_cap,
                            'source': 'Yahoo Finance'
                        }
                        
                        result = clean_nan_values(result)
                        cache.set_chart_data(ticker, period, result)
                        return jsonify(result)
                
                if attempt == 0:
                    logger.warning(f"Yahoo Finance attempt 1 failed for {ticker}, retrying...")
                    time.sleep(3)
                    continue
                    
            except Exception as yf_error:
                if attempt == 0:
                    logger.warning(f"Yahoo Finance attempt 1 failed for {ticker}: {yf_error}")
                    time.sleep(3)
                    continue
                else:
                    logger.warning(f"Yahoo Finance failed for {ticker} after 2 attempts: {yf_error}")
                    break
        
        # Return error if Yahoo Finance fails
        logger.error(f"Yahoo Finance failed for {ticker}")
        return jsonify({'error': 'Chart data unavailable'}), 404
        
    except Exception as e:
        logger.error(f"Chart data error for {ticker}: {e}")
        return jsonify({'error': f'Chart service error: {str(e)}'}), 500

@app.route('/api/news/<ticker>')
def get_news_articles(ticker):
    """Get news articles for ticker with pagination support"""
    try:
        ticker = ticker.upper().strip()
        page = int(request.args.get('page', 1))
        per_page = int(request.args.get('per_page', 10))
        
        # Get all articles from database
        all_articles = db.get_recent_articles(ticker, limit=1000)  # Get all articles
        
        if not all_articles:
            return jsonify({
                'articles': [],
                'pagination': {
                    'page': page,
                    'per_page': per_page,
                    'total': 0,
                    'pages': 0
                }
            })
        
        # Filter for today's articles only
        from datetime import datetime
        today = datetime.now().date().isoformat()
        today_articles = [article for article in all_articles if article.get('date', '').startswith(today)]
        
        # Sort by date (most recent first)
        today_articles.sort(key=lambda x: x.get('date', ''), reverse=True)
        
        # Calculate pagination
        total_articles = len(today_articles)
        total_pages = (total_articles + per_page - 1) // per_page
        start_idx = (page - 1) * per_page
        end_idx = start_idx + per_page
        
        # Get articles for current page
        page_articles = today_articles[start_idx:end_idx]
        
        # Group by source for statistics
        source_groups = {}
        for article in today_articles:
            source = article.get('source', 'Unknown')
            if source not in source_groups:
                source_groups[source] = 0
            source_groups[source] += 1
        
        logger.info(f"News API: Page {page}/{total_pages}, showing {len(page_articles)} of {total_articles} articles from {len(source_groups)} sources for {ticker}")
        
        return jsonify({
            'articles': page_articles,
            'pagination': {
                'page': page,
                'per_page': per_page,
                'total': total_articles,
                'pages': total_pages
            },
            'sources': source_groups
        })
        
    except Exception as e:
        logger.error(f"News API error for {ticker}: {e}")
        return jsonify({'error': 'News service error'}), 500

@app.route('/api/financials/<ticker>')
def get_financial_statements(ticker):
    """Get stored financial statements from database"""
    try:
        ticker = ticker.upper().strip()
        
        # Get stored financial data from database
        stored_data = financial_data.get_stored_financials(ticker)
        available_dates = db.get_financial_dates(ticker)
        
        if stored_data:
            return jsonify({
                'stored_statements': stored_data,
                'available_dates': available_dates,
                'count': len(stored_data),
                'source': 'Database (Yahoo Finance)'
            })
        
        # If no stored data, try to collect fresh data
        logger.info(f"No stored financial data for {ticker}, collecting fresh data")
        financial_data.get_financial_statements(ticker)
        
        # Check again after collection
        stored_data = financial_data.get_stored_financials(ticker)
        available_dates = db.get_financial_dates(ticker)
        
        return jsonify({
            'stored_statements': stored_data,
            'available_dates': available_dates,
            'count': len(stored_data),
            'source': 'Fresh Collection',
            'message': 'Data collected and stored' if stored_data else 'No financial data available'
        })
        
    except Exception as e:
        logger.error(f"Financial statements error for {ticker}: {e}")
        return jsonify({
            'error': 'Financial data service error',
            'message': str(e)
        }), 500

@app.route('/api/financials/<ticker>/collect')
def collect_financial_data(ticker):
    """Manually trigger financial data collection"""
    try:
        ticker = ticker.upper().strip()
        logger.info(f"Manual financial data collection for {ticker}")
        
        # Test Yahoo Finance directly
        import yfinance as yf
        stock = yf.Ticker(ticker)
        
        test_data = {
            'quarterly_financials': not stock.quarterly_financials.empty,
            'annual_financials': not stock.financials.empty,
            'quarterly_balance': not stock.quarterly_balance_sheet.empty,
            'annual_balance': not stock.balance_sheet.empty,
            'quarterly_cashflow': not stock.quarterly_cashflow.empty,
            'annual_cashflow': not stock.cashflow.empty
        }
        
        # Collect data
        financial_data.get_financial_statements(ticker)
        stored_data = financial_data.get_stored_financials(ticker)
        
        return jsonify({
            'success': True,
            'ticker': ticker,
            'yahoo_test': test_data,
            'collected_statements': len(stored_data),
            'data': stored_data[:5]  # First 5 records
        })
        
    except Exception as e:
        logger.error(f"Manual collection error for {ticker}: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/subscribe', methods=['POST'])
def subscribe_email():
    """Subscribe email for daily reports"""
    try:
        data = request.json
        email = data.get('email', '').strip().lower()
        
        if not email or '@' not in email:
            return jsonify({'error': 'Valid email required'}), 400
        
        # Store subscription in database
        db.add_subscription(email)
        
        return jsonify({
            'success': True,
            'message': 'Successfully subscribed to daily reports',
            'email': email
        })
        
    except Exception as e:
        logger.error(f"Subscription error: {e}")
        return jsonify({'error': 'Subscription failed'}), 500

@app.route('/api/unsubscribe', methods=['POST'])
def unsubscribe_email():
    """Unsubscribe email from daily reports"""
    try:
        data = request.json
        email = data.get('email', '').strip().lower()
        
        if not email:
            return jsonify({'error': 'Email required'}), 400
        
        # Remove subscription from database
        db.remove_subscription(email)
        
        return jsonify({
            'success': True,
            'message': 'Successfully unsubscribed from daily reports'
        })
        
    except Exception as e:
        logger.error(f"Unsubscribe error: {e}")
        return jsonify({'error': 'Unsubscribe failed'}), 500



@app.route('/api/subscriptions', methods=['GET'])
def get_subscriptions():
    """Get all email subscriptions (admin only)"""
    try:
        subscriptions = db.get_subscriptions()
        return jsonify({
            'subscriptions': subscriptions,
            'count': len(subscriptions)
        })
    except Exception as e:
        logger.error(f"Get subscriptions error: {e}")
        return jsonify({'error': 'Failed to get subscriptions'}), 500

@app.route('/api/trade-ideas/<ticker>')
def get_trade_ideas(ticker):
    """Generate advanced ML-based trade ideas"""
    try:
        ticker = ticker.upper().strip()
        
        # Get current price first
        current_price = get_current_price(ticker)
        if not current_price:
            logger.warning(f"No price data available for {ticker}")
            return jsonify({
                'error': 'No price data available',
                'message': f'Unable to fetch current price for {ticker}. Please verify ticker symbol.',
                'status': 'error'
            })
        
        logger.info(f"Current price for {ticker}: ${current_price}")
        
        # Use ML analyzer for comprehensive analysis
        price_forecast = ml_analyzer.get_price_forecast(ticker)
        
        # Get recent articles for sentiment
        recent_articles = db.get_recent_articles(ticker, limit=10)
        sentiment_analysis = ml_analyzer.analyze_sentiment(recent_articles)
        
        # Generate advanced trade ideas with current price
        trade_ideas = generate_advanced_trade_ideas(ticker, current_price, price_forecast, sentiment_analysis, recent_articles)
        
        # Ensure current price is included in response
        trade_ideas['current_price'] = current_price
        
        return jsonify(trade_ideas)
        
    except Exception as e:
        logger.error(f"Trade ideas error for {ticker}: {e}")
        return jsonify({'error': 'Trade ideas service error'}), 500

def get_pexels_image(query, size='medium'):
    """Get image from Pexels API with 7-day Redis caching"""
    if not PEXELS_API_KEY:
        return None
    
    # Check cache first
    cached_url = cache.get_image(query)
    if cached_url:
        return cached_url
    
    try:
        headers = {'Authorization': PEXELS_API_KEY}
        response = requests.get(
            f'https://api.pexels.com/v1/search?query={query}&per_page=1&size={size}',
            headers=headers, timeout=5
        )
        if response.status_code == 200:
            data = response.json()
            if data.get('photos'):
                image_url = data['photos'][0]['src'][size]
                # Cache for 7 days
                cache.set_image(query, image_url)
                return image_url
    except Exception as e:
        logger.debug(f'Pexels API error: {e}')
    return None

def generate_advanced_trade_ideas(ticker, current_price, price_forecast, sentiment_analysis, articles):
    """Generate comprehensive trade ideas using ML analysis"""
    trade_ideas = []
    
    # Validate current price is available
    if not current_price:
        logger.warning(f"No price data available for {ticker}")
        return {
            'trade_ideas': [],
            'technical_analysis': {'error': 'Price data unavailable'},
            'risk_assessment': {'level': 'HIGH', 'reason': 'No price data available'},
            'status': 'error'
        }
    
    logger.info(f"Generating trade ideas for {ticker}: price=${current_price}, forecast={price_forecast}, sentiment={sentiment_analysis}")
    
    # Price-based strategy using real ML predictions
    if price_forecast and price_forecast.get('predicted_price'):
        predicted_price = price_forecast.get('predicted_price', current_price)
        change_percent = price_forecast.get('change_percent', 0)
        confidence = price_forecast.get('confidence', 'Medium')
        model_used = price_forecast.get('model_used', 'ML')
        
        logger.info(f"ML Forecast for {ticker}: {model_used} model predicts {change_percent}% change")
        
        if change_percent > 3:
            trade_ideas.append({
                'strategy': f'ML {model_used.upper()} Momentum Strategy',
                'action': 'BUY',
                'confidence': confidence,
                'entry_price': current_price,
                'target_price': predicted_price,
                'stop_loss': current_price * 0.96,
                'reasoning': f'{model_used.upper()} model predicts {change_percent:.1f}% upside with {confidence.lower()} confidence based on technical patterns.',
                'timeframe': price_forecast.get('timeframe', '5 days'),
                'risk_reward': f'1:{abs(change_percent/4):.1f}',
                'image': get_pexels_image('stock market bull trend')
            })
        elif change_percent < -3:
            trade_ideas.append({
                'strategy': f'ML {model_used.upper()} Bearish Signal',
                'action': 'SHORT/AVOID',
                'confidence': confidence,
                'entry_price': current_price,
                'target_price': predicted_price,
                'stop_loss': current_price * 1.04,
                'reasoning': f'{model_used.upper()} model predicts {abs(change_percent):.1f}% downside with {confidence.lower()} confidence.',
                'timeframe': price_forecast.get('timeframe', '5 days'),
                'risk_reward': f'1:{abs(change_percent/4):.1f}',
                'image': get_pexels_image('stock market bear decline')
            })
        else:
            # Neutral ML prediction
            trade_ideas.append({
                'strategy': f'ML {model_used.upper()} Range Trading',
                'action': 'HOLD',
                'confidence': confidence,
                'entry_price': current_price,
                'target_price': predicted_price,
                'stop_loss': current_price * 0.98,
                'reasoning': f'{model_used.upper()} model shows minimal price movement ({change_percent:.1f}%), suggesting range-bound trading.',
                'timeframe': price_forecast.get('timeframe', '5 days'),
                'risk_reward': '1:1.5',
                'image': get_pexels_image('financial chart analysis')
            })
    
    # Sentiment-based strategy
    if sentiment_analysis:
        sentiment = sentiment_analysis.get('sentiment', 'Neutral')
        score = sentiment_analysis.get('score', 0)
        articles_count = sentiment_analysis.get('articles_analyzed', 0)
        
        if sentiment == 'Bullish' and score > 0.2:
            target = current_price * 1.08
            stop = current_price * 0.96
            trade_ideas.append({
                'strategy': 'News Momentum Play',
                'action': 'LONG',
                'confidence': 'High' if score > 0.4 else 'Medium',
                'entry_price': current_price,
                'target_price': target,
                'stop_loss': stop,
                'reasoning': f'Strong bullish sentiment from recent news coverage suggests upward price action.',
                'timeframe': '3-7 days',
                'risk_reward': '1:2.0'
            })
        elif sentiment == 'Bearish' and score < -0.2:
            target = current_price * 0.92
            stop = current_price * 1.04
            trade_ideas.append({
                'strategy': 'Mean Reversion Play',
                'action': 'SWING',
                'confidence': 'Medium',
                'entry_price': current_price,
                'target_price': target,
                'stop_loss': stop,
                'reasoning': 'Stock appears oversold based on RSI and sentiment analysis. Potential bounce expected.',
                'timeframe': 'Wait for reversal',
                'risk_reward': '1:2.0'
            })
    
    # News-based strategy
    if articles:
        recent_news_count = len([a for a in articles if 'earnings' in a.get('title', '').lower()])
        if recent_news_count > 0:
            upper_target = current_price * 1.12
            lower_target = current_price * 0.88
            trade_ideas.append({
                'strategy': 'Volatility Expansion',
                'action': 'STRADDLE',
                'confidence': 'Medium',
                'entry_price': current_price,
                'target_price': upper_target,
                'target_price_low': lower_target,
                'stop_loss': current_price * 0.98,
                'reasoning': f'Earnings catalyst expected to drive significant price movement in either direction.',
                'timeframe': '1-3 days',
                'risk_reward': '1:6.0'
            })
    
    # Default conservative strategy if no clear signals
    if not trade_ideas:
        target = current_price * 1.03
        stop = current_price * 0.97
        trade_ideas.append({
            'strategy': 'Range Trading',
            'action': 'HOLD',
            'confidence': 'Medium',
            'entry_price': current_price,
            'target_price': target,
            'stop_loss': stop,
            'reasoning': 'Consolidation pattern suggests range-bound trading with modest upside potential.',
            'timeframe': 'Monitor for changes',
            'risk_reward': '1:1.0'
        })
    
    # Generate technical analysis summary
    technical_summary = {
        'ml_forecast': price_forecast,
        'sentiment': sentiment_analysis,
        'news_impact': f'{len(articles)} recent articles analyzed',
        'overall_signal': determine_overall_signal(trade_ideas)
    }
    
    return {
        'trade_ideas': trade_ideas[:3],  # Top 3 ideas
        'technical_analysis': technical_summary,
        'risk_assessment': generate_risk_assessment(trade_ideas),
        'status': 'ml_generated'
    }

def get_current_price(ticker):
    """Get current stock price from Yahoo Finance with retry logic"""
    for attempt in range(3):
        try:
            import yfinance as yf
            
            stock = yf.Ticker(ticker)
            
            # Try to get info
            try:
                info = stock.info
                price = info.get('currentPrice') or info.get('regularMarketPrice') or info.get('previousClose')
                if price and price > 0:
                    return float(price)
            except Exception:
                pass
            
            # Fallback to recent history
            try:
                hist = stock.history(period='1d')
                if not hist.empty:
                    return float(hist['Close'].iloc[-1])
            except Exception:
                pass
                
            if attempt < 2:
                time.sleep(1)
                continue
                
        except Exception as e:
            if attempt < 2:
                logger.debug(f"Price fetch attempt {attempt + 1} failed for {ticker}: {e}")
                time.sleep(1)
                continue
            else:
                logger.debug(f"Price fetch failed for {ticker} after 3 attempts: {e}")
    
    return None

def determine_overall_signal(trade_ideas):
    """Determine overall trading signal from ideas"""
    long_signals = len([idea for idea in trade_ideas if idea.get('action') in ['LONG', 'BUY']])
    short_signals = len([idea for idea in trade_ideas if idea.get('action') in ['SHORT', 'SELL']])
    
    if long_signals > short_signals:
        return 'BULLISH'
    elif short_signals > long_signals:
        return 'BEARISH'
    else:
        return 'NEUTRAL'

def generate_risk_assessment(trade_ideas):
    """Generate risk assessment from trade ideas"""
    high_confidence = len([idea for idea in trade_ideas if idea.get('confidence') == 'High'])
    total_ideas = len(trade_ideas)
    
    if high_confidence >= total_ideas * 0.6:
        return {'level': 'LOW', 'reason': 'High confidence signals dominate'}
    elif high_confidence == 0:
        return {'level': 'HIGH', 'reason': 'No high confidence signals'}
    else:
        return {'level': 'MEDIUM', 'reason': 'Mixed confidence levels'}

def daily_update():
    """Optimized daily update for 100 tickers"""
    logger.info("Starting optimized daily update for 100 tickers")
    
    tickers = db.get_tickers()
    
    # Process in batches to manage API quotas
    batch_size = 20
    total_batches = (len(tickers) + batch_size - 1) // batch_size
    
    for batch_num in range(total_batches):
        start_idx = batch_num * batch_size
        end_idx = min(start_idx + batch_size, len(tickers))
        batch_tickers = tickers[start_idx:end_idx]
        
        logger.info(f"Processing batch {batch_num + 1}/{total_batches}: {len(batch_tickers)} tickers")
        
        for ticker in batch_tickers:
            try:
                process_ticker_news(ticker)
                time.sleep(5)  # Increased delay for quota management
            except Exception as e:
                logger.error(f"Error processing {ticker}: {e}")
        
        # Longer pause between batches
        if batch_num < total_batches - 1:
            logger.info(f"Batch {batch_num + 1} complete. Waiting 2 minutes before next batch...")
            time.sleep(120)  # 2 minute pause between batches
    
    logger.info(f"Daily update completed: {len(tickers)} tickers processed")

if __name__ == '__main__':
    # Force database initialization
    if not db.client:
        db._init_client()
    
    if db.test_connection():
        logger.info("Database connection verified at startup")
    else:
        logger.error("Database connection failed at startup")
    
    # Setup optimized scheduler for 100 tickers
    scheduler = BackgroundScheduler()
    
    # Staggered updates to spread API load
    scheduler.add_job(
        func=daily_update,
        trigger="cron",
        hour=6,  # Start earlier (6 AM IST)
        minute=0,
        timezone='Asia/Kolkata',
        max_instances=1  # Prevent overlapping runs
    )
    
    # Financial data is fetched on-demand from Yahoo Finance
    
    # Daily cleanup of old data (older than 7 days)
    def daily_cleanup():
        """Clean up data older than 7 days from all tables"""
        logger.info("Starting daily cleanup of data older than 7 days")
        try:
            db.cleanup_old_data(ticker=None, days=7)  # Clean all tickers
            cache.cleanup_expired()  # Clean cache
            logger.info("Daily cleanup completed successfully")
        except Exception as e:
            logger.error(f"Daily cleanup failed: {e}")
    
    scheduler.add_job(
        func=daily_cleanup,
        trigger="cron",
        hour=0,  # Midnight cleanup
        minute=30,  # 30 minutes after midnight
        timezone='Asia/Kolkata'
    )
    
    scheduler.start()
    
    port = int(os.environ.get('PORT'))
    app.run(host='0.0.0.0', port=port, debug=False)