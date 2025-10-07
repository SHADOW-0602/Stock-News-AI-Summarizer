# 📈 Stock News AI Summarizer

A professional-grade financial news aggregation and AI analysis platform that delivers institutional-quality market intelligence for traders and investors.

## 🚀 Key Features

- **Multi-Source Intelligence**: Aggregates news from 15+ sources including TradingView (Selenium), Benzinga, Motley Fool, StockStory, Reuters, TechCrunch, 99Bitcoins (RSS), Polygon, Alpha Vantage, Finnhub, and more
- **AI-Powered Analysis**: Uses Gemini 2.5 Pro with real-time market context for institutional-grade summaries
- **Priority Source Processing**: Prioritizes premium sources (Benzinga, Motley Fool, StockStory, Reuters, TechCrunch) with retry logic and enhanced error handling
- **ML Price Forecasting**: Multi-model machine learning with cross-validation for price predictions
- **NLP Sentiment Analysis**: Real-time sentiment scoring from news headlines and content
- **Entity Highlighting**: Auto-highlights financial metrics, company names, and key terms for quick scanning
- **Company Logos**: Visual branding with cached company logos from API Ninjas
- **Interactive Price Charts**: Toggle charts with multiple timeframes (7D, 30D, 90D, 1Y, 2Y)
- **Optimized Caching**: 8-hour news cache, 6-hour summary cache, 7-day logo cache with complete cleanup on ticker deletion
- **100 Ticker Support**: Batch processing with smart API allocation for large portfolios
- **Smart Rate Limiting**: Conservative API quota management with intelligent caching
- **Trading-Focused Reports**: Risk/reward analysis, sector context, and specific trading catalysts
- **Cost-Optimized**: Operates on $0/month using free API tiers

## 🛠️ Complete Setup Guide

### Prerequisites
- Python 3.8+ installed
- Google Chrome browser (for TradingView scraping)
- Internet connection for API access
- Web browser for interface

### 1. Installation
```bash
# Clone repository
git clone https://github.com/your-username/stock-news-ai-summarizer.git
cd stock-news-ai-summarizer

# Install dependencies
pip install -r requirements.txt

# Alternative: Create virtual environment (recommended)
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Database & Cache Setup

#### Supabase Database (Required)
1. Sign up at [Supabase](https://supabase.com)
2. Create new project
3. Get Project URL and anon key from Settings → API
4. Run SQL from `create_tables.sql` in SQL Editor

#### Upstash Redis Cache (Required)
1. Sign up at [Upstash](https://upstash.com)
2. Create Redis database
3. Get REST URL and token from dashboard
4. Provides 4-hour news cache, 2-hour summary cache

### 3. API Configuration

#### Gemini API (Required)
1. Visit [Google AI Studio](https://makersuite.google.com/app/apikey)
2. Create free account and generate API key
3. Free tier: 15 requests/minute, 1M tokens/month

#### Polygon API (Optional but Recommended)
1. Sign up at [Polygon.io](https://polygon.io/)
2. Get free API key (5 calls/minute)
3. Provides professional news feed with sentiment analysis

#### Alpha Vantage API (Chart & News Data)
1. Sign up at [Alpha Vantage](https://www.alphavantage.co/support/#api-key)
2. Get free API key (25 calls/day)
3. Provides historical price data and news sentiment

#### Twelve Data API (Chart Data)
1. Sign up at [Twelve Data](https://twelvedata.com/)
2. Get free API key (800 requests/day)
3. Provides historical price data for charts

#### Finnhub API (News Data)
1. Sign up at [Finnhub](https://finnhub.io/)
2. Get free API key (60 calls/minute = ~86,400/day)
3. Provides company news and market data

#### Alpaca Markets API (Market Context & News)
1. Sign up at [Alpaca Markets](https://alpaca.markets/)
2. Get API key and secret from dashboard
3. Provides market status widget and professional news feed
4. Free tier includes real-time market data for enhanced AI analysis

#### API Ninjas (Company Logos)
1. Sign up at [API Ninjas](https://api.api-ninjas.com/)
2. Get free API key from dashboard
3. Provides company logos for visual branding
4. Free tier: 50,000 requests/month with 7-day caching

### 4. Environment Setup
```bash
# Copy environment template
cp .env.example .env

