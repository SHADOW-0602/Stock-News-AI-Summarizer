-- Create tables in Supabase Dashboard SQL Editor

-- Tickers table
CREATE TABLE IF NOT EXISTS tickers (
    id SERIAL PRIMARY KEY,
    symbol TEXT UNIQUE NOT NULL,
    added_date TIMESTAMP DEFAULT NOW()
);

-- News articles table  
CREATE TABLE IF NOT EXISTS news_articles (
    id SERIAL PRIMARY KEY,
    ticker TEXT NOT NULL,
    title TEXT NOT NULL,
    url TEXT,
    source TEXT NOT NULL,
    content TEXT,
    date TIMESTAMP DEFAULT NOW(),
    relevance_score REAL
);

-- Daily summaries table
CREATE TABLE IF NOT EXISTS daily_summaries (
    id SERIAL PRIMARY KEY,
    ticker TEXT NOT NULL,
    date DATE NOT NULL,
    summary TEXT NOT NULL,
    articles_used JSONB,
    what_changed TEXT,
    risk_factors TEXT,
    UNIQUE(ticker, date)
);

-- Create indexes for better performance
CREATE INDEX IF NOT EXISTS idx_tickers_symbol ON tickers(symbol);
CREATE INDEX IF NOT EXISTS idx_news_ticker ON news_articles(ticker);
CREATE INDEX IF NOT EXISTS idx_summaries_ticker_date ON daily_summaries(ticker, date);