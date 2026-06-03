"""Claude-powered market analyst with RAG from knowledge base.

Uses claude-haiku-4-5 with prompt caching for cheap per-cycle analysis (~$0.30/day).
Calibration uses claude-opus-4-8 but runs rarely (weekly).
"""

import json
import re
import anthropic
from typing import List
from dataclasses import dataclass

from config import ANTHROPIC_API_KEY
from .knowledge_base import query as kb_query

_client = None

ANALYSIS_MODEL    = "claude-haiku-4-5-20251001"  # cheap + fast, cached system prompt
CALIBRATION_MODEL = "claude-opus-4-8"            # powerful, used only weekly


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    return _client


@dataclass
class TradingSignal:
    market_id: str
    question: str
    side: str          # "YES" or "NO"
    confidence: float  # 0.0 – 1.0
    reasoning: str
    news_used: List[str]


# Cached at API level — charged once per hour, saves ~90% on repeated calls
SYSTEM_PROMPT = {
    "type": "text",
    "text": """You are an expert prediction market trader specializing in Polymarket.
Analyze news and context to generate precise trading signals.

Output ONLY a JSON object — no other text:
{
  "side": "YES" or "NO",
  "confidence": float 0.0-1.0,
  "reasoning": "1-3 sentence explanation citing specific evidence",
  "signal": true or false
}

Rules:
- signal=true ONLY when confidence >= 0.65 AND evidence is strong and recent
- Consider: current market price vs your estimated true probability
- If YES price is 0.70 and you estimate 0.85 probability → strong YES signal
- If YES price is 0.70 and you estimate 0.72 probability → skip (edge too small)
- Factor in: source credibility, recency, historical base rates
- Be conservative — no signal is better than a wrong signal""",
    "cache_control": {"type": "ephemeral"},
}


async def analyze_market(
    market_id: str,
    question: str,
    current_yes_price: float,
    articles: List,
) -> TradingSignal | None:
    client = _get_client()

    news_text = "\n".join(a.to_text() for a in articles[:15])
    context_docs = kb_query(question, n_results=5)
    context_text = "\n---\n".join(context_docs) if context_docs else "No prior context."

    user_msg = (
        f"MARKET: {question}\n"
        f"YES price: {current_yes_price:.3f} (market implies {current_yes_price*100:.1f}% probability)\n\n"
        f"RECENT NEWS:\n{news_text}\n\n"
        f"HISTORICAL CONTEXT:\n{context_text}\n\n"
        "Output JSON:"
    )

    response = client.messages.create(
        model=ANALYSIS_MODEL,
        max_tokens=256,
        system=[SYSTEM_PROMPT],
        messages=[{"role": "user", "content": user_msg}],
        betas=["prompt-caching-2024-07-31"],
    )

    raw = response.content[0].text
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    if not m:
        return None

    try:
        data = json.loads(m.group())
    except json.JSONDecodeError:
        return None

    if not data.get("signal"):
        return None

    return TradingSignal(
        market_id=market_id,
        question=question,
        side=data["side"],
        confidence=float(data["confidence"]),
        reasoning=data["reasoning"],
        news_used=[a.title for a in articles[:5]],
    )
