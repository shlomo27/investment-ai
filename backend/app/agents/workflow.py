"""
LangGraph Workflow Orchestration
Defines and runs the 3-agent pipeline:
  fetch_data → fundamental_analysis → senior_review → save_recommendation → notify_users
  (or) → log_rejection
"""
import asyncio
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional
import structlog

from langgraph.graph import StateGraph, END

from app.agents.state import AgentWorkflowState, TechnicalWorkflowState
from app.agents.data_fetcher.agent import get_data_fetcher_agent
from app.agents.news.agent import get_news_agent
from app.agents.macro.agent import get_macro_agent
from app.agents.fundamental.agent import get_fundamental_agent
from app.agents.senior.agent import get_senior_agent
from app.agents.technical.agent import get_technical_agent
from app.core.config import settings

logger = structlog.get_logger(__name__)

# The fundamentals a verdict genuinely rests on: each one is either read by a
# hard exclusion rule or needed to value the company at all. All are mandatory
# disclosure for a US-listed company, so a gap means our fetch failed.
CRITICAL_FUNDAMENTALS = (
    "market_cap",        # exclusion: market cap below $500M
    "free_cash_flow",    # exclusion: negative 3-year average FCF
    "revenue_growth",    # exclusion: revenue declining 3+ quarters
    "profit_margin",     # earnings quality
    "debt_to_equity",    # exclusion: leverage
)


# ─────────────────────────────────────────────────────────────────────────────
# Main workflow nodes
# ─────────────────────────────────────────────────────────────────────────────

async def node_fetch_data(state: AgentWorkflowState) -> AgentWorkflowState:
    """Node 1: Run DataFetcherAgent (הפקיד) to gather all raw data."""
    logger.info("Workflow node: fetch_data", symbol=state["asset_symbol"])
    try:
        agent = get_data_fetcher_agent()
        market_data = await agent.fetch_all_data(
            symbol=state["asset_symbol"],
            exchange=state["exchange"],
        )

        # No verified price → no analysis. When every market-data source fails
        # the fetcher still returns a well-formed dict with price 0.0, which
        # used to flow straight into the committee: it would reason about
        # targets, stops and upside for a stock whose current price it did not
        # know, and the saved recommendation would carry
        # current_price_at_recommendation = 0, breaking P&L and outcome
        # tracking afterwards. A missing price is a data outage, not a verdict.
        price = float((market_data or {}).get("price") or 0)
        if price <= 0:
            logger.error(
                "All market data sources returned no price — aborting analysis",
                symbol=state["asset_symbol"],
            )
            return {
                **state,
                "data_fetcher_output": market_data,
                "data_fetcher_error": "no_price",
                "workflow_status": "failed",
                "error": "No price available from any market data source",
            }

        # Enough fundamentals to actually judge the company. Every field below
        # is one a hard exclusion rule or the valuation depends on, and every
        # one is mandatory disclosure for a US-listed company — so an absence
        # means our fetch failed, not that the company withheld it. Judging on
        # a mostly-empty sheet produces a confident-looking verdict backed by
        # nothing, which is worse than no verdict at all.
        #
        # Deliberately NOT required: P/E (legitimately absent for loss-making
        # companies) and dividend yield (absent for non-payers). Requiring
        # those would reject healthy candidates for telling the truth.
        missing = [f for f in CRITICAL_FUNDAMENTALS if (market_data or {}).get(f) is None]
        if len(missing) > len(CRITICAL_FUNDAMENTALS) // 2:
            logger.error(
                "Too many fundamentals missing — aborting analysis",
                symbol=state["asset_symbol"], missing=missing,
            )
            return {
                **state,
                "data_fetcher_output": market_data,
                "data_fetcher_error": "insufficient_fundamentals",
                "workflow_status": "failed",
                "error": f"Insufficient fundamental data — missing: {', '.join(missing)}",
            }
        if missing:
            logger.info(
                "Proceeding with partial fundamentals",
                symbol=state["asset_symbol"], missing=missing,
            )

        return {
            **state,
            "data_fetcher_output": market_data,
            "data_fetcher_error": None,
            "workflow_status": "data_fetched",
        }
    except Exception as e:
        logger.error("fetch_data node failed", symbol=state["asset_symbol"], error=str(e))
        return {
            **state,
            "data_fetcher_error": str(e),
            "workflow_status": "failed",
            "error": f"DataFetcher failed: {e}",
        }


