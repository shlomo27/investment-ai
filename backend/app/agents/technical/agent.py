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

            # New analysis modules
            candlestick_data: List[Dict] = []
            fib_data: Dict[str, Any] = {}
            wyckoff: str = "UNKNOWN"
            breakdown: List[Dict] = []
            try:
                candlestick_data = self._detect_candlestick_patterns(df)
            except Exception as e:
                logger.warning("Candlestick detection failed", error=str(e))
            try:
                fib_data = self._fibonacci_levels(df)
            except Exception as e:
                logger.warning("Fibonacci calculation failed", error=str(e))
            try:
                wyckoff = self._wyckoff_phase(df, indicators)
            except Exception as e:
                logger.warning("Wyckoff phase detection failed", error=str(e))
            try:
                breakdown = self._build_analysis_breakdown(indicators, patterns, candlestick_data, fib_data, support, resistance, df)
            except Exception as e:
                logger.warning("Analysis breakdown build failed", error=str(e))

            # Adjust signal score based on candlestick patterns
            try:
                for c in candlestick_data:
                    if c["signal"] == "BULLISH":
                        signal["score"] += 8 if c["strength"] == "STRONG" else 5
                    elif c["signal"] == "BEARISH":
                        signal["score"] -= 8 if c["strength"] == "STRONG" else 5
                signal["score"] = max(0, min(100, signal["score"]))
            except Exception:
                pass

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
                # New analysis modules
                "analysis_breakdown": breakdown,
                "fibonacci_levels": fib_data,
                "candlestick_patterns": [c["name"] for c in candlestick_data],
                "wyckoff_phase": wyckoff,
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
            # force_refresh=True ensures we bypass the 5-min cache so we
            # always get fresh fast_info data (year_high, year_low, MA50/200)
            stock = await self.yahoo_service.get_stock_info(symbol, force_refresh=True)
            logger.info("info-derived: got stock data", symbol=symbol,
                        price=stock.get("price"), high52=stock.get("fifty_two_week_high"),
                        low52=stock.get("fifty_two_week_low"), ma50=stock.get("ma_50"))
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

        # MA50/MA200 now come directly from get_stock_info() via fast_info or Alpha Vantage
        ma50_val  = stock.get("ma_50")  or 0
        ma200_val = stock.get("ma_200") or 0
        ma50:   float | None = float(ma50_val)  if ma50_val  else None
        ma200:  float | None = float(ma200_val) if ma200_val else None
        rec_mean_val = stock.get("recommendation_mean") or 0
        rec_mean: float | None = float(rec_mean_val) if rec_mean_val else None
        year_change: float | None = None

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

        # Simplified analysis breakdown for info-derived analysis
        info_breakdown: list = []
        try:
            if pos_52w is not None:
                range_signal = "BULLISH" if pos_52w < 25 else ("BEARISH" if pos_52w > 80 else "NEUTRAL")
                range_impact = 12 if pos_52w < 25 else (-10 if pos_52w > 80 else 0)
                info_breakdown.append({
                    "name": "52-Week Range",
                    "category": "STRUCTURE",
                    "signal": range_signal,
                    "score_impact": range_impact,
                    "detail": f"Price at {pos_52w:.0f}% of 52-week range",
                })
            if ma_trend:
                ma_signal = "BULLISH" if ma_trend == "BULLISH" else "BEARISH"
                ma_impact = 10 if ma_trend == "BULLISH" else -10
                info_breakdown.append({
                    "name": "Moving Averages",
                    "category": "TREND",
                    "signal": ma_signal,
                    "score_impact": ma_impact,
                    "detail": "50MA above 200MA" if ma_trend == "BULLISH" else "50MA below 200MA",
                })
            if ma50 and current:
                price_vs_ma50_signal = "BULLISH" if current > ma50 else "BEARISH"
                price_vs_ma50_impact = 5 if current > ma50 else -5
                info_breakdown.append({
                    "name": "Price vs 50MA",
                    "category": "TREND",
                    "signal": price_vs_ma50_signal,
                    "score_impact": price_vs_ma50_impact,
                    "detail": f"Price {'above' if current > ma50 else 'below'} 50MA ({ma50:.2f})",
                })
            if year_change is not None:
                yc_signal = "BULLISH" if year_change > 0.25 else ("BEARISH" if year_change < -0.20 else "NEUTRAL")
                yc_impact = 8 if year_change > 0.25 else (-8 if year_change < -0.20 else 0)
                info_breakdown.append({
                    "name": "52-Week Momentum",
                    "category": "MOMENTUM",
                    "signal": yc_signal,
                    "score_impact": yc_impact,
                    "detail": f"52-week price change: {year_change * 100:.1f}%",
                })
            if rec_mean is not None:
                if rec_mean <= 2.0:
                    an_signal, an_impact = "BULLISH", 10
                    an_detail = f"Strong analyst consensus (mean {rec_mean:.1f})"
                elif rec_mean <= 2.5:
                    an_signal, an_impact = "BULLISH", 5
                    an_detail = f"Buy consensus (mean {rec_mean:.1f})"
                elif rec_mean >= 3.5:
                    an_signal, an_impact = "BEARISH", -8
                    an_detail = f"Weak consensus (mean {rec_mean:.1f})"
                else:
                    an_signal, an_impact = "NEUTRAL", 0
                    an_detail = f"Neutral analyst consensus (mean {rec_mean:.1f})"
                info_breakdown.append({
                    "name": "Analyst Consensus",
                    "category": "MOMENTUM",
                    "signal": an_signal,
                    "score_impact": an_impact,
                    "detail": an_detail,
                })
            if short_pct:
                if short_pct > 0.15:
                    si_signal, si_impact = "BEARISH", -5
                    si_detail = f"High short interest ({short_pct * 100:.1f}%)"
                elif short_pct < 0.02:
                    si_signal, si_impact = "BULLISH", 3
                    si_detail = f"Low short interest ({short_pct * 100:.1f}%)"
                else:
                    si_signal, si_impact = "NEUTRAL", 0
                    si_detail = f"Moderate short interest ({short_pct * 100:.1f}%)"
                info_breakdown.append({
                    "name": "Short Interest",
                    "category": "VOLUME",
                    "signal": si_signal,
                    "score_impact": si_impact,
                    "detail": si_detail,
                })
        except Exception as e:
            logger.warning("Error building info-derived breakdown", error=str(e))

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
            "analysis_breakdown": info_breakdown,
        }

    def _detect_candlestick_patterns(self, df: pd.DataFrame) -> List[Dict]:
        """Detect candlestick patterns from the last 5 candles using raw OHLC math."""
        detected: List[Dict] = []
        try:
            if len(df) < 5:
                return detected

            # Determine short-term trend (last 10 candles slope)
            close = df["Close"]
            trend_window = min(10, len(close))
            slope = np.polyfit(range(trend_window), close.tail(trend_window).values, 1)[0]
            in_uptrend = slope > 0
            in_downtrend = slope < 0

            last5 = df.tail(5).reset_index(drop=True)

            for i in range(len(last5)):
                o = float(last5["Open"].iloc[i])
                h = float(last5["High"].iloc[i])
                l = float(last5["Low"].iloc[i])
                c = float(last5["Close"].iloc[i])
                body = abs(c - o)
                candle_range = h - l

                if candle_range <= 0:
                    continue

                upper_wick = h - max(o, c)
                lower_wick = min(o, c) - l

                # Doji: very small body relative to range
                if body < 0.1 * candle_range:
                    detected.append({"name": "DOJI", "signal": "NEUTRAL", "strength": "WEAK"})

                # Hammer: long lower wick, small upper wick, in downtrend
                if body > 0 and lower_wick > 2 * body and upper_wick < 0.3 * body and in_downtrend:
                    detected.append({"name": "HAMMER", "signal": "BULLISH", "strength": "MODERATE"})

                # Shooting Star: long upper wick, small lower wick, in uptrend
                if body > 0 and upper_wick > 2 * body and lower_wick < 0.3 * body and in_uptrend:
                    detected.append({"name": "SHOOTING_STAR", "signal": "BEARISH", "strength": "MODERATE"})

            # Engulfing patterns (need at least 2 candles)
            for i in range(1, len(last5)):
                po = float(last5["Open"].iloc[i - 1])
                pc = float(last5["Close"].iloc[i - 1])
                co = float(last5["Open"].iloc[i])
                cc = float(last5["Close"].iloc[i])

                prev_body_top = max(po, pc)
                prev_body_bot = min(po, pc)
                curr_body_top = max(co, cc)
                curr_body_bot = min(co, cc)

                # Bullish Engulfing
                if (pc < po and cc > co and  # prev bearish, curr bullish
                        curr_body_top > prev_body_top and curr_body_bot < prev_body_bot):
                    detected.append({"name": "BULLISH_ENGULFING", "signal": "BULLISH", "strength": "STRONG"})

                # Bearish Engulfing
                if (pc > po and cc < co and  # prev bullish, curr bearish
                        curr_body_top > prev_body_top and curr_body_bot < prev_body_bot):
                    detected.append({"name": "BEARISH_ENGULFING", "signal": "BEARISH", "strength": "STRONG"})

            # Morning Star (3-candle: bearish, doji/small, bullish closing above midpoint of first)
            if len(last5) >= 3:
                # Use last 3 candles
                c1o = float(last5["Open"].iloc[-3]); c1c = float(last5["Close"].iloc[-3])
                c2o = float(last5["Open"].iloc[-2]); c2c = float(last5["Close"].iloc[-2])
                c2h = float(last5["High"].iloc[-2]); c2l = float(last5["Low"].iloc[-2])
                c3o = float(last5["Open"].iloc[-1]); c3c = float(last5["Close"].iloc[-1])

                c1_bearish = c1c < c1o
                c1_body = abs(c1c - c1o)
                c2_body = abs(c2c - c2o)
                c2_range = c2h - c2l
                c2_small = c2_range > 0 and c2_body < 0.3 * c2_range
                c3_bullish = c3c > c3o
                c1_midpoint = (c1o + c1c) / 2

                if c1_bearish and c2_small and c3_bullish and c3c > c1_midpoint:
                    detected.append({"name": "MORNING_STAR", "signal": "BULLISH", "strength": "STRONG"})

                # Evening Star (3-candle: bullish, small, bearish closing below midpoint of first)
                c1_bullish = c1c > c1o
                c3_bearish = c3c < c3o

                if c1_bullish and c2_small and c3_bearish and c3c < c1_midpoint:
                    detected.append({"name": "EVENING_STAR", "signal": "BEARISH", "strength": "STRONG"})

        except Exception as e:
            logger.warning("Error detecting candlestick patterns", error=str(e))

        return detected

    def _fibonacci_levels(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Calculate Fibonacci retracement levels from the last 90 candles."""
        try:
            window = min(90, len(df))
            recent = df.tail(window)
            swing_high = float(recent["High"].max())
            swing_low = float(recent["Low"].min())
            diff = swing_high - swing_low

            if diff <= 0:
                return {}

            level_236 = swing_high - 0.236 * diff
            level_382 = swing_high - 0.382 * diff
            level_500 = swing_high - 0.500 * diff
            level_618 = swing_high - 0.618 * diff
            level_786 = swing_high - 0.786 * diff

            current_price = float(df["Close"].iloc[-1])
            levels = {
                "NEAR_236": level_236,
                "NEAR_382": level_382,
                "NEAR_500": level_500,
                "NEAR_618": level_618,
                "NEAR_786": level_786,
            }
            current_zone = None
            for zone_name, level_price in levels.items():
                if level_price > 0 and abs(current_price - level_price) / level_price < 0.015:
                    current_zone = zone_name
                    break

            return {
                "swing_high": round(swing_high, 4),
                "swing_low": round(swing_low, 4),
                "level_236": round(level_236, 4),
                "level_382": round(level_382, 4),
                "level_500": round(level_500, 4),
                "level_618": round(level_618, 4),
                "level_786": round(level_786, 4),
                "current_zone": current_zone,
            }
        except Exception as e:
            logger.warning("Error calculating Fibonacci levels", error=str(e))
            return {}

    def _wyckoff_phase(self, df: pd.DataFrame, indicators: Dict[str, Any]) -> str:
        """Determine Wyckoff market phase based on price action and volume."""
        try:
            close = df["Close"]
            current = float(close.iloc[-1])
            ma50 = indicators.get("ma_50")
            ma200 = indicators.get("ma_200")

            if len(close) < 20:
                return "UNKNOWN"

            # Trend strength: slope of last 20 closes
            slope = np.polyfit(range(20), close.tail(20).values, 1)[0]
            base_price = float(close.iloc[-20])
            slope_pct = slope / base_price * 100 if base_price else 0

            # Strong uptrend = MARKUP
            if ma50 and ma200 and slope_pct > 0.3 and current > ma50 and ma50 > ma200:
                return "MARKUP"

            # Strong downtrend = MARKDOWN
            if ma50 and ma200 and slope_pct < -0.3 and current < ma50 and ma50 < ma200:
                return "MARKDOWN"

            # Flat range detection
            high_20 = float(close.tail(20).max())
            low_20 = float(close.tail(20).min())
            range_pct = (high_20 - low_20) / low_20 * 100 if low_20 else 0

            if range_pct < 8:  # tight consolidation range
                # Use 52-week position to distinguish accumulation vs distribution
                high_52w = float(df["High"].tail(252).max())
                low_52w = float(df["Low"].tail(252).min())
                range_52w = high_52w - low_52w
                if range_52w > 0:
                    pos_in_52w = (current - low_52w) / range_52w * 100
                    if pos_in_52w < 35:
                        return "ACCUMULATION"
                    if pos_in_52w > 65:
                        return "DISTRIBUTION"

            return "UNKNOWN"
        except Exception as e:
            logger.warning("Error determining Wyckoff phase", error=str(e))
            return "UNKNOWN"

    def _build_analysis_breakdown(
        self,
        indicators: Dict[str, Any],
        patterns: List[str],
        candlesticks: List[Dict],
        fib_data: Dict[str, Any],
        support: List[float],
        resistance: List[float],
        df: pd.DataFrame,
    ) -> List[Dict]:
        """Build structured breakdown of each analysis module."""
        breakdown: List[Dict] = []
        current_price = float(df["Close"].iloc[-1])

        try:
            # 1. Moving Averages (TREND)
            ma_trend = indicators.get("ma_trend")
            ma50 = indicators.get("ma_50")
            ma200 = indicators.get("ma_200")
            golden = indicators.get("golden_cross", False)
            death = indicators.get("death_cross", False)
            ma_signal = "NEUTRAL"
            ma_score = 0
            ma_details = []
            if ma_trend == "BULLISH":
                ma_signal = "BULLISH"
                ma_score = 10
                ma_details.append("50MA above 200MA")
            elif ma_trend == "BEARISH":
                ma_signal = "BEARISH"
                ma_score = -10
                ma_details.append("50MA below 200MA")
            if golden:
                ma_score += 15
                ma_details.append("Golden cross recently occurred")
            if death:
                ma_score -= 15
                ma_details.append("Death cross recently occurred")
            if ma50 and current_price > ma50:
                ma_details.append(f"Price above 50MA ({ma50:.2f})")
            elif ma50:
                ma_details.append(f"Price below 50MA ({ma50:.2f})")
            breakdown.append({
                "name": "Moving Averages",
                "category": "TREND",
                "signal": ma_signal,
                "score_impact": max(-25, min(25, ma_score)),
                "detail": "; ".join(ma_details) if ma_details else "No MA data available",
            })
        except Exception:
            pass

        try:
            # 2. RSI (MOMENTUM)
            rsi = indicators.get("rsi_14")
            rsi_signal = "NEUTRAL"
            rsi_score = 0
            rsi_detail = "No RSI data"
            if rsi is not None:
                rsi_detail = f"RSI(14) = {rsi:.1f}"
                if rsi < 30:
                    rsi_signal = "BULLISH"
                    rsi_score = 15
                    rsi_detail += " — oversold"
                elif rsi < 40:
                    rsi_signal = "BULLISH"
                    rsi_score = 8
                    rsi_detail += " — approaching oversold"
                elif rsi > 70:
                    rsi_signal = "BEARISH"
                    rsi_score = -15
                    rsi_detail += " — overbought"
                elif rsi > 60:
                    rsi_signal = "BEARISH"
                    rsi_score = -8
                    rsi_detail += " — approaching overbought"
            breakdown.append({
                "name": "RSI",
                "category": "MOMENTUM",
                "signal": rsi_signal,
                "score_impact": rsi_score,
                "detail": rsi_detail,
            })
        except Exception:
            pass

        try:
            # 3. MACD (MOMENTUM)
            macd_cross = indicators.get("macd_crossover", "NONE")
            macd_hist = indicators.get("macd_histogram")
            macd_signal = "NEUTRAL"
            macd_score = 0
            macd_details = []
            if macd_cross == "BULLISH":
                macd_signal = "BULLISH"
                macd_score = 12
                macd_details.append("Bullish MACD crossover")
            elif macd_cross == "BEARISH":
                macd_signal = "BEARISH"
                macd_score = -12
                macd_details.append("Bearish MACD crossover")
            if macd_hist is not None:
                direction = "rising" if macd_hist > 0 else "falling"
                macd_details.append(f"Histogram {direction} ({macd_hist:.4f})")
                if macd_signal == "NEUTRAL":
                    macd_signal = "BULLISH" if macd_hist > 0 else "BEARISH"
                macd_score += 5 if macd_hist > 0 else -5
            breakdown.append({
                "name": "MACD",
                "category": "MOMENTUM",
                "signal": macd_signal,
                "score_impact": max(-25, min(25, macd_score)),
                "detail": "; ".join(macd_details) if macd_details else "No MACD data",
            })
        except Exception:
            pass

        try:
            # 4. Bollinger Bands (VOLATILITY)
            bb_pos = indicators.get("bb_position")
            bb_squeeze = indicators.get("bb_squeeze", False)
            bb_upper = indicators.get("bb_upper")
            bb_lower = indicators.get("bb_lower")
            bb_signal = "NEUTRAL"
            bb_score = 0
            bb_details = []
            if bb_pos is not None:
                bb_details.append(f"Position within bands: {bb_pos:.0f}%")
                if bb_pos < 10:
                    bb_signal = "BULLISH"
                    bb_score = 10
                    bb_details.append("Near lower band — oversold zone")
                elif bb_pos > 90:
                    bb_signal = "BEARISH"
                    bb_score = -10
                    bb_details.append("Near upper band — overbought zone")
            if bb_squeeze:
                bb_details.append("Bands squeezing — breakout potential")
            if bb_upper and bb_lower:
                bb_details.append(f"Range: {bb_lower:.2f} – {bb_upper:.2f}")
            breakdown.append({
                "name": "Bollinger Bands",
                "category": "VOLATILITY",
                "signal": bb_signal,
                "score_impact": bb_score,
                "detail": "; ".join(bb_details) if bb_details else "No BB data",
            })
        except Exception:
            pass

        try:
            # 5. Volume Analysis (VOLUME)
            vol_ratio = indicators.get("volume_ratio", 1.0)
            close = df["Close"]
            volume = df["Volume"]
            # OBV: cumulative sum of signed volume
            direction = np.where(close.diff() > 0, 1, -1)
            obv = (volume * direction).cumsum()
            obv_trend = "rising" if float(obv.iloc[-1]) > float(obv.iloc[-20]) else "falling"
            vol_signal = "NEUTRAL"
            vol_score = 0
            vol_details = []
            if vol_ratio is not None:
                vol_details.append(f"Volume ratio vs 20-day avg: {vol_ratio:.2f}x")
                if vol_ratio > 1.5:
                    vol_signal = "BULLISH"
                    vol_score = 5
                    vol_details.append("Above-average volume (strong conviction)")
                elif vol_ratio < 0.7:
                    vol_details.append("Below-average volume (weak conviction)")
            vol_details.append(f"OBV trend: {obv_trend}")
            if obv_trend == "rising":
                vol_score += 5
                if vol_signal == "NEUTRAL":
                    vol_signal = "BULLISH"
            else:
                vol_score -= 5
                if vol_signal == "NEUTRAL":
                    vol_signal = "BEARISH"
            breakdown.append({
                "name": "Volume Analysis",
                "category": "VOLUME",
                "signal": vol_signal,
                "score_impact": max(-25, min(25, vol_score)),
                "detail": "; ".join(vol_details),
            })
        except Exception:
            pass

        try:
            # 6. Support & Resistance (STRUCTURE)
            sr_signal = "NEUTRAL"
            sr_score = 0
            sr_details = []
            if support:
                nearest_sup = max(support)
                dist_pct = (current_price - nearest_sup) / nearest_sup * 100
                sr_details.append(f"Nearest support: {nearest_sup:.2f} ({dist_pct:.1f}% below)")
                if current_price <= nearest_sup * 1.02:
                    sr_signal = "BULLISH"
                    sr_score = 8
                    sr_details.append("Price near key support — potential bounce")
            if resistance:
                nearest_res = min(resistance)
                dist_pct = (nearest_res - current_price) / current_price * 100
                sr_details.append(f"Nearest resistance: {nearest_res:.2f} ({dist_pct:.1f}% above)")
                if current_price >= nearest_res * 0.98:
                    sr_signal = "BEARISH"
                    sr_score = -8
                    sr_details.append("Price near key resistance — potential rejection")
            if not sr_details:
                sr_details.append("No nearby support/resistance levels identified")
            breakdown.append({
                "name": "Support & Resistance",
                "category": "STRUCTURE",
                "signal": sr_signal,
                "score_impact": sr_score,
                "detail": "; ".join(sr_details),
            })
        except Exception:
            pass

        try:
            # 7. Candlestick Patterns (PATTERN)
            cs_signal = "NEUTRAL"
            cs_score = 0
            cs_details = []
            for c in candlesticks:
                sig = c.get("signal", "NEUTRAL")
                strength = c.get("strength", "WEAK")
                name = c.get("name", "")
                cs_details.append(f"{name} ({sig}, {strength})")
                if sig == "BULLISH":
                    cs_score += 8 if strength == "STRONG" else 5
                elif sig == "BEARISH":
                    cs_score -= 8 if strength == "STRONG" else 5
            if cs_score > 0:
                cs_signal = "BULLISH"
            elif cs_score < 0:
                cs_signal = "BEARISH"
            breakdown.append({
                "name": "Candlestick Patterns",
                "category": "PATTERN",
                "signal": cs_signal,
                "score_impact": max(-25, min(25, cs_score)),
                "detail": "; ".join(cs_details) if cs_details else "No candlestick patterns detected",
            })
        except Exception:
            pass

        try:
            # 8. Fibonacci (STRUCTURE)
            fib_signal = "NEUTRAL"
            fib_score = 0
            fib_details = []
            if fib_data:
                zone = fib_data.get("current_zone")
                swing_h = fib_data.get("swing_high")
                swing_l = fib_data.get("swing_low")
                if swing_h and swing_l:
                    fib_details.append(f"90-day range: {swing_l:.2f} – {swing_h:.2f}")
                if zone:
                    fib_details.append(f"Price near Fibonacci {zone}")
                    # 618 and 786 near lows = bullish support; 236 near high = bearish resistance
                    if zone in ("NEAR_618", "NEAR_786"):
                        fib_signal = "BULLISH"
                        fib_score = 8
                        fib_details.append("Strong Fibonacci support zone")
                    elif zone in ("NEAR_236",):
                        fib_signal = "BEARISH"
                        fib_score = -5
                        fib_details.append("Near Fibonacci resistance zone")
                    elif zone in ("NEAR_382", "NEAR_500"):
                        fib_details.append("Mid Fibonacci zone — neutral")
                else:
                    fib_details.append("Price not near a key Fibonacci level")
            breakdown.append({
                "name": "Fibonacci",
                "category": "STRUCTURE",
                "signal": fib_signal,
                "score_impact": fib_score,
                "detail": "; ".join(fib_details) if fib_details else "No Fibonacci data",
            })
        except Exception:
            pass

        try:
            # 9. Wyckoff Method (STRUCTURE)
            wyckoff = self._wyckoff_phase(df, indicators)
            wyckoff_signal = "NEUTRAL"
            wyckoff_score = 0
            wyckoff_descriptions = {
                "ACCUMULATION": "Smart money accumulating — potential markup ahead",
                "MARKUP": "Price in markup phase — uptrend in progress",
                "DISTRIBUTION": "Distribution phase — potential markdown ahead",
                "MARKDOWN": "Price in markdown phase — downtrend in progress",
                "UNKNOWN": "No clear Wyckoff phase identified",
            }
            if wyckoff in ("ACCUMULATION", "MARKUP"):
                wyckoff_signal = "BULLISH"
                wyckoff_score = 8 if wyckoff == "MARKUP" else 5
            elif wyckoff in ("DISTRIBUTION", "MARKDOWN"):
                wyckoff_signal = "BEARISH"
                wyckoff_score = -8 if wyckoff == "MARKDOWN" else -5
            breakdown.append({
                "name": "Wyckoff Method",
                "category": "STRUCTURE",
                "signal": wyckoff_signal,
                "score_impact": wyckoff_score,
                "detail": f"Phase: {wyckoff} — {wyckoff_descriptions.get(wyckoff, '')}",
            })
        except Exception:
            pass

        try:
            # 10. Chart Patterns (PATTERN)
            chart_signal = "NEUTRAL"
            chart_score = 0
            chart_details = []
            for p in patterns:
                if p == "UPTREND_20D":
                    chart_score += 5
                    chart_details.append("20-day uptrend")
                elif p == "DOWNTREND_20D":
                    chart_score -= 5
                    chart_details.append("20-day downtrend")
                elif p == "NEAR_52W_HIGH":
                    chart_score -= 5
                    chart_details.append("Near 52-week high — potential resistance")
                elif p == "NEAR_52W_LOW":
                    chart_score += 8
                    chart_details.append("Near 52-week low — potential value zone")
                elif p == "VOLUME_SPIKE":
                    chart_details.append("Volume spike detected")
            if chart_score > 0:
                chart_signal = "BULLISH"
            elif chart_score < 0:
                chart_signal = "BEARISH"
            breakdown.append({
                "name": "Chart Patterns",
                "category": "PATTERN",
                "signal": chart_signal,
                "score_impact": max(-25, min(25, chart_score)),
                "detail": "; ".join(chart_details) if chart_details else "No chart patterns detected",
            })
        except Exception:
            pass

        return breakdown

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
