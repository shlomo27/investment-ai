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


def run_migrations():
    """Run Alembic migrations synchronously in a separate thread to avoid event loop conflicts."""
    import threading
    import os

    def _migrate():
        try:
            from alembic.config import Config
            from alembic import command
            from sqlalchemy import create_engine, inspect, text

            alembic_cfg = Config(os.path.join(os.path.dirname(__file__), "alembic.ini"))

            # Use sync psycopg2 URL
            db_url = settings.DATABASE_URL.replace(
                "postgresql+asyncpg://", "postgresql+psycopg2://"
            )
            engine = create_engine(db_url, pool_pre_ping=True)

            try:
                with engine.connect() as conn:
                    inspector = inspect(engine)
                    has_users = inspector.has_table("users")
                    has_alembic = inspector.has_table("alembic_version")

                    if has_users and not has_alembic:
                        # Tables were created by SQLAlchemy create_all() without Alembic.
                        # Stamp at 001 so Alembic knows the base schema is in place,
                        # then upgrade will run 002, 003, 004 to add new columns.
                        logger.warning(
                            "DB tables exist without Alembic tracking. "
                            "Stamping at revision 001 then upgrading."
                        )
                        command.stamp(alembic_cfg, "001")
            finally:
                engine.dispose()

            command.upgrade(alembic_cfg, "head")
            logger.info("Alembic migrations applied successfully")
        except Exception as e:
            logger.error("Alembic migration failed", error=str(e))

    t = threading.Thread(target=_migrate)
    t.start()
    t.join(timeout=90)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown."""
    logger.info("Investment AI Platform starting up...", version=settings.APP_VERSION)

    # Run DB migrations on every startup
    run_migrations()

    # Check database connection
    db_ok = await check_db_connection()
    if not db_ok:
        logger.error("Database connection failed on startup")
    else:
        logger.info("Database connection verified")
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

    # ── In-process scheduler (replaces Celery Beat on Railway) ──────────────
    # uvicorn runs 4 workers and lifespan executes in EACH of them, but only
    # ONE worker may run the scheduler: APScheduler 3.x has no cross-process
    # coordination, so multiple schedulers sharing the same job store would
    # fire every job once per worker (4x Claude cost, duplicate notifications).
    # A session-scoped PostgreSQL advisory lock elects a single winner; the
    # lock auto-releases if that worker's connection dies, and a respawned
    # worker re-runs lifespan and can take it over.
    scheduler = None
    sched_lock_conn = None
    try:
        from sqlalchemy import text
        from app.core.database import engine
        from app.workers.in_process_scheduler import create_scheduler

        SCHEDULER_LOCK_KEY = 931_702  # arbitrary app-wide constant
        sched_lock_conn = await engine.connect()
        got_lock = (
            await sched_lock_conn.execute(
                text("SELECT pg_try_advisory_lock(:k)"), {"k": SCHEDULER_LOCK_KEY}
            )
        ).scalar()

        if got_lock:
            sync_db_url = settings.DATABASE_URL.replace(
                "postgresql+asyncpg://", "postgresql+psycopg2://"
            )
            scheduler = create_scheduler(sync_db_url)
            scheduler.start()
            logger.info(
                "In-process scheduler started (this worker holds the scheduler lock)",
                jobs=["load_universe Sun 07:00 IL", "prescreener daily 08:00 IL", "full_scan Wed 09:00 IL"],
            )
        else:
            await sched_lock_conn.close()
            sched_lock_conn = None
            logger.info("Scheduler skipped in this worker — another worker holds the lock")
    except Exception as exc:
        if sched_lock_conn is not None:
            try:
                await sched_lock_conn.close()
            except Exception:
                pass
            sched_lock_conn = None
        logger.warning("In-process scheduler failed to start — manual scans still available", error=str(exc))

    yield

    if scheduler and scheduler.running:
        scheduler.shutdown(wait=False)
    if sched_lock_conn is not None:
        try:
            await sched_lock_conn.close()  # releases the advisory lock
        except Exception:
            pass
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
