from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
import requests
from bs4 import BeautifulSoup
import json
import os
from datetime import datetime, timedelta
from chart_generator import ChartGenerator

from supabase import create_client, Client
import requests
import json
import google.genai as genai
from apscheduler.schedulers.background import BackgroundScheduler
import time
import logging
from dotenv import load_dotenv
import warnings
warnings.filterwarnings('ignore', category=UserWarning)

# Load environment variables
load_dotenv()

# Suppress Google library warnings
os.environ['GRPC_VERBOSITY'] = 'ERROR'
os.environ['GLOG_minloglevel'] = '2'


app = Flask(__name__)
CORS(app)

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
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
SUPABASE_URL = os.getenv('SUPABASE_URL')
SUPABASE_KEY = os.getenv('SUPABASE_ANON_KEY')

# Initialize Supabase client
try:
    if SUPABASE_URL and SUPABASE_KEY and SUPABASE_URL != 'your-supabase-url':
        supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
        logger.info("Supabase client initialized successfully")
    else:
        logger.error("Supabase credentials not configured properly")
        supabase = None
except Exception as e:
    logger.error(f"Failed to initialize Supabase: {e}")
    supabase = None

# Initialize Upstash Redis REST client
UPSTASH_REDIS_REST_URL = os.getenv('UPSTASH_REDIS_REST_URL')
UPSTASH_REDIS_REST_TOKEN = os.getenv('UPSTASH_REDIS_REST_TOKEN')

class UpstashRedis:
    def __init__(self, url, token):
        self.url = url
        self.headers = {'Authorization': f'Bearer {token}'}
    
    def get(self, key):
        try:
            response = requests.get(f'{self.url}/get/{key}', headers=self.headers)
            if response.status_code == 200:
                result = response.json().get('result')
                if result:
                    # Upstash returns string directly, not base64
                    return result.encode('utf-8')
            return None
        except:
            return None
    
    def setex(self, key, seconds, value):
        try:
            # Upstash expects string value directly
            string_value = value.decode('utf-8') if isinstance(value, bytes) else value
            data = {'value': string_value, 'ex': seconds}
            response = requests.post(f'{self.url}/set/{key}', headers=self.headers, json=data)
            return response.status_code == 200
        except:
            return False
    
    def delete(self, *keys):
        try:
            for key in keys:
                requests.post(f'{self.url}/del/{key}', headers=self.headers)
            return True
        except:
            return False
    
    def exists(self, key):
        try:
            response = requests.get(f'{self.url}/exists/{key}', headers=self.headers)
            return response.status_code == 200 and response.json().get('result', 0) == 1
        except:
            return False

# Initialize Redis client
try:
    if UPSTASH_REDIS_REST_URL and UPSTASH_REDIS_REST_TOKEN:
        redis_client = UpstashRedis(UPSTASH_REDIS_REST_URL, UPSTASH_REDIS_REST_TOKEN)
        # Test connection
        redis_client.setex('test', 10, b'test')
        logger.info("Upstash Redis connection successful")
    else:
        redis_client = None
        logger.warning("Upstash Redis credentials not found")
except Exception as e:
    logger.warning(f"Upstash Redis connection failed: {e}. Using fallback cache.")
    redis_client = None

logger.info(f"Gemini API Key loaded: {'Yes' if GEMINI_API_KEY != 'your-gemini-api-key' else 'No'}")
logger.info(f"Polygon API Key loaded: {'Yes' if POLYGON_API_KEY != 'your-polygon-api-key' else 'No'}")
logger.info(f"Twelve Data API Key loaded: {'Yes' if TWELVE_DATA_API_KEY else 'No'}")
logger.info(f"Finnhub API Key loaded: {'Yes' if FINNHUB_API_KEY else 'No'}")
logger.info(f"Alpaca API Key loaded: {'Yes' if ALPACA_API_KEY else 'No'}")

# API Usage Tracking
api_usage = {
    'gemini': {'calls': 0, 'last_reset': datetime.now().date()},
    'polygon': {'calls': 0, 'last_reset': datetime.now().date()},
    'alpha_vantage_realtime': {'calls': 0, 'last_reset': datetime.now().date()},
    'twelve_data_realtime': {'calls': 0, 'last_reset': datetime.now().date()}
}

# Caching System
CACHE_DURATION = 4 * 3600  # 4 hours in seconds
SUMMARY_CACHE_DURATION = 2 * 3600  # 2 hours in seconds

# Fallback in-memory cache if Redis unavailable
fallback_news_cache = {}
fallback_summary_cache = {}

def get_cached_news(ticker):
    """Get cached news if valid"""
    try:
        if redis_client:
            cached_data = redis_client.get(f"news:{ticker}")
            if cached_data:
                cache_entry = json.loads(cached_data.decode('utf-8'))
                logger.debug(f"Using Upstash cached news for {ticker}")
                return cache_entry['data'], cache_entry['sources']
        else:
            # Fallback to in-memory cache
            if ticker in fallback_news_cache:
                cache_entry = fallback_news_cache[ticker]
                if (datetime.now() - cache_entry['timestamp']).total_seconds() < CACHE_DURATION:
                    logger.debug(f"Using fallback cached news for {ticker}")
                    return cache_entry['data'], cache_entry['sources']
    except Exception as e:
        logger.debug(f"Cache read error for {ticker}: {e}")
    return None, None

