import yfinance as yf
import numpy as np
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import LinearRegression
from sklearn.svm import SVR
from sklearn.model_selection import cross_val_score, GridSearchCV
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import Pipeline
from textblob import TextBlob
import logging

logger = logging.getLogger(__name__)

class MLAnalyzer:
    def __init__(self):
        self.models = {
            'rf': RandomForestRegressor(random_state=42),
            'lr': LinearRegression(),
            'svr': SVR()
        }
        self.best_model = None
        self.scaler = StandardScaler()
    
    def get_price_forecast(self, ticker, days=5):
        """Robust ML price forecast with model selection and cross-validation"""
        try:
            # Get historical data
            stock = yf.Ticker(ticker)
            hist = stock.history(period="6mo")
            
            if len(hist) < 50:
                return None
            
            # Enhanced feature engineering
            hist['MA5'] = hist['Close'].rolling(5).mean()
            hist['MA20'] = hist['Close'].rolling(20).mean()
            hist['MA50'] = hist['Close'].rolling(50).mean()
            hist['Volume_MA'] = hist['Volume'].rolling(10).mean()
            hist['Price_Change'] = hist['Close'].pct_change()
            hist['Volume_Change'] = hist['Volume'].pct_change()
            hist['High_Low_Ratio'] = hist['High'] / hist['Low']
            hist['Price_Volume'] = hist['Close'] * hist['Volume']
            
            # Technical indicators
            hist['RSI'] = self._calculate_rsi(hist['Close'])
            hist['BB_Upper'], hist['BB_Lower'] = self._calculate_bollinger_bands(hist['Close'])
            
            # Prepare training data
            hist = hist.dropna()
            features = ['Close', 'Volume', 'MA5', 'MA20', 'MA50', 'Volume_MA', 
                       'Price_Change', 'Volume_Change', 'High_Low_Ratio', 'Price_Volume', 'RSI']
            
            X = hist[features].values[:-1]
            y = hist['Close'].values[1:]
            
            # Find best model using cross-validation
            best_score = -np.inf
            best_model_name = 'rf'
            
            for name, model in self.models.items():
                if name == 'svr':
                    # SVR needs scaling
                    pipeline = Pipeline([('scaler', StandardScaler()), ('model', model)])
                else:
                    pipeline = model
                
                # Cross-validation
                scores = cross_val_score(pipeline, X, y, cv=5, scoring='neg_mean_squared_error')
                avg_score = scores.mean()
                
                if avg_score > best_score:
                    best_score = avg_score
                    best_model_name = name
                    self.best_model = pipeline
            
            # Hyperparameter tuning for best model
            if best_model_name == 'rf':
                param_grid = {'n_estimators': [50, 100], 'max_depth': [5, 10, None]}
                grid_search = GridSearchCV(RandomForestRegressor(random_state=42), param_grid, cv=3)
                grid_search.fit(X, y)
                self.best_model = grid_search.best_estimator_
            
            # Train final model
            self.best_model.fit(X, y)
            
            # Predict
            last_features = hist[features].iloc[-1].values.reshape(1, -1)
            prediction = self.best_model.predict(last_features)[0]
            current_price = hist['Close'].iloc[-1]
            
            # Calculate confidence based on cross-validation score
            confidence_score = abs(best_score)
            if confidence_score < 100:
                confidence = 'High'
            elif confidence_score < 500:
                confidence = 'Medium'
            else:
                confidence = 'Low'
            
            return {
                'current_price': round(current_price, 2),
                'predicted_price': round(prediction, 2),
                'change_percent': round((prediction - current_price) / current_price * 100, 2),
                'confidence': confidence,
                'model_used': best_model_name,
                'cv_score': round(best_score, 2),
                'timeframe': f'{days} days'
            }
            
        except Exception as e:
            logger.error(f"Price forecast error for {ticker}: {e}")
            return None
    
    def _calculate_rsi(self, prices, window=14):
        """Calculate RSI indicator"""
        delta = prices.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=window).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=window).mean()
        rs = gain / loss
        return 100 - (100 / (1 + rs))
    
    def _calculate_bollinger_bands(self, prices, window=20):
        """Calculate Bollinger Bands"""
        ma = prices.rolling(window).mean()
        std = prices.rolling(window).std()
        upper = ma + (std * 2)
        lower = ma - (std * 2)
        return upper, lower
    
    def analyze_sentiment(self, articles):
        """NLP sentiment analysis of news articles"""
        try:
            if not articles:
                return {'sentiment': 'Neutral', 'score': 0, 'confidence': 'Low'}
            
            sentiments = []
            for article in articles:
                text = f"{article.get('title', '')} {article.get('content', '')}"
                blob = TextBlob(text)
                sentiments.append(blob.sentiment.polarity)
            
            avg_sentiment = np.mean(sentiments)
            
            # Classify sentiment
            if avg_sentiment > 0.1:
                sentiment = 'Bullish'
            elif avg_sentiment < -0.1:
                sentiment = 'Bearish'
            else:
                sentiment = 'Neutral'
            
            return {
                'sentiment': sentiment,
                'score': round(avg_sentiment, 3),
                'confidence': 'High' if abs(avg_sentiment) > 0.2 else 'Medium',
                'articles_analyzed': len(articles)
            }
            
        except Exception as e:
            logger.error(f"Sentiment analysis error: {e}")
            return {'sentiment': 'Neutral', 'score': 0, 'confidence': 'Low'}