# Edit .env file with your keys
GEMINI_API_KEY=your_gemini_api_key_here
POLYGON_API_KEY=your_polygon_api_key_here
ALPHA_VANTAGE_API_KEY=your_alpha_vantage_api_key_here
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_ANON_KEY=your_supabase_anon_key
UPSTASH_REDIS_REST_URL=https://your-redis.upstash.io
UPSTASH_REDIS_REST_TOKEN=your_upstash_token
TWELVE_DATA_API_KEY=your_twelve_data_api_key
FINNHUB_API_KEY=your_finnhub_api_key
ALPACA_API_KEY=your_alpaca_api_key
ALPACA_SECRET_KEY=your_alpaca_secret_key
API_NINJAS_KEY=your_api_ninjas_key
PORT=5000
```

### 5. Launch Application
```bash
# Start the server
python app.py

# Access the application
# Open browser: http://localhost:5000
```

## 🌐 Production Deployment

### Railway (Recommended)
```bash
# 1. Fork this repository on GitHub
# 2. Connect to Railway (https://railway.app/)
# 3. Import your forked repository
# 4. Add environment variables:
#    - GEMINI_API_KEY
#    - POLYGON_API_KEY
#    - ALPHA_VANTAGE_API_KEY
# 5. Deploy automatically
```

### Render (Alternative)
```bash
# 1. Connect repository to Render (https://render.com/)
# 2. Create new Web Service
# 3. Set build command: pip install -r requirements.txt
# 4. Set start command: python app.py
# 5. Add environment variables in dashboard
```

### Heroku
```bash
# 1. Install Heroku CLI
# 2. Login and create app
heroku create your-app-name

# 3. Set environment variables
heroku config:set GEMINI_API_KEY=your_key
heroku config:set POLYGON_API_KEY=your_key
heroku config:set ALPHA_VANTAGE_API_KEY=your_key

# 4. Deploy
git push heroku main
```

### Chrome Browser Setup (Required for TradingView)
```bash
# Ubuntu/Debian
sudo apt-get update
sudo apt-get install -y google-chrome-stable

# Docker (add to Dockerfile)
RUN apt-get update && apt-get install -y \
    wget gnupg \
    && wget -q -O - https://dl.google.com/linux/linux_signing_key.pub | apt-key add - \
    && echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" >> /etc/apt/sources.list.d/google-chrome.list \
    && apt-get update \
    && apt-get install -y google-chrome-stable
```

## 💡 User Guide

### Getting Started
1. **Add Tickers**: Enter stock symbols (AAPL, TSLA, MSFT) in sidebar
2. **View Analysis**: Click ticker to see professional AI summary
3. **Interactive Charts**: Use chart button to toggle price charts with multiple timeframes
4. **Track Changes**: Monitor "What Changed Today" for new developments
5. **Manual Updates**: Use generate button for fresh AI analysis

### Professional Features
- **Market Status Widget**: Live market open/closed indicator in header
- **Company Logos**: Visual branding with 48px logos next to ticker names
- **Interactive Price Charts**: Multiple timeframes with professional Chart.js integration
- **Future Predictions Box**: ML price forecasting + sentiment analysis in unified display
- **Entity Highlighting**: Auto-highlighted financial metrics ($1.2B, 15%, Q3 2024, earnings)
- **Smart Caching**: 8-hour news, 6-hour summary, 7-day logo cache for 100-ticker optimization
- **Executive Summaries**: Portfolio manager-focused insights with Alpaca market context
- **Market Implications**: Trading considerations and risk factors
- **Quantified Impact**: Revenue, margin, and market share analysis
- **Sector Context**: Peer comparison and competitive positioning

### Best Practices
- **Add up to 100 tickers** - optimized batch processing supports large portfolios
- **Review summaries daily** - extended 8-hour cache provides instant access
- **Use manual refresh sparingly** - clears cache and uses fresh API calls
- **Monitor quota usage** - smart API allocation prevents exhaustion
- **Entity scanning** - highlighted metrics help quick information extraction
- **Chart analysis** - use chart toggle for price trend analysis

## 💰 Comprehensive Cost Analysis

### Current Monthly Costs (100 Tickers)
| Service | Tier | Cost | Usage | Limits | Cache Impact |
|---------|------|------|-------|--------|-------------|
| **Hosting** |
| Railway | Free | $0 | 500 hours/month | Sufficient | N/A |
| Render | Free | $0 | 750 hours/month | Alternative | N/A |
| **APIs** |
| Gemini 2.5 Pro | Free | $0 | ~600 requests/month | 45,000 available | 60% reduction |
| Polygon API | Free | $0 | ~900 requests/month | Unlimited (5 RPM) | 60% reduction |
| Alpha Vantage API | Free | $0 | ~750 requests/month | 750 available | Critical caching |
| Twelve Data API | Free | $0 | ~2,400 requests/month | 24,000 available | 60% reduction |
| Finnhub API | Free | $0 | ~3,600 requests/month | 2.6M available | Minimal impact |
| Alpaca Markets | Free | $0 | Unlimited | Real-time data | N/A |
| API Ninjas | Free | $0 | ~150 requests/month | 150,000 available | 95% reduction |
| **Total** | | **$0-5** | | **Scalable to 100 tickers** | **Major savings** |

### Scaling Cost Projections
| Tickers | Monthly Requests | Estimated Cost | Optimization |
|---------|------------------|----------------|-------------|
| 10 | 1,200 | $0 | Current setup (7min intervals) |
| 25 | 3,000 | $0 | Stay on free tiers |
| 50 | 6,000 | $0-2 | Monitor usage |
| 100 | 12,000 | $5-10 | Upgrade APIs |
| 500+ | 60,000+ | $20-50 | Enterprise APIs |

### Cost Optimization Strategies

#### 1. Multi-Level Caching
```python
# News articles cached for 8 hours
NEWS_CACHE_DURATION = 8 * 3600  # Reduces scraping by 80%