def cache_news(ticker, articles, sources):
    """Cache news articles"""
    try:
        cache_data = {
            'data': articles,
            'timestamp': datetime.now().isoformat(),
            'sources': sources
        }
        
        if redis_client:
            redis_client.setex(f"news:{ticker}", CACHE_DURATION, json.dumps(cache_data))
            logger.debug(f"Cached {len(articles)} articles for {ticker} in Upstash")
        else:
            # Fallback to in-memory cache
            fallback_news_cache[ticker] = {
                'data': articles,
                'timestamp': datetime.now(),
                'sources': sources
            }
            logger.debug(f"Cached {len(articles)} articles for {ticker} in memory")
    except Exception as e:
        logger.debug(f"Cache write error for {ticker}: {e}")

def get_cached_summary(ticker):
    """Get cached summary if valid"""
    try:
        if redis_client:
            cached_data = redis_client.get(f"summary:{ticker}")
            if cached_data:
                cache_entry = json.loads(cached_data.decode('utf-8'))
                logger.debug(f"Using Upstash cached summary for {ticker}")
                return cache_entry['summary']
        else:
            # Fallback to in-memory cache
            if ticker in fallback_summary_cache:
                cache_entry = fallback_summary_cache[ticker]
                if (datetime.now() - cache_entry['timestamp']).total_seconds() < SUMMARY_CACHE_DURATION:
                    logger.debug(f"Using fallback cached summary for {ticker}")
                    return cache_entry['summary']
    except Exception as e:
        logger.debug(f"Summary cache read error for {ticker}: {e}")
    return None

def cache_summary(ticker, summary_data):
    """Cache summary data"""
    try:
        cache_data = {
            'summary': summary_data,
            'timestamp': datetime.now().isoformat()
        }
        
        if redis_client:
            redis_client.setex(f"summary:{ticker}", SUMMARY_CACHE_DURATION, json.dumps(cache_data))
            logger.debug(f"Cached summary for {ticker} in Upstash")
        else:
            # Fallback to in-memory cache
            fallback_summary_cache[ticker] = {
                'summary': summary_data,
                'timestamp': datetime.now()
            }
            logger.debug(f"Cached summary for {ticker} in memory")
    except Exception as e:
        logger.debug(f"Summary cache write error for {ticker}: {e}")

def cleanup_expired_cache():
    """Redis handles expiry automatically, clean fallback cache only"""
    if not redis_client:
        # Clean fallback caches
        current_time = datetime.now()
        
        expired_news = [ticker for ticker, data in fallback_news_cache.items() 
                       if (current_time - data['timestamp']).total_seconds() > CACHE_DURATION]
        for ticker in expired_news:
            del fallback_news_cache[ticker]
        
        expired_summaries = [ticker for ticker, data in fallback_summary_cache.items()
                            if (current_time - data['timestamp']).total_seconds() > SUMMARY_CACHE_DURATION]
        for ticker in expired_summaries:
            del fallback_summary_cache[ticker]
        
        if expired_news or expired_summaries:
            logger.info(f"Cleaned {len(expired_news)} news + {len(expired_summaries)} fallback cache entries")
    else:
        logger.debug("Redis handles cache expiry automatically")

# Daily Limits (official free tier limits)
DAILY_LIMITS = {
    'gemini': 1500,  # 15 RPM, 1M tokens/month (daily estimate)
    'polygon': 'unlimited',  # 5 RPM but unlimited monthly calls
    'alpha_vantage_realtime': 25,  # 25 requests/day (free tier)
    'twelve_data_realtime': 800,  # 800 requests/day (free tier)
    'finnhub': 60,  # 60 calls/minute, ~86,400/day theoretical
    'alpaca': 'unlimited'  # Unlimited real-time data
}

def check_api_quota(service):
    """Check if API quota is available"""
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
    api_usage[service]['calls'] += 1
    logger.debug(f"{service} API call #{api_usage[service]['calls']}")

client = genai.Client(api_key=GEMINI_API_KEY)

# Initialize scheduler for cache cleanup
scheduler = BackgroundScheduler()
scheduler.add_job(cleanup_expired_cache, 'interval', hours=1)
scheduler.start()
logger.info("Cache cleanup scheduler started (runs every hour)")

# Database setup
def init_db():
    """Supabase tables are created via SQL migrations in dashboard"""
    try:
        # Test connection with a simple query
        result = supabase.table('tickers').select('*').limit(1).execute()
        logger.info("Supabase connection and tables verified")
    except Exception as e:
        logger.warning(f"Supabase tables not found: {e}")
        logger.info("Please create tables using supabase_migration.sql in your Supabase dashboard")
        # Don't raise error - let app start but warn user

