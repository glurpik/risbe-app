"""
Learning system — logs every decision, tracks outcomes, extracts lessons.

Every signal (traded or skipped) is written to decisions.jsonl.
After each resolved market the bot records what it got right/wrong.
Weekly: DeepSeek R1 reads all outcomes and extracts actionable lessons
that go back into the ChromaDB knowledge base.
"""

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from openai import OpenAI

from config import DEEPSEEK_API_KEY
from .knowledge_base import load_documents

DECISIONS_LOG = Path("./data/decisions.jsonl")
LESSONS_LOG   = Path("./data/lessons.jsonl")

_client = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url="https://api.deepseek.com")
    return _client


# ── Log every decision ────────────────────────────────────────────────────────

def log_decision(
    market_id: str,
    question: str,
    signal_generated: bool,
    side: Optional[str],
    confidence: Optional[float],
    base_rate: Optional[float],
    my_estimate: Optional[float],
    market_price: float,
    edge: Optional[float],
    reasoning: Optional[str],
    filter_passed: bool,
    filter_reason: str,
    news_headlines: list[str],
    trade_executed: bool,
):
    DECISIONS_LOG.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "market_id": market_id,
        "question": question,
        "signal_generated": signal_generated,
        "trade_executed": trade_executed,
        "side": side,
        "confidence": confidence,
        "base_rate": base_rate,
        "my_estimate": my_estimate,
        "market_price": market_price,
        "edge": edge,
        "reasoning": reasoning,
        "filter_passed": filter_passed,
        "filter_reason": filter_reason,
        "news_headlines": news_headlines[:5],
        "outcome": None,   # filled later when market resolves
        "pnl": None,
    }
    with open(DECISIONS_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def record_outcome(market_id: str, outcome: str, pnl: float):
    """Call this when a market resolves — updates the decision log."""
    if not DECISIONS_LOG.exists():
        return
    lines = DECISIONS_LOG.read_text(encoding="utf-8").splitlines()
    updated = []
    for line in lines:
        try:
            rec = json.loads(line)
            if rec.get("market_id") == market_id and rec.get("outcome") is None:
                rec["outcome"] = outcome
                rec["pnl"] = pnl
            updated.append(json.dumps(rec, ensure_ascii=False))
        except Exception:
            updated.append(line)
    DECISIONS_LOG.write_text("\n".join(updated) + "\n", encoding="utf-8")


# ── Load resolved decisions for analysis ─────────────────────────────────────

def get_resolved_decisions(limit: int = 100) -> list[dict]:
    if not DECISIONS_LOG.exists():
        return []
    records = []
    for line in DECISIONS_LOG.read_text(encoding="utf-8").splitlines():
        try:
            rec = json.loads(line)
            if rec.get("outcome") is not None:
                records.append(rec)
        except Exception:
            continue
    return records[-limit:]


# ── Weekly lesson extraction ──────────────────────────────────────────────────

LESSON_EXTRACTION_PROMPT = """You are analyzing an AI prediction market bot's track record.
Study the resolved trades and extract concrete, actionable lessons.

Output JSON:
{
  "lessons": [
    "Lesson 1: specific pattern observed",
    "Lesson 2: ...",
    ...
  ],
  "strong_categories": ["list of market types where bot performed well"],
  "weak_categories": ["list of market types where bot lost"],
  "recommended_threshold": 0.XX,
  "key_insight": "single most important finding"
}"""


async def extract_lessons() -> dict:
    resolved = get_resolved_decisions(100)
    if len(resolved) < 10:
        return {"status": "need_more_data", "have": len(resolved), "need": 10}

    client = _get_client()

    wins   = [r for r in resolved if r.get("pnl", 0) > 0]
    losses = [r for r in resolved if r.get("pnl", 0) < 0]
    skipped = [r for r in resolved if not r.get("trade_executed")]

    summary = {
        "total_resolved": len(resolved),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": round(len(wins) / max(len(wins) + len(losses), 1), 3),
        "total_pnl": round(sum(r.get("pnl", 0) for r in resolved), 2),
        "avg_confidence_wins":  round(sum(r.get("confidence", 0) for r in wins)   / max(len(wins), 1), 3),
        "avg_confidence_losses":round(sum(r.get("confidence", 0) for r in losses) / max(len(losses), 1), 3),
        "skipped_correct": sum(1 for r in skipped if r.get("outcome") != r.get("side")),
        "sample_wins":   [{"q": r["question"][:80], "conf": r["confidence"], "edge": r["edge"]} for r in wins[:5]],
        "sample_losses": [{"q": r["question"][:80], "conf": r["confidence"], "edge": r["edge"], "why": r["reasoning"]} for r in losses[:5]],
    }

    response = client.chat.completions.create(
        model="deepseek-reasoner",
        max_tokens=1500,
        messages=[
            {"role": "system", "content": LESSON_EXTRACTION_PROMPT},
            {"role": "user",   "content": f"Bot performance data:\n{json.dumps(summary, indent=2)}\n\nExtract lessons. JSON only."},
        ],
    )

    raw = response.choices[0].message.content or ""
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    if not m:
        return {"status": "parse_error"}

    data = json.loads(m.group())
    lessons = data.get("lessons", [])

    # Save lessons to ChromaDB so future analyses use them
    if lessons:
        lesson_texts = [f"LEARNED LESSON: {l}" for l in lessons]
        if data.get("key_insight"):
            lesson_texts.append(f"KEY INSIGHT FROM PERFORMANCE REVIEW: {data['key_insight']}")
        load_documents(lesson_texts, source="self_learning")

    # Save to lessons log
    LESSONS_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(LESSONS_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps({
            "ts": datetime.now(timezone.utc).isoformat(),
            "summary": summary,
            "lessons": data,
        }, ensure_ascii=False) + "\n")

    return {"status": "ok", "lessons": lessons, "summary": summary, **data}
