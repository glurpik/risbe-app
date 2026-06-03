#!/usr/bin/env python3
"""
Trading Bot — AI-powered prediction market & crypto trader.
Modes: confirm (default) | auto
"""

import asyncio
import argparse
import sys
import threading
from pathlib import Path
from datetime import datetime

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich import print as rprint

import config
from storage.db import init_db
from news.aggregator import fetch_all_news
from ai.knowledge_base import add_articles, load_documents
from ai.analyzer import analyze_market
from ai.calibrator import calibrate
from trading.polymarket import get_active_markets
from trading.wallet import get_balance_matic, get_address
from modes.confirm_mode import run_confirm_cycle
from modes.auto_mode import run_auto_cycle

console = Console()


# ── Startup banner ────────────────────────────────────────────────────────────

def print_banner(auto_mode: bool):
    mode_label = "[red bold]AUTO (саморабота)[/red bold]" if auto_mode else "[green bold]CONFIRM (с подтверждением)[/green bold]"
    console.print(Panel.fit(
        f"[bold cyan]Trading Bot[/bold cyan]\n"
        f"Mode: {mode_label}\n"
        f"Threshold: [yellow]{config.CONFIDENCE_THRESHOLD:.0%}[/yellow]  "
        f"MaxTrade: [yellow]${config.MAX_TRADE_USD}[/yellow]  "
        f"NewsInterval: [yellow]{config.NEWS_INTERVAL_MIN}min[/yellow]",
        title="🤖 AI Trader",
    ))


# ── One full cycle ─────────────────────────────────────────────────────────────

async def run_cycle(auto_mode: bool):
    console.rule(f"[dim]{datetime.utcnow().strftime('%H:%M:%S UTC')} — New cycle[/dim]")

    # 1. Fetch news
    console.print("[cyan]Fetching news from 50+ sources…[/cyan]", end=" ")
    articles = await fetch_all_news()
    console.print(f"[green]{len(articles)} articles[/green]")

    # 2. Store in knowledge base
    add_articles(articles)

    # 3. Get markets
    markets = get_active_markets(limit=10)
    console.print(f"[cyan]Analyzing {len(markets)} Polymarket markets…[/cyan]")

    # 4. Analyze each market
    signals = []
    for market in markets:
        sig = await analyze_market(
            market_id=market.id,
            question=market.question,
            current_yes_price=market.yes_price,
            articles=articles,
        )
        if sig:
            signals.append(sig)

    # 5. Execute
    if auto_mode:
        await run_auto_cycle(signals)
    else:
        await run_confirm_cycle(signals)


# ── Load knowledge base from files ────────────────────────────────────────────

def cmd_load(args):
    path = Path(args.path)
    if not path.exists():
        console.print(f"[red]Path not found: {path}[/red]")
        sys.exit(1)

    files = list(path.rglob("*.txt")) + list(path.rglob("*.md")) if path.is_dir() else [path]
    total = 0
    for f in files:
        text = f.read_text(errors="ignore")
        chunks = [text[i:i+1000] for i in range(0, len(text), 1000)]
        n = load_documents(chunks, source=f.name)
        total += n
        console.print(f"  [green]+{n}[/green] chunks from {f.name}")

    console.print(f"\n[bold green]Loaded {total} chunks into knowledge base.[/bold green]")


# ── Stats / calibration ───────────────────────────────────────────────────────

async def cmd_stats():
    from storage.db import get_calibration_stats, get_recent_trades
    stats = await get_calibration_stats()
    trades = await get_recent_trades(10)

    t = Table(title="Calibration Stats")
    t.add_column("Metric"); t.add_column("Value")
    t.add_row("Total resolved trades", str(stats["total"]))
    t.add_row("Accuracy", f"{stats['accuracy']:.0%}")
    t.add_row("Avg confidence", f"{stats['avg_confidence']:.0%}")
    console.print(t)

    if trades:
        t2 = Table(title="Recent Trades")
        t2.add_column("Time"); t2.add_column("Market"); t2.add_column("Side"); t2.add_column("$"); t2.add_column("Conf")
        for tr in trades:
            t2.add_row(tr["ts"][:16], tr["market"][:40], tr["side"], f"{tr['amount_usd']:.2f}", f"{tr['confidence']:.0%}")
        console.print(t2)


async def cmd_calibrate():
    console.print("[cyan]Running calibration…[/cyan]")
    result = await calibrate()
    if result["action"] == "update":
        rprint(f"[green]New threshold suggestion: {result['new_threshold']:.0%}[/green]")
        rprint(f"Reasoning: {result['reasoning']}")
        rprint(f"Patterns: {result['pattern_notes']}")
    else:
        rprint(f"[yellow]{result['reason']}[/yellow]")


# ── Main ──────────────────────────────────────────────────────────────────────

async def main():
    parser = argparse.ArgumentParser(description="AI Trading Bot")
    sub = parser.add_subparsers(dest="cmd")

    # run command
    run_p = sub.add_parser("run", help="Start the trading loop")
    run_p.add_argument("--auto", action="store_true", help="Enable autonomous mode (no confirmation)")
    run_p.add_argument("--once", action="store_true", help="Run one cycle then exit")

    # load command
    load_p = sub.add_parser("load", help="Load knowledge base from files")
    load_p.add_argument("path", help="File or directory to load (.txt, .md)")

    # stats/calibrate
    sub.add_parser("stats", help="Show trade statistics")
    sub.add_parser("calibrate", help="Run AI self-calibration")

    args = parser.parse_args()

    await init_db()

    if args.cmd == "load":
        cmd_load(args)
        return

    if args.cmd == "stats":
        await cmd_stats()
        return

    if args.cmd == "calibrate":
        await cmd_calibrate()
        return

    # Default: run
    auto_mode = getattr(args, "auto", False) or config.AUTO_MODE
    once = getattr(args, "once", False)

    print_banner(auto_mode)

    # Start dashboard in background thread
    from dashboard import run as dashboard_run
    t = threading.Thread(target=dashboard_run, daemon=True)
    t.start()
    console.print("[dim]Dashboard: http://localhost:8080[/dim]")

    wallet_addr = get_address()
    balance = get_balance_matic()
    console.print(f"Wallet: [dim]{wallet_addr}[/dim]  Balance: [yellow]{balance:.4f} MATIC[/yellow]\n")

    if once:
        await run_cycle(auto_mode)
        return

    # Loop forever
    import schedule, time
    console.print(f"[dim]Running every {config.NEWS_INTERVAL_MIN} minutes. Ctrl+C to stop.[/dim]\n")
    asyncio.ensure_future(run_cycle(auto_mode))

    schedule.every(config.NEWS_INTERVAL_MIN).minutes.do(
        lambda: asyncio.ensure_future(run_cycle(auto_mode))
    )

    while True:
        schedule.run_pending()
        await asyncio.sleep(30)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        console.print("\n[dim]Bot stopped.[/dim]")
