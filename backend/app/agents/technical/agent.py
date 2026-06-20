"""
Technical Analyst Agent
On-demand agent that performs technical analysis using pandas-ta.
Calculates RSI, MACD, Bollinger Bands, Moving Averages, support/resistance levels.
"""
import asyncio
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
import numpy as np
import pandas as pd
import structlog

try:
    import pandas_ta as ta
    HAS_PANDAS_TA = True
except ImportError:
    HAS_PANDAS_TA = False

from app.core.config import settings
from app.services.market_data.yahoo_service import YahooFinanceService
from app.services.market_data.tase_service import TASEService

logger = structlog.get_logger(__name__)


class TechnicalAnalystAgent:
    """
    Technical Analyst - performs chart-based technical analysis on price history.
    Called on-demand for watchlist items or when senior committee requests timing analysis.
    """

    def __init__(self):
        self.yahoo_service = YahooFinanceService()
        self.tase_service = TASEService()

    async def analyze(self, symbol: str, exchange: str, period: str = "6mo", fallback_price: float | None = None) -> Dict[str, Any]:
        """
        Main analysis method. Fetches historical data and computes all technical indicators.
        Returns structured technical analysis dict.
        """
        logger.info("TechnicalAnalystAgent starting", symbol=symbol, exchange=exchange)

        try:
            # Fetch historical price data
            is_tase = exchange == "TASE"
            if is_tase:
                df = await self.tase_service.get_tase_historical(symbol)
            else:
                df = await self.yahoo_service.get_historical_prices(symbol, period)

            if df is None or df.empty:
                logger.warning("No historical price bars, falling back to info-derived analysis", symbol=symbol)
                return await self._analyze_from_info(symbol, exchange, fallback_price=fallback_price)

            # Ensure required columns
            required_cols = ["Open", "High", "Low", "Close", "Volume"]
            for col in required_cols:
                if col not in df.columns:
                    return self._error_result(symbol, f"Missing column: {col}")

            df = df.dropna(subset=["Close"]).copy()

            if len(df) < 50:
                return self._error_result(symbol, f"Insufficient data: only {len(df)} bars")

            # Calculate all indicators
            indicators = self._calculate_indicators(df)
            support, resistance = self._find_support_resistance(df)
            patterns = self._detect_patterns(df)
            signal = self._determine_signal(indicators, support, resistance, df)

            result = {
                "symbol": symbol,
                "exchange": exchange,
                "analysis_timestamp": datetime.now(timezone.utc).isoformat(),
                "current_price": float(df["Close"].iloc[-1]),
                "previous_close": float(df["Close"].iloc[-2]) if len(df) > 1 else None,
                "price_change_pct": float(
                    ((df["Close"].iloc[-1] - df["Close"].iloc[-2]) / df["Close"].iloc[-2] * 100)
                    if len(df) > 1 else 0.0
                ),
                # RSI
                "rsi_14": indicators.get("rsi_14"),
                "rsi_signal": self._rsi_signal(indicators.get("rsi_14")),
                # MACD
                "macd": indicators.get("macd"),
                "macd_signal": indicators.get("macd_signal"),
                "macd_histogram": indicators.get("macd_histogram"),
                "macd_crossover": indicators.get("macd_crossover"),
                # Bollinger Bands
                "bb_upper": indicators.get("bb_upper"),
                "bb_middle": indicators.get("bb_middle"),
                "bb_lower": indicators.get("bb_lower"),
                "bb_position": indicators.get("bb_position"),  # % position within bands
                "bb_squeeze": indicators.get("bb_squeeze"),
                # Moving Averages
                "ma_20": indicators.get("ma_20"),
                "ma_50": indicators.get("ma_50"),
                "ma_200": indicators.get("ma_200"),
                "ma_trend": indicators.get("ma_trend"),
                "golden_cross": indicators.get("golden_cross"),
                "death_cross": indicators.get("death_cross"),
                # Volume
                "volume_sma_20": indicators.get("volume_sma_20"),
                "current_volume": int(df["Volume"].iloc[-1]),
                "volume_ratio": indicators.get("volume_ratio"),
                # ATR
                "atr_14": indicators.get("atr_14"),
                "atr_pct": indicators.get("atr_pct"),
                # Support / Resistance
                "support_levels": support,
                "resistance_levels": resistance,
                "nearest_support": max(support, default=None) if support else None,
                "nearest_resistance": min(resistance, default=None) if resistance else None,
                # Patterns
                "chart_patterns": patterns,
                # Overall Signal
                "timing_signal": signal["signal"],   # BUY_NOW | SELL_NOW | WAIT | STRONG_BUY | STRONG_SELL
                "entry_price": signal.get("entry_price"),
                "technical_score": signal["score"],  # 0-100
                "signal_strength": signal["strength"],  # WEAK | MODERATE | STRONG
                "signal_reasoning": signal["reasoning"],
                "data_bars": len(df),
            }

            logger.info(
                "TechnicalAnalystAgent completed",
                symbol=symbol,
                signal=result["timing_signal"],
                score=result["technical_score"],
                rsi=result["rsi_14"],
            )

            return result

        except Exception as e:
            logger.error("Technical analysis failed", symbol=symbol, error=str(e))
            return self._error_result(symbol, str(e))

    def _calculate_indicators(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Calculate all technical indicators using pandas-ta."""
        indicators: Dict[str, Any] = {}
        close = df["Close"]
        high = df["High"]
        low = df["Low"]
        volume = df["Volume"]

        try:
            if HAS_PANDAS_TA:
                # RSI
                rsi = ta.rsi(close, length=14)
                indicators["rsi_14"] = float(rsi.iloc[-1]) if rsi is not None and not rsi.empty else None

                # MACD
                macd_result = ta.macd(close, fast=12, slow=26, signal=9)
                if macd_result is not None and not macd_result.empty:
                    indicators["macd"] = float(macd_result["MACD_12_26_9"].iloc[-1])
                    indicators["macd_signal"] = float(macd_result["MACDs_12_26_9"].iloc[-1])
                    indicators["macd_histogram"] = float(macd_result["MACDh_12_26_9"].iloc[-1])
                    # Check for crossover in last 2 bars
                    prev_macd = macd_result["MACD_12_26_9"].iloc[-2]
                    prev_sig = macd_result["MACDs_12_26_9"].iloc[-2]
                    curr_macd = macd_result["MACD_12_26_9"].iloc[-1]
                    curr_sig = macd_result["MACDs_12_26_9"].iloc[-1]
                    if prev_macd < prev_sig and curr_macd >= curr_sig:
                        indicators["macd_crossover"] = "BULLISH"
                    elif prev_macd > prev_sig and curr_macd <= curr_sig:
                        indicators["macd_crossover"] = "BEARISH"
                    else:
                        indicators["macd_crossover"] = "NONE"

                # Bollinger Bands
                bb = ta.bbands(close, length=20, std=2)
                if bb is not None and not bb.empty:
                    indicators["bb_upper"] = float(bb["BBU_20_2.0"].iloc[-1])
                    indicators["bb_middle"] = float(bb["BBM_20_2.0"].iloc[-1])
                    indicators["bb_lower"] = float(bb["BBL_20_2.0"].iloc[-1])
                    curr_price = float(close.iloc[-1])
                    bb_range = indicators["bb_upper"] - indicators["bb_lower"]
                    if bb_range > 0:
                        indicators["bb_position"] = (curr_price - indicators["bb_lower"]) / bb_range * 100
                    else:
                        indicators["bb_position"] = 50.0
                    # Squeeze: bands narrow < 5% of price
                    indicators["bb_squeeze"] = bb_range < (curr_price * 0.05)

                # Moving Averages
                ma_20 = ta.sma(close, length=20)
                ma_50 = ta.sma(close, length=50)
                ma_200 = ta.sma(close, length=200)

                indicators["ma_20"] = float(ma_20.iloc[-1]) if ma_20 is not None and not ma_20.empty else None
                indicators["ma_50"] = float(ma_50.iloc[-1]) if ma_50 is not None and not ma_50.empty else None
                indicators["ma_200"] = float(ma_200.iloc[-1]) if ma_200 is not None and not ma_200.empty else None

                if indicators["ma_50"] and indicators["ma_200"]:
                    if indicators["ma_50"] > indicators["ma_200"]:
                        indicators["ma_trend"] = "BULLISH"
                    else:
                        indicators["ma_trend"] = "BEARISH"

                    # Golden/Death cross detection (last 5 bars)
                    if len(df) > 5 and ma_50 is not None and ma_200 is not None:
                        prev_ma50 = float(ma_50.iloc[-5]) if len(ma_50) > 5 else None
                        prev_ma200 = float(ma_200.iloc[-5]) if len(ma_200) > 5 else None
                        if prev_ma50 and prev_ma200:
                            if prev_ma50 < prev_ma200 and indicators["ma_50"] > indicators["ma_200"]:
                                indicators["golden_cross"] = True
                                indicators["death_cross"] = False
                            elif prev_ma50 > prev_ma200 and indicators["ma_50"] < indicators["ma_200"]:
                                indicators["golden_cross"] = False
                                indicators["death_cross"] = True
                            else:
                                indicators["golden_cross"] = False
                                indicators["death_cross"] = False

                # ATR
                atr = ta.atr(high, low, close, length=14)
                if atr is not None and not atr.empty:
                    indicators["atr_14"] = float(atr.iloc[-1])
                    if float(close.iloc[-1]) > 0:
                        indicators["atr_pct"] = indicators["atr_14"] / float(close.iloc[-1]) * 100

                # Volume SMA
                vol_sma = ta.sma(volume, length=20)
                if vol_sma is not None and not vol_sma.empty:
                    indicators["volume_sma_20"] = float(vol_sma.iloc[-1])
                    if indicators["volume_sma_20"] > 0:
                        indicators["volume_ratio"] = float(volume.iloc[-1]) / indicators["volume_sma_20"]

            else:
                # Fallback manual calculations if pandas-ta not available
                indicators = self._manual_indicators(df)

        except Exception as e:
            logger.warning("Error calculating indicators", error=str(e))
            indicators = self._manual_indicators(df)

        return indicators

    def _manual_indicators(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Manual indicator calculations as fallback."""
        close = df["Close"]
        indicators: Dict[str, Any] = {}

        # RSI manual
        delta = close.diff()
        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)
        avg_gain = gain.rolling(14).mean()
        avg_loss = loss.rolling(14).mean()
        rs = avg_gain / avg_loss.replace(0, 1e-10)
        rsi = 100 - (100 / (1 + rs))
        indicators["rsi_14"] = float(rsi.iloc[-1]) if not pd.isna(rsi.iloc[-1]) else None

        # Simple MAs
        for period in [20, 50, 200]:
            if len(close) >= period:
                ma = close.rolling(period).mean()
                indicators[f"ma_{period}"] = float(ma.iloc[-1])

        # MACD
        ema12 = close.ewm(span=12).mean()
        ema26 = close.ewm(span=26).mean()
        macd_line = ema12 - ema26
        signal_line = macd_line.ewm(span=9).mean()
        indicators["macd"] = float(macd_line.iloc[-1])
        indicators["macd_signal"] = float(signal_line.iloc[-1])
        indicators["macd_histogram"] = float((macd_line - signal_line).iloc[-1])

        # Volume
        vol_sma = df["Volume"].rolling(20).mean()
        indicators["volume_sma_20"] = float(vol_sma.iloc[-1]) if not pd.isna(vol_sma.iloc[-1]) else None
        if indicators.get("volume_sma_20") and indicators["volume_sma_20"] > 0:
            indicators["volume_ratio"] = float(df["Volume"].iloc[-1]) / indicators["volume_sma_20"]

        return indicators

    def _find_support_resistance(self, df: pd.DataFrame, lookback: int = 60) -> Tuple[List[float], List[float]]:
        """Find key support and resistance levels using pivot points."""
        support_levels: List[float] = []
        resistance_levels: List[float] = []
        current_price = float(df["Close"].iloc[-1])

        window = min(lookback, len(df))
        recent = df.tail(window).copy()

        # Pivot high/low detection (simple approach)
        for i in range(2, len(recent) - 2):
            high = recent["High"].iloc[i]
            low = recent["Low"].iloc[i]

            # Pivot high (resistance)
            if (high > recent["High"].iloc[i - 1] and
                    high > recent["High"].iloc[i - 2] and
                    high > recent["High"].iloc[i + 1] and
                    high > recent["High"].iloc[i + 2]):
                resistance_levels.append(float(high))

            # Pivot low (support)
            if (low < recent["Low"].iloc[i - 1] and
                    low < recent["Low"].iloc[i - 2] and
                    low < recent["Low"].iloc[i + 1] and
                    low < recent["Low"].iloc[i + 2]):
                support_levels.append(float(low))

        # Filter to levels within ±20% of current price and deduplicate
        price_range = current_price * 0.20
        support_levels = sorted(set(
            round(s, 2) for s in support_levels
            if s < current_price and s > current_price - price_range
        ), reverse=True)[:5]

        resistance_levels = sorted(set(
            round(r, 2) for r in resistance_levels
            if r > current_price and r < current_price + price_range
        ))[:5]

        return support_levels, resistance_levels

    def _detect_patterns(self, df: pd.DataFrame) -> List[str]:
        """Detect basic chart patterns."""
        patterns: List[str] = []
        close = df["Close"]

        if len(close) < 20:
            return patterns

        # Recent trend
        recent_20 = close.tail(20)
        slope = np.polyfit(range(20), recent_20.values, 1)[0]
        if slope > 0:
            patterns.append("UPTREND_20D")
        else:
            patterns.append("DOWNTREND_20D")

        # Oversold/overbought based on position in 52-week range
        high_52w = df["High"].tail(252).max()
        low_52w = df["Low"].tail(252).min()
        current = float(close.iloc[-1])
        range_52w = high_52w - low_52w
        if range_52w > 0:
            position_52w = (current - low_52w) / range_52w
            if position_52w > 0.90:
                patterns.append("NEAR_52W_HIGH")
            elif position_52w < 0.10:
                patterns.append("NEAR_52W_LOW")

        # Volume spike
        vol_avg = df["Volume"].tail(20).mean()
        last_vol = float(df["Volume"].iloc[-1])
        if vol_avg > 0 and last_vol > vol_avg * 2:
            patterns.append("VOLUME_SPIKE")

        return patterns

    def _determine_signal(
        self,
        indicators: Dict[str, Any],
        support: List[float],
        resistance: List[float],
        df: pd.DataFrame,
    ) -> Dict[str, Any]:
        """Compute overall timing signal from all indicators."""
        score = 50.0  # Neutral
        reasons: List[str] = []
        current_price = float(df["Close"].iloc[-1])

        # RSI signals
        rsi = indicators.get("rsi_14")
        if rsi is not None:
            if rsi < 30:
                score += 15
                reasons.append(f"RSI oversold ({rsi:.1f})")
            elif rsi < 40:
                score += 8
                reasons.append(f"RSI approaching oversold ({rsi:.1f})")
            elif rsi > 70:
                score -= 15
                reasons.append(f"RSI overbought ({rsi:.1f})")
            elif rsi > 60:
                score -= 8
                reasons.append(f"RSI approaching overbought ({rsi:.1f})")

        # MACD signals
        macd_cross = indicators.get("macd_crossover")
        macd_hist = indicators.get("macd_histogram")
        if macd_cross == "BULLISH":
            score += 12
            reasons.append("MACD bullish crossover")
        elif macd_cross == "BEARISH":
            score -= 12
            reasons.append("MACD bearish crossover")
        if macd_hist is not None:
            if macd_hist > 0:
                score += 5
            elif macd_hist < 0:
                score -= 5

        # MA trend
        ma_trend = indicators.get("ma_trend")
        if ma_trend == "BULLISH":
            score += 10
            reasons.append("Price above 50MA > 200MA (golden cross zone)")
        elif ma_trend == "BEARISH":
            score -= 10
            reasons.append("50MA below 200MA (death cross zone)")

        if indicators.get("golden_cross"):
            score += 15
            reasons.append("Golden cross just occurred")
        if indicators.get("death_cross"):
            score -= 15
            reasons.append("Death cross just occurred")

        # Bollinger bands
        bb_pos = indicators.get("bb_position")
        if bb_pos is not None:
            if bb_pos < 10:
                score += 10
                reasons.append("Price near lower Bollinger Band (oversold)")
            elif bb_pos > 90:
                score -= 10
                reasons.append("Price near upper Bollinger Band (overbought)")

        # Volume confirmation
        vol_ratio = indicators.get("volume_ratio")
        if vol_ratio is not None and vol_ratio > 1.5:
            reasons.append(f"High volume confirmation ({vol_ratio:.1f}x avg)")

        # Support/resistance context
        if support and current_price <= support[0] * 1.02:
            score += 8
            reasons.append(f"Price near key support ${support[0]:.2f}")
        if resistance and current_price >= resistance[0] * 0.98:
            score -= 8
            reasons.append(f"Price near key resistance ${resistance[0]:.2f}")

        # Clamp score
        score = max(0.0, min(100.0, score))

        # Determine signal
        if score >= 75:
            signal = "STRONG_BUY"
            strength = "STRONG"
        elif score >= 62:
            signal = "BUY_NOW"
            strength = "MODERATE"
        elif score <= 25:
            signal = "STRONG_SELL"
            strength = "STRONG"
        elif score <= 38:
            signal = "SELL_NOW"
            strength = "MODERATE"
        else:
            signal = "WAIT"
            strength = "WEAK"

        # Entry price suggestion
        entry_price = None
        if signal in ("BUY_NOW", "STRONG_BUY"):
            # Suggest slight below current if near support
            entry_price = round(current_price * 0.995, 2)
        elif signal in ("SELL_NOW", "STRONG_SELL"):
            entry_price = round(current_price * 1.005, 2)

        return {
            "signal": signal,
            "score": round(score, 1),
            "strength": strength,
            "entry_price": entry_price,
            "reasoning": "; ".join(reasons) if reasons else "No strong technical signals",
        }

    def _rsi_signal(self, rsi: Optional[float]) -> str:
        if rsi is None:
            return "UNKNOWN"
        if rsi < 30:
            return "OVERSOLD"
        if rsi < 40:
            return "APPROACHING_OVERSOLD"
        if rsi > 70:
            return "OVERBOUGHT"
        if rsi > 60:
            return "APPROACHING_OVERBOUGHT"
        return "NEUTRAL"

    async def _analyze_from_info(self, symbol: str, exchange: str, fallback_price: float | None = None) -> Dict[str, Any]:
        """
        Derive technical signals from yfinance .info when historical OHLCV is unavailable.
        Uses self.yahoo_service.get_stock_info() which uses fast_info (v8) + caching —
        the same reliable path the DataFetcher already uses successfully.
        """
        stock: dict = {}
        try:
            stock = await self.yahoo_service.get_stock_info(symbol)
        except Exception as e:
            logger.warning("get_stock_info failed in info-derived analysis, using fallback", symbol=symbol, error=str(e))

        current = stock.get("price") or 0
        if not current and fallback_price:
            current = fallback_price
            logger.info("Using fallback_price for technical analysis", symbol=symbol, price=current)
        if not current:
            return self._error_result(symbol, "No current price available from any source")

        high_52w = stock.get("fifty_two_week_high") or 0
        low_52w  = stock.get("fifty_two_week_low")  or 0
        short_pct = stock.get("short_interest")
        analyst_rec = stock.get("analyst_recommendation")

        # Try to supplement with MA50/MA200 from raw info
        ma50 = ma200 = year_change = rec_mean = None
        try:
            from app.services.market_data.yahoo_service import _make_session
            import yfinance as yf
            session = _make_session()
            raw = await asyncio.get_event_loop().run_in_executor(
                None, lambda: yf.Ticker(symbol, session=session).info or {}
            )
            ma50        = raw.get("fiftyDayAverage")
            ma200       = raw.get("twoHundredDayAverage")
            year_change = raw.get("52WeekChange")
            rec_mean    = raw.get("recommendationMean")
        except Exception:
            pass

        score = 50.0
        reasons: list = []

        pos_52w: float | None = None
        if high_52w and low_52w and (high_52w - low_52w) > 0:
            pos_52w = (current - low_52w) / (high_52w - low_52w) * 100
            if pos_52w < 25:
                score += 12; reasons.append(f"Near 52w low ({pos_52w:.0f}% range)")
            elif pos_52w > 80:
                score -= 10; reasons.append(f"Near 52w high ({pos_52w:.0f}% range)")

        ma_trend = golden_cross = death_cross = None
        if ma50 and ma200:
            if ma50 > ma200:
                ma_trend, golden_cross, death_cross = "BULLISH", True, False
                score += 10; reasons.append("50MA above 200MA (bullish)")
            else:
                ma_trend, golden_cross, death_cross = "BEARISH", False, True
                score -= 10; reasons.append("50MA below 200MA (bearish)")
        if current and ma50:
            if current > ma50:
                score += 5; reasons.append("Price above 50MA")
            else:
                score -= 5; reasons.append("Price below 50MA")

        if year_change is not None:
            if year_change > 0.25:
                score += 8; reasons.append(f"Strong 52w momentum (+{year_change*100:.0f}%)")
            elif year_change < -0.20:
                score -= 8; reasons.append(f"Weak 52w momentum ({year_change*100:.0f}%)")

        if rec_mean is not None:
            if rec_mean <= 2.0:
                score += 10; reasons.append(f"Strong analyst consensus (mean {rec_mean:.1f})")
            elif rec_mean <= 2.5:
                score += 5;  reasons.append(f"Buy consensus (mean {rec_mean:.1f})")
            elif rec_mean >= 3.5:
                score -= 8;  reasons.append(f"Weak consensus (mean {rec_mean:.1f})")
        elif analyst_rec:
            if analyst_rec in ("buy", "strong_buy"):
                score += 8; reasons.append(f"Analyst: {analyst_rec}")
            elif analyst_rec in ("sell", "strong_sell"):
                score -= 8; reasons.append(f"Analyst: {analyst_rec}")

        if short_pct:
            if short_pct > 0.15:
                score -= 5; reasons.append(f"High short interest ({short_pct*100:.1f}%)")
            elif short_pct < 0.02:
                score += 3; reasons.append(f"Low short interest ({short_pct*100:.1f}%)")

        score = max(0.0, min(100.0, score))

        if score >= 72:   signal, strength = "STRONG_BUY",  "STRONG"
        elif score >= 60: signal, strength = "BUY_NOW",     "MODERATE"
        elif score <= 28: signal, strength = "STRONG_SELL", "STRONG"
        elif score <= 40: signal, strength = "SELL_NOW",    "MODERATE"
        else:             signal, strength = "WAIT",        "WEAK"

        patterns: list = []
        if year_change is not None:
            if year_change > 0.10:  patterns.append("UPTREND_52W")
            elif year_change < -0.10: patterns.append("DOWNTREND_52W")
        if pos_52w is not None:
            if pos_52w < 20:   patterns.append("NEAR_52W_LOW")
            elif pos_52w > 85: patterns.append("NEAR_52W_HIGH")
        if short_pct and short_pct > 0.10:
            patterns.append("HIGH_SHORT_INTEREST")

        return {
            "symbol": symbol,
            "exchange": exchange,
            "analysis_timestamp": datetime.now(timezone.utc).isoformat(),
            "current_price": float(current),
            "rsi_14": round(pos_52w, 1) if pos_52w is not None else None,
            "rsi_signal": "OVERSOLD" if (pos_52w or 50) < 30 else "OVERBOUGHT" if (pos_52w or 50) > 70 else "NEUTRAL",
            "ma_50": float(ma50) if ma50 else None,
            "ma_200": float(ma200) if ma200 else None,
            "ma_trend": ma_trend,
            "golden_cross": golden_cross,
            "death_cross": death_cross,
            "chart_patterns": patterns,
            "support_levels": [round(float(low_52w) * 1.01, 2)] if low_52w else [],
            "resistance_levels": [round(float(high_52w) * 0.99, 2)] if high_52w else [],
            "nearest_support": round(float(low_52w) * 1.01, 2) if low_52w else None,
            "nearest_resistance": round(float(high_52w) * 0.99, 2) if high_52w else None,
            "timing_signal": signal,
            "technical_score": round(score, 1),
            "signal_strength": strength,
            "signal_reasoning": "; ".join(reasons) if reasons else "Derived from static indicators",
            "data_source": "info_derived",
            "data_bars": 0,
            "week52_high": float(high_52w) if high_52w else None,
            "week52_low":  float(low_52w)  if low_52w  else None,
            "week52_change_pct": round(year_change * 100, 1) if year_change is not None else None,
            "analyst_consensus_mean": float(rec_mean) if rec_mean else None,
            "short_interest_pct": round(float(short_pct) * 100, 1) if short_pct else None,
        }

    def _error_result(self, symbol: str, error: str) -> Dict[str, Any]:
        return {
            "symbol": symbol,
            "analysis_timestamp": datetime.now(timezone.utc).isoformat(),
            "error": error,
            "timing_signal": "WAIT",
            "technical_score": 50.0,
            "signal_strength": "WEAK",
            "signal_reasoning": f"Analysis failed: {error}",
            "chart_patterns": [],
            "support_levels": [],
            "resistance_levels": [],
        }


_technical_agent: Optional[TechnicalAnalystAgent] = None


def get_technical_agent() -> TechnicalAnalystAgent:
    global _technical_agent
    if _technical_agent is None:
        _technical_agent = TechnicalAnalystAgent()
    return _technical_agent