async def node_enrich_data(state: AgentWorkflowState) -> AgentWorkflowState:
    """Node 2: Run GPT (news) + Gemini (macro) in parallel to enrich the raw data."""
    logger.info("Workflow node: enrich_data", symbol=state["asset_symbol"])

    if state.get("data_fetcher_error") or not state.get("data_fetcher_output"):
        return {**state, "enrichment_error": "Skipped - no data from fetcher"}

    # Warn if price data is missing — analysis will proceed but with lower confidence
    price = (state["data_fetcher_output"] or {}).get("price", 0)
    if not price or price == 0.0:
        logger.warning(
            "Price is 0 — Yahoo Finance likely blocked on Railway. "
            "Quantitative models (DCF/Monte Carlo) will be skipped. "
            "Analysis continues using training knowledge.",
            symbol=state["asset_symbol"],
        )

    market_data = state["data_fetcher_output"]
    try:
        news_result, macro_result = await asyncio.gather(
            get_news_agent().analyze(market_data),
            get_macro_agent().analyze(market_data),
            return_exceptions=True,
        )

        if isinstance(news_result, Exception):
            logger.warning("News agent failed", error=str(news_result))
            news_result = None
        if isinstance(macro_result, Exception):
            logger.warning("Macro agent failed", error=str(macro_result))
            macro_result = None

        return {
            **state,
            "news_analysis": news_result,
            "macro_analysis": macro_result,
            "enrichment_error": None,
            "workflow_status": "enriched",
        }
    except Exception as e:
        logger.error("enrich_data node failed", symbol=state["asset_symbol"], error=str(e))
        return {**state, "enrichment_error": str(e)}


async def node_fundamental_analysis(state: AgentWorkflowState) -> AgentWorkflowState:
    """Node 2: Run FundamentalAnalystAgent on the fetched data."""
    logger.info("Workflow node: fundamental_analysis", symbol=state["asset_symbol"])

    if state.get("data_fetcher_error") or not state.get("data_fetcher_output"):
        return {
            **state,
            "fundamental_error": "Skipped - no data from fetcher",
            "workflow_status": "failed",
        }

    try:
        agent = get_fundamental_agent()
        analysis = await agent.analyze(
            market_data=state["data_fetcher_output"],
            portfolio_context=state.get("portfolio_context"),
            news_analysis=state.get("news_analysis"),
            macro_analysis=state.get("macro_analysis"),
            direction_bias=state.get("direction_bias"),
            language=state.get("language", "en"),
        )
        return {
            **state,
            "fundamental_analysis": analysis,
            "fundamental_error": None,
            "workflow_status": "fundamental_done",
        }
    except Exception as e:
        logger.error("fundamental_analysis node failed", symbol=state["asset_symbol"], error=str(e))
        return {
            **state,
            "fundamental_error": str(e),
            "workflow_status": "failed",
            "error": f"FundamentalAnalyst failed: {e}",
        }


async def node_senior_review(state: AgentWorkflowState) -> AgentWorkflowState:
    """Node 3: Run SeniorCommitteeAgent to approve/reject the recommendation."""
    logger.info("Workflow node: senior_review", symbol=state["asset_symbol"])

    if state.get("fundamental_error") or not state.get("fundamental_analysis"):
        return {
            **state,
            "senior_error": "Skipped - no fundamental analysis",
            "workflow_status": "failed",
        }

    # Filter low-confidence analyses before sending to senior
    confidence = state["fundamental_analysis"].get("confidence_score", 0)
    if confidence < settings.FUNDAMENTAL_CONFIDENCE_THRESHOLD * 100:
        return {
            **state,
            "senior_decision": {
                "approved": False,
                "rejection_reasoning": f"Fundamental confidence too low: {confidence:.1f}",
                "final_recommendation": "HOLD",
            },
            "workflow_status": "rejected",
        }

    try:
        agent = get_senior_agent()
        decision = await agent.review(
            raw_data=state["data_fetcher_output"],
            fundamental_analysis=state["fundamental_analysis"],
            news_analysis=state.get("news_analysis"),
            macro_analysis=state.get("macro_analysis"),
            user_risk_context=state.get("user_risk_context"),
            direction_bias=state.get("direction_bias"),
            language=state.get("language", "en"),
        )
        new_status = "approved" if decision.get("approved") else "rejected"
        return {
            **state,
            "senior_decision": decision,
            "senior_error": None,
            "workflow_status": new_status,
        }
    except Exception as e:
        logger.error("senior_review node failed", symbol=state["asset_symbol"], error=str(e))
        return {
            **state,
            "senior_error": str(e),
            "workflow_status": "failed",
            "error": f"SeniorAgent failed: {e}",
        }


def _risk_level_from_beta(beta: float):
    """Volatility band from beta — how hard the stock swings relative to the
    market. Beta captures market-correlated movement only, so a low-beta stock
    can still gap on its own news; it is what every data provider actually
    returns for us, and far better than the constant it replaces.

    Delegates to the backfill worker's version so a stock measured here and one
    measured there cannot be classified by two different rules.
    """
    from app.workers.beta_backfill import risk_level_from_beta

    return risk_level_from_beta(beta)


