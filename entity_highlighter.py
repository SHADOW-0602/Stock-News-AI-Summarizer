import re

class EntityHighlighter:
    def __init__(self):
        # Financial metrics patterns
        self.financial_patterns = [
            (r'\$[\d,]+\.?\d*[BMK]?', 'financial-amount'),  # $1.2B, $500M, $50K
            (r'\b\d+\.?\d*%', 'percentage'),  # 15%, 2.5%
            (r'\b\d+\.?\d*[BMK]\b', 'large-number'),  # 1.5B, 500M, 50K
            (r'\bQ[1-4]\s+\d{4}', 'quarter'),  # Q3 2024
            (r'\bFY\s*\d{4}', 'fiscal-year'),  # FY 2024
        ]
        
        # Company/People patterns
        self.entity_patterns = [
            (r'\b[A-Z]{2,5}\b', 'ticker-symbol'),  # AAPL, MSFT
            (r'\bCEO\b|\bCFO\b|\bCTO\b', 'executive-title'),
            (r'\b[A-Z][a-z]+\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?\b', 'person-name'),
        ]
        
        # Important terms
        self.important_terms = [
            'earnings', 'revenue', 'profit', 'loss', 'guidance', 'outlook',
            'acquisition', 'merger', 'partnership', 'IPO', 'dividend',
            'buyback', 'split', 'FDA', 'approval', 'patent', 'lawsuit'
        ]
    
    def highlight_entities(self, text):
        """Highlight key entities in text with HTML spans"""
        highlighted = text
        
        # Highlight financial metrics
        for pattern, css_class in self.financial_patterns:
            highlighted = re.sub(
                pattern, 
                f'<span class="highlight-{css_class}">\\g<0></span>', 
                highlighted, 
                flags=re.IGNORECASE
            )
        
        # Highlight important terms
        for term in self.important_terms:
            pattern = f'\\b{re.escape(term)}\\b'
            highlighted = re.sub(
                pattern,
                f'<span class="highlight-term">\\g<0></span>',
                highlighted,
                flags=re.IGNORECASE
            )
        
        # Highlight ticker symbols (but avoid over-highlighting)
        ticker_pattern = r'\b[A-Z]{2,5}\b(?![^<]*>)'  # Not inside HTML tags
        highlighted = re.sub(
            ticker_pattern,
            '<span class="highlight-ticker">\\g<0></span>',
            highlighted
        )
        
        return highlighted