"""
Telegram bot — управление ботом и уведомления прямо в телефоне.

Команды:
  /start   — главное меню
  /status  — быстрый статус

Инлайн-кнопки:
  Главное меню → Статистика / Сделки / Настройки / Пауза
  При новом сигнале → Исполнить / Пропустить
"""

import asyncio
import logging
from typing import Optional
from datetime import datetime

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Bot
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, ContextTypes
)
from telegram.constants import ParseMode

from config import TELEGRAM_TOKEN, TELEGRAM_ADMIN

log = logging.getLogger(__name__)

# ── Premium emoji helpers ─────────────────────────────────────────────────────
# Используем твои emoji ID из сообщения

def e(emoji_id: str, fallback: str) -> str:
    """Wrap custom emoji for HTML parse mode."""
    return f'<tg-emoji emoji-id="{emoji_id}">{fallback}</tg-emoji>'

# Маппинг твоих emoji ID
E = {
    "chart":    e("5776219138917668486", "📈"),
    "ok":       e("5776375003280838798", "✅"),
    "no":       e("5778527486270770928", "❌"),
    "settings": e("5877260593903177342", "⚙️"),
    "right":    e("5877468380125990242", "➡️"),
    "up":       e("5884343982816759327", "↗️"),
    "box":      e("5924720918826848520", "📦"),
    "folder":   e("5875206779196935950", "📁"),
    "trash":    e("5879896690210639947", "🗑"),
    "warn":     e("5881702736843511327", "⚠️"),
    "globe":    e("5879585266426973039", "🌐"),
    "msg":      e("5994297722574737553", "💬"),
    "shield":   e("5931409969613116639", "🛡"),
    "plane":    e("5875465628285931233", "✈️"),
    "back":     e("5875082500023258804", "⬅️"),
    "users":    e("5942877472163892475", "👥"),
    "hammer":   e("5931546553868095844", "🔨"),
}

# ── Shared state (main bot ↔ telegram bot) ────────────────────────────────────

class BotState:
    paused:     bool  = False
    auto_mode:  bool  = False
    risky_mode: bool  = False
    threshold:  float = 0.75
    last_pnl:   float = 0.0
    total_trades: int = 0
    win_rate:   float = 0.0
    last_cycle: str   = "—"

    # Pending signal waiting for user confirmation
    pending_signal: Optional[dict] = None
    pending_event:  Optional[asyncio.Event] = None
    pending_approve: bool = False

state = BotState()

_app: Optional[Application] = None
_bot: Optional[Bot] = None


def get_bot() -> Optional["TelegramBot"]:
    global _tg_bot
    return _tg_bot

_tg_bot: Optional["TelegramBot"] = None


# ── Keyboards ─────────────────────────────────────────────────────────────────

def kb_main() -> InlineKeyboardMarkup:
    mode_label = f"{E['ok']} Авто" if state.auto_mode else f"{E['no']} Ручной"
    risky_label = f"{E['warn']} Риск ВКЛ" if state.risky_mode else f"{E['shield']} Риск ВЫКЛ"
    pause_label = f"{E['right']} Запустить" if state.paused else f"{E['box']} Пауза"

    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(f"{E['chart']} Статистика", callback_data="stats"),
            InlineKeyboardButton(f"{E['folder']} Сделки",    callback_data="trades"),
        ],
        [
            InlineKeyboardButton(f"{E['settings']} Настройки", callback_data="settings"),
            InlineKeyboardButton(f"{E['msg']} Лог",            callback_data="log"),
        ],
        [
            InlineKeyboardButton(mode_label,  callback_data="toggle_auto"),
            InlineKeyboardButton(risky_label, callback_data="toggle_risky"),
        ],
        [
            InlineKeyboardButton(pause_label, callback_data="toggle_pause"),
        ],
    ])


def kb_settings() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(f"{E['up']} Порог +5%",  callback_data="thresh_up"),
            InlineKeyboardButton(f"{E['back']} Порог -5%", callback_data="thresh_down"),
        ],
        [
            InlineKeyboardButton(f"{E['hammer']} Калибровка",   callback_data="calibrate"),
            InlineKeyboardButton(f"{E['globe']} Обучение",      callback_data="learn"),
        ],
        [
            InlineKeyboardButton(f"{E['back']} Назад", callback_data="main"),
        ],
    ])


def kb_signal(signal_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton(f"{E['ok']} Исполнить", callback_data=f"approve_{signal_id}"),
        InlineKeyboardButton(f"{E['no']} Пропустить", callback_data=f"reject_{signal_id}"),
    ]])