async def node_save_recommendation(state: AgentWorkflowState) -> AgentWorkflowState:
    """Node 4a: Save approved recommendation to database."""
    logger.info("Workflow node: save_recommendation", symbol=state["asset_symbol"])

    try:
        from app.core.database import AsyncSessionLocal
        from app.db.models.recommendation import Recommendation, RecommendationStatus, RecommendationType
        from app.db.models.asset import Asset
        from sqlalchemy import select

        senior = state["senior_decision"]
        fundamental = state["fundamental_analysis"]
        raw = state["data_fetcher_output"]

        async with AsyncSessionLocal() as session:
            # Find asset
            result = await session.execute(
                select(Asset).where(Asset.symbol == state["asset_symbol"])
            )
            asset = result.scalar_one_or_none()

            if not asset:
                logger.warning("Asset not found for recommendation", symbol=state["asset_symbol"])
                return {**state, "workflow_status": "failed", "error": "Asset not found in DB"}

            # Persist the volatility we just measured.
            #
            # Asset.risk_level was written once, at universe load, as a literal
            # MEDIUM for every US stock, and nothing ever revised it. Two things
            # downstream read it and were therefore both dead: the "high
            # volatility" badge on the card never appeared, and the user's
            # allows_volatile setting filtered on a constant. Asset.beta was
            # declared but never written at all, even though every analysis
            # fetches it.
            _beta = raw.get("beta")
            try:
                _beta = float(_beta) if _beta is not None else None
            except (TypeError, ValueError):
                _beta = None
            if _beta is not None and 0 < _beta < 10:
                asset.beta = _beta
                asset.risk_level = _risk_level_from_beta(_beta)

            # Map recommendation type
            rec_type_str = senior.get("final_recommendation", "HOLD")
            try:
                rec_type = RecommendationType(rec_type_str)
            except ValueError:
                rec_type = RecommendationType.HOLD

            # Supersede any previous live recommendation for this symbol so the
            # feed always holds exactly ONE active recommendation per stock —
            # a rerun (weekly scan, duplicate job, manual trigger) refreshes
            # instead of piling up duplicates.
            from sqlalchemy import update as sa_update
            _ACTIONABLE_TYPES = {
                RecommendationType.BUY, RecommendationType.STRONG_BUY,
                RecommendationType.SELL, RecommendationType.STRONG_SELL,
            }
            prev_live = (await session.execute(
                select(Recommendation).where(
                    Recommendation.symbol == state["asset_symbol"],
                    Recommendation.status.in_([
                        RecommendationStatus.APPROVED,
                        RecommendationStatus.PRESENTED_TO_USER,
                        RecommendationStatus.ACTIONED,
                    ]),
                )
            )).scalars().all()
            _BUY_SIDE = {RecommendationType.BUY, RecommendationType.STRONG_BUY}
            _LESS_FAVORABLE = {RecommendationType.HOLD, RecommendationType.SELL, RecommendationType.STRONG_SELL}
            prev_buy = next(
                (p.recommendation_type for p in prev_live
                 if p.recommendation_type in _BUY_SIDE), None
            )
            superseded = await session.execute(
                sa_update(Recommendation)
                .where(
                    Recommendation.symbol == state["asset_symbol"],
                    Recommendation.status.in_([
                        RecommendationStatus.APPROVED,
                        RecommendationStatus.PRESENTED_TO_USER,
                        RecommendationStatus.ACTIONED,  # superseded by fresher analysis
                    ]),
                )
                .values(status=RecommendationStatus.DISMISSED)
            )
            if superseded.rowcount:
                logger.info(
                    "Superseded stale recommendations",
                    symbol=state["asset_symbol"], count=superseded.rowcount,
                )
            # Remember if we just downgraded a live BUY into something less
            # favorable (HOLD or SELL) so notify_users alerts holders/watchers.
            if prev_buy and rec_type in _LESS_FAVORABLE:
                state = {**state, "_downgraded_from": prev_buy.value}

            recommendation = Recommendation(
                asset_id=asset.id,
                symbol=state["asset_symbol"],
                recommendation_type=rec_type,
                status=RecommendationStatus.APPROVED,
                confidence_score=float(senior.get("decision_confidence", 0)),
                target_price=senior.get("final_target_price") or fundamental.get("target_price"),
                stop_loss=senior.get("final_stop_loss") or fundamental.get("stop_loss"),
                current_price_at_recommendation=raw.get("price"),
                data_fetcher_raw={
                    "price": raw.get("price"),
                    "market_cap": raw.get("market_cap"),
                    "pe_ratio": raw.get("pe_ratio"),
                    # Beta is fetched on every run and was dropped here, so the
                    # card had no volatility figure to show even for a stock
                    # that had just been analysed.
                    "beta": raw.get("beta"),
                    "sentiment": raw.get("social_sentiment"),
                    "fetch_timestamp": raw.get("fetch_timestamp"),
                    "fetch_errors": raw.get("fetch_errors"),
                    "news_analysis": state.get("news_analysis"),
                    "macro_analysis": state.get("macro_analysis"),
                },
                fundamental_analysis={
                    "recommendation_type": fundamental.get("recommendation_type"),
                    "confidence_score": fundamental.get("confidence_score"),
                    "valuation_assessment": fundamental.get("valuation_assessment"),
                    "financial_health": fundamental.get("financial_health"),
                    "key_metrics_summary": fundamental.get("key_metrics_summary"),
                    "bull_case": fundamental.get("bull_case"),
                    "bear_case": fundamental.get("bear_case"),
                    "risk_factors": fundamental.get("risk_factors"),
                    "catalysts": fundamental.get("catalysts"),
                    "short_catalysts": fundamental.get("short_catalysts"),
                    "investment_horizon": fundamental.get("investment_horizon"),
                    "thesis": fundamental.get("thesis"),
                    "sector_comparison": fundamental.get("sector_comparison"),
                    "analyst_notes": fundamental.get("analyst_notes"),
                    "data_completeness": fundamental.get("data_completeness"),
                    # 5-criterion upgrade fields
                    "hard_exclusions_triggered": fundamental.get("hard_exclusions_triggered"),
                    "auto_disqualified": fundamental.get("auto_disqualified"),
                    "moat_classification": fundamental.get("moat_classification"),
                    "moat_evidence": fundamental.get("moat_evidence"),
                    "catalyst_validation": fundamental.get("catalyst_validation"),
                    "scenario_analysis": fundamental.get("scenario_analysis"),
                    "thesis_breakers": fundamental.get("thesis_breakers"),
                    "expected_value": fundamental.get("expected_value"),
                    "expected_value_vs_current_pct": fundamental.get("expected_value_vs_current_pct"),
                    "allocation_recommendation": fundamental.get("allocation_recommendation"),
                    "suggested_weight_range": fundamental.get("suggested_weight_range"),
                    # Quantitative models
                    "quantitative_models": fundamental.get("quantitative_models"),
                },
                fundamental_notes=fundamental.get("analyst_notes"),
                sentiment_data=raw.get("social_sentiment"),
                senior_review_notes=senior.get("approval_reasoning"),
                senior_notes=senior.get("senior_notes"),
                senior_approved_by="senior_committee_v1",
                risk_factors=fundamental.get("risk_factors"),
                expected_return_pct=fundamental.get("expected_return_pct"),
                trigger_type=state.get("trigger_type", "SCHEDULED"),
                trigger_details=state.get("trigger_details"),
                approved_at=datetime.now(timezone.utc),
            )

            session.add(recommendation)
            await session.flush()
            rec_id = recommendation.id
            await session.commit()

        logger.info("Recommendation saved", symbol=state["asset_symbol"], rec_id=rec_id)

        return {
            **state,
            "recommendation_id": rec_id,
            "workflow_status": "saved",
            "completed_at": datetime.now(timezone.utc).isoformat(),
        }

    except Exception as e:
        logger.error("save_recommendation failed", error=str(e))
        return {**state, "workflow_status": "failed", "error": f"Save failed: {e}"}


