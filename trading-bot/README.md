# AI Trading Bot

Торгует на Polymarket и управляет крипто-кошельком, анализируя 50+ новостных источников через Claude AI.

## Быстрый старт

```bash
cd trading-bot
pip install -r requirements.txt
cp .env.example .env
# заполни .env своими ключами
```

## Команды

```bash
# Режим с подтверждением (по умолчанию)
python main.py run

# Автономный режим — торгует сам
python main.py run --auto

# Один цикл и выйти
python main.py run --once

# Загрузить базу знаний из файлов/папки
python main.py load ./my_docs/

# Статистика и история сделок
python main.py stats

# Авто-калибровка порогов через AI
python main.py calibrate
```

## Архитектура

```
news/           ← RSS-парсер 50+ источников (Meduza, Reuters, CoinDesk…)
ai/
  analyzer.py   ← Claude claude-opus-4-8 анализирует рынки с RAG
  calibrator.py ← Само-калибровка порогов на основе истории
  knowledge_base.py ← ChromaDB: хранит новости + исходы сделок
trading/
  polymarket.py ← CLOB API предсказательного рынка
  wallet.py     ← EVM-кошелёк (Polygon/Ethereum)
  executor.py   ← Kelly-lite позиционирование
patterns/       ← Технический анализ (RSI, MACD, Bollinger Bands)
modes/
  confirm_mode.py ← Показывает сигналы, ждёт подтверждения
  auto_mode.py    ← Торгует автоматически
storage/        ← SQLite: история сделок + калибровка
```

## Переменные окружения (.env)

| Переменная | Описание |
|---|---|
| `ANTHROPIC_API_KEY` | Ключ Claude API |
| `POLYMARKET_API_KEY` | Polymarket CLOB ключ |
| `POLYMARKET_SECRET` | Polymarket secret |
| `POLYMARKET_PASSPHRASE` | Polymarket passphrase |
| `WALLET_PRIVATE_KEY` | Приватный ключ EVM-кошелька |
| `RPC_URL` | RPC узел (по умолч. Polygon) |
| `AUTO_MODE` | `true` = автономный режим |
| `CONFIDENCE_THRESHOLD` | Мин. уверенность для сделки (по умолч. 0.72) |
| `MAX_TRADE_USD` | Макс. размер одной сделки в USD |
| `NEWS_INTERVAL_MIN` | Интервал опроса новостей в минутах |
