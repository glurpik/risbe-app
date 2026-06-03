"""Trade executor — applies position sizing and routes orders."""

from ai.analyzer import TradingSignal
from trading.polymarket import place_order
from storage.db import log_trade
from config import MAX_TRADE_USD, CONFIDENCE_THRESHOLD


def _size_usd(confidence: float) -> float:
    """Kelly-lite: scale bet size with confidence above threshold."""
    edge = confidence - CONFIDENCE_THRESHOLD
    fraction = min(edge / (1 - CONFIDENCE_THRESHOLD), 1.0)
    return round(MAX_TRADE_USD * fraction, 2)


async def execute_signal(signal: TradingSignal) -> dict:
    if signal.confidence < CONFIDENCE_THRESHOLD:
        return {"status": "skipped", "reason": f"confidence {signal.confidence:.2f} < threshold {CONFIDENCE_THRESHOLD}"}

    amount = _size_usd(signal.confidence)
    if amount < 1.0:
        return {"status": "skipped", "reason": "position too small"}

    result = place_order(signal.market_id, signal.side, amount)

    await log_trade(
        market=signal.market_id,
        side=signal.side,
        amount_usd=amount,
        confidence=signal.confidence,
        metadata={"question": signal.question, "reasoning": signal.reasoning},
    )

    return {
        "status": result.get("status"),
        "market": signal.question,
        "side": signal.side,
        "amount_usd": amount,
        "confidence": signal.confidence,
        "order": result,
    }
