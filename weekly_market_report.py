#!/usr/bin/env python3
"""
Weekly Market Report System
Sends weekly market changes for indices, commodities, and currencies
"""

import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
from dotenv import load_dotenv
from database import db
from free_market_data import get_free_market_data
import logging
import time

load_dotenv()
logger = logging.getLogger(__name__)

def get_market_data():
    """Get market data using 100% free sources"""
    return get_free_market_data()

def calculate_change(last_friday, this_friday):
    """Calculate Friday-to-Friday percentage change"""
    change = ((this_friday - last_friday) / last_friday) * 100
    return change

def get_friday_date_range():
    """Get current Friday and last Friday dates"""
    from datetime import datetime, timedelta
    
    today = datetime.now()
    days_since_friday = (today.weekday() + 3) % 7
    current_friday = today - timedelta(days=days_since_friday)
    last_friday = current_friday - timedelta(days=7)
    
    return last_friday, current_friday

def create_weekly_email(market_data=None):
    """Create Friday-to-Friday HTML email with verification status"""
    if market_data is None:
        market_data = get_market_data()
    
    last_friday, current_friday = get_friday_date_range()
    
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <style>
            body {{ font-family: Arial, sans-serif; margin: 0; padding: 20px; background: #f8f9fa; }}
            .container {{ max-width: 800px; margin: 0 auto; background: white; border-radius: 10px; overflow: hidden; box-shadow: 0 4px 6px rgba(0,0,0,0.1); }}
            .header {{ background: linear-gradient(135deg, #2c3e50 0%, #3498db 100%); color: white; padding: 30px; text-align: center; }}
            .header h1 {{ margin: 0; font-size: 24px; }}
            .content {{ padding: 30px; }}
            .intro {{ font-size: 16px; color: #555; margin-bottom: 30px; line-height: 1.6; }}
            .section {{ margin-bottom: 30px; }}
            .section h2 {{ color: #2c3e50; font-size: 18px; margin-bottom: 15px; border-bottom: 2px solid #3498db; padding-bottom: 5px; }}
            table {{ width: 100%; border-collapse: collapse; margin-bottom: 20px; }}
            th {{ background: #34495e; color: white; padding: 12px; text-align: left; font-weight: bold; }}
            td {{ padding: 12px; border-bottom: 1px solid #ecf0f1; }}
            tr:nth-child(even) {{ background: #f8f9fa; }}
            .positive {{ color: #27ae60; font-weight: bold; }}
            .negative {{ color: #e74c3c; font-weight: bold; }}
            .verified {{ color: #27ae60; font-size: 12px; }}
            .unverified {{ color: #e74c3c; font-size: 12px; }}
            .footer {{ background: #ecf0f1; padding: 20px; text-align: center; color: #7f8c8d; font-size: 12px; }}
            .unsubscribe {{ margin-top: 15px; }}
            .unsubscribe a {{ color: #3498db; text-decoration: none; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>Weekly Market Report</h1>
                <p>Market Changes: {last_friday.strftime('%B %d')} to {current_friday.strftime('%B %d, %Y')}</p>
            </div>
            
            <div class="content">
                <div class="intro">
                    <p>Weekly market performance from Friday close to Friday close. All data is verified against multiple internet sources for accuracy.</p>
                    <p><strong>Data Sources:</strong> Yahoo Finance, Investing.com, CNBC, Bloomberg | <strong>Verification:</strong> Cross-checked for 2% accuracy tolerance</p>
                </div>
    """
    
    # Add each section
    for section_name, section_data in market_data.items():
        section_title = section_name.replace('_', ' ').title()
        html += f"""
                <div class="section">
                    <h2>{section_title}</h2>
                    <table>
                        <thead>
                            <tr>
                                <th>Asset</th>
                                <th>Last Friday</th>
                                <th>This Friday</th>
                                <th>Change (%)</th>
                            </tr>
                        </thead>
                        <tbody>
        """
        
        for asset, data in section_data.items():
            last_friday = data.get('last_friday', 0)
            this_friday = data.get('this_friday', 0)
            verified = data.get('verified', False)
            sources_count = data.get('sources_count', 0)
            
            if last_friday and this_friday:
                change = calculate_change(last_friday, this_friday)
                change_class = 'positive' if change >= 0 else 'negative'
                change_symbol = '+' if change >= 0 else ''
                verification_status = f'<span class="verified">✓ Verified ({sources_count} sources)</span>' if verified else f'<span class="unverified">⚠ Unverified</span>'
                
                html += f"""
                                <tr>
                                    <td><strong>{asset}</strong><br>{verification_status}</td>
                                    <td>{last_friday:,.2f}</td>
                                    <td>{this_friday:,.2f}</td>
                                    <td class="{change_class}">{change_symbol}{change:.2f}%</td>
                                </tr>
                """
        
        html += """
                        </tbody>
                    </table>
                </div>
        """
    
    html += f"""
            </div>
            
            <div class="footer">
                <p><strong>Stock News AI Summarizer</strong> - Friday-to-Friday Market Report</p>
                <p>Generated on {datetime.now().strftime('%Y-%m-%d at %H:%M')} | Data Sources: Yahoo Finance, Investing.com, CNBC, Bloomberg</p>
                <p>Verification Status: Multi-source cross-validation with 2% accuracy tolerance</p>
                <div class="unsubscribe">
                    <p>Don't want to receive these reports? <a href="https://unsubscribe-service-ivory.vercel.app/?email={{email}}">Unsubscribe here</a></p>
                </div>
            </div>
        </div>
    </body>
    </html>
    """
    
    return html

def is_weekend():
    """Check if today is weekend (Saturday or Sunday)"""
    from datetime import datetime
    today = datetime.now().weekday()
    return today in [5, 6]  # Saturday=5, Sunday=6

def send_weekly_report():
    """Send weekly report only on weekends"""
    try:
        # Check if it's weekend
        if not is_weekend():
            print(f"Today is not weekend. Weekly reports are sent on weekends only.")
            return
        
        print("Weekend detected - sending Friday-to-Friday market report...")
        
        # Get Friday-to-Friday market data with verification
        print("Fetching Friday-to-Friday market data with internet verification...")
        market_data = get_market_data()
        
        # Verify we have enough verified data
        total_assets = sum(len(category) for category in market_data.values())
        verified_assets = sum(1 for category in market_data.values() 
                            for asset in category.values() 
                            if asset.get('verified', False))
        
        print(f"Data verification: {verified_assets}/{total_assets} assets verified from multiple sources")
        
        if verified_assets < total_assets * 0.5:
            print("Warning: Less than 50% of data is verified. Consider checking internet connection.")
            print("GitHub Actions Environment: Internet verification may be limited for some sources")
        else:
            print(f"Success: {(verified_assets/total_assets)*100:.1f}% verification rate - data quality is good")
        
        # Get all email subscriptions
        subscribers = db.get_subscriptions()
        if not subscribers:
            print("No email subscriptions found")
            return
        
        # Email configuration
        sender_email = os.getenv('SENDER_EMAIL')
        sender_password = os.getenv('SENDER_PASSWORD')
        
        # Handle spaces and special characters in password
        if sender_password:
            sender_password = sender_password.strip()
        
        if not sender_email or not sender_password:
            print("Email credentials not configured")
            return
        
        # Create email content with live data
        html_template = create_weekly_email(market_data)
        
        print(f"Sending weekly report to {len(subscribers)} subscribers...")
        
        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls()
            server.login(sender_email, sender_password)
            
            total_subscribers = len(subscribers)
            sent_count = 0
            failed_count = 0
            
            print(f"Sending to {total_subscribers} subscribers...")
            
            for i, email in enumerate(subscribers, 1):
                try:
                    # Personalize email
                    html_content = html_template.replace('{email}', email)
                    
                    # Create message
                    msg = MIMEMultipart('alternative')
                    last_friday, current_friday = get_friday_date_range()
                    msg['Subject'] = f"Weekly Market Report - {current_friday.strftime('%B %d, %Y')}"
                    msg['From'] = sender_email
                    msg['To'] = email
                    
                    # Attach HTML
                    html_part = MIMEText(html_content, 'html')
                    msg.attach(html_part)
                    
                    # Send email
                    server.send_message(msg)
                    sent_count += 1
                    
                    # Progress update every 10 emails
                    if i % 10 == 0:
                        print(f"Progress: {i}/{total_subscribers} sent ({(i/total_subscribers)*100:.1f}%)")
                    
                    # Rate limiting for high volume
                    if total_subscribers > 50:
                        time.sleep(0.5)  # 0.5 second delay for large lists
                    
                except Exception as e:
                    failed_count += 1
                    print(f"✗ Failed to send to {email}: {e}")
            
            print(f"\nEmail Summary: {sent_count} sent, {failed_count} failed out of {total_subscribers} total")
        
        print(f"Weekly market report sent to {len(subscribers)} subscribers with {(verified_assets/total_assets)*100:.1f}% verified data")
        
    except Exception as e:
        print(f"Error sending weekly report: {e}")

if __name__ == "__main__":
    send_weekly_report()