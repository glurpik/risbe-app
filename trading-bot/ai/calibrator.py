"""Self-calibration using DeepSeek R1 (reasoning model) — runs weekly."""

import json
import re
from openai import OpenAI
from config import DEEPSEEK_API_KEY
from storage.db import get_calibration_stats, get_recent_trades
from .analyzer import CALIBRATION_MODEL

_client = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url="https://api.deepseek.com")
    return _client


CALIBRATION_SYSTEM = """You are a quant analyst reviewing an AI trading bot's performance.
Your job: identify patterns in wins/losses and recommend threshold adjustments.

Output JSON only:
{
  "new_threshold": float (0.55–0.90),
  "reasoning": "what patterns you found",
  "pattern_notes": "specific advice: e.g. 'avoid political markets', 'crypto signals are strong'"
}"""


async def calibrate() -> dict:
    stats = await get_calibration_stats()
    trades = await get_recent_trades(30)

    if stats["total"] < 5:
        return {"action": "wait", "reason": "Need 5+ resolved trades to calibrate"}

    client = _get_client()
    trades_summary = json.dumps(trades, indent=2, default=str)

    response = client.chat.completions.create(
        model=CALIBRATION_MODEL,
        max_tokens=1024,
        messages=[
            {"role": "system", "content": CALIBRATION_SYSTEM},
            {"role": "user", "content": (
                f"Performance stats: {json.dumps(stats)}\n\n"
                f"Last 30 trades:\n{trades_summary}\n\n"
                "Analyze and output JSON."
            )},
        ],
    )

    raw = response.choices[0].message.content or ""
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    if not m:
        return {"action": "no_change", "reason": "Could not parse output"}

    data = json.loads(m.group())
    return {
        "action": "update",
        "new_threshold": float(data.get("new_threshold", 0.72)),
        "reasoning": data.get("reasoning", ""),
        "pattern_notes": data.get("pattern_notes", ""),
        "stats": stats,
    }
