"""
Main API v1 router - aggregates all sub-routers
"""
from fastapi import APIRouter

from app.api.v1 import auth, portfolio, orders, recommendations, market, watchlist

api_router = APIRouter(prefix="/api/v1")

api_router.include_router(auth.router)
api_router.include_router(portfolio.router)
api_router.include_router(orders.router)
api_router.include_router(recommendations.router)
api_router.include_router(market.router)
api_router.include_router(watchlist.router)