class NewsCollector:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
    
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
    
    def get_tradingview_news(self, ticker):
        """Scrape TradingView news for ticker - improved version"""
        logger.debug(f"Starting TradingView scraping for {ticker}")
        try:
            # Try different TradingView URLs
            urls = [
                f"https://www.tradingview.com/symbols/{ticker}/news/",
                f"https://www.tradingview.com/symbols/NASDAQ-{ticker}/news/",
                f"https://www.tradingview.com/symbols/NYSE-{ticker}/news/"
            ]
            
            articles = []
            for url in urls:
                try:
                    logger.debug(f"Trying URL: {url}")
                    response = self.session.get(url, timeout=15)
                    
                    if response.status_code != 200:
                        continue
                    
                    soup = BeautifulSoup(response.content, 'html.parser')
                    
                    # Look for JSON data in script tags (TradingView often embeds data)
                    scripts = soup.find_all('script')
                    for script in scripts:
                        if script.string and 'news' in script.string.lower():
                            script_content = script.string
                            # Try to extract news titles from JSON-like content
                            import re
                            titles = re.findall(r'"title"\s*:\s*"([^"]+)"', script_content)
                            urls_found = re.findall(r'"url"\s*:\s*"([^"]+)"', script_content)
                            
                            for i, title in enumerate(titles[:8]):
                                if len(title) > 15:
                                    article_url = urls_found[i] if i < len(urls_found) else url
                                    articles.append({
                                        'title': title,
                                        'url': article_url,
                                        'source': 'TradingView',
                                        'content': title,
                                        'date': datetime.now().isoformat()
                                    })
                    
                    # Fallback: look for any text that looks like news headlines
                    if not articles:
                        # Find all text elements and filter for news-like content
                        all_text = soup.get_text()
                        lines = [line.strip() for line in all_text.split('\n') if line.strip()]
                        
                        potential_headlines = []
                        for line in lines:
                            # Filter for lines that look like headlines
                            if (20 < len(line) < 150 and 
                                not line.startswith(('http', 'www', 'Copyright', 'Terms')) and
                                any(word in line.lower() for word in ['stock', 'market', 'price', 'earnings', 'revenue', ticker.lower()])):
                                potential_headlines.append(line)
                        
                        # Take first few potential headlines
                        for headline in potential_headlines[:5]:
                            articles.append({
                                'title': headline,
                                'url': url,
                                'source': 'TradingView',
                                'content': headline,
                                'date': datetime.now().isoformat()
                            })
                    
                    if articles:
                        break
                        
                except Exception as url_error:
                    logger.debug(f"Error with URL {url}: {url_error}")
                    continue
            
            logger.info(f"TradingView: Found {len(articles)} articles for {ticker}")
            return articles
            
        except Exception as e:
            logger.error(f"TradingView scraping error for {ticker}: {e}")
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
                    articles.append({
                        'title': item.get('title', ''),
                        'url': item.get('article_url', ''),
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
                for item in data['feed'][:10]:
                    try:
                        title = item.get('title', '')
                        url = item.get('url', '')
                        summary = item.get('summary', '')
                        
                        if title and len(title) > 15:
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
        """Get news from Twelve Data API"""
        logger.debug(f"Starting Twelve Data API call for {ticker}")
        try:
            url = "https://api.twelvedata.com/news"
            params = {
                'symbol': ticker,
                'apikey': TWELVE_DATA_API_KEY,
                'limit': 10
            }
            
            logger.debug(f"Twelve Data API call: {url} with params: {params}")
            response = self.session.get(url, params=params, timeout=15)
            logger.debug(f"Twelve Data response status: {response.status_code}")
            
            if response.status_code != 200:
                logger.error(f"Twelve Data returned status {response.status_code}, response: {response.text[:200]}")
                return []
            
            data = response.json()
            logger.debug(f"Twelve Data response keys: {list(data.keys()) if isinstance(data, dict) else 'Not a dict'}")
            
            articles = []
            if 'data' in data:
                for item in data['data'][:10]:
                    try:
                        title = item.get('title', '')
                        url = item.get('url', '')
                        summary = item.get('summary', '')
                        
                        if title and len(title) > 15:
                            articles.append({
                                'title': title,
                                'url': url,
                                'source': 'Twelve Data',
                                'content': summary or title,
                                'date': item.get('datetime', datetime.now().isoformat())
                            })
                    except Exception as item_error:
                        logger.debug(f"Error processing Twelve Data item: {item_error}")
                        continue
            
            logger.info(f"Twelve Data: Found {len(articles)} articles for {ticker}")
            return articles
            
        except Exception as e:
            logger.error(f"Twelve Data API error for {ticker}: {e}")
            logger.debug(f"Twelve Data full error: {repr(e)}")
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
                for item in data[:10]:
                    try:
                        title = item.get('headline', '')
                        url = item.get('url', '')
                        summary = item.get('summary', '')
                        
                        if title and len(title) > 15:
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

class AIProcessor:
    def __init__(self):
        self.client = client
    
    def _call_gemini_with_fallback(self, prompt, fallback_result):
        """Call Gemini API with quota checking and fallback"""
        if not check_api_quota('gemini'):
            logger.warning("Gemini quota exhausted, using fallback")
            return fallback_result
        
        try:
            time.sleep(4)  # Rate limiting
            response = self.client.models.generate_content(
                model='gemini-2.5-pro',
                contents=prompt
            )
            increment_api_usage('gemini')
            return response
        except Exception as e:
            error_str = str(e)
            if 'quota' in error_str.lower() or 'limit' in error_str.lower():
                logger.error(f"Gemini quota/rate limit hit: {error_str}")
                api_usage['gemini']['calls'] = DAILY_LIMITS['gemini']
                return fallback_result
            raise e
    
    def select_top_articles(self, articles, ticker):
        """Use Gemini to select top 5-7 most relevant articles"""
        logger.debug(f"Starting article selection with {len(articles)} articles")
        if not articles:
            logger.warning("No articles provided for selection")
            return []
        
        try:
            articles_text = "\n\n".join([
                f"Article {i+1}:\nTitle: {art['title']}\nSource: {art['source']}\nContent: {art['content'][:200]}..."
                for i, art in enumerate(articles)
            ])
            
            prompt = f"""
            You are a senior equity research analyst at a top-tier investment bank. Select the 5-7 most market-moving articles for {ticker} that professional traders need to know:
            
            PRIORITY CRITERIA (rank by importance):
            1. EARNINGS/FINANCIAL RESULTS - Revenue beats/misses, guidance changes, margin impacts
            2. REGULATORY/LEGAL - FDA approvals, antitrust, compliance issues, lawsuits
            3. STRATEGIC MOVES - M&A, partnerships, market expansion, product launches
            4. MANAGEMENT CHANGES - CEO/CFO changes, insider trading, leadership shifts
            5. COMPETITIVE THREATS - Market share loss, new competitors, pricing pressure
            6. MACROECONOMIC IMPACT - Interest rate sensitivity, inflation effects, sector rotation
            
            EXCLUDE: General market commentary, analyst upgrades/downgrades without new data, promotional content
            
            Articles:
            {articles_text}
            
            Return only article numbers (1,2,3,etc.) separated by commas. Prioritize immediate trading catalysts.
            """
            
            logger.debug(f"Sending prompt to Gemini (length: {len(prompt)} chars)")
            logger.debug(f"Using API key: {GEMINI_API_KEY[:10]}...")
            if GEMINI_API_KEY == 'your-gemini-api-key':
                logger.error("Gemini API key not configured properly")
                return articles[:5]
            
            response = self._call_gemini_with_fallback(prompt, None)
            if response is None:
                logger.warning("Using fallback article selection")
                return articles[:5]
            logger.debug(f"Gemini response: {response.text[:100]}...")
            selected_indices = [int(x.strip()) - 1 for x in response.text.split(',') if x.strip().isdigit()]
            logger.debug(f"Selected article indices: {selected_indices}")
            
            return [articles[i] for i in selected_indices if 0 <= i < len(articles)]
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Article selection error: {error_msg}")
            logger.error(f"Full error details: {repr(e)}")
            return articles[:5]  # Fallback to first 5
    
    def generate_summary(self, ticker, selected_articles, historical_summaries, alpaca_quote=None):
        """Generate comprehensive summary with 'What changed today' section"""
        logger.debug(f"Starting summary generation for {ticker}")
        
        # Add Alpaca context if available
        market_context = ""
        if alpaca_quote:
            market_context = "\n\nCURRENT MARKET DATA:\n"
            market_context += f"Price: ${alpaca_quote['price']:.2f}\n"
            market_context += f"Bid/Ask: ${alpaca_quote['bid']:.2f}/${alpaca_quote['ask']:.2f} (Spread: ${alpaca_quote['spread']:.2f})\n"
        try:
            if GEMINI_API_KEY == 'your-gemini-api-key':
                logger.error("Gemini API key not configured")
                return {
                    'summary': f"API key not configured for {ticker}. Check .env file.",
                    'what_changed': "Unable to generate summary."
                }
            articles_text = "\n\n".join([
                f"Source: {art['source']}\nTitle: {art['title']}\nContent: {art['content']}"
                for art in selected_articles
            ])
            
            history_text = "\n".join([
                f"Day {i+1}: {summary['what_changed']}"
                for i, summary in enumerate(historical_summaries[-7:])
            ])
            
            prompt = f"""
            You are a senior equity research analyst providing a trading desk briefing for {ticker}. Write for professional traders and portfolio managers.
            
            TODAY'S NEWS:
            {articles_text}
            
            HISTORICAL CONTEXT (Past 7 Days):
            {history_text}{market_context}
            
            IMPORTANT: Do NOT include memo headers like TO:, FROM:, SUBJECT:, or similar formatting. Start directly with content.
            
            REQUIRED FORMAT:
            
            **TRADING THESIS** (2-3 sentences)
            Bull/bear case with specific price catalysts and timeframe. Reference current price levels and technical context.
            
            **MATERIAL DEVELOPMENTS**
            • QUANTIFY financial impact: Revenue/EPS/margin changes with specific numbers
            • REGULATORY updates: FDA approvals, legal settlements, compliance costs
            • COMPETITIVE position: Market share gains/losses, pricing power changes
            • MANAGEMENT actions: Buybacks, dividends, guidance revisions, insider activity
            
            **RISK/REWARD ANALYSIS**
            • UPSIDE catalysts: Specific events, earnings beats, product launches (with timeline)
            • DOWNSIDE risks: Regulatory threats, competitive pressure, execution risks
            • TECHNICAL levels: Current price vs OHLC range, volume analysis, bid-ask spread insights
            
            **SECTOR CONTEXT**
            • Peer comparison: How {ticker} compares to competitors on key metrics
            • Sector rotation implications: Growth vs value, cyclical positioning
            
            **WHAT CHANGED TODAY**
            NEW information only - compare to past 7 days. Focus on material changes to investment thesis.
            
            CRITICAL REQUIREMENTS:
            - Include specific numbers (revenue, margins, market cap impact)
            - Reference current market data (price, bid-ask spread)
            - Mention timeframes for catalysts (Q1 earnings, FDA decision by March, etc.)
            - Use trading terminology (support, resistance, breakout, momentum, VWAP)
            - Analyze volume patterns and price action context
            - Focus on actionable intelligence for position sizing
            - Maximum 500 words, minimum 300 words
            - No fluff or general market commentary
            """
            
            logger.debug(f"Sending summary prompt to Gemini (length: {len(prompt)} chars)")
            fallback_summary = {
                'summary': f"**TRADING ALERT: {ticker}** - API quota exceeded. Manual review required for today's developments. Key articles collected from multiple sources indicate potential market-moving news. Recommend checking primary sources for earnings, regulatory updates, or management announcements that may impact trading position.",
                'what_changed': "API quota exceeded - check for earnings releases, FDA approvals, or management guidance changes that may affect trading thesis."
            }
            
            response = self._call_gemini_with_fallback(prompt, fallback_summary)
            if isinstance(response, dict):  # Fallback was returned
                return response
            logger.debug(f"Gemini summary response received: {len(response.text)} chars")
            logger.debug(f"Response preview: {response.text[:200]}...")
            
            # Extract "What changed today" section
            summary_text = response.text
            what_changed = "No material developments identified."
            
            # Try multiple section headers with more flexible matching
            change_indicators = ["**WHAT CHANGED TODAY**", "WHAT CHANGED TODAY", "What Changed Today", "**What Changed Today**"]
            for indicator in change_indicators:
                if indicator in summary_text:
                    parts = summary_text.split(indicator)
                    if len(parts) > 1:
                        # Get everything after the indicator until next section or end
                        remaining_text = parts[1]
                        # Split by double newlines or next section headers
                        next_section_patterns = ["\n\n**", "\n\n##", "\n\nEXECUTIVE", "\n\nKEY", "\n\nMARKET"]
                        end_pos = len(remaining_text)
                        for pattern in next_section_patterns:
                            pos = remaining_text.find(pattern)
                            if pos != -1 and pos < end_pos:
                                end_pos = pos
                        
                        what_changed = remaining_text[:end_pos].strip()
                        
                        # Clean up formatting
                        what_changed = what_changed.replace("**", "").replace("*", "").strip()
                        # Remove memo-style headers and empty lines
                        lines = what_changed.split('\n')
                        cleaned_lines = []
                        for line in lines:
                            line = line.strip()
                            if (line and not line.startswith('TO:') and not line.startswith('FROM:') and 
                                not line.startswith('SUBJECT:') and not line.startswith('DATE:') and
                                not line.startswith('---') and line != '**' and line != '*'):
                                cleaned_lines.append(line)
                        
                        if cleaned_lines:
                            what_changed = ' '.join(cleaned_lines)
                            logger.debug(f"Extracted what_changed: {what_changed[:100]}...")
                            break
            
            # If no specific section found, try to extract from the end of summary
            if what_changed == "No material developments identified.":
                # Look for change-related content at the end
                lines = summary_text.split('\n')
                for i in range(len(lines)-1, max(0, len(lines)-10), -1):
                    line = lines[i].strip()
                    if (line and ('new' in line.lower() or 'today' in line.lower() or 'changed' in line.lower() or 
                                 'development' in line.lower() or 'announcement' in line.lower())):
                        # Found potential change content
                        what_changed = line
                        logger.debug(f"Found change content from end: {what_changed[:100]}...")
                        break
            
            result = {
                'summary': summary_text,
                'what_changed': what_changed
            }
            logger.debug(f"Final what_changed content: '{what_changed}'")
            return result
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Summary generation error for {ticker}: {error_msg}")
            logger.error(f"API Key being used: {GEMINI_API_KEY[:10]}...{GEMINI_API_KEY[-5:]}")
            logger.error(f"Full error details: {repr(e)}")
            return {
                'summary': f"**TRADING ALERT: {ticker}** - Technical error in analysis. Raw data collected but AI processing failed. Error: {error_msg[:100]}. Recommend manual review of collected articles for potential trading catalysts.",
                'what_changed': "Technical error - manual review required for trading-relevant developments."
            }

# Initialize components
collector = NewsCollector()
ai_processor = AIProcessor()
chart_generator = ChartGenerator()



@app.route('/')
def index():
    return render_template('index.html')

@app.route('/test_ticker.html')
def test_ticker():
    return app.send_static_file('../test_ticker.html')



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
                'gemini': {'configured': bool(GEMINI_API_KEY and GEMINI_API_KEY != 'your-gemini-api-key')},
                'polygon': {'configured': bool(POLYGON_API_KEY and POLYGON_API_KEY != 'your-polygon-api-key')},
                'alpha_vantage': {'configured': bool(ALPHA_VANTAGE_API_KEY and ALPHA_VANTAGE_API_KEY != 'your-alpha-vantage-api-key')},
                'twelve_data': {'configured': bool(TWELVE_DATA_API_KEY)},
                'finnhub': {'configured': bool(FINNHUB_API_KEY)},
                'alpaca': {'configured': bool(ALPACA_API_KEY and ALPACA_SECRET_KEY)}
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
        status = {
            'cache_type': 'Upstash' if redis_client else 'Memory',
            'upstash_configured': bool(UPSTASH_REDIS_REST_URL and UPSTASH_REDIS_REST_TOKEN),
            'connection_test': False,
            'cache_keys': [],
            'test_result': None
        }
        
        if redis_client:
            # Test Redis connection
            try:
                test_key = 'cache_test'
                test_value = {'test': 'data', 'timestamp': datetime.now().isoformat()}
                
                # Test write
                write_success = redis_client.setex(test_key, 60, json.dumps(test_value))
                
                # Test read
                read_data = redis_client.get(test_key)
                read_success = read_data is not None
                
                if read_success:
                    read_value = json.loads(read_data.decode('utf-8'))
                    status['test_result'] = 'SUCCESS: Write and read operations working'
                else:
                    status['test_result'] = 'FAILED: Could not read test data'
                
                status['connection_test'] = write_success and read_success
                
                # Clean up test
                redis_client.delete(test_key)
                
            except Exception as e:
                status['test_result'] = f'ERROR: {str(e)}'
                status['connection_test'] = False
        else:
            status['test_result'] = 'Using fallback memory cache'
            status['connection_test'] = True
        
        # Get current cache info and durations
        status['cache_durations'] = {
            'news_cache': f'{CACHE_DURATION // 3600} hours ({CACHE_DURATION} seconds)',
            'summary_cache': f'{SUMMARY_CACHE_DURATION // 3600} hours ({SUMMARY_CACHE_DURATION} seconds)'
        }
        
        if redis_client:
            # Can't easily list keys in Upstash REST, so show configured status
            status['cache_info'] = 'Upstash Redis REST API configured'
        else:
            status['cache_keys'] = {
                'news_cache': list(fallback_news_cache.keys()),
                'summary_cache': list(fallback_summary_cache.keys())
            }
        
        return jsonify(status)
        
    except Exception as e:
        return jsonify({
            'error': str(e),
            'cache_type': 'Error',
            'connection_test': False
        }), 500

@app.route('/api/tickers', methods=['GET'])
def get_tickers():
    try:
        if not supabase:
            logger.error("Supabase not initialized")
            return jsonify([])
            
        logger.debug("Getting tickers list")
        result = supabase.table('tickers').select('symbol').order('symbol', desc=False).execute()
        
        if hasattr(result, 'data') and result.data:
            tickers = [row['symbol'] for row in result.data]
            logger.debug(f"Found {len(tickers)} tickers: {tickers}")
            return jsonify(tickers)
        else:
            logger.warning(f"No data in result: {result}")
            return jsonify([])
            
    except Exception as e:
        logger.error(f"Error getting tickers: {e}")
        # Return empty array to prevent frontend errors
        return jsonify([])

def validate_ticker(ticker):
    """Validate if ticker exists by checking multiple sources"""
    try:
        logger.debug(f"Validating ticker: {ticker}")
        
        # Format check first
        if len(ticker) > 5 or not ticker.isalpha():
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
    
    if len(ticker) > 5 or not ticker.isalpha():
        return jsonify({'error': 'Invalid ticker format'}), 400
    
    # Validate ticker exists
    logger.info(f"Validating ticker: {ticker}")
    if not validate_ticker(ticker):
        return jsonify({'error': f'Ticker {ticker} not found or invalid'}), 400
    
    try:
        result = supabase.table('tickers').insert({
            'symbol': ticker,
            'added_date': datetime.now().isoformat()
        }).execute()
        logger.info(f"Successfully added ticker: {ticker}")
        return jsonify({'success': True})
    except Exception as e:
        error_msg = str(e)
        if 'duplicate' in error_msg.lower() or 'unique' in error_msg.lower():
            return jsonify({'error': 'Ticker already exists'}), 400
        logger.error(f"Error adding ticker {ticker}: {e}")
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/api/tickers/<ticker>', methods=['DELETE'])
def remove_ticker(ticker):
    """Remove a ticker from the watchlist"""
    try:
        if not supabase:
            logger.error("Supabase not initialized")
            return jsonify({'error': 'Database not available'}), 500
            
        ticker = ticker.upper().strip()
        logger.info(f"Remove ticker requested: {ticker}")
        
        # Remove ticker (skip existence check to avoid extra API call)
        supabase.table('tickers').delete().eq('symbol', ticker).execute()
        
        # Clear cache
        try:
            if redis_client:
                redis_client.delete(f"news:{ticker}", f"summary:{ticker}")
            else:
                if ticker in fallback_news_cache:
                    del fallback_news_cache[ticker]
                if ticker in fallback_summary_cache:
                    del fallback_summary_cache[ticker]
        except Exception as e:
            logger.debug(f"Cache clear error for {ticker}: {e}")
        
        logger.info(f"Successfully removed ticker: {ticker}")
        return jsonify({'success': True})
        
    except Exception as e:
        logger.error(f"Error removing ticker {ticker}: {e}")
        return jsonify({'success': True})  # Return success even on error to prevent UI issues

@app.route('/api/summary/<ticker>')
def get_summary(ticker):
    try:
        ticker = ticker.upper().strip()
        logger.debug(f"Getting summary for {ticker}")
        
        if not ticker or len(ticker) > 10:
            return jsonify({'error': 'Invalid ticker format'}), 400
        
        # Get latest summary
        result = supabase.table('daily_summaries').select('date, summary, articles_used, what_changed, risk_factors').eq('ticker', ticker).order('date', desc=True).limit(1).execute()
        
        logger.debug(f"Executed query for {ticker}")
        logger.debug(f"Query result for {ticker}: {'Found' if result.data else 'None'}")
        
        if result.data:
            row = result.data[0]
            logger.debug(f"Summary data found: date={row['date']}, summary_len={len(row['summary'])}, what_changed_len={len(row.get('what_changed', ''))}") 
            summary_data = {
                'date': row['date'],
                'summary': row['summary'],
                'articles_used': json.loads(row['articles_used']),
                'what_changed': row.get('what_changed', ''),
                'risk_factors': row.get('risk_factors', '')
            }
        else:
            logger.warning(f"No summary data found for {ticker}")
            summary_data = None
        
        # Get 7-day history
        history_result = supabase.table('daily_summaries').select('date, what_changed').eq('ticker', ticker).order('date', desc=True).limit(7).execute()
        history = [{'date': row['date'], 'what_changed': row['what_changed']} for row in history_result.data]
        
        return jsonify({
            'current_summary': summary_data,
            'history': history,
            'api_status': {
                'gemini_remaining': max(0, DAILY_LIMITS['gemini'] - api_usage['gemini']['calls']) if isinstance(DAILY_LIMITS['gemini'], int) else 'unlimited',
                'polygon_remaining': 'unlimited' if DAILY_LIMITS['polygon'] == 'unlimited' else max(0, DAILY_LIMITS['polygon'] - api_usage['polygon']['calls']),
                'quota_reset': 'Daily at midnight'
            },
            'cache_status': {
                'news_cached': redis_client.exists(f"news:{ticker}") if redis_client else ticker in fallback_news_cache,
                'summary_cached': redis_client.exists(f"summary:{ticker}") if redis_client else ticker in fallback_summary_cache,
                'cache_duration': f'{CACHE_DURATION // 3600} hours',
                'cache_type': 'Upstash' if redis_client else 'Memory'
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
            import time
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
    """Process news for a single ticker with caching"""
    logger.info(f"=== Starting news processing for {ticker} ===")
    
    # Get Alpaca quote for context
    alpaca_quote = alpaca.get_quote(ticker)
    
    if alpaca_quote:
        logger.info(f"Alpaca data for {ticker}: ${alpaca_quote['price']:.2f} (Bid: ${alpaca_quote['bid']:.2f}, Ask: ${alpaca_quote['ask']:.2f})")
    
    # Check for cached news first
    cached_articles, cached_sources = get_cached_news(ticker)
    if cached_articles:
        logger.info(f"Using cached news for {ticker} ({len(cached_articles)} articles)")
        all_articles = cached_articles
        source_counts = cached_sources
    else:
        # Collect news from all sources
        logger.debug("Collecting fresh news from all sources")
        all_articles = []
        tv_articles = collector.get_tradingview_news(ticker)
        all_articles.extend(tv_articles)
        fv_articles = collector.get_finviz_news(ticker)
        all_articles.extend(fv_articles)
        pg_articles = collector.get_polygon_news(ticker)
        all_articles.extend(pg_articles)
        av_articles = collector.get_alphavantage_news(ticker)
        all_articles.extend(av_articles)
        td_articles = collector.get_twelve_data_news(ticker)
        all_articles.extend(td_articles)
        fh_articles = collector.get_finnhub_news(ticker)
        all_articles.extend(fh_articles)
        # Add Alpaca news
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
        
        alpaca_count = len(alpaca_news['news']) if alpaca_news and 'news' in alpaca_news else 0
        source_counts = {'TV': len(tv_articles), 'FV': len(fv_articles), 'PG': len(pg_articles), 'AV': len(av_articles), 'TD': len(td_articles), 'FH': len(fh_articles), 'AL': alpaca_count}
        logger.info(f"Fresh articles collected: {len(all_articles)} (TV:{len(tv_articles)}, FV:{len(fv_articles)}, PG:{len(pg_articles)}, AV:{len(av_articles)}, TD:{len(td_articles)}, FH:{len(fh_articles)})")
        
        # Cache the collected news
        if all_articles:
            cache_news(ticker, all_articles, source_counts)
    
    if not all_articles:
        logger.warning(f"No articles found for {ticker} - stopping processing")
        return
    
    # Select top articles using AI
    logger.debug("Selecting top articles using AI")
    selected_articles = ai_processor.select_top_articles(all_articles, ticker)
    logger.info(f"Selected {len(selected_articles)} articles for summary")
    
    # Get historical summaries
    result = supabase.table('daily_summaries').select('summary, what_changed').eq('ticker', ticker).order('date', desc=True).limit(7).execute()
    historical_summaries = [{'summary': row['summary'], 'what_changed': row['what_changed']} for row in result.data]
    
    # Check for cached summary first
    cached_summary = get_cached_summary(ticker)
    if cached_summary and not cached_articles:  # Only use cached summary if news is also cached
        logger.info(f"Using cached summary for {ticker}")
        summary_result = cached_summary
    else:
        # Generate fresh summary with Alpaca context
        logger.debug("Generating fresh AI summary")
        summary_result = ai_processor.generate_summary(ticker, selected_articles, historical_summaries, alpaca_quote)
        logger.info(f"Generated fresh summary for {ticker} (length: {len(summary_result['summary'])} chars)")
        
        # Cache the summary
        cache_summary(ticker, summary_result)
    
    # Save articles to database
    today = datetime.now().date().isoformat()
    
    # Save all collected articles with duplicate prevention
    articles_saved = 0
    articles_skipped = 0
    
    for article in all_articles:
        try:
            # Check if article already exists (by ticker, title, and source)
            existing = supabase.table('news_articles').select('id').eq('ticker', ticker).eq('title', article['title']).eq('source', article['source']).limit(1).execute()
            
            if existing.data:
                articles_skipped += 1
                logger.debug(f"Skipping duplicate article: {article['title'][:50]}...")
                continue
            
            # Insert new article
            supabase.table('news_articles').insert({
                'ticker': ticker,
                'title': article['title'],
                'url': article['url'],
                'source': article['source'],
                'content': article['content'],
                'date': article['date']
            }).execute()
            articles_saved += 1
            
        except Exception as e:
            logger.error(f"Error saving article '{article['title'][:50]}...': {e}")
            articles_skipped += 1
    
    logger.info(f"Articles saved: {articles_saved}, skipped: {articles_skipped}")
    
    # Save summary
    articles_used = json.dumps([{
        'title': art['title'],
        'url': art['url'],
        'source': art['source']
    } for art in selected_articles])
    
    logger.debug(f"Saving summary to database for {ticker} on {today}")
    logger.debug(f"Summary length: {len(summary_result['summary'])} chars")
    logger.debug(f"What changed: {summary_result['what_changed'][:100]}...")
    
    # Upsert (insert or update) with conflict resolution
    supabase.table('daily_summaries').upsert({
        'ticker': ticker,
        'date': today,
        'summary': summary_result['summary'],
        'articles_used': articles_used,
        'what_changed': summary_result['what_changed']
    }, on_conflict='ticker,date').execute()
    
    logger.info(f"Processed {len(all_articles)} articles ({articles_saved} saved, {articles_skipped} skipped) and summary for {ticker}")
    logger.debug(f"Database save completed for {ticker}")
    
    logger.info(f"=== Completed processing for {ticker} ===")

@app.route('/api/refresh/<ticker>')
def refresh_ticker(ticker):
    """Manual refresh for a ticker - clears cache"""
    try:
        ticker = ticker.upper().strip()
        logger.info(f"Manual refresh requested for {ticker}")
        
        if not ticker or len(ticker) > 10:
            return jsonify({'error': 'Invalid ticker format'}), 400
        
        # Clear cache for fresh data
        try:
            if redis_client:
                redis_client.delete(f"news:{ticker}", f"summary:{ticker}")
                logger.debug(f"Cleared Redis cache for {ticker}")
            else:
                if ticker in fallback_news_cache:
                    del fallback_news_cache[ticker]
                if ticker in fallback_summary_cache:
                    del fallback_summary_cache[ticker]
                logger.debug(f"Cleared fallback cache for {ticker}")
        except Exception as e:
            logger.debug(f"Cache clear error for {ticker}: {e}")
        
        process_ticker_news(ticker)
        return jsonify({'success': True})
    except Exception as e:
        logger.error(f"Refresh error for {ticker}: {e}")
        return jsonify({'error': str(e)}), 500

def daily_update():
    """Daily update job - runs at 8 AM IST"""
    logger.info("Starting daily update")
    
    result = supabase.table('tickers').select('symbol').execute()
    tickers = [row['symbol'] for row in result.data]
    
    for ticker in tickers:
        try:
            process_ticker_news(ticker)
            time.sleep(2)  # Rate limiting
        except Exception as e:
            logger.error(f"Error processing {ticker}: {e}")
    
    logger.info("Daily update completed")

if __name__ == '__main__':
    init_db()
    
    # Setup scheduler for daily updates
    scheduler = BackgroundScheduler()
    scheduler.add_job(
        func=daily_update,
        trigger="cron",
        hour=8,
        minute=0,
        timezone='Asia/Kolkata'
    )
    scheduler.start()
    
    port = int(os.environ.get('PORT'))
    app.run(host='0.0.0.0', port=port, debug=False)