"""Claude-powered market analyst with RAG from knowledge base."""

import anthropic
from typing import List
from dataclasses import dataclass

from config import ANTHROPIC_API_KEY
from .knowledge_base import query as kb_query

_client = None


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


SYSTEM_PROMPT = """You are an expert prediction market and crypto trader.
You analyze news and context to generate high-confidence trading signals.

For each Polymarket question you must output a JSON object with:
{
  "side": "YES" or "NO",
  "confidence": float 0.0-1.0 (only signal if >= 0.65),
  "reasoning": "1-3 sentence explanation",
  "signal": true/false
}

Be conservative. Only signal=true when confidence >= 0.65 based on strong evidence.
Factor in: recency, source credibility, historical patterns from context.
"""


async def analyze_market(
    market_id: str,
    question: str,
    current_yes_price: float,
    articles: List,
) -> TradingSignal | None:
    client = _get_client()

    news_text = "\n".join(a.to_text() for a in articles[:20])
    context_docs = kb_query(question, n_results=6)
    context_text = "\n---\n".join(context_docs) if context_docs else "No prior context."

    user_msg = f"""POLYMARKET QUESTION: {question}
Current YES price: {current_yes_price:.3f} (implied probability {current_yes_price*100:.1f}%)

LATEST NEWS:
{news_text}

KNOWLEDGE BASE CONTEXT (historical patterns & past trades):
{context_text}

Analyze this market and output JSON."""

    response = client.messages.create(
        model="claude-opus-4-8",
        max_tokens=512,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_msg}],
        betas=["prompt-caching-2024-07-31"],
    )

    raw = response.content[0].text
    import json, re
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    if not m:
        return None

    data = json.loads(m.group())
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