async def _notify_recommendation_removed(symbol: str, old_type: str, new_type: str,
                                         notes: str, current_price=None) -> None:
    """Alert holders + technical-alert watchlisters that the committee walked
    back a BUY on a stock they own/watch. Message severity matches the new
    state: HOLD = calm ("no longer a buy, reconsider"), SELL = urgent
    ("turned negative, consider selling"), rejection = moderate. Holders also
    see their own P&L so they can decide fast."""
    from app.core.database import AsyncSessionLocal
    from app.db.models.portfolio import Portfolio
    from app.db.models.watchlist import Watchlist
    from app.db.models.notification import NotificationType
    from app.services.notifications.service import NotificationService
    from sqlalchemy import select

    old_label = {"BUY": "📈 קנייה", "STRONG_BUY": "🚀 קנייה חזקה"}.get(old_type, old_type)
    nt = (new_type or "").upper()
    urgent = nt in ("SELL", "STRONG_SELL")
    if urgent:
        headline = f"🔴 {symbol}: ההמלצה התהפכה למכירה"
        action = "הוועדה הפכה שלילית על המניה — שקול למכור, לא להחזיק."
    elif nt in ("REJECTED", "REJECT"):
        headline = f"🔻 {symbol}: ההמלצה בוטלה"
        action = "המניה כבר לא עומדת בקריטריונים של הוועדה. שקול לבחון מחדש את הפוזיציה."
    else:  # HOLD
        headline = f"🔻 {symbol}: כבר לא {old_label} — עברה ל'החזק'"
        action = "אין סיבה חדה למכור, אבל גם לא לקנות עוד. סביר להמשיך להחזיק ולעקוב."

    try:
        async with AsyncSessionLocal() as db:
            hp = await db.execute(
                select(Portfolio.user_id, Portfolio.avg_buy_price)
                .where(Portfolio.symbol == symbol, Portfolio.quantity > 0)
            )
            holder_avg = {r[0]: r[1] for r in hp.all()}
            watchers = await db.execute(
                select(Watchlist.user_id).where(
                    Watchlist.symbol == symbol, Watchlist.alert_on_technical_signal == True
                ).distinct()
            )
            watcher_ids = {r[0] for r in watchers.all()}
            user_ids = list(set(holder_avg) | watcher_ids)
            if not user_ids:
                return
            reason = f" הסיבה: {notes.strip()}" if notes and notes.strip() else ""
            svc = NotificationService()
            for uid in user_ids:
                pnl = ""
                avg = holder_avg.get(uid)
                if avg and current_price:
                    pct = (current_price - avg) / avg * 100 if avg else 0
                    sign = "+" if pct >= 0 else ""
                    pnl = (f" | הפוזיציה שלך: קנית ב-${avg:.2f}, מחיר נוכחי ${current_price:.2f} "
                           f"({sign}{pct:.1f}%)")
                title = f"{headline}{pnl}.{reason} 👈 פתח את הניתוח המלא כדי להחליט."
                await svc.send_notification(
                    user_id=uid, recommendation_id=None,
                    internal_detail={"symbol": symbol, "signal": "REMOVED",
                                     "previous_signal": old_type, "new_state": nt,
                                     "senior_notes": notes, "trigger": "REC_REMOVED"},
                    db=db, notification_type=NotificationType.ALERT, title=title,
                )
        logger.info("Notified rec downgrade", symbol=symbol, old=old_type, new=nt, users=len(user_ids))
    except Exception as e:
        logger.warning("rec-downgrade notify failed", symbol=symbol, error=str(e))


