from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
import requests
from bs4 import BeautifulSoup
import json
import os
from datetime import datetime
from supabase import create_client, Client
import requests
import json
import base64
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
SUPABASE_URL = os.getenv('SUPABASE_URL')
SUPABASE_KEY = os.getenv('SUPABASE_ANON_KEY')

# Initialize Supabase client
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

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
                    return base64.b64decode(result)
            return None
        except:
            return None
    
    def setex(self, key, seconds, value):
        try:
            encoded_value = base64.b64encode(value).decode('utf-8')
            data = {'value': encoded_value, 'ex': seconds}
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

# API Usage Tracking
api_usage = {
    'gemini': {'calls': 0, 'last_reset': datetime.now().date()},
    'polygon': {'calls': 0, 'last_reset': datetime.now().date()}
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
            redis_client.setex(f"news:{ticker}", CACHE_DURATION, json.dumps(cache_data).encode('utf-8'))
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
            redis_client.setex(f"summary:{ticker}", SUMMARY_CACHE_DURATION, json.dumps(cache_data).encode('utf-8'))
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

# Daily Limits (conservative)
DAILY_LIMITS = {
    'gemini': 800,  # ~15 RPM * 60 * 16 hours (conservative)
    'polygon': 7200  # ~5 RPM * 60 * 24 hours
}

def check_api_quota(service):
    """Check if API quota is available"""
    today = datetime.now().date()
    if api_usage[service]['last_reset'] != today:
        api_usage[service]['calls'] = 0
        api_usage[service]['last_reset'] = today
        logger.info(f"Reset {service} daily counter")
    
    if api_usage[service]['calls'] >= DAILY_LIMITS[service]:
        logger.warning(f"{service} daily limit reached ({DAILY_LIMITS[service]})")
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
            You are a senior financial analyst. Evaluate these news articles for {ticker} and select the 5-7 most impactful ones for institutional investors:
            
            SELECTION CRITERIA:
            • Market-moving potential and trading implications
            • Credible sources (avoid promotional content)
            • Quantifiable business impact (earnings, revenue, partnerships)
            • Regulatory or competitive developments
            • Management changes or strategic shifts
            
            Articles:
            {articles_text}
            
            Return only article numbers (1,2,3,etc.) separated by commas. Focus on actionable intelligence.
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
    
    def generate_summary(self, ticker, selected_articles, historical_summaries):
        """Generate comprehensive summary with 'What changed today' section"""
        logger.debug(f"Starting summary generation for {ticker}")
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
            Analyze {ticker} based on today's news and provide a professional investment summary.
            
            TODAY'S NEWS:
            {articles_text}
            
            HISTORICAL CONTEXT (Past 7 Days):
            {history_text}
            
            PROVIDE:
            
            **EXECUTIVE SUMMARY**
            Brief market impact assessment and key takeaway (2-3 sentences).
            
            **KEY DEVELOPMENTS**
            • Quantify impact where possible (revenue, margins, market share)
            • Focus on material business changes, not speculation
            • Include regulatory, competitive, or operational updates
            
            **MARKET IMPLICATIONS**
            • Price catalysts and trading considerations
            • Investment opportunities and upside potential
            • Sector/peer comparison context
            
            **WHAT CHANGED TODAY**
            Compare to previous 7 days - highlight NEW developments only.
            
            IMPORTANT: Do not include section headers with empty bullet points. Only include sections that have actual substantive content.
            Keep it professional, data-driven, and concise. Focus on material business impact.
            Length: 400-500 words maximum.
            """
            
            logger.debug(f"Sending summary prompt to Gemini (length: {len(prompt)} chars)")
            fallback_summary = {
                'summary': f"Summary temporarily unavailable for {ticker} due to API limits. Key articles collected from multiple sources.",
                'what_changed': "API quota exceeded - manual review recommended."
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
                'summary': f"API Error: {error_msg[:200]}",
                'what_changed': "Unable to determine changes due to API error."
            }

# Initialize components
collector = NewsCollector()
ai_processor = AIProcessor()


@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/tickers', methods=['GET'])
def get_tickers():
    try:
        logger.debug("Getting tickers list")
        result = supabase.table('tickers').select('symbol').order('added_date', desc=True).execute()
        tickers = [row['symbol'] for row in result.data]
        logger.debug(f"Found {len(tickers)} tickers: {tickers}")
        return jsonify(tickers)
    except Exception as e:
        logger.error(f"Error getting tickers: {e}")
        return jsonify([])

def validate_ticker(ticker):
    """Validate if ticker exists by checking multiple sources"""
    try:
        logger.debug(f"Validating ticker: {ticker}")
        # Check Finviz first (fastest)
        url = f"https://finviz.com/quote.ashx?t={ticker}"
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        response = requests.get(url, headers=headers, timeout=5)
        
        if response.status_code != 200:
            logger.debug(f"Finviz returned status {response.status_code} for {ticker}")
            return False
        
        if "not found" in response.text.lower() or "invalid" in response.text.lower():
            logger.debug(f"Ticker {ticker} not found on Finviz")
            return False
        
        # Check if page has stock data
        if "quote.ashx" in response.url and response.status_code == 200:
            logger.debug(f"Ticker {ticker} validated successfully")
            return True
            
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
        ticker = ticker.upper().strip()
        logger.info(f"Remove ticker requested: {ticker}")
        
        # Check if ticker exists
        result = supabase.table('tickers').select('symbol').eq('symbol', ticker).execute()
        if not result.data:
            return jsonify({'error': 'Ticker not found'}), 404
        
        # Remove ticker and related data
        supabase.table('tickers').delete().eq('symbol', ticker).execute()
        supabase.table('daily_summaries').delete().eq('ticker', ticker).execute()
        supabase.table('news_articles').delete().eq('ticker', ticker).execute()
        
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
        return jsonify({'error': 'Failed to remove ticker'}), 500

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
                'gemini_remaining': max(0, DAILY_LIMITS['gemini'] - api_usage['gemini']['calls']),
                'polygon_remaining': max(0, DAILY_LIMITS['polygon'] - api_usage['polygon']['calls']),
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

def process_ticker_news(ticker):
    """Process news for a single ticker with caching"""
    logger.info(f"=== Starting news processing for {ticker} ===")
    
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
        
        source_counts = {'TV': len(tv_articles), 'FV': len(fv_articles), 'PG': len(pg_articles), 'AV': len(av_articles)}
        logger.info(f"Fresh articles collected: {len(all_articles)} (TV:{len(tv_articles)}, FV:{len(fv_articles)}, PG:{len(pg_articles)}, AV:{len(av_articles)})")
        
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
        # Generate fresh summary
        logger.debug("Generating fresh AI summary")
        summary_result = ai_processor.generate_summary(ticker, selected_articles, historical_summaries)
        logger.info(f"Generated fresh summary for {ticker} (length: {len(summary_result['summary'])} chars)")
        
        # Cache the summary
        cache_summary(ticker, summary_result)
    
    # Save articles to database
    today = datetime.now().date().isoformat()
    
    # Save all collected articles
    for article in all_articles:
        try:
            supabase.table('news_articles').insert({
                'ticker': ticker,
                'title': article['title'],
                'url': article['url'],
                'source': article['source'],
                'content': article['content'],
                'date': article['date']
            }).execute()
        except Exception as e:
            logger.debug(f"Article already exists or error: {e}")
    
    # Save summary
    articles_used = json.dumps([{
        'title': art['title'],
        'url': art['url'],
        'source': art['source']
    } for art in selected_articles])
    
    logger.debug(f"Saving summary to database for {ticker} on {today}")
    logger.debug(f"Summary length: {len(summary_result['summary'])} chars")
    logger.debug(f"What changed: {summary_result['what_changed'][:100]}...")
    
    # Upsert (insert or update)
    supabase.table('daily_summaries').upsert({
        'ticker': ticker,
        'date': today,
        'summary': summary_result['summary'],
        'articles_used': articles_used,
        'what_changed': summary_result['what_changed']
    }).execute()
    
    logger.info(f"Saved {len(all_articles)} articles and summary for {ticker}")
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
    
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port, debug=False)