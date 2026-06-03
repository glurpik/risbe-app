"""Автономный режим — бот торгует сам, только логирует."""

from rich.console import Console
from rich import print as rprint

from ai.analyzer import TradingSignal
from trading.executor import execute_signal

console = Console()


async def run_auto_cycle(signals: list[TradingSignal]) -> list[dict]:
    if not signals:
        console.print("[dim]Auto: no actionable signals this cycle.[/dim]")
        return []

    results = []
    for sig in signals:
        result = await execute_signal(sig)
        if result["status"] in ("ok", "mock"):
            rprint(
                f"[green]AUTO ✓[/green] {sig.question[:60]} | "
                f"[bold]{sig.side}[/bold] | "
                f"${result['amount_usd']:.2f} | "
                f"conf={sig.confidence:.0%}"
            )
        elif result["status"] == "skipped":
            rprint(f"[dim]AUTO skip: {result['reason']}[/dim]")
        else:
            rprint(f"[red]AUTO ✗[/red] {result.get('order', {}).get('message', 'error')}")
        results.append(result)

    return results
