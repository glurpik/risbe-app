"""Режим с подтверждением — бот предлагает сделки, ты решаешь."""

from rich.console import Console
from rich.table import Table
from rich.prompt import Confirm
from rich import print as rprint

from ai.analyzer import TradingSignal
from trading.executor import execute_signal

console = Console()


async def run_confirm_cycle(signals: list[TradingSignal]) -> list[dict]:
    if not signals:
        console.print("[yellow]No signals this cycle.[/yellow]")
        return []

    console.print(f"\n[bold cyan]── {len(signals)} signal(s) found ──[/bold cyan]")
    results = []

    for sig in signals:
        table = Table(show_header=False, box=None, padding=(0, 1))
        table.add_row("[bold]Market[/bold]", sig.question)
        table.add_row("[bold]Side[/bold]",   f"[green]{sig.side}[/green]" if sig.side == "YES" else f"[red]{sig.side}[/red]")
        table.add_row("[bold]Confidence[/bold]", f"{sig.confidence:.0%}")
        table.add_row("[bold]Reasoning[/bold]", sig.reasoning)
        table.add_row("[bold]Sources[/bold]", ", ".join(sig.news_used[:3]))
        console.print(table)

        if Confirm.ask(f"  [bold]Execute this trade?[/bold]", default=False):
            result = await execute_signal(sig)
            if result["status"] in ("ok", "mock"):
                rprint(f"  [green]✓ Order placed — ${result['amount_usd']:.2f} on {result['side']}[/green]")
            else:
                rprint(f"  [red]✗ Failed: {result.get('order', {}).get('message', 'unknown')}[/red]")
            results.append(result)
        else:
            rprint("  [dim]Skipped.[/dim]")

    return results