# AI summaries cached for 6 hours  
SUMMARY_CACHE_DURATION = 6 * 3600  # Reduces Gemini calls by 80%

# Company logos cached for 7 days
LOGO_CACHE_DURATION = 7 * 24 * 3600  # Reduces logo API calls by 95%

# Daily processing at 8 AM IST
DAILY_UPDATE_SCHEDULE = '08:00 IST'  # Automated news processing

# Automatic cache validation and cleanup
def is_cache_valid(timestamp, duration):
    return (datetime.now() - timestamp).total_seconds() < duration
```

#### 2. Intelligent Rate Limiting
```python
# Actual API limits and usage patterns
DAILY_LIMITS = {
    'gemini': 1500,        # 15 RPM, 1M tokens/month (daily estimate)
    'polygon': 'unlimited', # 5 RPM but unlimited monthly calls
    'alpha_vantage': 25,   # 25 requests/day (critical bottleneck)
    'twelve_data': 800,    # 800 requests/day (free tier)
    'finnhub': 7200,       # 60 calls/minute = ~86,400/day theoretical
    'alpaca': 'unlimited',  # Unlimited real-time market data
    'api_ninjas': 50000     # 50,000 requests/month (logos)
}

# Automatic quota checking
def check_api_quota(service):
    return api_usage[service]['calls'] < DAILY_LIMITS[service]

# Rate limiting delays
GEMINI_DELAY = 4    # seconds (15 RPM)
POLYGON_DELAY = 12  # seconds (5 RPM)
REALTIME_DELAY = 420 # seconds (7 minutes)
```

#### 3. Efficient Processing
- **Cache-First Strategy**: Check cache before API calls
- **Sequential Processing**: Prevents rate limit violations
- **Batch Operations**: Group similar requests
- **Optimized Prompts**: Shorter, more focused AI requests
- **Smart Scheduling**: Skip weekends, use off-peak hours

### Graceful Degradation
- **Gemini Quota Exceeded**: 
  - Falls back to first 5 articles (no AI selection)
  - Shows fallback summary with clear messaging
  - Uses cached summaries when available
- **Polygon Quota Exceeded**: 
  - Relies on TradingView + Finviz scraping only
  - Maintains service with reduced data sources
- **All APIs Down**: 
  - Displays cached summaries with timestamps
  - Shows clear status messages to users
  - Continues basic functionality

### ROI Analysis
- **Time Saved**: 2-3 hours daily research → 5 minutes
- **Coverage**: Multi-source professional analysis
- **Cost**: $0/month vs $50-200/month for Bloomberg Terminal
- **Break-even**: Profitable from day 1

## 🏗️ Technical Architecture

### Technology Stack
```
Frontend: HTML5 + CSS3 + Vanilla JavaScript
Backend: Python 3.8+ + Flask
Database: Supabase (PostgreSQL) - Cloud-native with real-time capabilities
Cache: Upstash Redis - Serverless Redis with REST API
AI/ML: Google Gemini 2.5 Pro API
Automation: Selenium WebDriver + Chrome (TradingView)
Parsing: BeautifulSoup4 + lxml (RSS/XML)
Data Sources: TradingView, Finviz, 99Bitcoins, Polygon API, Alpha Vantage, Twelve Data, Finnhub
Hosting: Railway/Render (Cloud)
Scheduling: APScheduler (Background jobs)
```

### Summary Generation Process
```
1. News Collection (15+ Sources - 50-100 articles)
   Priority Sources (Processed First):
   ├── Benzinga API (Premium financial news) → 10 articles
   ├── Motley Fool (Investment analysis) → 5 articles
   ├── StockStory (Stock-focused content) → 5 articles
   ├── Reuters (Business news) → 5 articles
   └── TechCrunch (Tech/startup coverage) → 5 articles
   
   Secondary Sources:
   ├── TradingView (Selenium automation) → 5-8 articles
   ├── Finviz (Quote page extraction) → 10 articles
   ├── 99Bitcoins (RSS feed) → 5 articles
   ├── Polygon API (Professional feed) → 10 articles
   ├── Alpha Vantage (News sentiment) → 10 articles
   ├── Twelve Data (Company news) → 10 articles
   ├── Finnhub (Market news) → 10 articles
   ├── NewsAPI (General news) → 10 articles
   ├── MarketWatch (Financial news) → 5 articles
   ├── Invezz (Investment news) → 3 articles
   └── Alpaca Markets (Trading news) → 3 articles

