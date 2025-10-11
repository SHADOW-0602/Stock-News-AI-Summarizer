"""Supabase database operations"""

import os
import logging
from supabase import create_client, Client
from datetime import datetime
from functools import wraps

logger = logging.getLogger(__name__)

def safe_db_operation(default_return=None):
    """Decorator to safely handle database operations"""
    def decorator(func):
        @wraps(func)
        def wrapper(self, *args, **kwargs):
            if not self.client:
                logger.warning(f"Database not available for {func.__name__}")
                return default_return
            try:
                return func(self, *args, **kwargs)
            except Exception as e:
                logger.error(f"Database operation {func.__name__} failed: {e}")
                return default_return
        return wrapper
    return decorator

class Database:
    def __init__(self):
        self.client = None
        # Ensure environment variables are loaded
        from dotenv import load_dotenv
        load_dotenv()
        self._init_client()
    
    def _init_client(self):
        """Initialize Supabase client with error handling"""
        url = os.getenv('SUPABASE_URL')
        key = os.getenv('SUPABASE_ANON_KEY')
        
        if not url or not key or url == 'your-supabase-url':
            logger.error("Supabase credentials not configured")
            return
        
        for attempt in range(3):
            try:
                self.client = create_client(url, key)
                logger.info("Supabase client initialized successfully")
                return
            except KeyboardInterrupt:
                logger.warning("Initialization interrupted by user")
                break
            except Exception as e:
                if attempt < 2:
                    logger.warning(f"Supabase init attempt {attempt + 1} failed, retrying...")
                    import time
                    time.sleep(1)
                else:
                    logger.error(f"Failed to initialize Supabase after 3 attempts: {e}")
    
    def test_connection(self):
        """Test database connection and validate schema"""
        try:
            if not self.client:
                logger.error("No Supabase client available")
                return False
            
            # Test basic connection
            result = self.client.table('tickers').select('*').limit(1).execute()
            logger.info("Supabase connection verified")
            
            # Validate critical tables exist
            self._validate_schema()
            return True
        except Exception as e:
            logger.warning(f"Supabase connection test failed: {e}")
            return False
    
    def _validate_schema(self):
        """Validate database schema and log any issues"""
        if not self.client:
            return
        
        try:
            # Test each critical table with safe queries
            tables_to_test = [
                ('tickers', 'symbol'),
                ('daily_summaries', 'ticker, date, summary'),
                ('news_articles', 'ticker, title, source'),
                ('financial_statements', 'ticker, statement_type'),
                ('company_logos', 'ticker, logo_url')
            ]
            
            for table_name, columns in tables_to_test:
                try:
                    self.client.table(table_name).select(columns).limit(1).execute()
                    logger.debug(f"Table {table_name} validated successfully")
                except Exception as e:
                    logger.warning(f"Table {table_name} validation failed: {e}")
                    
        except Exception as e:
            logger.warning(f"Schema validation error: {e}")
    
    @safe_db_operation(default_return=[])
    def get_tickers(self):
        """Get all tickers safely"""
        result = self.client.table('tickers').select('symbol').order('symbol', desc=False).execute()
        tickers = [row['symbol'] for row in result.data] if result.data else []
        logger.debug(f"Retrieved {len(tickers)} tickers from database")
        return tickers
    
    def add_ticker(self, ticker):
        """Add new ticker"""
        if not self.client:
            raise Exception("Database not available")
        
        return self.client.table('tickers').insert({
            'symbol': ticker,
            'added_date': datetime.now().isoformat()
        }).execute()
    
    def remove_ticker(self, ticker):
        """Remove ticker"""
        if not self.client:
            return
        
        self.client.table('tickers').delete().eq('symbol', ticker).execute()
    
    def save_articles(self, ticker, articles):
        """Save news articles"""
        if not self.client or not articles:
            logger.warning(f"Cannot save articles: client={bool(self.client)}, articles_count={len(articles) if articles else 0}")
            return 0, 0
        
        saved, skipped = 0, 0
        logger.info(f"Attempting to save {len(articles)} articles for {ticker}")
        
        for i, article in enumerate(articles):
            try:
                # Validate article data
                if not article.get('title') or not article.get('source'):
                    logger.warning(f"Article {i+1} missing required fields: title={bool(article.get('title'))}, source={bool(article.get('source'))}")
                    skipped += 1
                    continue
                
                # Prepare article data with proper defaults
                article_data = {
                    'ticker': ticker,
                    'title': article['title'][:500] if article.get('title') else '',  # Limit title length
                    'url': article.get('url', '')[:1000],  # Limit URL length
                    'source': article['source'][:100] if article.get('source') else '',  # Limit source length
                    'content': article.get('content', '')[:2000],  # Limit content length
                    'date': article.get('date', datetime.now().isoformat())
                }
                
                result = self.client.table('news_articles').insert(article_data).execute()
                
                if result.data:
                    saved += 1
                    logger.debug(f"Saved article {i+1}/{len(articles)}: {article['title'][:50]}...")
                else:
                    skipped += 1
                    logger.warning(f"No data returned for article {i+1}: {article['title'][:50]}...")
                    
            except Exception as e:
                error_str = str(e).lower()
                if 'duplicate' in error_str or 'unique' in error_str:
                    skipped += 1
                    logger.debug(f"Duplicate article {i+1} skipped: {article.get('title', 'Unknown')[:50]}...")
                else:
                    logger.error(f"Article {i+1} save error: {e}")
                    logger.error(f"Article data: title={article.get('title', 'None')[:50]}, source={article.get('source', 'None')}")
                    skipped += 1
        
        logger.info(f"Article save results for {ticker}: {saved} saved, {skipped} skipped out of {len(articles)} total")
        return saved, skipped
    
    def save_summary(self, ticker, summary_data, articles_used):
        """Save daily summary with error handling"""
        if not self.client:
            return
        
        try:
            import json
            
            # Prepare data with safe defaults
            data = {
                'ticker': ticker,
                'date': datetime.now().date().isoformat(),
                'summary': summary_data.get('summary', ''),
                'articles_used': json.dumps(articles_used or []),
                'what_changed': summary_data.get('what_changed', '')
            }
            
            self.client.table('daily_summaries').upsert(
                data, on_conflict='ticker,date'
            ).execute()
            
        except Exception as e:
            logger.error(f"Error saving summary for {ticker}: {e}")
            # Don't raise exception - log and continue
    
    def get_summary(self, ticker):
        """Get latest summary with safe column handling"""
        if not self.client:
            return None
        
        try:
            # Safe column selection - handle missing columns gracefully
            result = self.client.table('daily_summaries').select(
                'date, summary, articles_used, what_changed'
            ).eq('ticker', ticker).order('date', desc=True).limit(1).execute()
            
            if result.data:
                import json
                row = result.data[0]
                return {
                    'date': row.get('date', ''),
                    'summary': row.get('summary', ''),
                    'articles_used': json.loads(row.get('articles_used', '[]')),
                    'what_changed': row.get('what_changed', ''),
                    'risk_factors': row.get('risk_factors', '')  # Optional column
                }
        except Exception as e:
            logger.error(f"Error getting summary for {ticker}: {e}")
            # Return None on any error to prevent crashes
        
        return None
    
    def get_history(self, ticker, limit=7):
        """Get summary history with safe column handling"""
        if not self.client:
            return []
        
        try:
            # Safe column selection - include summary for better AI comparison
            result = self.client.table('daily_summaries').select(
                'date, summary, what_changed'
            ).eq('ticker', ticker).order('date', desc=True).limit(limit).execute()
            
            return [{
                'date': row.get('date', ''),
                'summary': row.get('summary', '')[:200] + '...' if len(row.get('summary', '')) > 200 else row.get('summary', ''),  # Truncate for AI context
                'what_changed': row.get('what_changed', ''),
                'created_at': row.get('date', '')  # Use date as fallback for created_at
            } for row in result.data] if result.data else []
        except Exception as e:
            logger.error(f"Error getting history for {ticker}: {e}")
            # Return empty list on any database error to prevent crashes
            return []
    
    @safe_db_operation(default_return=[])
    def get_recent_articles(self, ticker, limit=50):
        """Get recent articles safely"""
        result = self.client.table('news_articles').select(
            'title, content, source, url, date'
        ).eq('ticker', ticker).order('date', desc=True).limit(limit).execute()
        
        return result.data if result.data else []
    
    def get_logo(self, ticker):
        """Get cached logo URL"""
        if not self.client:
            return None
        
        try:
            result = self.client.table('company_logos').select(
                'logo_url'
            ).eq('ticker', ticker).execute()
            
            if result.data:
                return result.data[0]['logo_url']
        except Exception as e:
            logger.debug(f"Error getting logo for {ticker}: {e}")
        
        return None
    
    def save_logo(self, ticker, logo_url, company_name=None):
        """Save logo URL to database with retry"""
        if not self.client:
            return
        
        for attempt in range(3):
            try:
                self.client.table('company_logos').upsert({
                    'ticker': ticker,
                    'logo_url': logo_url,
                    'company_name': company_name or ticker,
                    'updated_at': datetime.now().isoformat()
                }, on_conflict='ticker').execute()
                
                logger.debug(f"Saved logo for {ticker}: {logo_url}")
                return
            except Exception as e:
                if attempt < 2:
                    logger.warning(f"Logo save attempt {attempt + 1} failed for {ticker}, retrying...")
                    import time
                    time.sleep(1)
                else:
                    logger.error(f"Error saving logo for {ticker} after 3 attempts: {e}")
    
    def delete_articles(self, ticker):
        """Delete all articles for ticker"""
        if not self.client:
            return
        
        self.client.table('news_articles').delete().eq('ticker', ticker).execute()
        logger.info(f"Deleted articles for {ticker}")
    
    def delete_summaries(self, ticker):
        """Delete all summaries for ticker"""
        if not self.client:
            return
        
        self.client.table('daily_summaries').delete().eq('ticker', ticker).execute()
        logger.info(f"Deleted summaries for {ticker}")
    
    def delete_logo(self, ticker):
        """Delete logo for ticker"""
        if not self.client:
            return
        
        self.client.table('company_logos').delete().eq('ticker', ticker).execute()
        logger.info(f"Deleted logo for {ticker}")
    
    def save_financial_data(self, ticker, statement_type, period, data):
        """Save financial statement data"""
        if not self.client:
            return
        
        import json
        
        self.client.table('financial_statements').upsert({
            'ticker': ticker,
            'statement_type': statement_type,
            'period': period,
            'data': json.dumps(data),
            'updated_at': datetime.now().isoformat()
        }, on_conflict='ticker,statement_type,period').execute()
    
    def get_financial_data(self, ticker, statement_type, period):
        """Get financial statement data"""
        if not self.client:
            return None
        
        try:
            result = self.client.table('financial_statements').select(
                'data, updated_at'
            ).eq('ticker', ticker).eq('statement_type', statement_type).eq('period', period).execute()
            
            if result.data:
                import json
                return json.loads(result.data[0]['data'])
        except Exception as e:
            logger.error(f"Error getting financial data for {ticker}: {e}")
        
        return None
    
    def delete_financial_data(self, ticker):
        """Delete all financial data for ticker"""
        if not self.client:
            return
        
        self.client.table('financial_statements').delete().eq('ticker', ticker).execute()
        logger.info(f"Deleted financial data for {ticker}")
    
    def save_financial_statement(self, ticker, statement_type, period, fiscal_date, data):
        """Save financial statement with fiscal date"""
        if not self.client:
            return
        
        import json
        self.client.table('financial_statements').upsert({
            'ticker': ticker,
            'statement_type': statement_type,
            'period': period,
            'fiscal_date': fiscal_date,
            'data': json.dumps(data) if isinstance(data, dict) else data,
            'created_at': datetime.now().isoformat()
        }, on_conflict='ticker,statement_type,period,fiscal_date').execute()
    
    def get_recent_financials(self, ticker, days=7):
        """Get financial statements saved in last 7 days"""
        if not self.client:
            return []
        
        try:
            from datetime import datetime, timedelta
            cutoff_date = (datetime.now() - timedelta(days=days)).isoformat()
            
            result = self.client.table('financial_statements').select('*').eq(
                'ticker', ticker
            ).gte('created_at', cutoff_date).execute()
            
            return result.data if result.data else []
        except Exception as e:
            logger.error(f"Error getting recent financials for {ticker}: {e}")
            return []
    
    def get_financial_dates(self, ticker):
        """Get financial statement dates saved in last 7 days"""
        if not self.client:
            return []
        
        try:
            from datetime import datetime, timedelta
            cutoff_date = (datetime.now() - timedelta(days=7)).isoformat()
            
            result = self.client.table('financial_statements').select('created_at').eq('ticker', ticker).gte('created_at', cutoff_date).order('created_at', desc=True).execute()
            dates = list(set([item['created_at'][:10] for item in result.data if item.get('created_at')])) if result.data else []
            return sorted(dates, reverse=True)
        except Exception as e:
            logger.error(f"Error getting financial dates for {ticker}: {e}")
            return []

# Global database instance with safe initialization
try:
    db = Database()
except KeyboardInterrupt:
    logger.warning("Database initialization interrupted")
    db = None
except Exception as e:
    logger.error(f"Database initialization failed: {e}")
    db = None

# Ensure db object exists even if initialization failed
if db is None:
    class MockDatabase:
        def __init__(self):
            self.client = None
        def __getattr__(self, name):
            return lambda *args, **kwargs: None
    db = MockDatabase()