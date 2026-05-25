"""
Import all models here to ensure they are registered with SQLAlchemy metadata.
This file is imported by Alembic's env.py.
"""
from app.core.database import Base  # noqa: F401
from app.db.models.user import User  # noqa: F401
from app.db.models.asset import Asset  # noqa: F401
from app.db.models.portfolio import Portfolio  # noqa: F401
from app.db.models.order import Order  # noqa: F401
from app.db.models.recommendation import Recommendation  # noqa: F401
from app.db.models.notification import Notification  # noqa: F401
from app.db.models.watchlist import Watchlist  # noqa: F401
