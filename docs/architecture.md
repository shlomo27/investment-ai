# Investment AI Platform - Architecture Documentation
# מערכת ייעוץ השקעות AI - תיעוד ארכיטקטורה

---

## System Overview / סקירת מערכת

The Investment AI Platform is an AI-powered investment advisory and trading system that combines:
- **LangGraph** agent orchestration for multi-agent AI workflows
- **FastAPI** async backend with PostgreSQL + Redis + TimescaleDB
- **Internal broker engine** for simulated order execution
- **24/7 Celery scanning** of asset pools
- **Multi-channel notifications** (Push/SMS/Email)
- **TASE (Israel) + Global markets** support

---

## Agent Architecture / ארכיטקטורת הסוכנים

### The 3-Agent Pipeline (Real-time)

```
Asset Pool
    │
    ▼
┌─────────────────────────────────────┐
│  Agent 1: הפקיד (Data Fetcher)      │
│  - Fetches price data (Yahoo/TASE)  │
│  - Social sentiment (Twitter/Reddit) │
│  - News (NewsAPI + Israeli RSS)     │
│  - Financial statements             │
│  → Returns: MarketDataState         │
└────────────────┬────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────┐
│  Agent 2: Fundamental Analyst       │
│  - P/E, PEG, P/B ratio analysis    │
│  - Revenue & earnings quality       │
│  - Balance sheet health             │
│  - Sentiment cross-check            │
│  - Sector comparison                │
│  → Returns: recommendation + target  │
└────────────────┬────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────┐
│  Agent 3: הבכיר (Senior Committee)  │
│  - Cross-validates raw vs analysis  │
│  - Contrarian check (euphoria?)     │
│  - Final APPROVE or REJECT          │
│  - If REJECT: sends feedback        │
│  → Returns: final_decision          │
└────────────────┬────────────────────┘
                 │
        ┌────────┴────────┐
        │ APPROVED         │ REJECTED
        ▼                  ▼
  Save to DB          Log rejection
  Notify users        (audit trail)
```

### Agent 4: Technical Analyst (On-demand)

```
User Request (watchlist or recommendation)
    │
    ▼
┌─────────────────────────────────────────┐
│  Technical Analyst Agent                │
│  - RSI (14), MACD (12,26,9)            │
│  - Bollinger Bands (20, 2σ)            │
│  - MA 50/200 (Golden/Death Cross)      │
│  - Volume analysis                      │
│  - Support & Resistance levels          │
│  - Chart patterns detection             │
│  → Signal: BUY_NOW/SELL_NOW/WAIT       │
└─────────────────────────────────────────┘
```

---

## Data Flow / זרימת נתונים

```
External APIs                 Internal Systems
───────────────               ─────────────────
Yahoo Finance  ─────────────► Data Fetcher
TASE API       ─────────────► Agent (הפקיד)
Twitter/X      ─────────────►     │
Reddit         ─────────────►     │
NewsAPI        ─────────────►     │
Israeli RSS    ─────────────►     ▼
                           Fundamental Analyst
                                  │
                                  ▼
                           Senior Committee
                                  │
                         ┌────────┴────────┐
                         │                 │
                    PostgreSQL          Notifications
                    (Recommendation)   (Push/SMS/Email)
                         │
                         ▼
                      Users
                    (via App)
```

---

## Security Design / עיצוב אבטחה

### Notification Privacy Model
- **External channels** (Push/SMS/Email): Always send ONLY the generic message:
  `"יש לך עדכון השקעות חדש. אנא היכנס למערכת לצפייה בפרטים."`
- **Internal app** (after JWT authentication): Full AI analysis details visible
- This prevents sensitive investment signals from leaking via notification content

### Authentication
- JWT tokens (access + refresh)
- bcrypt password hashing
- All routes require authentication except /login and /register

---

## Database Schema / סכמת בסיס הנתונים

```
users ──────────┬── portfolios
                ├── orders
                ├── notifications
                └── watchlist

assets ─────────┬── portfolios
                ├── recommendations
                └── watchlist

recommendations ─┬── notifications
                 └── orders
```

---

## Worker Architecture / ארכיטקטורת העובדים

```
Celery Beat (Scheduler)
    │
    ├── scan_asset_pool (every 5 min, 24/7)
    │       └── Runs 3-agent pipeline on all active pool assets
    │
    ├── scan_user_portfolios (every 5 min)
    │       └── Checks existing holdings for sell signals
    │
    ├── update_portfolio_prices (every 2 min)
    │       └── Keeps P&L calculations current
    │
    └── cleanup_old_data (daily 2 AM IL)
            └── Removes old notifications and cancelled orders
```

---

## Technology Stack / מחסנית טכנולוגית

| Layer | Technology |
|-------|-----------|
| Backend API | FastAPI (Python 3.11) |
| AI Orchestration | LangGraph + LangChain |
| AI Models | Anthropic Claude (claude-sonnet-4-6) |
| Primary DB | PostgreSQL 15 (TimescaleDB) |
| Cache/Queue | Redis 7 |
| Task Queue | Celery + Celery Beat |
| Market Data | yfinance, TASE API |
| Sentiment | tweepy (Twitter), PRAW (Reddit) |
| News | NewsAPI, Israeli RSS feeds |
| Technical Analysis | pandas-ta |
| Push Notifications | Firebase Admin SDK |
| SMS | Twilio |
| Email | SendGrid |
| Frontend | React 18 + TypeScript |
| State Management | Redux Toolkit |
| Charts | Recharts |
| Styling | Tailwind CSS |
| Containerization | Docker + Docker Compose |

---

## Market Support / תמיכה בשווקים

| Market | Exchange | Currency | Hours |
|--------|----------|----------|-------|
| Israel | TASE | ILS (₪) | Sun-Thu 9:00-17:00 IL |
| US Stocks | NASDAQ, NYSE | USD ($) | Mon-Fri 9:30-16:00 ET |
| US ETFs | NYSE, NASDAQ | USD ($) | Mon-Fri 9:30-16:00 ET |
| Global | LSE, EURONEXT | Various | Market hours |

The system scans 24/7 and agents handle market-hours logic based on exchange type.

---

## Risk Management Rules / כללי ניהול סיכונים

1. **Max single asset exposure**: 3% of portfolio (configurable per user)
2. **Max sector exposure**: 20% (Herfindahl Index monitoring)
3. **Contrarian check**: Senior agent flags sentiment extremes (>0.7 or <-0.7)
4. **Rebalancing**: Automatic suggestions when positions exceed limits
5. **Stop loss**: Required for all BUY recommendations
6. **Confidence threshold**: Only send recommendations >65% confidence (fundamental), >70% (senior approval)