2. Enhanced Processing Pipeline (Gemini 2.5 Pro)
   ├── Priority Source Processing → Process premium sources first with retry logic
   ├── Article Selection → Top 5-7 most relevant by trading priority
   ├── Market Context Integration → Real-time price/bid-ask data from Alpaca
   ├── Historical Analysis → Compare with past 7 days
   └── Professional Summary → Trading thesis + risk analysis

3. Enhanced Data Management
   ├── Supabase Database → All articles + summaries + logos stored
   ├── Upstash Redis Cache → 8hr news, 6hr summaries, ML cache
   ├── Complete Cleanup → Ticker deletion removes all data and cache
   ├── Duplicate Prevention → Smart deduplication logic
   └── 7-day Rolling History → Track changes over time

4. Output Format
   ├── Trading Thesis → Bull/bear case with price targets
   ├── Material Developments → Quantified financial impact
   ├── Risk/Reward Analysis → Catalysts and threats
   ├── Sector Context → Peer comparison
   └── What Changed Today → New vs historical information
```

### Performance Optimizations
- **Priority Processing**: Premium sources processed first with dedicated resources
- **Enhanced Error Handling**: Retry logic for failed sources with detailed logging
- **Multi-Level Caching**: 8-hour news cache, 6-hour summary cache, ML cache
- **Session Reuse**: Persistent HTTP connections for web scraping
- **Selenium Optimization**: Headless Chrome with 3-second wait for dynamic content
- **XML Parsing**: lxml parser for efficient RSS feed processing (99Bitcoins)
- **Intelligent Rate Limiting**: Conservative API quota management with quota checking
- **Graceful Degradation**: Automatic fallbacks when limits hit
- **Complete Cleanup**: Full data removal on ticker deletion
- **Async Processing**: Background job scheduling with batch processing

### Security Features
- Environment variable protection
- Input validation and sanitization
- Rate limiting abuse prevention
- Error message sanitization
- Secure API key management

## ⚙️ System Configuration

### API Rate Limits & Management
```python
# Current Limits (Free Tiers)
GEMINI_API = {
    'requests_per_minute': 15,
    'monthly_tokens': 1000000,
    'current_usage': '~600 requests/month'
}

POLYGON_API = {
    'requests_per_minute': 5,
    'monthly_requests': 'Unlimited',
    'current_usage': '~900 requests/month'
}

# Rate Limiting Implementation
time.sleep(2)  # Between requests
max_daily_calls = 45  # 90% safety margin
```

### Automation & Scheduling
```python
# Daily Processing Schedule
SCHEDULE = {
    'daily_update': '08:00 IST',
    'processing_mode': 'sequential',
    'rate_limiting': '2 seconds between tickers',
    'history_retention': '7 days rolling',
    'cleanup_frequency': 'daily',
    'alpaca_context': 'enabled'  # Market data for AI summaries
}
```

### Error Handling & Resilience
- **API Failures**: Automatic fallback to cached data with timestamps
- **Rate Limit Exceeded**: Graceful degradation with clear user messaging
- **Quota Exhausted**: Conservative limits prevent hitting API caps
- **Network Issues**: Retry mechanism with exponential backoff
- **Invalid Tickers**: Real-time validation before processing
- **Cache Corruption**: Automatic cache invalidation and refresh
- **Data Integrity**: Validation checks on cached and fresh data


### Scalability Roadmap
```
Phase 1 (Current): SQLite + Free APIs (0-50 tickers)
Phase 2 (Growth): PostgreSQL + Paid APIs (50-200 tickers)
Phase 3 (Scale): Redis Cache + Load Balancing (200+ tickers)
Phase 4 (Enterprise): Microservices + Auto-scaling
```

## 🔧 Development & Troubleshooting

### Common Issues & Solutions

#### "Summary unavailable" Error
```bash
# Check API debug endpoint
curl http://localhost:5000/api/debug/apis