_REC_LABELS = {
    "STRONG_BUY":  "🚀 קנייה חזקה",
    "BUY":         "📈 קנייה",
    "SELL":        "📉 מכירה",
    "STRONG_SELL": "⚠️ מכירה חזקה",
}


def _new_rec_title(state: AgentWorkflowState, recommendation) -> str:
    """One line saying what the committee decided and on what.

    This alert was the only one sent without a title, so it fell back to the
    generic "עדכון השקעות" — the inbox showed the same five words against
    every new recommendation, and the reader had to open each one to find out
    which stock it was about, let alone whether to buy or sell.
    """
    senior = state.get("senior_decision") or {}
    rec_type = senior.get("final_recommendation", "")
    symbol = state["asset_symbol"]
    label = _REC_LABELS.get(rec_type, rec_type)

    parts = [f"{label} — {symbol}"]

    price = (state.get("data_fetcher_output") or {}).get("price")
    if price:
        parts.append(f"מחיר נוכחי ${price:,.2f}")

    target = getattr(recommendation, "target_price", None) if recommendation else None
    if target and price:
        pct = (target - price) / price * 100
        parts.append(f"יעד ${target:,.2f} ({pct:+.0f}%)")
    elif target:
        parts.append(f"יעד ${target:,.2f}")

    conf = senior.get("decision_confidence")
    if conf:
        parts.append(f"ביטחון {float(conf):.0f}%")

    return " | ".join(parts) + " 👈 פתח את דוח המחקר המלא."


