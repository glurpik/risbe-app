"""Self-calibration: Claude reflects on past predictions and adjusts thresholds."""

import anthropic
import json
from config import ANTHROPIC_API_KEY
from storage.db import get_calibration_stats, get_recent_trades

_client = None


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    return _client


async def calibrate() -> dict:
    stats = await get_calibration_stats()
    trades = await get_recent_trades(30)

    if stats["total"] < 5:
        return {"action": "wait", "reason": "Not enough data yet (need 5+ resolved trades)"}

    client = _get_client()

    trades_summary = json.dumps(trades, indent=2, default=str)

    response = client.messages.create(
        model="claude-opus-4-8",
        max_tokens=512,
        system="""You are calibrating an AI trading bot. Analyze performance and suggest threshold adjustments.
Output JSON: {"new_threshold": float, "reasoning": str, "pattern_notes": str}""",
        messages=[{"role": "user", "content": f"""
Bot stats: {json.dumps(stats)}
Recent trades: {trades_summary}

Current confidence_threshold to trade. Suggest new threshold (between 0.55 and 0.90).
Output JSON only."""}],
    )

    raw = response.content[0].text
    import re
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    if not m:
        return {"action": "no_change", "reason": "Could not parse calibration output"}

    data = json.loads(m.group())
    return {
        "action": "update",
        "new_threshold": float(data.get("new_threshold", 0.72)),
        "reasoning": data.get("reasoning", ""),
        "pattern_notes": data.get("pattern_notes", ""),
        "stats": stats,
    }