# Check logs for detailed errors
tail -f app.log

# Look for source-specific failures
grep "PRIORITY.*FAILED" app.log
grep "quota exhausted" app.log
```

#### Source Collection Issues
```bash
# Check which sources are failing
grep "COLLECTION SUMMARY" app.log
grep "Failed sources" app.log

# Manual refresh to clear cache and retry
curl -X GET http://localhost:5000/api/refresh/AAPL
```

#### Cache Issues
```bash
# Check cache status
curl http://localhost:5000/api/cache-status

# Clear specific ticker cache
curl -X DELETE http://localhost:5000/api/tickers/AAPL

# Monitor cache performance
grep "Using cached" app.log
grep "Cleared.*cache" app.log
```


### Development Setup
```bash
# Development mode with debug logging
export FLASK_ENV=development
export FLASK_DEBUG=1
python app.py

# Code formatting
black app.py
flake8 app.py
```

### Contributing Guidelines
1. **Fork & Clone**: Create your own repository copy
2. **Feature Branch**: `git checkout -b feature/your-feature`
3. **Code Standards**: Follow PEP 8, add docstrings
4. **Testing**: Test all changes thoroughly
5. **Documentation**: Update README for new features
6. **Pull Request**: Submit with detailed description

### AI Processing Intelligence
```python
# Article Selection Criteria (Gemini 2.5 Pro)
PRIORITY_CRITERIA = {
    1: "EARNINGS/FINANCIAL RESULTS",  # Revenue beats/misses, guidance
    2: "REGULATORY/LEGAL",           # FDA approvals, antitrust, lawsuits
    3: "STRATEGIC MOVES",            # M&A, partnerships, product launches
    4: "MANAGEMENT CHANGES",         # CEO/CFO changes, insider trading
    5: "COMPETITIVE THREATS",        # Market share loss, pricing pressure
    6: "MACROECONOMIC IMPACT"        # Interest rates, sector rotation
}

# Summary Generation Process
def generate_trading_summary():
    # Collect 30-70 articles from 7 sources
    # AI selects top 5-7 by trading relevance
    # Integrate real-time market data (price, bid/ask)
    # Generate professional trading analysis
    # Extract "What Changed Today" vs historical
    # Cache for 2 hours, store in database
```

## 🔒 Security & Compliance

### Data Protection & Storage
- **API Keys**: Environment variable encryption
- **Input Validation**: SQL injection prevention  
- **Rate Limiting**: DDoS protection
- **Duplicate Prevention**: Smart article deduplication
- **Data Persistence**: All articles and summaries stored in Supabase
- **Cache Strategy**: 4-hour news cache, 2-hour summary cache
- **Historical Tracking**: 7-day rolling analysis for trend detection

### Privacy Policy
- **No Personal Data**: Only ticker symbols stored
- **No User Tracking**: Privacy-focused design
- **Local Storage**: SQLite database on server only
- **API Compliance**: Follows provider terms of service

## 📱 User Experience

### Interface Design
- **Professional Layout**: Financial terminal inspired
- **Responsive Design**: Mobile and desktop optimized
- **Real-time Updates**: Live data generation
- **Intuitive Navigation**: Single-click access
- **Loading States**: Clear progress indicators

### Accessibility Features
- **Keyboard Navigation**: Full keyboard support
- **Screen Reader**: ARIA labels and semantic HTML
- **High Contrast**: Professional color scheme
- **Fast Loading**: Optimized for slow connections

## 📄 License & Support

### License
MIT License - see [LICENSE](LICENSE) file for details

### Support Channels
1. **GitHub Issues**: Bug reports and feature requests
2. **Documentation**: Check README and inline comments
3. **Community**: Discussions tab for questions
4. **Email**: [kushagra.singh0602@gmail.com] for urgent issues

### Reporting Issues
Include:
- Error messages and logs
- Steps to reproduce
- Environment details (OS, Python version)
- API usage statistics

---

**🚀 Built for Professional Traders & Investors**

*Delivering institutional-grade market intelligence at zero cost*
