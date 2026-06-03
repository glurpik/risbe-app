"""
Risky mode — uses exactly 10% of current balance per cycle.

Differences from conservative mode:
  - Confidence threshold: 0.58 (vs 0.75 normal)
  - Accepts higher-volatility markets near 50/50
  - Larger single bet: up to 10% of balance
  - Shorter timeframes from combo signals
  - Still has hard stop: never exceeds 10% of total balance

The remaining 90% is NEVER touched by this mode.
"""

import asyncio
from dataclasses import dataclass
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm
from rich import print as rprint

from ai.analyzer import TradingSignal
from trading.executor import execute_signal
from trading.polymarket import get_active_markets, place_order
from trading.wallet import get_balance_matic

console = Console()

RISKY_CONFIDENCE_THRESHOLD = 0.58
RISKY_BUDGET_PCT = 0.10   # 10% of balance
RISKY_MAX_USD    = 500.0  # hard cap regardless of balance size


@dataclass
class RiskyBet:
    source: str          # "polymarket" | "crypto"
    description: str
    direction: str
    confidence: float
    amount_usd: float
    reasoning: str
    risk_level: str      # "medium" | "high"


def calc_risky_budget(total_balance_usd: float) -> float:
    """10% of balance, never more than RISKY_MAX_USD."""
    budget = total_balance_usd * RISKY_BUDGET_PCT
    return min(budget, RISKY_MAX_USD)


def _risky_signals_from_polymarket(articles: list, budget: float) -> list[RiskyBet]:
    """Find higher-risk Polymarket bets — markets closer to 50/50 with news edge."""
    bets = []
    markets = get_active_markets(limit=30)

    for m in markets:
        # Risky mode looks at markets near 50/50 where crowd is uncertain
        if not (0.30 <= m.yes_price <= 0.70):
            continue
        if m.volume < 2_000:  # still avoid tiny markets
            continue

        # Quick news-based check: any mention of market topic?
        q_words = set(m.question.lower().split())
        hits = sum(
            1 for a in articles[:20]
            if any(w in a.title.lower() for w in q_words if len(w) > 4)
        )

        if hits >= 2:  # at least 2 news articles touch this topic
            bets.append(RiskyBet(
                source="polymarket",
                description=m.question[:80],
                direction="YES" if m.yes_price < 0.50 else "NO",
                confidence=0.62,
                amount_usd=round(budget * 0.4, 2),  # 40% of risky budget per bet
                reasoning=f"{hits} news articles relevant. Market at {m.yes_price:.0%} — undecided.",
                risk_level="medium",
            ))

        if len(bets) >= 2:
            break

    return bets


async def run_risky_cycle(signals: list[TradingSignal], articles: list, balance_usd: float, auto: bool = False) -> dict:
    """
    Run the risky 10% mode.

    signals  — high-confidence signals from main analyzer (can be reused here at lower threshold)
    articles — latest news
    balance_usd — total portfolio in USD (10% will be used)
    auto     — True = no confirmation
    """
    budget = calc_risky_budget(balance_usd)

    console.print(Panel.fit(
        f"[bold red]⚡ RISKY MODE — 10% бюджет[/bold red]\n"
        f"Баланс: [yellow]${balance_usd:.2f}[/yellow]  "
        f"Рисковый бюджет: [red bold]${budget:.2f}[/red bold]\n"
        f"Порог уверенности: [yellow]{RISKY_CONFIDENCE_THRESHOLD:.0%}[/yellow]  "
        f"Остаток вне риска: [green]${balance_usd - budget:.2f}[/green]",
        border_style="red",
    ))

    if budget < 2.0:
        rprint("[yellow]Рисковый бюджет < $2 — пропуск.[/yellow]")
        return {"status": "skipped", "reason": "budget too small"}

    # Collect risky bets
    risky_bets: list[RiskyBet] = []

    # 1. Lower-confidence Polymarket signals
    for sig in signals:
        if RISKY_CONFIDENCE_THRESHOLD <= sig.confidence < 0.75:
            amount = round(budget * 0.5, 2)
            risky_bets.append(RiskyBet(
                source="polymarket",
                description=sig.question[:80],
                direction=sig.side,
                confidence=sig.confidence,
                amount_usd=amount,
                reasoning=sig.reasoning,
                risk_level="medium",
            ))

    # 2. Near-50/50 markets with news support
    poly_bets = _risky_signals_from_polymarket(articles, budget)
    risky_bets.extend(poly_bets)

    # Limit total spend to budget
    total_planned = sum(b.amount_usd for b in risky_bets)
    if total_planned > budget:
        scale = budget / total_planned
        for b in risky_bets:
            b.amount_usd = round(b.amount_usd * scale, 2)

    if not risky_bets:
        rprint("[yellow]Рисковых сигналов нет в этом цикле.[/yellow]")
        return {"status": "no_signals"}

    results = []
    for bet in risky_bets:
        _print_bet(bet)

        if not auto:
            if not Confirm.ask(f"  [red bold]Рискнуть ${bet.amount_usd:.2f}?[/red bold]", default=False):
                rprint("  [dim]Пропущено.[/dim]")
                continue

        result = place_order(bet.description[:20], bet.direction, bet.amount_usd)
        if result.get("status") in ("ok", "mock"):
            rprint(f"  [red]⚡ Рисковая ставка: ${bet.amount_usd:.2f} на {bet.direction}[/red]")
        results.append(result)

    total_spent = sum(b.amount_usd for b in risky_bets[:len(results)])
    console.print(f"\n[dim]Рисковый бюджет использован: ${total_spent:.2f} / ${budget:.2f}[/dim]")
    return {"status": "ok", "bets": len(results), "spent_usd": total_spent}


def _print_bet(bet: RiskyBet):
    color = "red" if bet.risk_level == "high" else "yellow"
    console.print(
        f"\n  [{color}]⚡ {bet.source.upper()}[/{color}] {bet.description}\n"
        f"  Направление: [bold]{bet.direction}[/bold]  "
        f"Уверенность: {bet.confidence:.0%}  "
        f"Ставка: [bold]${bet.amount_usd:.2f}[/bold]\n"
        f"  [dim]{bet.reasoning}[/dim]"
    )
