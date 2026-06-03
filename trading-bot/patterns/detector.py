"""Technical pattern detection using pandas-ta."""

from typing import Optional
import pandas as pd

try:
    import pandas_ta as ta
    TA_AVAILABLE = True
except ImportError:
    TA_AVAILABLE = False


def analyze_price_series(prices: list[float]) -> dict:
    """Given a list of closing prices, return key technical signals."""
    if len(prices) < 20:
        return {"error": "Need at least 20 data points"}

    df = pd.DataFrame({"close": prices})

    result = {}

    if TA_AVAILABLE:
        df.ta.rsi(length=14, append=True)
        df.ta.ema(length=9, append=True)
        df.ta.ema(length=21, append=True)
        df.ta.macd(append=True)
        df.ta.bbands(length=20, append=True)

        last = df.iloc[-1]
        result["rsi_14"] = round(float(last.get("RSI_14", 50)), 2)
        result["ema_9"]  = round(float(last.get("EMA_9",  0)), 4)
        result["ema_21"] = round(float(last.get("EMA_21", 0)), 4)

        macd_val = last.get("MACD_12_26_9", 0)
        macd_sig = last.get("MACDs_12_26_9", 0)
        result["macd_bullish"] = bool(macd_val > macd_sig)

        bb_upper = last.get("BBU_20_2.0", 0)
        bb_lower = last.get("BBL_20_2.0", 0)
        price = prices[-1]
        result["bb_position"] = round((price - bb_lower) / max(bb_upper - bb_lower, 1e-9), 3)
    else:
        sma = sum(prices[-20:]) / 20
        result["sma_20"] = round(sma, 4)
        result["above_sma"] = prices[-1] > sma

    result["trend"] = _detect_trend(prices[-20:])
    return result


def _detect_trend(prices: list) -> str:
    if len(prices) < 5:
        return "unknown"
    slope = (prices[-1] - prices[0]) / len(prices)
    if slope > 0.01 * prices[0]:
        return "uptrend"
    if slope < -0.01 * prices[0]:
        return "downtrend"
    return "sideways"


def format_signals(signals: dict) -> str:
    parts = []
    if "rsi_14" in signals:
        rsi = signals["rsi_14"]
        label = "oversold" if rsi < 30 else ("overbought" if rsi > 70 else "neutral")
        parts.append(f"RSI={rsi} ({label})")
    if "macd_bullish" in signals:
        parts.append(f"MACD={'bullish' if signals['macd_bullish'] else 'bearish'}")
    if "trend" in signals:
        parts.append(f"Trend={signals['trend']}")
    return " | ".join(parts) if parts else "no signals"
