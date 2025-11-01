from apscheduler.schedulers.background import BackgroundScheduler
from weekly_market_report import send_weekly_report, is_weekend
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

class WeekendScheduler:
    def __init__(self):
        self.scheduler = BackgroundScheduler()
        self.setup_weekend_jobs()
    
    def setup_weekend_jobs(self):
        """Setup weekend-only market report jobs"""
        
        # Saturday market report at 9 AM IST
        self.scheduler.add_job(
            func=self.send_weekend_report,
            trigger="cron",
            day_of_week='sat',
            hour=9,
            minute=0,
            timezone='Asia/Kolkata',
            id='saturday_report',
            max_instances=1
        )
        
        # Sunday market report at 10 AM IST
        self.scheduler.add_job(
            func=self.send_weekend_report,
            trigger="cron",
            day_of_week='sun',
            hour=10,
            minute=0,
            timezone='Asia/Kolkata',
            id='sunday_report',
            max_instances=1
        )
    
    def send_weekend_report(self):
        """Send market report only on weekends"""
        try:
            if is_weekend():
                logger.info("Weekend detected - sending Friday-to-Friday market report")
                send_weekly_report()
            else:
                logger.info("Not weekend - skipping market report")
        except Exception as e:
            logger.error(f"Weekend market report failed: {e}")
    
    def start(self):
        """Start the weekend scheduler"""
        if not self.scheduler.running:
            self.scheduler.start()
            logger.info("Weekend scheduler started (Saturday 9AM, Sunday 10AM IST)")
    
    def stop(self):
        """Stop the scheduler"""
        if self.scheduler.running:
            self.scheduler.shutdown()
            logger.info("Weekend scheduler stopped")

# Global instance
weekend_scheduler = WeekendScheduler()