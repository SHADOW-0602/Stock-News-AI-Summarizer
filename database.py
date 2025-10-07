"""Supabase database operations"""

import os
import logging
from supabase import create_client, Client
from datetime import datetime

logger = logging.getLogger(__name__)

class Database:
    def __init__(self):
        self.client = None
        # Ensure environment variables are loaded
        from dotenv import load_dotenv
        load_dotenv()
        self._init_client()
    
    def _init_client(self):
        """Initialize Supabase client"""
        url = os.getenv('SUPABASE_URL')
        key = os.getenv('SUPABASE_ANON_KEY')
        
        logger.debug(f"Supabase URL: {url[:30]}..." if url else "No URL")
        logger.debug(f"Supabase Key: {key[:30]}..." if key else "No Key")
        
        try:
            if url and key and url != 'your-supabase-url':
                self.client: Client = create_client(url, key)
                logger.info("Supabase client initialized successfully")
            else:
                logger.error(f"Supabase credentials not configured properly. URL: {bool(url)}, Key: {bool(key)}")
        except Exception as e:
            logger.error(f"Failed to initialize Supabase: {e}")
    
    def test_connection(self):
        """Test database connection"""
        try:
            if not self.client:
                logger.error("No Supabase client available")
                return False
            result = self.client.table('tickers').select('*').limit(1).execute()
            logger.info("Supabase connection verified")
            return True
        except Exception as e:
            logger.warning(f"Supabase connection test failed: {e}")
            return False
    
    def get_tickers(self):
        """Get all tickers"""
        if not self.client:
            logger.error("Database client not initialized")
            return []
        try:
            result = self.client.table('tickers').select('symbol').order('symbol', desc=False).execute()
            tickers = [row['symbol'] for row in result.data] if result.data else []
            logger.debug(f"Retrieved {len(tickers)} tickers from database")
            return tickers
        except Exception as e:
            logger.error(f"Error getting tickers: {e}")
            # Check if it's a table not found error
            if 'relation "tickers" does not exist' in str(e) or 'table "tickers" does not exist' in str(e):
                logger.error("Tickers table does not exist. Please run the SQL migration in Supabase.")
            return []
    
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
        """Save daily summary"""
        if not self.client:
            return
        
        import json
        
        self.client.table('daily_summaries').upsert({
            'ticker': ticker,
            'date': datetime.now().date().isoformat(),
            'summary': summary_data['summary'],
            'articles_used': json.dumps(articles_used),
            'what_changed': summary_data['what_changed']
        }, on_conflict='ticker,date').execute()
    
    def get_summary(self, ticker):
        """Get latest summary"""
        if not self.client:
            return None
        
        try:
            result = self.client.table('daily_summaries').select(
                'date, summary, articles_used, what_changed, risk_factors'
            ).eq('ticker', ticker).order('date', desc=True).limit(1).execute()
            
            if result.data:
                import json
                row = result.data[0]
                return {
                    'date': row['date'],
                    'summary': row['summary'],
                    'articles_used': json.loads(row['articles_used']),
                    'what_changed': row.get('what_changed', ''),
                    'risk_factors': row.get('risk_factors', '')
                }
        except Exception as e:
            logger.error(f"Error getting summary for {ticker}: {e}")
        
        return None
    
    def get_history(self, ticker, limit=7):
        """Get summary history"""
        if not self.client:
            return []
        
        try:
            result = self.client.table('daily_summaries').select(
                'date, what_changed'
            ).eq('ticker', ticker).order('date', desc=True).limit(limit).execute()
            
            return [{'date': row['date'], 'what_changed': row['what_changed']} 
                   for row in result.data] if result.data else []
        except Exception as e:
            logger.error(f"Error getting history for {ticker}: {e}")
            return []
    
    def get_recent_articles(self, ticker, limit=10):
        """Get recent articles for sentiment analysis"""
        if not self.client:
            return []
        
        try:
            result = self.client.table('news_articles').select(
                'title, content'
            ).eq('ticker', ticker).order('date', desc=True).limit(limit).execute()
            
            return result.data if result.data else []
        except Exception as e:
            logger.error(f"Error getting recent articles for {ticker}: {e}")
            return []
    
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
        """Save logo URL to database"""
        if not self.client:
            return
        
        try:
            self.client.table('company_logos').upsert({
                'ticker': ticker,
                'logo_url': logo_url,
                'company_name': company_name or ticker,
                'updated_at': datetime.now().isoformat()
            }, on_conflict='ticker').execute()
            
            logger.debug(f"Saved logo for {ticker}: {logo_url}")
        except Exception as e:
            logger.error(f"Error saving logo for {ticker}: {e}")
    
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

# Global database instance
db = Database()