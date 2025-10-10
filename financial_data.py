"""Financial statements data collection and storage"""

import logging
from datetime import datetime
from database import db

logger = logging.getLogger(__name__)

class FinancialData:
    def __init__(self):
        pass
    
    def get_financial_statements(self, ticker):
        """Get financial statements using Yahoo Finance and store in database"""
        try:
            import yfinance as yf
            stock = yf.Ticker(ticker)
            
            # Get all financial statements
            statements = {
                'income': {'quarterly': stock.quarterly_financials, 'annual': stock.financials},
                'balance': {'quarterly': stock.quarterly_balance_sheet, 'annual': stock.balance_sheet},
                'cashflow': {'quarterly': stock.quarterly_cashflow, 'annual': stock.cashflow}
            }
            
            for statement_type, periods in statements.items():
                for period, df in periods.items():
                    if not df.empty:
                        self._store_yahoo_data(ticker, statement_type, period, df)
                        
            logger.info(f"Yahoo Finance data collection completed for {ticker}")
            
        except Exception as e:
            logger.error(f"Error collecting financial data for {ticker}: {e}")
    
    def _store_yahoo_data(self, ticker, statement_type, period, df):
        """Store Yahoo Finance data in database"""
        if not db.client or df.empty:
            return
            
        for date in df.columns:
            fiscal_date = date.strftime('%Y-%m-%d')
            
            # Convert DataFrame row to dictionary
            report = {'fiscalDateEnding': fiscal_date}
            for metric in df.index:
                value = df.loc[metric, date]
                # Check for NaN using pandas isna
                import pandas as pd
                if not pd.isna(value):
                    report[str(metric)] = float(value) if isinstance(value, (int, float)) else str(value)
            
            try:
                db.save_financial_statement(ticker, statement_type, period, fiscal_date, report)
                logger.info(f"Stored Yahoo {statement_type} {period} data for {ticker} ({fiscal_date})")
            except Exception as e:
                logger.error(f"Failed to store Yahoo {statement_type} for {ticker}: {e}")
    
    def get_stored_financials(self, ticker):
        """Get stored financial data for ticker"""
        if not db.client:
            return []
        
        try:
            result = db.client.table('financial_statements').select('*').eq('ticker', ticker).order('fiscal_date', desc=True).execute()
            if result.data:
                import json
                for item in result.data:
                    if isinstance(item.get('data'), str):
                        item['data'] = json.loads(item['data'])
                return result.data
            return []
        except Exception as e:
            logger.error(f"Error retrieving financial data for {ticker}: {e}")
            return []

# Global instance
financial_data = FinancialData()