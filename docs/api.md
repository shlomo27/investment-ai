# Investment AI Platform - API Documentation

Base URL: `http://localhost:8000/api/v1`

All endpoints require `Authorization: Bearer <access_token>` unless noted.

---

## Authentication

### POST /auth/register
Register a new user account.
```json
{
  "email": "user@example.com",
  "password": "password123",
  "full_name": "John Doe",
  "phone": "+972501234567",
  "preferred_language": "he"
}
```
Returns: `{ user: User, tokens: { access_token, refresh_token } }`

### POST /auth/login
```json
{ "email": "user@example.com", "password": "password123" }
```

### POST /auth/onboarding
Complete the onboarding wizard.
```json
{
  "risk_profile": "PASSIVE",
  "risk_score": 45,
  "initial_deposit": 10000,
  "notification_email": true,
  "notification_sms": true,
  "notification_push": false
}
```

### GET /auth/me
Returns current user profile.

### PUT /auth/profile
Update profile fields.

---

## Portfolio

### GET /portfolio/
Returns all portfolio positions.

### GET /portfolio/summary
Returns portfolio summary with P&L and risk score.

### GET /portfolio/risk
Returns detailed risk metrics (HHI, diversification score, exposure breakdown).

### GET /portfolio/rebalancing
Returns AI-generated rebalancing suggestions.

### POST /portfolio/settings
```json
{ "max_single_asset_exposure_pct": 3.0 }
```

### GET /portfolio/{symbol}
Returns position for a specific asset.

---

## Orders

### POST /orders/
Create and auto-execute an order.
```json
{
  "symbol": "AAPL",
  "order_type": "BUY",
  "quantity": 10,
  "price": 185.50,
  "recommendation_id": 42
}
```

### GET /orders/
Returns order history. Query params: `status_filter`, `limit`, `offset`.

### GET /orders/exposure-check
Check exposure before placing. Query params: `symbol`, `amount`.

### DELETE /orders/{order_id}
Cancel a pending order.

---

## Recommendations (Inbox)

### GET /recommendations/inbox
The main authenticated inbox - full AI analysis visible here.
Query: `unread_only=true`, `limit=50`

### GET /recommendations/unread-count
Returns `{ unread_count: N }`

### GET /recommendations/
List approved recommendations.

### GET /recommendations/{id}
Full detail of a specific recommendation including all AI analysis.

### POST /recommendations/{id}/acknowledge
Dismiss a recommendation.

### POST /recommendations/{id}/request-technical
Trigger on-demand technical analysis for a recommendation.
Returns technical analysis results immediately.

### POST /recommendations/inbox/{notification_id}/read
Mark a notification as read.

---

## Market Data

### GET /market/search?q=AAPL
Search global stocks. Returns results from Yahoo Finance + asset pool.

### GET /market/tase/search?q=בנק
Search Israeli TASE stocks.

### GET /market/pool
List the active asset pool. Query: `active_only`, `exchange`, `risk_level`, `sector`.

### GET /market/asset/{symbol}
Get comprehensive real-time data for an asset.
Query: `include_technical=true`

### POST /market/pool/add?symbol=TSLA&exchange=NASDAQ
Add an asset to the scanning pool.

---

## Watchlist

### GET /watchlist/
Get all watchlist items with last technical signal.

### POST /watchlist/
```json
{
  "symbol": "NVDA",
  "exchange": "NASDAQ",
  "alert_on_technical_signal": true
}
```

### DELETE /watchlist/{id}
Remove from watchlist.

### POST /watchlist/{id}/technical-analysis
Trigger on-demand technical analysis. Returns:
```json
{
  "timing_signal": "BUY_NOW",
  "technical_score": 73.5,
  "rsi_14": 38.2,
  "macd_crossover": "BULLISH",
  "support_levels": [182.0, 178.5],
  "resistance_levels": [190.0, 195.0],
  "signal_reasoning": "RSI oversold (38.2); MACD bullish crossover"
}
```

---

## WebSocket

### WS /ws/{user_id}?token={access_token}

Real-time updates channel. Message types:
- `connected` - Connection established
- `heartbeat` - Keep-alive ping every 30s
- `new_recommendation` - New AI recommendation available
- `order_executed` - Order confirmed
- `price_update` - Portfolio price update
- `risk_alert` - Risk limit warning

---

## AI Recommendation Object

```json
{
  "id": 1,
  "symbol": "AAPL",
  "recommendation_type": "BUY",
  "status": "PRESENTED_TO_USER",
  "confidence_score": 78.5,
  "target_price": 210.0,
  "stop_loss": 172.0,
  "current_price_at_recommendation": 185.50,
  "fundamental_analysis": {
    "recommendation_type": "BUY",
    "confidence_score": 75.0,
    "valuation_assessment": "UNDERVALUED",
    "financial_health": "EXCELLENT",
    "bull_case": "Strong services revenue growth...",
    "bear_case": "China exposure risk...",
    "risk_factors": ["China sales slowdown", "AI competition"],
    "catalysts": ["iPhone 16 super-cycle", "AI features monetization"]
  },
  "sentiment_data": {
    "score": 0.342,
    "mentions": 15420,
    "trending": true,
    "twitter_score": 0.38,
    "reddit_score": 0.29
  },
  "senior_review_notes": "Analyst recommendation validated against raw data...",
  "senior_notes": "Approved with high confidence. Sentiment confirms fundamentals."
}
```