async def node_notify_users(state: AgentWorkflowState) -> AgentWorkflowState:
    """Node 4b: Notify eligible users about new recommendation."""
    logger.info("Workflow node: notify_users", rec_id=state.get("recommendation_id"))

    rec_id = state.get("recommendation_id")
    if not rec_id:
        return {**state, "workflow_status": "completed"}

    # HOLD approvals stay in the feed/scan-log but never page anyone —
    # "do nothing" is not an actionable alert worth waking users for.
    rec_type = (state.get("senior_decision") or {}).get("final_recommendation", "")

    # Downgrade alert to holders/watchers — fires whenever a live BUY was
    # walked back (→ HOLD or → SELL). Runs before the HOLD early-return so
    # the SELL case gets the personalized alert (with P&L) too.
    if state.get("_downgraded_from"):
        await _notify_recommendation_removed(
            state["asset_symbol"], state["_downgraded_from"], rec_type,
            (state.get("senior_decision") or {}).get("senior_notes") or "",
            (state.get("data_fetcher_output") or {}).get("price"),
        )

    if rec_type not in ("BUY", "STRONG_BUY", "SELL", "STRONG_SELL"):
        logger.info("notify_users skipped for non-actionable recommendation", rec_type=rec_type)
        return {**state, "workflow_status": "completed"}

    try:
        from app.services.notifications.service import NotificationService
        from app.core.database import AsyncSessionLocal
        from app.db.models.user import User
        from app.db.models.recommendation import Recommendation
        from sqlalchemy import select

        notification_service = NotificationService()

        async with AsyncSessionLocal() as session:
            rec_result = await session.execute(
                select(Recommendation).where(Recommendation.id == rec_id)
            )
            recommendation = rec_result.scalar_one_or_none()

            users_result = await session.execute(
                select(User).where(User.is_active == True, User.is_onboarded == True)
            )
            users = users_result.scalars().all()

            for user in users:
                try:
                    internal_detail = {
                        "recommendation_id": rec_id,
                        "symbol": state["asset_symbol"],
                        "recommendation_type": state["senior_decision"].get("final_recommendation"),
                        "confidence_score": state["senior_decision"].get("decision_confidence"),
                        "target_price": recommendation.target_price if recommendation else None,
                        "stop_loss": recommendation.stop_loss if recommendation else None,
                        "fundamental_analysis": state.get("fundamental_analysis"),
                        "senior_notes": state["senior_decision"].get("senior_notes"),
                        "trigger_type": state.get("trigger_type", "SCHEDULED"),
                        "trigger_details": state.get("trigger_details"),
                        "sentiment_summary": {
                            "score": (state["data_fetcher_output"].get("social_sentiment") or {}).get("score"),
                            "mentions": (state["data_fetcher_output"].get("social_sentiment") or {}).get("mentions"),
                        },
                    }
                    await notification_service.send_notification(
                        user_id=user.id,
                        recommendation_id=rec_id,
                        internal_detail=internal_detail,
                        db=session,
                        title=_new_rec_title(state, recommendation),
                    )
                except Exception as ue:
                    logger.warning("Failed to notify user", user_id=user.id, error=str(ue))

        return {**state, "workflow_status": "completed"}

    except Exception as e:
        logger.error("notify_users failed", error=str(e))
        return {**state, "workflow_status": "completed"}  # Don't fail workflow on notification error


