#!/usr/bin/env python3
"""
Simple Email Generator for Stock Summaries
Assumes Flask app is already running on port 8080
"""

import time
import requests
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
import os
import re
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configuration
TICKERS = [
    'TSLA', 'AMZN', 'MRNA', 'SNAP', 'DOCU', 'ADBE', 'JD', 'REGN', 
    'VRTX', 'FTNT', 'OPRA', 'CMCSA', 'YELP', 'PINS', 'INFY', 'CORT', 'FANG', 'TGT'
]
EMAIL_TO = 'himanshu_somani@ymail.com'
BASE_URL = 'http://127.0.0.1:8080'



def process_ticker(ticker):
    """Process a single ticker"""
    try:
        print(f"Processing {ticker}...")
        
        # Add ticker
        requests.post(f'{BASE_URL}/api/tickers', json={'ticker': ticker}, timeout=30)
        
        # Generate fresh summary
        refresh_response = requests.get(f'{BASE_URL}/api/refresh/{ticker}', timeout=300)
        
        if refresh_response.status_code == 200:
            # Get summary
            summary_response = requests.get(f'{BASE_URL}/api/summary/{ticker}', timeout=60)
            
            if summary_response.status_code == 200:
                data = summary_response.json()
                if data.get('current_summary'):
                    print(f"✅ {ticker} completed")
                    return data['current_summary']
        
        print(f"⚠️ {ticker} - no summary generated")
        return {'summary': f'Summary unavailable for {ticker}'}
        
    except Exception as e:
        print(f"❌ {ticker} failed: {e}")
        return {'summary': f'Processing error for {ticker}'}

def generate_all_summaries():
    """Generate summaries for all tickers"""
    print(f"\nProcessing {len(TICKERS)} tickers...")
    
    summaries = {}
    start_time = time.time()
    
    for i, ticker in enumerate(TICKERS):
        print(f"\n[{i+1}/{len(TICKERS)}] {ticker}")
        
        summary = process_ticker(ticker)
        summaries[ticker] = summary
        
        # Progress update
        elapsed = time.time() - start_time
        avg_time = elapsed / (i + 1)
        remaining = len(TICKERS) - (i + 1)
        eta = (remaining * avg_time) / 60
        
        print(f"Progress: {i+1}/{len(TICKERS)} | ETA: {eta:.1f} minutes")
    
    total_time = time.time() - start_time
    print(f"\n✅ All tickers processed in {total_time/60:.1f} minutes")
    
    return summaries

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

def send_email(summaries):
    """Send email with all summaries"""
    try:
        sender_email = os.getenv('SENDER_EMAIL')
        sender_password = os.getenv('SENDER_PASSWORD')
        
        if not sender_email or not sender_password:
            print("❌ Email credentials not found in .env file")
            return False
        
        print(f"Sending email to {EMAIL_TO}...")
        
        # Create email
        msg = MIMEMultipart()
        msg['From'] = sender_email
        msg['To'] = EMAIL_TO
        msg['Subject'] = f"Daily Stock Analysis Report - {len(summaries)} Tickers"
        
        # Email body
        body = f"""Daily Stock Analysis Report
{datetime.now().strftime('%B %d, %Y - %I:%M %p IST')}

{'='*50}

"""
        
        for ticker, data in summaries.items():
            summary = data.get('summary', 'No summary available')
            what_changed = data.get('what_changed', '')
            
            # Clean HTML tags and formatting
            clean_summary = clean_html_tags(summary)
            clean_summary = clean_summary.replace('**', '').replace('*', '').replace('#', '')
            
            body += f"""TICKER: {ticker}

AI Analyst Commentary
Here is a concise trading analysis for {ticker}.

{clean_summary}"""
            
            if what_changed and 'unavailable' not in what_changed.lower():
                clean_what_changed = clean_html_tags(what_changed)
                clean_what_changed = clean_what_changed.replace('**', '').replace('*', '').replace('#', '')
                body += f"""

WHAT CHANGED TODAY:
{clean_what_changed}"""
            
            body += f"""

Last updated: {datetime.now().strftime('%m/%d/%Y')}

{'-'*50}

"""
        
        body += f"""Stock News AI Summarizer - Report
Generated: {datetime.now().strftime('%Y-%m-%d at %H:%M IST')}"""
        
        msg.attach(MIMEText(body, 'plain'))
        
        # Send email
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(sender_email, sender_password)
        server.send_message(msg)
        server.quit()
        
        print(f"✅ Email sent successfully to {EMAIL_TO}")
        return True
        
    except Exception as e:
        print(f"❌ Email failed: {e}")
        return False



def main():
    """Main function"""
    print("Stock Summary Email Generator")
    print("=" * 40)
    
    # Check if Flask app is running
    try:
        response = requests.get(BASE_URL, timeout=5)
        if response.status_code != 200:
            print("ERROR: Flask app not running")
            print("Please start Flask app first: python app.py")
            return
    except:
        print("ERROR: Flask app not running")
        print("Please start Flask app first: python app.py")
        return
    
    print("SUCCESS: Flask app is running")
    
    # Process all tickers
    response = input(f"\nProceed with all {len(TICKERS)} tickers? (y/n): ")
    if response.lower() == 'y':
        summaries = generate_all_summaries()
        send_email(summaries)
    else:
        print("Operation cancelled.")

if __name__ == "__main__":
    main()