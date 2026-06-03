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
from ai.market_filter import filter_market
from ai.learning import log_decision, extract_lessons
from ai.combo_signal import scan_crypto_signals
from trading.bybit import get_price as bybit_price
from trading.polymarket import get_active_markets
from trading.wallet import get_balance_matic, get_address
from modes.confirm_mode import run_confirm_cycle
from modes.auto_mode import run_auto_cycle
from modes.risky_mode import run_risky_cycle

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

async def run_cycle(auto_mode: bool, risky_mode: bool = False):
    console.rule(f"[dim]{datetime.utcnow().strftime('%H:%M:%S UTC')} — New cycle[/dim]")

    # 1. Fetch news
    console.print("[cyan]Fetching news from 50+ sources…[/cyan]", end=" ")
    articles = await fetch_all_news()
    console.print(f"[green]{len(articles)} articles[/green]")

    # 2. Store in knowledge base
    add_articles(articles)

    # 3. Get markets
    markets = get_active_markets(limit=20)

    # 4. Filter bad markets before spending API tokens
    passed, skipped_count = [], 0
    for m in markets:
        f = filter_market(m.question, m.volume, m.yes_price)
        if f.passed:
            passed.append((m, f))
        else:
            skipped_count += 1
            log_decision(
                market_id=m.id, question=m.question, signal_generated=False,
                side=None, confidence=None, base_rate=None, my_estimate=None,
                market_price=m.yes_price, edge=None, reasoning=None,
                filter_passed=False, filter_reason=f.reason,
                news_headlines=[], trade_executed=False,
            )

    console.print(
        f"[cyan]Markets:[/cyan] {len(passed)} passed filter, "
        f"[dim]{skipped_count} rejected (hype/thin/extreme)[/dim]"
    )

    # 5. Analyze filtered markets
    signals = []
    for market, flt in passed:
        sig = await analyze_market(
            market_id=market.id,
            question=market.question,
            current_yes_price=market.yes_price,
            articles=articles,
        )
        log_decision(
            market_id=market.id,
            question=market.question,
            signal_generated=sig is not None,
            side=sig.side if sig else None,
            confidence=sig.confidence if sig else None,
            base_rate=sig.base_rate if sig else None,
            my_estimate=sig.my_estimate if sig else None,
            market_price=market.yes_price,
            edge=sig.edge if sig else None,
            reasoning=sig.reasoning if sig else None,
            filter_passed=True,
            filter_reason=flt.reason,
            news_headlines=[a.title for a in articles[:5]],
            trade_executed=False,  # updated by executor
        )
        if sig:
            signals.append(sig)

    console.print(f"[cyan]Signals:[/cyan] {len(signals)} actionable (skipped {len(passed)-len(signals)} low-edge)")

    # 6. Crypto pattern scan (Bybit — runs in parallel with signal execution)
    try:
        crypto_signals = await scan_crypto_signals(articles)
        if crypto_signals:
            console.print(f"[magenta]Crypto patterns:[/magenta] {len(crypto_signals)} signal(s)")
            for cs in crypto_signals:
                console.print(f"  [bold]{cs.symbol}[/bold] {cs.timeframe} — {cs.summary()}")
    except Exception as e:
        console.print(f"[dim]Crypto scan skipped: {e}[/dim]")

    # 7. Execute Polymarket signals (conservative 90%)
    if auto_mode:
        await run_auto_cycle(signals)
    else:
        await run_confirm_cycle(signals)

    # 8. Risky mode — 10% of balance (optional)
    if risky_mode:
        balance_usd = get_balance_matic() * 0.6  # rough MATIC→USD, replace with real price
        await run_risky_cycle(signals, articles, balance_usd, auto=auto_mode)


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


async def cmd_learn():
    console.print("[cyan]Running self-learning session (DeepSeek R1)…[/cyan]")
    result = await extract_lessons()
    if result.get("status") == "need_more_data":
        rprint(f"[yellow]Not enough data yet: {result['have']}/{result['need']} resolved trades[/yellow]")
        return
    console.print(f"\n[bold]Win rate:[/bold] {result['summary']['win_rate']:.0%}  "
                  f"PnL: ${result['summary']['total_pnl']:.2f}")
    console.print(f"\n[bold green]Lessons extracted and saved to knowledge base:[/bold green]")
    for i, lesson in enumerate(result.get("lessons", []), 1):
        rprint(f"  {i}. {lesson}")
    if result.get("key_insight"):
        rprint(f"\n[bold yellow]Key insight:[/bold yellow] {result['key_insight']}")
    if result.get("recommended_threshold"):
        rprint(f"[bold]Recommended threshold:[/bold] {result['recommended_threshold']:.0%}")


# ── Main ──────────────────────────────────────────────────────────────────────

async def main():
    parser = argparse.ArgumentParser(description="AI Trading Bot")
    sub = parser.add_subparsers(dest="cmd")

    # run command
    run_p = sub.add_parser("run", help="Start the trading loop")
    run_p.add_argument("--auto",  action="store_true", help="Autonomous mode (no confirmation)")
    run_p.add_argument("--risky", action="store_true", help="Enable risky mode: use 10% of balance on aggressive bets")
    run_p.add_argument("--once",  action="store_true", help="Run one cycle then exit")

    # load command
    load_p = sub.add_parser("load", help="Load knowledge base from files")
    load_p.add_argument("path", help="File or directory to load (.txt, .md)")

    # stats/calibrate/learn/seed
    sub.add_parser("stats",     help="Show trade statistics")
    sub.add_parser("calibrate", help="Run AI self-calibration (DeepSeek R1)")
    sub.add_parser("learn",     help="Extract lessons from resolved trades → save to knowledge base")
    sub.add_parser("seed",      help="Seed knowledge base with base rates, pattern stats, Polymarket history")

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

    if args.cmd == "learn":
        await cmd_learn()
        return

    if args.cmd == "seed":
        from ai.seed_knowledge import seed_all
        await seed_all()
        return

    # Default: run
    auto_mode  = getattr(args, "auto",  False) or config.AUTO_MODE
    risky_mode = getattr(args, "risky", False) or config.RISKY_MODE
    once       = getattr(args, "once",  False)

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
        await run_cycle(auto_mode, risky_mode)
        return

    # Loop forever — pure asyncio, no schedule library
    interval = config.NEWS_INTERVAL_MIN * 60
    console.print(f"[dim]Running every {config.NEWS_INTERVAL_MIN} minutes. Ctrl+C to stop.[/dim]\n")

    while True:
        await run_cycle(auto_mode, risky_mode)
        await asyncio.sleep(interval)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        console.print("\n[dim]Bot stopped.[/dim]")