# ── Message builders ──────────────────────────────────────────────────────────

def msg_main() -> str:
    status = f"{E['warn']} ПАУЗА" if state.paused else f"{E['ok']} Работает"
    mode   = f"{E['ok']} Авто" if state.auto_mode else f"{E['shield']} Ручной"
    risky  = f"{E['warn']} ВКЛ" if state.risky_mode else f"{E['no']} ВЫКЛ"

    return (
        f"{E['chart']} <b>CLAUDE BOT</b>\n\n"
        f"{E['right']} Статус: {status}\n"
        f"{E['right']} Режим: {mode}\n"
        f"{E['right']} Рисковый: {risky}\n"
        f"{E['right']} Порог: <b>{state.threshold:.0%}</b>\n\n"
        f"{E['chart']} P&L: <b>${state.last_pnl:+.2f}</b>\n"
        f"{E['ok']} Win rate: <b>{state.win_rate:.0%}</b>\n"
        f"{E['box']} Сделок: <b>{state.total_trades}</b>\n\n"
        f"{E['msg']} Цикл: <i>{state.last_cycle}</i>"
    )


def msg_stats(trades: list) -> str:
    if not trades:
        return f"{E['folder']} Сделок пока нет."

    pnl_total = sum(t.get("pnl") or 0 for t in trades)
    wins = sum(1 for t in trades if (t.get("pnl") or 0) > 0)
    total = len([t for t in trades if t.get("pnl") is not None])
    wr = wins / total if total else 0

    lines = [f"{E['chart']} <b>Последние сделки</b>\n"]
    for t in trades[:8]:
        pnl = t.get("pnl")
        icon = E["ok"] if (pnl or 0) > 0 else E["no"]
        pnl_str = f"${pnl:+.2f}" if pnl is not None else "—"
        lines.append(
            f"{icon} {t['market'][:35]}…\n"
            f"   {t['side']} · {pnl_str} · {t['ts'][:10]}\n"
        )

    lines.append(f"\n{E['right']} Итого P&L: <b>${pnl_total:+.2f}</b>  Win: <b>{wr:.0%}</b>")
    return "\n".join(lines)


def msg_signal(sig: dict) -> str:
    conf = sig.get("confidence", 0)
    edge = sig.get("edge", 0)
    side = sig.get("side", "?")
    icon = E["up"] if side == "YES" else E["back"]

    stars = "🔥" * min(int(conf * 10) - 5, 5)

    return (
        f"{E['warn']} <b>НОВЫЙ СИГНАЛ</b> {stars}\n\n"
        f"{E['globe']} <b>{sig.get('question', '')[:70]}</b>\n\n"
        f"{icon} Направление: <b>{side}</b>\n"
        f"{E['chart']} Уверенность: <b>{conf:.0%}</b>\n"
        f"{E['right']} Edge: <b>{edge:.0%}</b>\n"
        f"{E['box']} Ставка: <b>${sig.get('amount_usd', 0):.2f}</b>\n\n"
        f"{E['msg']} <i>{sig.get('reasoning', '')}</i>\n\n"
        f"📰 {sig.get('news_used', ['—'])[0][:60]}"
    )


# ── Handlers ──────────────────────────────────────────────────────────────────

def _admin_only(func):
    async def wrapper(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        uid = update.effective_user.id if update.effective_user else 0
        if uid != TELEGRAM_ADMIN:
            await update.effective_message.reply_text("⛔ Доступ запрещён.")
            return
        return await func(update, ctx)
    return wrapper


@_admin_only
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        msg_main(),
        parse_mode=ParseMode.HTML,
        reply_markup=kb_main(),
    )


@_admin_only
async def cmd_status(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        msg_main(),
        parse_mode=ParseMode.HTML,
        reply_markup=kb_main(),
    )


