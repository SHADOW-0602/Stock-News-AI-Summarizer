from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
import requests
from bs4 import BeautifulSoup
import os
from datetime import datetime, timedelta
from chart_generator import ChartGenerator
from ml_analysis import MLAnalyzer
from entity_highlighter import EntityHighlighter
import google.genai as genai
from apscheduler.schedulers.background import BackgroundScheduler
import time
import logging
from dotenv import load_dotenv
from concurrent.futures import ThreadPoolExecutor, as_completed
from database import db
from cache import cache
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
API_NINJAS_KEY = os.getenv('API_NINJAS_KEY')
BENZINGA_API_KEY = os.getenv('BENZINGA_API_KEY')
NEWSAPI_KEY = os.getenv('NEWSAPI_KEY')


logger.info(f"Gemini API Key loaded: {'Yes' if GEMINI_API_KEY != 'your-gemini-api-key' else 'No'}")
logger.info(f"Polygon API Key loaded: {'Yes' if POLYGON_API_KEY != 'your-polygon-api-key' else 'No'}")
logger.info(f"Twelve Data API Key loaded: {'Yes' if TWELVE_DATA_API_KEY else 'No'}")
logger.info(f"Finnhub API Key loaded: {'Yes' if FINNHUB_API_KEY else 'No'}")
logger.info(f"Benzinga API Key loaded: {'Yes' if BENZINGA_API_KEY else 'No'}")
logger.info(f"NewsAPI Key loaded: {'Yes' if NEWSAPI_KEY else 'No'}")
logger.info(f"Alpaca API Key loaded: {'Yes' if ALPACA_API_KEY else 'No'}")
logger.info(f"StockStory scraping: Enabled (no API key required)")
logger.info(f"Motley Fool scraping: Enabled (no API key required)")
logger.info(f"Reuters scraping: Enabled (no API key required)")
logger.info(f"TechCrunch scraping: Enabled (no API key required)")
logger.info(f"99Bitcoins scraping: Enabled (no API key required)")
logger.info(f"MarketWatch scraping: Enabled (no API key required)")
logger.info(f"Invezz scraping: Enabled (no API key required)")
logger.info(f"11theState scraping: Enabled (no API key required)")

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
    logger.debug(f"{service} API call #{api_usage[service]['calls']}")

