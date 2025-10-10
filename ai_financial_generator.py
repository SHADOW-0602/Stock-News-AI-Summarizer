import json
import logging

logger = logging.getLogger(__name__)

def generate_ai_financial_data(ticker, statement, period):
    """Generate realistic financial data using Gemini AI"""
    try:
        from app import client, GEMINI_API_KEY
        
        if GEMINI_API_KEY == 'your-gemini-api-key':
            logger.error("Gemini API key not configured")
            return []
        
        prompt = f"""
        Generate realistic {statement} statement data for {ticker} for the last 5 {period} periods.
        
        Requirements:
        - Use realistic financial ratios for a public company
        - Show logical progression over time periods
        - Include all standard financial statement line items
        - Use proper accounting terminology
        - Return as JSON array with fiscalDateEnding, reportedCurrency, and financial metrics
        
        Statement type: {statement.upper()}
        Period: {period.upper()}
        
        For INCOME statement include: totalRevenue, grossProfit, operatingIncome, netIncome, ebitda, eps
        For BALANCE sheet include: totalAssets, totalCurrentAssets, totalLiabilities, totalShareholderEquity, cashAndCashEquivalentsAtCarryingValue
        For CASHFLOW include: operatingCashflow, cashflowFromInvestment, cashflowFromFinancing, changeInCashAndCashEquivalents
        
        Return only valid JSON array, no explanations.
        """
        
        response = client.models.generate_content(
            model='gemini-2.5-pro',
            contents=prompt
        )
        
        # Parse JSON response
        json_text = response.text.strip()
        if json_text.startswith('```json'):
            json_text = json_text[7:-3]
        elif json_text.startswith('```'):
            json_text = json_text[3:-3]
        
        reports = json.loads(json_text)
        logger.info(f"Generated AI financial data for {ticker}: {len(reports)} reports")
        return reports
        
    except Exception as e:
        logger.error(f"AI financial generation error for {ticker}: {e}")
        return []