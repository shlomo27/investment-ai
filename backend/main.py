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
    #
    # A session-scoped PostgreSQL advisory lock elects a single winner. The
    # keeper task RETRIES every 60s: during rolling deploys the OLD container
    # still holds the lock when the new workers boot, so a one-shot try left
    # the new container with NO scheduler at all (missed the weekly scan).
    # With the retry loop, whichever worker grabs the lock first — possibly
    # minutes later, after the old container dies — starts the scheduler.
    sched_state: dict = {"scheduler": None, "conn": None, "task": None}

    async def _scheduler_keeper():
        from sqlalchemy import text
        from app.core.database import engine
        from app.workers.in_process_scheduler import (
            create_scheduler, dedupe_live_recommendations, remove_stale_jobs,
            restore_actioned_recommendations,
        )

        SCHEDULER_LOCK_KEY = 931_702  # arbitrary app-wide constant
        logged_waiting = False
        did_maintenance = False

        import os as _os
        _WORKER_KEY = f"investment_ai:scheduler:worker:{_os.getpid()}"

        async def _publish(payload: dict, key: str = _WORKER_KEY):
            """Write this worker's own state where the panel can read it.

            One key per worker, because every shared key has been clobbered.
            uvicorn runs four of these and the advisory lock elects one, so
            three are always waiting — the design working. Writing them all to
            one key meant the last write won and it was a loser three times
            out of four, and the panel reported "waiting for the lock"
            whatever the holder was doing. Splitting it into holder/waiter
            keys moved the problem rather than fixing it: a keeper that
            crashed wrote the failure to the waiter key, where the three
            genuine waiters immediately overwrote the only line that said
            what had actually gone wrong.

            Per-worker keys cannot collide. The reader looks at all of them
            and reports the holder if there is one, then any crash, then
            waiting.

            Every failure in this loop was caught, logged and retried, so from
            outside it was indistinguishable from a scheduler that had simply
            not started — and the panel could only say "no scheduler is
            running", which is a symptom, not a cause. Three deploys were
            spent guessing at reasons that turned out to be wrong. The reason
            is published here instead.
            """
            try:
                import redis.asyncio as _aioredis, json as _json
                from datetime import datetime as _dt, timezone as _tz
                rc = _aioredis.from_url(settings.REDIS_URL)
                try:
                    await rc.set(
                        key,
                        _json.dumps({"alive_at": _dt.now(_tz.utc).isoformat(), **payload}),
                        # Shorter than the holder's, and shorter than the 60s
                        # publish interval times three, so a stale "waiting"
                        # from a container that has since won or died expires
                        # on its own rather than outliving the truth.
                        ex=180,
                    )
                finally:
                    await rc.aclose()
            except Exception:
                pass
        while True:
            conn = None
            try:
                conn = await engine.connect()
                got_lock = (
                    await conn.execute(
                        text("SELECT pg_try_advisory_lock(:k)"), {"k": SCHEDULER_LOCK_KEY}
                    )
                ).scalar()
                if got_lock:
                    sched_state["conn"] = conn  # hold connection = hold lock
                    held_pid = (await conn.execute(text("SELECT pg_backend_pid()"))).scalar()

                    # A breadcrumb at each step, because the failure has no
                    # exception to report.
                    #
                    # Four workers all report "waiting for the lock" while a
                    # live backend holds it and nobody publishes a running
                    # scheduler — and nobody reports a crash either. So one
                    # worker reaches this branch and stops inside it without
                    # raising: a hang, not an error. create_scheduler and
                    # scheduler.start() both drive a synchronous psycopg2 job
                    # store from inside the event loop, and roughly twenty
                    # add_job calls each write to Postgres the same way.
                    #
                    # Nothing downstream can name which of those it is, so
                    # each step says so before it starts. Whichever stage the
                    # panel is stuck on is the one that does not return.
                    async def _step(name: str):
                        await _publish({
                            "running": False, "stage": name,
                            "detail": f"holder pid {held_pid} reached: {name}",
                        })

                    await _step("lock_acquired")
                    sync_db_url = settings.DATABASE_URL.replace(
                        "postgresql+asyncpg://", "postgresql+psycopg2://"
                    )
                    # Off the event loop, and with a deadline.
                    #
                    # create_scheduler builds a SQLAlchemyJobStore and
                    # scheduler.start() reads and writes it with synchronous
                    # psycopg2 — around twenty add_job calls, each a blocking
                    # round trip — all of it running directly on the async
                    # loop. If Postgres is slow to hand out a connection, or
                    # never does, that blocks forever with no timeout and no
                    # exception: the worker holds the advisory lock, publishes
                    # nothing, and looks from outside exactly like a worker
                    # that is merely waiting for a lock it is itself holding.
                    #
                    # A thread keeps the loop responsive, and 120 seconds
                    # turns an indefinite hang into something that raises,
                    # gets caught, releases the lock and lets another worker
                    # try.
                    await _step("creating_scheduler")
                    scheduler = await asyncio.wait_for(
                        asyncio.to_thread(create_scheduler, sync_db_url), timeout=120
                    )
                    await _step("starting_scheduler")
                    await asyncio.wait_for(asyncio.to_thread(scheduler.start), timeout=120)
                    await _step("scheduler_started")
                    sched_state["scheduler"] = scheduler
                    logger.info(
                        "In-process scheduler started (this worker holds the scheduler lock)",
                        jobs=["load_universe Sun 07:00 IL", "prescreener daily 08:00 IL", "full_scan Wed 09:00 IL"],
                    )
                    async def _publish_jobs():
                        try:
                            import redis.asyncio as _aioredis, json as _json
                            from datetime import datetime as _dt, timezone as _tz
                            rc = _aioredis.from_url(settings.REDIS_URL)
                            try:
                                await rc.set(
                                    # The authoritative key: only the worker
                                    # holding the lock ever writes it.
                                    "investment_ai:scheduler:state",
                                    _json.dumps({
                                        "alive_at": _dt.now(_tz.utc).isoformat(),
                                        "running": bool(scheduler.running),
                                        "holder_pid": held_pid,
                                        "jobs": sorted(
                                            (
                                                {
                                                    "id": j.id,
                                                    "next_run": j.next_run_time.isoformat()
                                                    if j.next_run_time else None,
                                                }
                                                for j in scheduler.get_jobs()
                                            ),
                                            key=lambda d: d["id"],
                                        ),
                                    }),
                                    ex=600,
                                )
                            finally:
                                await rc.aclose()
                        except Exception as pub_exc:
                            logger.debug("scheduler state publish failed", error=str(pub_exc))

                    # Say it is up before doing anything else.
                    #
                    # The first publish used to sit after stale-job cleanup, a
                    # Telegram admin alert with no timeout, and two unguarded
                    # database maintenance calls. Any of them failing or
                    # hanging meant a scheduler that had genuinely started was
                    # never reported as started — the panel said "no scheduler
                    # is running" about a running scheduler.
                    await _publish_jobs()

                    # Maintenance cannot unwind the lock holder. It used to run
                    # unguarded in the same try block, so a failure here threw
                    # the worker out of the branch holding the lock.
                    # Purge ghost jobs persisted by older code versions — the
                    # Postgres job store outlives deploys, so renamed/removed
                    # jobs would keep firing forever (stale daily full scan!).
                    try:
                        removed = remove_stale_jobs(scheduler)
                    except Exception as maint_exc:
                        removed = []
                        logger.warning("Stale-job cleanup failed", error=str(maint_exc))
                    if removed:
                        try:
                            from app.services.notifications.telegram_service import get_telegram_service
                            await get_telegram_service().send_admin_alert(
                                "🧹 <b>נוקו עבודות-רפאים מהמתזמן</b>\n"
                                f"עבודות ישנות שהוסרו: {', '.join(removed)}\n"
                                "אלה גרמו לסריקות לא מתוכננות."
                            )
                        except Exception:
                            pass
                    # One-shot maintenance: restore bought-then-hidden recs,
                    # then collapse duplicate live recommendations.
                    if not did_maintenance:
                        try:
                            await restore_actioned_recommendations()
                            await dedupe_live_recommendations()
                        except Exception as maint_exc:
                            logger.warning(
                                "Start-up maintenance failed — scheduler stays up",
                                error=str(maint_exc),
                            )
                        # Fill SEC issuer ids now rather than waiting for
                        # Sunday. Until this has run, share-class grouping has
                        # nothing to key on: GOOGL and GOOG stay two unrelated
                        # companies and the card says nothing about either.
                        #
                        # Detached so a slow or unreachable SEC never delays
                        # the server accepting requests — the job logs its own
                        # failure and the weekly run tries again.
                        from app.core.background import detach
                        from app.workers.in_process_scheduler import job_backfill_ciks

                        detach(job_backfill_ciks())
                        did_maintenance = True
                    logged_waiting = False

                    # Hold the lock and KEEP VERIFYING it. Postgres releases a
                    # session-scoped advisory lock the moment the session dies,
                    # which happens on every database restart — a managed
                    # security patch, a failover, a connection reaper. This used
                    # to `return` here, so the winner never noticed: its
                    # scheduler kept running while the freed lock was picked up
                    # by another worker within 60s, leaving TWO schedulers alive
                    # and firing every job twice — double AI spend and duplicate
                    # alerts, exactly what the lock exists to prevent.
                    # Publish what the scheduler is actually doing, where the
                    # other three uvicorn workers can read it.
                    #
                    # Only one worker holds the scheduler, so an endpoint that
                    # looked at local state would answer "no scheduler" three
                    # times out of four. Writing it to Redis makes the answer
                    # the same whichever worker serves the request — and turns
                    # "the panel says the scan never completed" into something
                    # with a cause attached: no scheduler at all, a scheduler
                    # with the job missing, or a job whose next run is an hour
                    # away.
                    await _publish_jobs()
                    while True:
                        await asyncio.sleep(60)
                        await _publish_jobs()
                        try:
                            pid = (await conn.execute(text("SELECT pg_backend_pid()"))).scalar()
                            # A silently re-established connection is a NEW
                            # backend, and the lock did not survive with it.
                            if pid != held_pid:
                                raise RuntimeError(f"backend changed {held_pid}→{pid}")
                        except Exception as hb_exc:
                            logger.warning(
                                "Scheduler lock lost (database restart?) — stopping this "
                                "scheduler and re-entering the election",
                                error=str(hb_exc),
                            )
                            break

                    try:
                        if scheduler.running:
                            scheduler.shutdown(wait=False)
                    except Exception:
                        pass
                    sched_state["scheduler"] = None
                    try:
                        await conn.close()
                    except Exception:
                        pass
                    sched_state["conn"] = None
                    await asyncio.sleep(5)
                    continue
                # Who holds it, and is that process still alive?
                #
                # The lock is session-scoped, so a container killed without a
                # clean shutdown leaves its backend holding it until the TCP
                # connection is reaped — with default keepalives that is up to
                # two hours. For that whole window the lock belongs to a
                # process that no longer exists, every new container waits for
                # it, and nothing is scheduled. "Usually the previous
                # container during a deploy" was the comforting reading;
                # "a dead one from an hour ago" is the other.
                holder = None
                try:
                    holder = (await conn.execute(text("""
                        SELECT a.pid, a.state,
                               EXTRACT(EPOCH FROM (now() - a.state_change))::int AS idle_seconds
                        FROM pg_locks l
                        JOIN pg_stat_activity a ON a.pid = l.pid
                        WHERE l.locktype = 'advisory' AND l.objid = :k AND l.granted
                        LIMIT 1
                    """), {"k": SCHEDULER_LOCK_KEY})).mappings().first()
                except Exception:
                    holder = None

                # Reclaim it from a backend that has been idle long enough to
                # be dead. Five minutes is far longer than any real handover:
                # the holder heartbeats its connection every 60 seconds, so a
                # live scheduler is never idle this long.
                reclaimed = False
                if holder and holder["state"] == "idle" and (holder["idle_seconds"] or 0) > 300:
                    try:
                        await conn.execute(
                            text("SELECT pg_terminate_backend(:pid)"), {"pid": holder["pid"]}
                        )
                        reclaimed = True
                        logger.warning(
                            "Terminated a stale scheduler-lock holder",
                            pid=holder["pid"], idle_seconds=holder["idle_seconds"],
                        )
                    except Exception as kill_exc:
                        logger.warning("Could not terminate lock holder", error=str(kill_exc))

                await conn.close()
                await _publish({
                    "running": False,
                    "stage": "waiting_for_lock",
                    "detail": (
                        f"lock held by pid {holder['pid']} "
                        f"({holder['state']}, idle {holder['idle_seconds']}s)"
                        + (" — terminated as stale, retrying shortly" if reclaimed else "")
                        if holder else
                        "another process holds the scheduler lock — "
                        "usually the previous container during a deploy"
                    ),
                })
                if reclaimed:
                    # Do not wait the full minute after clearing it.
                    await asyncio.sleep(2)
                    continue
                if not logged_waiting:
                    logger.info("Scheduler lock held elsewhere — will keep retrying every 60s")
                    logged_waiting = True
            except Exception as exc:
                if conn is not None:
                    # Release the lock explicitly before letting the
                    # connection go.
                    #
                    # pg_try_advisory_lock is session-scoped and conn.close()
                    # on a pooled SQLAlchemy connection does not end the
                    # session — it returns the connection to the pool with the
                    # lock still held. So a worker that acquired the lock and
                    # then failed during start-up kept it forever: its own
                    # retry a minute later asked a different pooled connection,
                    # was refused by the session it had abandoned, and
                    # reported "waiting for the lock". The holder it was
                    # waiting for was itself.
                    #
                    # The retry loop also kept querying on that same pooled
                    # connection, which reset its state_change, so it always
                    # looked freshly idle — "lock held by pid 66581 (idle,
                    # idle 9s)" — and never aged into the stale-holder reclaim.
                    try:
                        await conn.execute(
                            text("SELECT pg_advisory_unlock(:k)"), {"k": SCHEDULER_LOCK_KEY}
                        )
                    except Exception:
                        pass
                    try:
                        await conn.close()
                    except Exception:
                        pass
                logger.warning("Scheduler keeper iteration failed — retrying", error=str(exc))
                await _publish({
                    "running": False,
                    "stage": "keeper_failed",
                    "detail": f"{type(exc).__name__}: {exc}"[:300],
                })
            await asyncio.sleep(60)

    sched_state["task"] = asyncio.create_task(_scheduler_keeper())

    yield

    task = sched_state.get("task")
    if task and not task.done():
        task.cancel()
    scheduler = sched_state.get("scheduler")
    if scheduler and scheduler.running:
        scheduler.shutdown(wait=False)
    conn = sched_state.get("conn")
    if conn is not None:
        try:
            await conn.close()  # releases the advisory lock
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
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def _security_headers(request, call_next):
    """Standard browser-hardening headers — the kind a broker's security
    questionnaire and a pentest expect."""
    resp = await call_next(request)
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["X-Frame-Options"] = "DENY"
    resp.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    resp.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
    resp.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return resp

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
