from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, validator
from typing import Optional, List
import secrets


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", case_sensitive=False)

    # Application
    APP_NAME: str = "InvestmentAI"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False
    ENVIRONMENT: str = "production"
    ALLOWED_ORIGINS: List[str] = ["http://localhost:3000", "http://localhost:5173"]

    # Security — must be set via env var in production; dev fallback is stable
    SECRET_KEY: str = "dev-stable-secret-key-change-in-production-via-SECRET_KEY-env-var"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30

    # Database — Railway provides postgresql://, we need postgresql+asyncpg://
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/investment_ai"

    @property
    def async_database_url(self) -> str:
        url = self.DATABASE_URL
        if url.startswith("postgresql://"):
            url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
        if url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql+asyncpg://", 1)
        return url
    DATABASE_POOL_SIZE: int = 20
    DATABASE_MAX_OVERFLOW: int = 10

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"
    REDIS_CACHE_TTL: int = 300  # 5 minutes

    # Anthropic / Claude
    ANTHROPIC_API_KEY: str = ""
    CLAUDE_MODEL: str = "claude-sonnet-4-6"
    CLAUDE_MAX_TOKENS: int = 4096

    # OpenAI / GPT (News Analyst)
    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = "gpt-4o-mini"

    # Google Gemini (Macro Context)
    GEMINI_API_KEY: str = ""
    GOOGLE_AI_API_KEY: str = ""  # alias accepted from Railway
    GEMINI_MODEL: str = "gemini-1.5-flash"

    # Twitter/X API v2
    TWITTER_BEARER_TOKEN: str = ""
    TWITTER_API_KEY: str = ""
    TWITTER_API_SECRET: str = ""
    TWITTER_ACCESS_TOKEN: str = ""
    TWITTER_ACCESS_TOKEN_SECRET: str = ""

    # Reddit
    REDDIT_CLIENT_ID: str = ""
    REDDIT_CLIENT_SECRET: str = ""
    REDDIT_USER_AGENT: str = "InvestmentAI/1.0"

    # News APIs
    NEWSAPI_KEY: str = ""
    ALPHA_VANTAGE_KEY: str = ""

    # Twilio (SMS)
    TWILIO_ACCOUNT_SID: str = ""
    TWILIO_AUTH_TOKEN: str = ""
    TWILIO_FROM_NUMBER: str = ""

    # SendGrid (Email)
    SENDGRID_API_KEY: str = ""
    SENDGRID_FROM_EMAIL: str = "noreply@investment-ai.com"
    SENDGRID_FROM_NAME: str = "Investment AI"

    # Firebase (Push Notifications)
    FIREBASE_CREDENTIALS_PATH: str = "/app/secrets/firebase-credentials.json"

    # Risk Management
    MAX_SINGLE_ASSET_EXPOSURE: float = 0.03  # 3% of portfolio per asset
    MAX_SECTOR_EXPOSURE: float = 0.20  # 20% per sector
    MAX_PORTFOLIO_RISK_SCORE: int = 80

    # Agent Configuration
    AGENT_SCAN_INTERVAL_SECONDS: int = 300  # 5 minutes
    FUNDAMENTAL_CONFIDENCE_THRESHOLD: float = 0.25
    SENIOR_APPROVAL_THRESHOLD: float = 0.30
    MAX_CONCURRENT_SCANS: int = 10
    MAX_SCAN_STOCKS: int = 20  # limit daily full scan to save API tokens (override via Railway env var)
    MIN_EARNINGS_TRIGGER: int = 20  # min stocks with fresh earnings to trigger quarterly scan

    # Market Hours (Israel Time UTC+3)
    TASE_OPEN_HOUR: int = 9
    TASE_CLOSE_HOUR: int = 17
    US_OPEN_HOUR_UTC: int = 14  # 9:30 ET = 14:30 UTC
    US_CLOSE_HOUR_UTC: int = 21  # 16:00 ET = 21:00 UTC

    # TASE API
    TASE_API_BASE_URL: str = "https://api.tase.co.il/api"
    MAYA_BASE_URL: str = "https://mayaapi.tase.co.il/api"

    # Websocket
    WS_HEARTBEAT_INTERVAL: int = 30

    # Celery
    CELERY_BROKER_URL: str = "redis://localhost:6379/1"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/2"

    # Notification message (Hebrew - generic external)
    NOTIFICATION_EXTERNAL_MESSAGE: str = "יש לך עדכון השקעות חדש. אנא היכנס למערכת לצפייה בפרטים."
    NOTIFICATION_EXTERNAL_MESSAGE_EN: str = "You have a new investment update. Please log in to view details."


settings = Settings()