async def node_log_rejection(state: AgentWorkflowState) -> AgentWorkflowState:
    """Node 4c: Log rejected recommendations for audit trail."""
    logger.info(
        "Workflow node: log_rejection",
        symbol=state["asset_symbol"],
        reason=(state.get("senior_decision") or {}).get("rejection_reasoning"),
    )

    try:
        from app.core.database import AsyncSessionLocal
        from app.db.models.recommendation import Recommendation, RecommendationStatus, RecommendationType
        from app.db.models.asset import Asset
        from sqlalchemy import select

        senior = state.get("senior_decision") or {}
        fundamental = state.get("fundamental_analysis") or {}
        raw = state.get("data_fetcher_output") or {}

        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(Asset).where(Asset.symbol == state["asset_symbol"])
            )
            asset = result.scalar_one_or_none()

            if asset:
                rec_type_str = senior.get("final_recommendation", "HOLD")
                try:
                    rec_type = RecommendationType(rec_type_str)
                except ValueError:
                    rec_type = RecommendationType.HOLD

                rejected_rec = Recommendation(
                    asset_id=asset.id,
                    symbol=state["asset_symbol"],
                    recommendation_type=rec_type,
                    status=RecommendationStatus.REJECTED,
                    confidence_score=float(senior.get("decision_confidence", 0)),
                    data_fetcher_raw={"price": raw.get("price"), "fetch_timestamp": raw.get("fetch_timestamp")},
                    fundamental_analysis={"confidence_score": fundamental.get("confidence_score")},
                    senior_review_notes=senior.get("rejection_reasoning"),
                    senior_notes=senior.get("senior_notes"),
                    trigger_type=state.get("trigger_type", "SCHEDULED"),
                    trigger_details=state.get("trigger_details"),
                )
                session.add(rejected_rec)

                # If this is a GENUINE rejection (not an engine-down 0.0
                # fallback) that overturned a live BUY/SELL, supersede the
                # stale rec and tell holders it's no longer recommended.
                fconf = fundamental.get("confidence_score")
                engine_down = (
                    fconf == 0.0
                    and str(fundamental.get("analyst_notes", "")).startswith("Analysis failed")
                )
                # A data outage is not a verdict either. Without this, a stock
                # whose price we simply could not fetch would have its live
                # recommendation cancelled and its holders told it "no longer
                # meets the criteria" — on no evidence at all.
                data_outage = bool(state.get("data_fetcher_error"))
                genuine = not (engine_down or data_outage)
                downgraded_from = None
                if genuine:
                    from sqlalchemy import update as sa_update
                    _ACT = {RecommendationType.BUY, RecommendationType.STRONG_BUY,
                            RecommendationType.SELL, RecommendationType.STRONG_SELL}
                    prev_live = (await session.execute(
                        select(Recommendation).where(
                            Recommendation.symbol == state["asset_symbol"],
                            Recommendation.status.in_([
                                RecommendationStatus.APPROVED,
                                RecommendationStatus.PRESENTED_TO_USER,
                                RecommendationStatus.ACTIONED,
                            ]),
                        )
                    )).scalars().all()
                    downgraded_from = next(
                        (p.recommendation_type.value for p in prev_live
                         if p.recommendation_type in _ACT), None
                    )
                    if prev_live:
                        await session.execute(
                            sa_update(Recommendation)
                            .where(
                                Recommendation.symbol == state["asset_symbol"],
                                Recommendation.status.in_([
                                    RecommendationStatus.APPROVED,
                                    RecommendationStatus.PRESENTED_TO_USER,
                                    RecommendationStatus.ACTIONED,
                                ]),
                            )
                            .values(status=RecommendationStatus.DISMISSED)
                        )
                await session.commit()

                if downgraded_from:
                    await _notify_recommendation_removed(
                        state["asset_symbol"], downgraded_from, "REJECTED",
                        senior.get("rejection_reasoning") or "", raw.get("price"),
                    )

    except Exception as e:
        logger.warning("log_rejection failed", error=str(e))

    return {
        **state,
        "workflow_status": "rejected_logged",
        "completed_at": datetime.now(timezone.utc).isoformat(),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Routing functions
# ─────────────────────────────────────────────────────────────────────────────

def route_after_senior(state: AgentWorkflowState) -> str:
    """Route based on senior committee decision."""
    if state.get("workflow_status") == "failed":
        return "log_rejection"
    senior = state.get("senior_decision") or {}
    if senior.get("approved"):
        return "save_recommendation"
    return "log_rejection"


def route_after_fetch(state: AgentWorkflowState) -> str:
    """Route after data fetching - fail fast if no data."""
    if state.get("workflow_status") == "failed" or state.get("data_fetcher_error"):
        return "log_rejection"
    return "enrich_data"


def route_after_enrich(state: AgentWorkflowState) -> str:
    """Route after enrichment — always continue to fundamental (enrichment failures are non-fatal)."""
    if state.get("workflow_status") == "failed":
        return "log_rejection"
    return "run_fundamental"


def route_after_fundamental(state: AgentWorkflowState) -> str:
    """Route after fundamental analysis."""
    if state.get("workflow_status") == "failed" or state.get("fundamental_error"):
        return "log_rejection"
    return "senior_review"


# ─────────────────────────────────────────────────────────────────────────────
# Build main workflow graph
# ─────────────────────────────────────────────────────────────────────────────

def build_main_workflow() -> StateGraph:
    """Build and compile the main 3-agent investment workflow."""
    workflow = StateGraph(AgentWorkflowState)

    # Add nodes
    workflow.add_node("fetch_data", node_fetch_data)
    workflow.add_node("enrich_data", node_enrich_data)
    workflow.add_node("run_fundamental", node_fundamental_analysis)
    workflow.add_node("senior_review", node_senior_review)
    workflow.add_node("save_recommendation", node_save_recommendation)
    workflow.add_node("notify_users", node_notify_users)
    workflow.add_node("log_rejection", node_log_rejection)

    # Set entry point
    workflow.set_entry_point("fetch_data")

    # Add conditional edges
    workflow.add_conditional_edges(
        "fetch_data",
        route_after_fetch,
        {
            "enrich_data": "enrich_data",
            "log_rejection": "log_rejection",
        }
    )

    workflow.add_conditional_edges(
        "enrich_data",
        route_after_enrich,
        {
            "run_fundamental": "run_fundamental",
            "log_rejection": "log_rejection",
        }
    )

    workflow.add_conditional_edges(
        "run_fundamental",
        route_after_fundamental,
        {
            "senior_review": "senior_review",
            "log_rejection": "log_rejection",
        }
    )

    workflow.add_conditional_edges(
        "senior_review",
        route_after_senior,
        {
            "save_recommendation": "save_recommendation",
            "log_rejection": "log_rejection",
        }
    )

    # Linear edges for approved path
    workflow.add_edge("save_recommendation", "notify_users")
    workflow.add_edge("notify_users", END)
    workflow.add_edge("log_rejection", END)

    return workflow.compile()


# ─────────────────────────────────────────────────────────────────────────────
# Technical workflow for on-demand analysis
# ─────────────────────────────────────────────────────────────────────────────

async def node_technical_fetch_and_analyze(state: TechnicalWorkflowState) -> TechnicalWorkflowState:
    """Single-node technical analysis workflow."""
    logger.info("Technical workflow: fetch_and_analyze", symbol=state["asset_symbol"])
    try:
        agent = get_technical_agent()
        analysis = await agent.analyze(
            symbol=state["asset_symbol"],
            exchange=state["exchange"],
            fallback_price=state.get("fallback_price"),
        )
        return {
            **state,
            "technical_analysis": analysis,
            "error": None,
            "workflow_status": "completed",
        }
    except Exception as e:
        logger.error("Technical analysis workflow failed", error=str(e))
        return {
            **state,
            "error": str(e),
            "workflow_status": "failed",
        }


async def node_save_technical_result(state: TechnicalWorkflowState) -> TechnicalWorkflowState:
    """Save technical analysis result to watchlist item."""
    if not state.get("technical_analysis"):
        return {**state, "workflow_status": "completed"}

    try:
        from app.core.database import AsyncSessionLocal
        from app.db.models.watchlist import Watchlist
        from sqlalchemy import select

        watchlist_id = state.get("watchlist_item_id")
        if not watchlist_id:
            return {**state, "workflow_status": "completed"}

        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(Watchlist).where(Watchlist.id == watchlist_id)
            )
            item = result.scalar_one_or_none()
            if item:
                item.last_technical_analysis = state["technical_analysis"]
                item.last_signal_sent_at = datetime.now(timezone.utc)
                await session.commit()

    except Exception as e:
        logger.warning("Failed to save technical result", error=str(e))

    return {**state, "workflow_status": "completed"}


