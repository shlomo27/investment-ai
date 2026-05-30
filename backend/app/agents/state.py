"""
LangGraph state definitions for the Investment AI agent workflow.
"""
from typing import TypedDict, Optional, List, Dict, Any


class NewsItem(TypedDict):
    title: str
    source: str
    url: str
    published_at: str
    summary: str
    sentiment: float  # -1 to 1


class SocialSentiment(TypedDict):
    score: float          # -1 to 1
    mentions: int
    trending: bool
    top_posts: List[Dict[str, Any]]
    key_themes: List[str]
    twitter_score: float
    reddit_score: float
    tweet_count: int
    reddit_post_count: int


class TechnicalIndicators(TypedDict):
    rsi_14: float
    macd: float
    macd_signal: float
    macd_histogram: float
    bb_upper: float
    bb_middle: float
    bb_lower: float
    ma_50: float
    ma_200: float
    volume_sma: float
    current_volume: float
    atr: float
    support_levels: List[float]
    resistance_levels: List[float]


class EarningsData(TypedDict):
    last_eps: float
    eps_estimate: float
    eps_surprise_pct: float
    revenue_last: float
    revenue_estimate: float
    revenue_surprise_pct: float
    earnings_date: Optional[str]
    earnings_history: List[Dict[str, Any]]


class MarketDataState(TypedDict):
    symbol: str
    exchange: str
    price: float
    previous_close: float
    volume: int
    avg_volume_30d: int
    market_cap: float
    pe_ratio: Optional[float]
    forward_pe: Optional[float]
    peg_ratio: Optional[float]
    price_to_book: Optional[float]
    price_to_sales: Optional[float]
    debt_to_equity: Optional[float]
    current_ratio: Optional[float]
    quick_ratio: Optional[float]
    revenue_growth: Optional[float]
    earnings_growth: Optional[float]
    profit_margin: Optional[float]
    operating_margin: Optional[float]
    roe: Optional[float]
    roa: Optional[float]
    free_cash_flow: Optional[float]
    dividend_yield: Optional[float]
    beta: Optional[float]
    fifty_two_week_high: float
    fifty_two_week_low: float
    earnings_data: Optional[EarningsData]
    news_items: List[NewsItem]
    social_sentiment: SocialSentiment
    technical_indicators: Optional[TechnicalIndicators]
    sector: Optional[str]
    industry: Optional[str]
    country: str
    currency: str
    company_description: Optional[str]
    analyst_target_price: Optional[float]
    analyst_recommendation: Optional[str]
    institutional_ownership: Optional[float]
    short_interest: Optional[float]
    fetch_timestamp: str
    fetch_errors: List[str]


class AgentWorkflowState(TypedDict):
    asset_symbol: str
    exchange: str
    # Stage 1: Raw data from הפקיד
    data_fetcher_output: Optional[MarketDataState]
    data_fetcher_error: Optional[str]
    # Stage 2: Fundamental analysis
    fundamental_analysis: Optional[Dict[str, Any]]
    fundamental_error: Optional[str]
    # Stage 3: Senior committee decision
    senior_decision: Optional[Dict[str, Any]]
    senior_error: Optional[str]
    # Stage 4: Technical analysis (optional, on-demand)
    technical_analysis: Optional[Dict[str, Any]]
    technical_error: Optional[str]
    # Workflow metadata
    workflow_status: str  # "running" | "completed" | "failed" | "rejected"
    workflow_id: str
    started_at: str
    completed_at: Optional[str]
    error: Optional[str]
    # Result
    recommendation_id: Optional[int]
    # Optional context passed from caller
    portfolio_context: Optional[Dict[str, Any]]
    user_risk_context: Optional[Dict[str, Any]]


class TechnicalWorkflowState(TypedDict):
    asset_symbol: str
    exchange: str
    historical_data: Optional[Dict[str, Any]]
    technical_analysis: Optional[Dict[str, Any]]
    error: Optional[str]
    workflow_status: str
    watchlist_item_id: Optional[int]
    user_id: Optional[int]
