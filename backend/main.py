"""
Investment AI Platform - FastAPI Main Application
"""
import asyncio
import json
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, Dict, Set
import structlog
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.core.database import check_db_connection, create_tables
from app.api.v1.router import api_router

logger = structlog.get_logger(__name__)

# WebSocket connection manager
class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[int, Set[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, user_id: int):
        await websocket.accept()
        if user_id not in self.active_connections:
            self.active_connections[user_id] = set()
        self.active_connections[user_id].add(websocket)
        logger.info("WebSocket connected", user_id=user_id)

    def disconnect(self, websocket: WebSocket, user_id: int):
        if user_id in self.active_connections:
            self.active_connections[user_id].discard(websocket)
            if not self.active_connections[user_id]:
                del self.active_connections[user_id]
        logger.info("WebSocket disconnected", user_id=user_id)

    async def send_to_user(self, user_id: int, data: Dict[str, Any]):
        if user_id in self.active_connections:
            dead_connections = set()
            for connection in self.active_connections[user_id]:
                try:
                    await connection.send_json(data)
                except Exception:
                    dead_connections.add(connection)
            for dc in dead_connections:
                self.active_connections[user_id].discard(dc)

    async def broadcast(self, data: Dict[str, Any]):
        for user_id in list(self.active_connections.keys()):
            await self.send_to_user(user_id, data)


manager = ConnectionManager()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown."""
    logger.info("Investment AI Platform starting up...", version=settings.APP_VERSION)

    # Check database connection
    db_ok = await check_db_connection()
    if not db_ok:
        logger.error("Database connection failed on startup")
    else:
        logger.info("Database connection verified")
        # Create tables if they don't exist (development mode)
        if settings.DEBUG:
            await create_tables()

    # Check Redis connection
    try:
        import redis.asyncio as aioredis
        redis_client = aioredis.from_url(settings.REDIS_URL)
        await redis_client.ping()
        await redis_client.close()
        logger.info("Redis connection verified")
    except Exception as e:
        logger.warning("Redis connection check failed", error=str(e))

    logger.info(
        "Investment AI Platform ready",
        environment=settings.ENVIRONMENT,
        debug=settings.DEBUG,
        claude_model=settings.CLAUDE_MODEL,
    )

    yield

    logger.info("Investment AI Platform shutting down...")


# ─── Application Setup ──────────────────────────────────────────────────────────

app = FastAPI(
    title="Investment AI Platform",
    description="""
    AI-powered investment advisory and trading platform.

    Features:
    - 4 AI agents: Data Fetcher (הפקיד), Fundamental Analyst, Senior Committee (הבכיר), Technical Analyst
    - Real-time TASE + Global market support
    - Social sentiment analysis (Twitter/X + Reddit)
    - Smart multi-channel notifications
    - Internal broker with risk management
    - 24/7 Celery worker scanning
    """,
    version=settings.APP_VERSION,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Prometheus metrics
try:
    from prometheus_fastapi_instrumentator import Instrumentator
    Instrumentator().instrument(app).expose(app, endpoint="/metrics")
    logger.info("Prometheus metrics enabled at /metrics")
except Exception as e:
    logger.warning("Prometheus instrumentation failed", error=str(e))

# Include API routes
app.include_router(api_router)


# ─── Health & Status Endpoints ─────────────────────────────────────────────────

@app.get("/health")
async def health_check():
    """Health check endpoint for Docker/k8s."""
    db_ok = await check_db_connection()
    return {
        "status": "healthy" if db_ok else "degraded",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "version": settings.APP_VERSION,
        "environment": settings.ENVIRONMENT,
        "database": "ok" if db_ok else "error",
    }


@app.get("/health/detailed")
async def health_detailed():
    """Detailed health check showing all service statuses."""
    checks = {}

    # DB check
    checks["database"] = await check_db_connection()

    # Redis check
    try:
        import redis.asyncio as aioredis
        r = aioredis.from_url(settings.REDIS_URL)
        await r.ping()
        await r.close()
        checks["redis"] = True
    except Exception:
        checks["redis"] = False

    # Claude API check (just key presence, don't make API call)
    checks["anthropic_api_key"] = bool(settings.ANTHROPIC_API_KEY)

    overall = "healthy" if checks["database"] else "degraded"

    return {
        "status": overall,
        "checks": checks,
        "version": settings.APP_VERSION,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "docs": "/docs",
        "health": "/health",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


# ─── WebSocket Endpoint ─────────────────────────────────────────────────────────

@app.websocket("/ws/{user_id}")
async def websocket_endpoint(websocket: WebSocket, user_id: int):
    """
    WebSocket endpoint for real-time updates.
    Requires user_id parameter. Token validation should be done via query param.
    """
    # Validate token from query string
    token = websocket.query_params.get("token")
    if not token:
        await websocket.close(code=4001, reason="Missing authentication token")
        return

    try:
        from app.core.security import verify_token
        token_data = verify_token(token)
        if token_data.user_id != user_id:
            await websocket.close(code=4001, reason="Token mismatch")
            return
    except Exception:
        await websocket.close(code=4001, reason="Invalid token")
        return

    await manager.connect(websocket, user_id)

    try:
        # Send connection confirmation
        await websocket.send_json({
            "type": "connected",
            "user_id": user_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

        # Keep-alive loop
        while True:
            try:
                # Wait for messages with timeout for heartbeat
                data = await asyncio.wait_for(
                    websocket.receive_json(),
                    timeout=settings.WS_HEARTBEAT_INTERVAL,
                )
                # Echo ping/pong
                if data.get("type") == "ping":
                    await websocket.send_json({
                        "type": "pong",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    })
            except asyncio.TimeoutError:
                # Send heartbeat
                await websocket.send_json({
                    "type": "heartbeat",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                })
    except WebSocketDisconnect:
        manager.disconnect(websocket, user_id)
    except Exception as e:
        logger.error("WebSocket error", user_id=user_id, error=str(e))
        manager.disconnect(websocket, user_id)


# ─── Exception Handlers ─────────────────────────────────────────────────────────

@app.exception_handler(404)
async def not_found_handler(request, exc):
    # Preserve detail when the 404 comes from inside a route handler
    detail = getattr(exc, "detail", None) or "Resource not found"
    return JSONResponse(
        status_code=404,
        content={"detail": detail, "path": str(request.url.path)},
    )


@app.exception_handler(500)
async def server_error_handler(request, exc):
    logger.error("Unhandled server error", path=str(request.url.path), error=str(exc))
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.DEBUG,
        workers=1 if settings.DEBUG else 4,
        log_level="debug" if settings.DEBUG else "info",
    )