client = genai.Client(api_key=GEMINI_API_KEY)

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
                for item in data[:10]:
                    try:
                        title = item.get('title', '')
                        url = item.get('url', '')
                        content = item.get('body', item.get('teaser', ''))
                        
                        if title and len(title) > 15:
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
            
            for link in article_links[:15]:
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
                        
                        if len(articles) >= 5:
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
            
            for link in article_links[:30]:
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
                        
                        if len(articles) >= 5:
                            break
                            
                except Exception as item_error:
                    logger.debug(f"Error processing Motley Fool item: {item_error}")
                    continue
            
            logger.info(f"Motley Fool: Found {len(articles)} articles for {ticker}")
            return articles
            
        except Exception as e:
            logger.error(f"Motley Fool scraping error for {ticker}: {e}")
            return []
    
    def get_reuters_news(self, ticker):
        """Scrape Reuters news for ticker"""
        logger.debug(f"Starting Reuters scraping for {ticker}")
        try:
            # Use business section with proper headers
            url = "https://www.reuters.com/business/"
            
            # Add proper headers to avoid 401
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
                'Accept-Encoding': 'gzip, deflate, br',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1',
                'Sec-Fetch-Dest': 'document',
                'Sec-Fetch-Mode': 'navigate',
                'Sec-Fetch-Site': 'none'
            }
            
            response = requests.get(url, headers=headers, timeout=15)
            
            if response.status_code != 200:
                logger.debug(f"Reuters returned status {response.status_code} for {ticker}")
                return []
            
            soup = BeautifulSoup(response.content, 'html.parser')
            articles = []
            
            # Look for actual article links with better selectors
            # Reuters uses specific patterns for article URLs
            all_links = soup.find_all('a', href=True)
            
            for link in all_links:
                try:
                    href = link.get('href', '')
                    title = link.get_text(strip=True)
                    
                    # Reuters articles typically have dates in URL like /2025/10/07/
                    if (title and len(title) > 30 and 
                        href and href.startswith('/') and
                        ('/2025/' in href or '/2024/' in href) and
                        not any(skip in href for skip in ['video', 'graphics', 'podcast'])):
                        
                        full_url = f"https://www.reuters.com{href}"
                        
                        articles.append({
                            'title': title,
                            'url': full_url,
                            'source': 'Reuters',
                            'content': title,
                            'date': datetime.now().isoformat()
                        })
                        
                        if len(articles) >= 5:
                            break
                            
                except Exception as item_error:
                    logger.debug(f"Error processing Reuters item: {item_error}")
                    continue
            
            logger.info(f"Reuters: Found {len(articles)} articles for {ticker}")
            return articles
            
        except Exception as e:
            logger.error(f"Reuters scraping error for {ticker}: {e}")
            return []
    
    def get_techcrunch_news(self, ticker):
        """Scrape TechCrunch news for ticker"""
        logger.debug(f"Starting TechCrunch scraping for {ticker}")
        try:
            url = f"https://techcrunch.com/?s={ticker}"
            response = self.session.get(url, timeout=15)
            
            if response.status_code != 200:
                logger.debug(f"TechCrunch returned status {response.status_code} for {ticker}")
                return []
            
            soup = BeautifulSoup(response.content, 'html.parser')
            articles = []
            
            # Look for article links
            article_links = soup.find_all('a', href=True)
            
            for link in article_links[:20]:
                try:
                    href = link.get('href', '')
                    title = link.get_text(strip=True)
                    
                    # Filter for relevant articles
                    if (title and len(title) > 20 and 
                        any(word in title.lower() for word in [ticker.lower(), 'stock', 'ipo', 'funding', 'startup']) and
                        href and 'techcrunch.com' in href and '/20' in href):
                        
                        articles.append({
                            'title': title,
                            'url': href,
                            'source': 'TechCrunch',
                            'content': title,
                            'date': datetime.now().isoformat()
                        })
                        
                        if len(articles) >= 5:
                            break
                            
                except Exception as item_error:
                    logger.debug(f"Error processing TechCrunch item: {item_error}")
                    continue
            
            logger.info(f"TechCrunch: Found {len(articles)} articles for {ticker}")
            return articles
            
        except Exception as e:
            logger.error(f"TechCrunch scraping error for {ticker}: {e}")
            return []
    
    def get_99bitcoins_news(self, ticker):
        """Get news from 99Bitcoins RSS feed"""
        logger.debug(f"Starting 99Bitcoins RSS feed collection for {ticker}")
        try:
            # Use RSS feed which is accessible
            url = "https://99bitcoins.com/feed/"
            response = self.session.get(url, timeout=15)
            
            if response.status_code != 200:
                logger.debug(f"99Bitcoins RSS returned status {response.status_code} for {ticker}")
                return []
            
            soup = BeautifulSoup(response.content, 'html.parser')
            articles = []
            
            # Parse RSS feed
            items = soup.find_all('item')
            
            for item in items[:10]:
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
                            
                            if len(articles) >= 5:
                                break
                                
                except Exception as item_error:
                    logger.debug(f"Error processing 99Bitcoins RSS item: {item_error}")
                    continue
            
            logger.info(f"99Bitcoins: Found {len(articles)} articles for {ticker}")
            return articles
            
        except Exception as e:
            logger.error(f"99Bitcoins RSS error for {ticker}: {e}")
            return []
    
    def get_newsapi_news(self, ticker):
        """Get news from NewsAPI.org"""
        logger.debug(f"Starting NewsAPI collection for {ticker}")
        try:
            if not NEWSAPI_KEY or NEWSAPI_KEY == 'your-newsapi-key':
                logger.debug(f"NewsAPI key not configured for {ticker}")
                return []
            
            if not check_api_quota('newsapi'):
                logger.warning("NewsAPI quota exhausted, skipping API call")
                return []
            
            url = "https://newsapi.org/v2/everything"
            params = {
                'q': f'{ticker} stock OR {ticker} earnings OR {ticker} company',
                'language': 'en',
                'sortBy': 'publishedAt',
                'pageSize': 10,
                'apiKey': NEWSAPI_KEY
            }
            
            response = self.session.get(url, params=params, timeout=15)
            increment_api_usage('newsapi')
            
            if response.status_code != 200:
                logger.error(f"NewsAPI returned status {response.status_code} for {ticker}")
                return []
            
            data = response.json()
            articles = []
            
            if 'articles' in data and data['articles']:
                for item in data['articles'][:10]:
                    try:
                        title = item.get('title', '')
                        url = item.get('url', '')
                        description = item.get('description', '')
                        source_name = item.get('source', {}).get('name', 'NewsAPI')
                        
                        if title and len(title) > 15:
                            articles.append({
                                'title': title,
                                'url': url,
                                'source': f'NewsAPI ({source_name})',
                                'content': description or title,
                                'date': item.get('publishedAt', datetime.now().isoformat())
                            })
                    except Exception as item_error:
                        logger.debug(f"Error processing NewsAPI item: {item_error}")
                        continue
            
            logger.info(f"NewsAPI: Found {len(articles)} articles for {ticker}")
            return articles
            
        except Exception as e:
            logger.error(f"NewsAPI error for {ticker}: {e}")
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
        """Scrape Invezz news for ticker"""
        logger.debug(f"Starting Invezz scraping for {ticker}")
        try:
            # Use news section which is accessible
            url = "https://invezz.com/news/"
            response = self.session.get(url, timeout=15)
            
            if response.status_code != 200:
                logger.debug(f"Invezz returned status {response.status_code} for {ticker}")
                return []
            
            soup = BeautifulSoup(response.content, 'html.parser')
            articles = []
            
            article_links = soup.find_all('a', href=True)
            
            for link in article_links[:30]:
                try:
                    href = link.get('href', '')
                    title = link.get_text(strip=True)
                    
                    # Look for general financial/stock news since we can't search specifically
                    if (title and len(title) > 25 and 
                        any(word in title.lower() for word in ['stock', 'trading', 'invest', 'market', 'crypto', 'finance']) and
                        href and 'invezz.com' in href and
                        not any(skip in href for skip in ['author', 'category', 'tag'])):
                        
                        articles.append({
                            'title': title,
                            'url': href,
                            'source': 'Invezz',
                            'content': title,
                            'date': datetime.now().isoformat()
                        })
                        
                        if len(articles) >= 3:
                            break
                            
                except Exception as item_error:
                    logger.debug(f"Error processing Invezz item: {item_error}")
                    continue
            
            logger.info(f"Invezz: Found {len(articles)} articles for {ticker}")
            return articles
            
        except Exception as e:
            logger.error(f"Invezz scraping error for {ticker}: {e}")
            return []
    
    def get_11thestate_news(self, ticker):
        """Scrape 11theState news for ticker"""
        logger.debug(f"Starting 11theState scraping for {ticker}")
        try:
            url = f"https://11thestate.com/?s={ticker}"
            response = self.session.get(url, timeout=15)
            
            if response.status_code != 200:
                logger.debug(f"11theState returned status {response.status_code} for {ticker}")
                return []
            
            soup = BeautifulSoup(response.content, 'html.parser')
            articles = []
            
            article_links = soup.find_all('a', href=True)
            
            for link in article_links[:15]:
                try:
                    href = link.get('href', '')
                    title = link.get_text(strip=True)
                    
                    if (title and len(title) > 20 and 
                        any(word in title.lower() for word in [ticker.lower(), 'stock', 'finance', 'market']) and
                        href and '11thestate.com' in href):
                        
                        articles.append({
                            'title': title,
                            'url': href,
                            'source': '11theState',
                            'content': title,
                            'date': datetime.now().isoformat()
                        })
                        
                        if len(articles) >= 3:
                            break
                            
                except Exception as item_error:
                    logger.debug(f"Error processing 11theState item: {item_error}")
                    continue
            
            logger.info(f"11theState: Found {len(articles)} articles for {ticker}")
            return articles
            
        except Exception as e:
            logger.debug(f"11theState scraping error for {ticker}: {e}")
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
            time.sleep(1)  # Optimized for speed
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
ml_analyzer = MLAnalyzer()
entity_highlighter = EntityHighlighter()



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
                'newsapi': {'configured': bool(NEWSAPI_KEY and NEWSAPI_KEY != 'your-newsapi-key')},
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
        return jsonify(cache.get_status())
    except Exception as e:
        return jsonify({
            'error': str(e),
            'cache_type': 'Error',
            'connection_test': False
        }), 500

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
        result = db.add_ticker(ticker)
        logger.info(f"Successfully added ticker: {ticker}")
        
        # Immediately process news for the new ticker
        try:
            logger.info(f"Processing initial news for new ticker: {ticker}")
            process_ticker_news(ticker)
            logger.info(f"Initial news processing completed for {ticker}")
        except Exception as process_error:
            logger.error(f"Error processing initial news for {ticker}: {process_error}")
            # Don't fail the ticker addition if news processing fails
        
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
        ticker = ticker.upper().strip()
        logger.info(f"Remove ticker requested: {ticker}")
        
        db.remove_ticker(ticker)
        cache.clear(ticker)
        
        logger.info(f"Successfully removed ticker: {ticker}")
        return jsonify({'success': True})
        
    except Exception as e:
        logger.error(f"Error removing ticker {ticker}: {e}")
        return jsonify({'success': True})

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
        
        # Priority sources first
        priority_tasks = []
        if BENZINGA_API_KEY:
            priority_tasks.append(('Benzinga', collector.get_benzinga_news, ticker))
        priority_tasks.extend([
            ('Motley Fool', collector.get_motley_fool_news, ticker),
            ('StockStory', collector.get_stockstory_news, ticker),
            ('Reuters', collector.get_reuters_news, ticker),
            ('TechCrunch', collector.get_techcrunch_news, ticker)
        ])
        
        # Secondary sources
        secondary_tasks = [
            ('TradingView', collector.get_tradingview_news, ticker),
            ('Finviz', collector.get_finviz_news, ticker),
            ('99Bitcoins', collector.get_99bitcoins_news, ticker),
            ('MarketWatch', collector.get_marketwatch_news, ticker),
            ('Invezz', collector.get_invezz_news, ticker),
            ('11theState', collector.get_11thestate_news, ticker)
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
            api_tasks.append(('NewsAPI', collector.get_newsapi_news, ticker))
        
        # Combine in priority order
        tasks = priority_tasks + api_tasks + secondary_tasks
        
        # Execute priority sources first
        logger.info(f"Processing {len(priority_tasks)} priority sources first...")
        with ThreadPoolExecutor(max_workers=3) as executor:
            priority_futures = {executor.submit(task[1], task[2]): task[0] for task in priority_tasks}
            
            for future in as_completed(priority_futures, timeout=45):
                source_name = priority_futures[future]
                try:
                    articles = future.result(timeout=30)
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
        
        # Execute remaining sources
        remaining_tasks = api_tasks + secondary_tasks
        logger.info(f"Processing {len(remaining_tasks)} remaining sources...")
        with ThreadPoolExecutor(max_workers=4) as executor:
            future_to_source = {executor.submit(task[1], task[2]): task[0] for task in remaining_tasks}
            
            for future in as_completed(future_to_source, timeout=60):
                source_name = future_to_source[future]
                try:
                    articles = future.result(timeout=45)
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
                    
                    # Retry failed sources once
                    if source_name not in ['Polygon', 'Alpha Vantage', 'NewsAPI']:  # Don't retry API sources
                        try:
                            logger.info(f"Retrying {source_name}...")
                            retry_task = next((t for t in tasks if t[0] == source_name), None)
                            if retry_task:
                                retry_articles = retry_task[1](retry_task[2])
                                if retry_articles:
                                    all_articles.extend(retry_articles)
                                    source_counts[source_name] = len(retry_articles)
                                    logger.info(f"{source_name}: RETRY SUCCESS - {len(retry_articles)} articles")
                        except Exception as retry_error:
                            logger.error(f"{source_name}: RETRY FAILED - {str(retry_error)[:50]}")
        
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
        # Get historical summaries and run AI processing in parallel
        with ThreadPoolExecutor(max_workers=2) as executor:
            # Submit both tasks
            history_future = executor.submit(db.get_history, ticker)
            selection_future = executor.submit(ai_processor.select_top_articles, all_articles, ticker)
            
            # Get results
            selected_articles = selection_future.result()
            history = history_future.result()
            
        historical_summaries = [{'summary': '', 'what_changed': item['what_changed']} for item in history]
        
        # Generate summary
        summary_result = ai_processor.generate_summary(ticker, selected_articles, historical_summaries, alpaca_quote)
        logger.info(f"Generated fresh summary for {ticker} (length: {len(summary_result['summary'])} chars)")
        
        # Cache the summary
        cache.set_summary(ticker, summary_result)
    
    # Save articles to database
    articles_saved, articles_skipped = db.save_articles(ticker, all_articles)
    logger.info(f"DATABASE SAVE RESULT for {ticker}: {articles_saved} SAVED, {articles_skipped} SKIPPED out of {len(all_articles)} TOTAL")
    
    # Save summary
    articles_used = [{
        'title': art['title'],
        'url': art['url'],
        'source': art['source']
    } for art in selected_articles]
    
    logger.debug(f"Saving summary to database for {ticker}")
    db.save_summary(ticker, summary_result, articles_used)
    
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
        cache.clear(ticker)
        
        # Process the ticker
        process_ticker_news(ticker)
        return jsonify({'success': True, 'message': f'Successfully refreshed {ticker}'})
        
    except Exception as e:
        logger.error(f"Refresh error for {ticker}: {e}")
        return jsonify({'error': f'Failed to refresh {ticker}: {str(e)}'}), 500

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
    db.test_connection()
    
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
    
    # Optional: Add weekend summary generation
    scheduler.add_job(
        func=cache.cleanup_expired,
        trigger="cron",
        hour=0,  # Midnight cleanup
        minute=0,
        timezone='Asia/Kolkata'
    )
    
    scheduler.start()
    
    port = int(os.environ.get('PORT'))
    app.run(host='0.0.0.0', port=port, debug=False)