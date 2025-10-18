import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os
from dotenv import load_dotenv
import logging
from datetime import datetime

load_dotenv()

logger = logging.getLogger(__name__)

def clean_html_tags(text):
    """Remove HTML tags and convert to clean text"""
    import re
    if not text:
        return text
    
    # Remove HTML tags but keep the content
    text = re.sub(r'<span class="highlight-ticker">(.*?)</span>', r'\1', text)
    text = re.sub(r'<span class="highlight-term">(.*?)</span>', r'\1', text)
    text = re.sub(r'<[^>]+>', '', text)
    
    # Clean up HTML entities
    text = text.replace('&lt;', '<').replace('&gt;', '>').replace('&amp;', '&')
    text = text.replace('&quot;', '"').replace('&#39;', "'")
    
    return text

def send_summary_email(ticker, summary_data, recipient_email):
    """Send ticker summary via email"""
    try:
        sender_email = os.getenv('SENDER_EMAIL')
        sender_password = os.getenv('SENDER_PASSWORD')
        
        if not sender_email or not sender_password:
            logger.error("Email credentials not configured")
            return False
        
        # Create message
        msg = MIMEMultipart()
        msg['From'] = sender_email
        msg['To'] = recipient_email
        msg['Subject'] = f"{ticker} Stock Analysis Summary"
        
        # Clean HTML from summary content
        clean_summary = clean_html_tags(summary_data.get('summary', 'No summary available'))
        clean_what_changed = clean_html_tags(summary_data.get('what_changed', 'No changes detected'))
        
        # Email body
        body = f"""
Stock Analysis Summary for {ticker}

{clean_summary}

What Changed Today:
{clean_what_changed}

Generated: {summary_data.get('date', 'Unknown')}

---
Stock News AI Summarizer
        """
        
        msg.attach(MIMEText(body, 'plain'))
        
        # Send email
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(sender_email, sender_password)
        server.send_message(msg)
        server.quit()
        
        logger.info(f"Email sent successfully to {recipient_email} for {ticker}")
        return True
        
    except Exception as e:
        logger.error(f"Email send failed: {e}")
        return False

def send_all_tickers_email(recipient_email):
    """Send complete summary of all tickers in one email"""
    try:
        from database import db
        
        sender_email = os.getenv('SENDER_EMAIL')
        sender_password = os.getenv('SENDER_PASSWORD')
        
        if not sender_email or not sender_password:
            logger.error("Email credentials not configured")
            return False
        
        # Get all tickers
        tickers = db.get_tickers()
        if not tickers:
            return False
        
        # Create message
        msg = MIMEMultipart()
        msg['From'] = sender_email
        msg['To'] = recipient_email
        msg['Subject'] = f"Complete Stock Analysis - {len(tickers)} Tickers"
        
        # Build email body with all summaries
        body = f"Complete Stock Analysis Report\nGenerated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        body += "=" * 60 + "\n\n"
        
        for i, ticker in enumerate(tickers, 1):
            summary_data = db.get_summary(ticker)
            
            body += f"{i}. {ticker} ANALYSIS\n"
            body += "-" * 30 + "\n"
            
            if summary_data and summary_data.get('summary'):
                # Clean HTML tags from summary content
                clean_summary = clean_html_tags(summary_data['summary'])
                clean_what_changed = clean_html_tags(summary_data.get('what_changed', 'No changes'))
                
                body += f"{clean_summary}\n\n"
                body += f"What Changed: {clean_what_changed}\n"
                body += f"Last Updated: {summary_data.get('date', 'Unknown')}\n"
            else:
                body += "No analysis available\n"
            
            body += "\n" + "=" * 60 + "\n\n"
        
        body += "---\nStock News AI Summarizer"
        
        msg.attach(MIMEText(body, 'plain'))
        
        # Send email
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(sender_email, sender_password)
        server.send_message(msg)
        server.quit()
        
        logger.info(f"Complete summary email sent to {recipient_email} for {len(tickers)} tickers")
        return True
        
    except Exception as e:
        logger.error(f"Complete summary email failed: {e}")
        return False