async def cb_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    data = q.data

    if q.from_user.id != TELEGRAM_ADMIN:
        return

    # ── Main menu actions ──
    if data == "main":
        await q.edit_message_text(msg_main(), parse_mode=ParseMode.HTML, reply_markup=kb_main())

    elif data == "stats":
        try:
            from storage.db import get_recent_trades
            trades = await get_recent_trades(20)
        except Exception:
            trades = []
        text = msg_stats(trades)
        kb = InlineKeyboardMarkup([[InlineKeyboardButton(f"{E['back']} Назад", callback_data="main")]])
        await q.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)

    elif data == "trades":
        try:
            from storage.db import get_recent_trades
            trades = await get_recent_trades(5)
            text = msg_stats(trades)
        except Exception:
            text = f"{E['folder']} Нет данных"
        kb = InlineKeyboardMarkup([[InlineKeyboardButton(f"{E['back']} Назад", callback_data="main")]])
        await q.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)

    elif data == "settings":
        text = (
            f"{E['settings']} <b>Настройки</b>\n\n"
            f"{E['right']} Порог уверенности: <b>{state.threshold:.0%}</b>\n"
            f"{E['right']} Авто режим: <b>{'ВКЛ' if state.auto_mode else 'ВЫКЛ'}</b>\n"
            f"{E['right']} Рисковый: <b>{'ВКЛ' if state.risky_mode else 'ВЫКЛ'}</b>\n"
        )
        await q.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb_settings())

    elif data == "log":
        text = (
            f"{E['msg']} <b>Лог</b>\n\n"
            f"Последний цикл: <i>{state.last_cycle}</i>\n"
            f"P&L сессии: <b>${state.last_pnl:+.2f}</b>\n"
            f"Всего сделок: <b>{state.total_trades}</b>"
        )
        kb = InlineKeyboardMarkup([[InlineKeyboardButton(f"{E['back']} Назад", callback_data="main")]])
        await q.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)

    # ── Toggles ──
    elif data == "toggle_auto":
        state.auto_mode = not state.auto_mode
        await q.edit_message_text(msg_main(), parse_mode=ParseMode.HTML, reply_markup=kb_main())

    elif data == "toggle_risky":
        state.risky_mode = not state.risky_mode
        await q.edit_message_text(msg_main(), parse_mode=ParseMode.HTML, reply_markup=kb_main())

    elif data == "toggle_pause":
        state.paused = not state.paused
        status = f"{E['warn']} Бот поставлен на паузу" if state.paused else f"{E['ok']} Бот возобновлён"
        await q.answer(status, show_alert=True)
        await q.edit_message_text(msg_main(), parse_mode=ParseMode.HTML, reply_markup=kb_main())

    # ── Settings actions ──
    elif data == "thresh_up":
        state.threshold = min(state.threshold + 0.05, 0.95)
        await q.edit_message_text(
            f"{E['settings']} <b>Настройки</b>\n\n{E['ok']} Порог: <b>{state.threshold:.0%}</b>",
            parse_mode=ParseMode.HTML, reply_markup=kb_settings()
        )

    elif data == "thresh_down":
        state.threshold = max(state.threshold - 0.05, 0.50)
        await q.edit_message_text(
            f"{E['settings']} <b>Настройки</b>\n\n{E['ok']} Порог: <b>{state.threshold:.0%}</b>",
            parse_mode=ParseMode.HTML, reply_markup=kb_settings()
        )

    elif data == "calibrate":
        await q.answer(f"⏳ Калибровка запущена...", show_alert=True)
        try:
            from ai.calibrator import calibrate
            result = await calibrate()
            text = (
                f"{E['hammer']} <b>Калибровка завершена</b>\n\n"
                f"{E['right']} Новый порог: <b>{result.get('new_threshold', state.threshold):.0%}</b>\n"
                f"{E['msg']} {result.get('reasoning', '')[:200]}"
            )
            kb = InlineKeyboardMarkup([[InlineKeyboardButton(f"{E['back']} Назад", callback_data="settings")]])
            await q.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
        except Exception as ex:
            await q.answer(f"Ошибка: {ex}", show_alert=True)

    elif data == "learn":
        await q.answer("⏳ Извлекаю уроки (R1)...", show_alert=True)
        try:
            from ai.learning import extract_lessons
            result = await extract_lessons()
            lessons = result.get("lessons", [])
            text = (
                f"{E['globe']} <b>Уроки извлечены</b>\n\n" +
                "\n".join(f"{E['right']} {l}" for l in lessons[:5])
            )
            kb = InlineKeyboardMarkup([[InlineKeyboardButton(f"{E['back']} Назад", callback_data="settings")]])
            await q.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
        except Exception as ex:
            await q.answer(f"Ошибка: {ex}", show_alert=True)

    # ── Signal approval ──
    elif data.startswith("approve_"):
        if state.pending_event:
            state.pending_approve = True
            state.pending_event.set()
        await q.edit_message_text(
            q.message.text + f"\n\n{E['ok']} <b>Исполняется...</b>",
            parse_mode=ParseMode.HTML,
        )

    elif data.startswith("reject_"):
        if state.pending_event:
            state.pending_approve = False
            state.pending_event.set()
        await q.edit_message_text(
            q.message.text + f"\n\n{E['no']} <b>Пропущено.</b>",
            parse_mode=ParseMode.HTML,
        )