def build_technical_workflow() -> StateGraph:
    """Build the on-demand technical analysis workflow."""
    workflow = StateGraph(TechnicalWorkflowState)

    workflow.add_node("analyze", node_technical_fetch_and_analyze)
    workflow.add_node("save_result", node_save_technical_result)

    workflow.set_entry_point("analyze")
    workflow.add_edge("analyze", "save_result")
    workflow.add_edge("save_result", END)

    return workflow.compile()


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

# Compiled workflow singletons
_main_workflow = None
_technical_workflow = None


def get_main_workflow():
    global _main_workflow
    if _main_workflow is None:
        _main_workflow = build_main_workflow()
    return _main_workflow


def get_technical_workflow():
    global _technical_workflow
    if _technical_workflow is None:
        _technical_workflow = build_technical_workflow()
    return _technical_workflow


async def run_investment_workflow(
    symbol: str,
    exchange: str,
    portfolio_context: Optional[Dict[str, Any]] = None,
    user_risk_context: Optional[Dict[str, Any]] = None,
    trigger_type: Optional[str] = "SCHEDULED",
    trigger_details: Optional[str] = None,
    direction_bias: Optional[str] = None,
    language: str = "he",
) -> AgentWorkflowState:
    """
    Entry point for the main investment analysis workflow.
    Called by Celery workers for scheduled scanning or event-triggered scans.
    """
    workflow = get_main_workflow()

    initial_state: AgentWorkflowState = {
        "asset_symbol": symbol,
        "exchange": exchange,
        "data_fetcher_output": None,
        "data_fetcher_error": None,
        "news_analysis": None,
        "macro_analysis": None,
        "enrichment_error": None,
        "fundamental_analysis": None,
        "fundamental_error": None,
        "senior_decision": None,
        "senior_error": None,
        "technical_analysis": None,
        "technical_error": None,
        "workflow_status": "running",
        "workflow_id": str(uuid.uuid4()),
        "started_at": datetime.now(timezone.utc).isoformat(),
        "completed_at": None,
        "error": None,
        "recommendation_id": None,
        "portfolio_context": portfolio_context,
        "user_risk_context": user_risk_context,
        "trigger_type": trigger_type,
        "trigger_details": trigger_details,
        "direction_bias": direction_bias,
        "language": language,
    }

    final_state = await workflow.ainvoke(initial_state)
    return final_state


async def run_technical_workflow(
    symbol: str,
    exchange: str,
    watchlist_item_id: Optional[int] = None,
    user_id: Optional[int] = None,
    fallback_price: Optional[float] = None,
    language: str = "en",
) -> TechnicalWorkflowState:
    """
    Entry point for on-demand technical analysis.
    Called from watchlist API endpoints.
    """
    workflow = get_technical_workflow()

    initial_state: TechnicalWorkflowState = {
        "asset_symbol": symbol,
        "exchange": exchange,
        "historical_data": None,
        "technical_analysis": None,
        "error": None,
        "workflow_status": "running",
        "watchlist_item_id": watchlist_item_id,
        "user_id": user_id,
        "fallback_price": fallback_price,
        "language": language,
    }

    final_state = await workflow.ainvoke(initial_state)
    return final_state
