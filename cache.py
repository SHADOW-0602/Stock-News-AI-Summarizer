"""Redis cache operations"""

import os
import json
import logging
import requests
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

# Cache durations
CACHE_DURATION = 8 * 3600  # 8 hours
SUMMARY_CACHE_DURATION = 6 * 3600  # 6 hours

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
                    return result.encode('utf-8')
            return None
        except:
            return None
    
    def setex(self, key, seconds, value):
        try:
            string_value = value.decode('utf-8') if isinstance(value, bytes) else value
            headers = {**self.headers, 'Content-Type': 'text/plain'}
            response = requests.post(f'{self.url}/setex/{key}/{seconds}', 
                                   headers=headers, 
                                   data=string_value)
            return response.status_code == 200
        except Exception as e:
            logger.debug(f"Cache setex error: {e}")
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

class Cache:
    def __init__(self):
        self.redis_client = None
        self.fallback_news_cache = {}
        self.fallback_summary_cache = {}
        self._init_redis()
    
    def _init_redis(self):
        """Initialize Redis client"""
        url = os.getenv('UPSTASH_REDIS_REST_URL')
        token = os.getenv('UPSTASH_REDIS_REST_TOKEN')
        
        try:
            if url and token:
                self.redis_client = UpstashRedis(url, token)
                # Test connection
                self.redis_client.setex('test', 10, b'test')
                logger.info("Upstash Redis connection successful")
            else:
                logger.warning("Upstash Redis credentials not found")
        except Exception as e:
            logger.warning(f"Upstash Redis connection failed: {e}")
            self.redis_client = None
    
    def get_news(self, ticker):
        """Get cached news"""
        try:
            if self.redis_client:
                cached_data = self.redis_client.get(f"news:{ticker}")
                if cached_data:
                    cache_entry = json.loads(cached_data.decode('utf-8'))
                    logger.debug(f"Using cached news for {ticker}")
                    return cache_entry['data'], cache_entry['sources']
            else:
                # Fallback to in-memory cache
                if ticker in self.fallback_news_cache:
                    cache_entry = self.fallback_news_cache[ticker]
                    if (datetime.now() - cache_entry['timestamp']).total_seconds() < CACHE_DURATION:
                        logger.debug(f"Using fallback cached news for {ticker}")
                        return cache_entry['data'], cache_entry['sources']
        except Exception as e:
            logger.debug(f"Cache read error for {ticker}: {e}")
        
        return None, None
    
    def set_news(self, ticker, articles, sources):
        """Cache news articles"""
        try:
            cache_data = {
                'data': articles,
                'timestamp': datetime.now().isoformat(),
                'sources': sources
            }
            
            if self.redis_client:
                self.redis_client.setex(f"news:{ticker}", CACHE_DURATION, json.dumps(cache_data))
                logger.debug(f"Cached {len(articles)} articles for {ticker}")
            else:
                self.fallback_news_cache[ticker] = {
                    'data': articles,
                    'timestamp': datetime.now(),
                    'sources': sources
                }
                logger.debug(f"Cached {len(articles)} articles for {ticker} in memory")
        except Exception as e:
            logger.debug(f"Cache write error for {ticker}: {e}")
    
    def get_summary(self, ticker):
        """Get cached summary"""
        try:
            if self.redis_client:
                cached_data = self.redis_client.get(f"summary:{ticker}")
                if cached_data:
                    cache_entry = json.loads(cached_data.decode('utf-8'))
                    logger.debug(f"Using cached summary for {ticker}")
                    return cache_entry['summary']
            else:
                if ticker in self.fallback_summary_cache:
                    cache_entry = self.fallback_summary_cache[ticker]
                    if (datetime.now() - cache_entry['timestamp']).total_seconds() < SUMMARY_CACHE_DURATION:
                        logger.debug(f"Using fallback cached summary for {ticker}")
                        return cache_entry['summary']
        except Exception as e:
            logger.debug(f"Summary cache read error for {ticker}: {e}")
        
        return None
    
    def set_summary(self, ticker, summary_data):
        """Cache summary data"""
        try:
            cache_data = {
                'summary': summary_data,
                'timestamp': datetime.now().isoformat()
            }
            
            if self.redis_client:
                self.redis_client.setex(f"summary:{ticker}", SUMMARY_CACHE_DURATION, json.dumps(cache_data))
                logger.debug(f"Cached summary for {ticker}")
            else:
                self.fallback_summary_cache[ticker] = {
                    'summary': summary_data,
                    'timestamp': datetime.now()
                }
                logger.debug(f"Cached summary for {ticker} in memory")
        except Exception as e:
            logger.debug(f"Summary cache write error for {ticker}: {e}")
    
    def clear(self, ticker):
        """Clear all cache for ticker"""
        try:
            if self.redis_client:
                self.redis_client.delete(f"news:{ticker}", f"summary:{ticker}", f"ml:{ticker}")
                logger.info(f"Cleared Redis cache for {ticker}")
            else:
                if ticker in self.fallback_news_cache:
                    del self.fallback_news_cache[ticker]
                if ticker in self.fallback_summary_cache:
                    del self.fallback_summary_cache[ticker]
                logger.info(f"Cleared memory cache for {ticker}")
        except Exception as e:
            logger.error(f"Cache clear error for {ticker}: {e}")
    
    def cleanup_expired(self):
        """Clean up expired cache entries"""
        if not self.redis_client:
            current_time = datetime.now()
            
            # Clean news cache
            expired_news = [ticker for ticker, data in self.fallback_news_cache.items() 
                           if (current_time - data['timestamp']).total_seconds() > CACHE_DURATION]
            for ticker in expired_news:
                del self.fallback_news_cache[ticker]
            
            # Clean summary cache
            expired_summaries = [ticker for ticker, data in self.fallback_summary_cache.items()
                                if (current_time - data['timestamp']).total_seconds() > SUMMARY_CACHE_DURATION]
            for ticker in expired_summaries:
                del self.fallback_summary_cache[ticker]
            
            if expired_news or expired_summaries:
                logger.info(f"Cleaned {len(expired_news)} news + {len(expired_summaries)} cache entries")
        else:
            logger.debug("Redis handles cache expiry automatically")
    
    def get_status(self):
        """Get cache status"""
        status = {
            'cache_type': 'Upstash' if self.redis_client else 'Memory',
            'upstash_configured': bool(os.getenv('UPSTASH_REDIS_REST_URL') and os.getenv('UPSTASH_REDIS_REST_TOKEN')),
            'connection_test': False,
            'test_result': None
        }
        
        if self.redis_client:
            try:
                test_key = 'cache_test'
                test_value = {'test': 'data', 'timestamp': datetime.now().isoformat()}
                
                write_success = self.redis_client.setex(test_key, 60, json.dumps(test_value))
                read_data = self.redis_client.get(test_key)
                read_success = read_data is not None
                
                if read_success:
                    status['test_result'] = 'SUCCESS: Write and read operations working'
                else:
                    status['test_result'] = 'FAILED: Could not read test data'
                
                status['connection_test'] = write_success and read_success
                self.redis_client.delete(test_key)
                
            except Exception as e:
                status['test_result'] = f'ERROR: {str(e)}'
                status['connection_test'] = False
        else:
            status['test_result'] = 'Using fallback memory cache'
            status['connection_test'] = True
        
        status['cache_durations'] = {
            'news_cache': f'{CACHE_DURATION // 3600} hours ({CACHE_DURATION} seconds)',
            'summary_cache': f'{SUMMARY_CACHE_DURATION // 3600} hours ({SUMMARY_CACHE_DURATION} seconds)'
        }
        
        return status

# Global cache instance
cache = Cache()