# ── Public API (called from main trading loop) ────────────────────────────────

class TelegramBot:
    def __init__(self, app: Application):
        self._app = app

    async def notify_signal(self, sig_dict: dict, signal_id: str = "0") -> bool:
        """Send signal notification. In confirm mode returns True if user approved."""
        if not TELEGRAM_TOKEN or state.paused:
            return True  # no bot configured = auto-approve

        text = msg_signal(sig_dict)
        await self._app.bot.send_message(
            chat_id=TELEGRAM_ADMIN,
            text=text,
            parse_mode=ParseMode.HTML,
            reply_markup=kb_signal(signal_id),
        )

        if state.auto_mode:
            return True  # auto mode = no wait

        # Wait for inline button response (max 5 minutes)
        event = asyncio.Event()
        state.pending_event = event
        state.pending_approve = False
        try:
            await asyncio.wait_for(event.wait(), timeout=300)
        except asyncio.TimeoutError:
            state.pending_approve = False
        finally:
            state.pending_event = None

        return state.pending_approve

    async def notify_result(self, result: dict):
        if not TELEGRAM_TOKEN:
            return
        pnl = result.get("amount_usd", 0)
        side = result.get("side", "")
        icon = E["ok"] if result.get("status") in ("ok", "mock") else E["no"]
        text = (
            f"{icon} <b>Сделка исполнена</b>\n\n"
            f"{E['box']} {result.get('market', '')[:60]}\n"
            f"{E['right']} {side} · <b>${pnl:.2f}</b>\n"
            f"{E['chart']} Уверенность: {result.get('confidence', 0):.0%}"
        )
        await self._app.bot.send_message(
            chat_id=TELEGRAM_ADMIN, text=text, parse_mode=ParseMode.HTML
        )

    async def notify_cycle(self, n_signals: int, pnl_delta: float):
        if not TELEGRAM_TOKEN:
            return
        state.last_cycle = datetime.utcnow().strftime("%H:%M UTC")
        state.last_pnl += pnl_delta
        icon = E["ok"] if pnl_delta >= 0 else E["warn"]
        text = (
            f"{icon} <b>Цикл завершён</b>\n"
            f"{E['right']} Сигналов: <b>{n_signals}</b>\n"
            f"{E['chart']} Изменение: <b>${pnl_delta:+.2f}</b>"
        )
        await self._app.bot.send_message(
            chat_id=TELEGRAM_ADMIN, text=text, parse_mode=ParseMode.HTML
        )

    async def send_text(self, text: str):
        if not TELEGRAM_TOKEN:
            return
        await self._app.bot.send_message(
            chat_id=TELEGRAM_ADMIN, text=text, parse_mode=ParseMode.HTML
        )


# ── Bot runner ────────────────────────────────────────────────────────────────

async def start_bot() -> Optional[TelegramBot]:
    global _app, _tg_bot

    if not TELEGRAM_TOKEN:
        log.warning("TELEGRAM_TOKEN not set — bot disabled")
        return None

    _app = (
        Application.builder()
        .token(TELEGRAM_TOKEN)
        .build()
    )
    _app.add_handler(CommandHandler("start",  cmd_start))
    _app.add_handler(CommandHandler("status", cmd_status))
    _app.add_handler(CallbackQueryHandler(cb_handler))

    await _app.initialize()
    await _app.start()
    await _app.updater.start_polling(drop_pending_updates=True)

    _tg_bot = TelegramBot(_app)

    # Send startup message
    try:
        await _app.bot.send_message(
            chat_id=TELEGRAM_ADMIN,
            text=(
                f"{E['plane']} <b>CLAUDE BOT запущен</b>\n\n"
                f"{E['ok']} Система готова к торговле\n"
                f"{E['right']} Порог: <b>{state.threshold:.0%}</b>\n"
                f"{E['shield']} Рисковый режим: <b>{'ВКЛ' if state.risky_mode else 'ВЫКЛ'}</b>"
            ),
            parse_mode=ParseMode.HTML,
            reply_markup=kb_main(),
        )
    except Exception:
        pass

    return _tg_bot


async def stop_bot():
    if _app:
        await _app.updater.stop()
        await _app.stop()
        await _app.shutdown()
