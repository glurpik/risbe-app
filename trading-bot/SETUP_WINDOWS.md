# Установка на Windows

## Шаг 1 — Python 3.11

Открой **PowerShell** (Win+X → Windows PowerShell) и выполни:

```powershell
winget install Python.Python.3.11
```

Закрой и открой PowerShell заново, потом проверь:

```powershell
python --version
# должно быть Python 3.11.x
```

---

## Шаг 2 — Скачай репо

```powershell
winget install Git.Git
git clone https://github.com/glurpik/risbe-app.git
cd risbe-app\trading-bot
```

---

## Шаг 3 — Виртуальное окружение

```powershell
python -m venv venv
venv\Scripts\activate
# в строке появится (venv) — значит всё ок
```

---

## Шаг 4 — Зависимости

```powershell
pip install -r requirements.txt
```

Если ошибка на `lxml` или `newspaper3k` — ничего страшного, они опциональные:

```powershell
pip install -r requirements.txt --ignore-requires-python
```

---

## Шаг 5 — Ключи

```powershell
copy .env.example .env
notepad .env
```

Вставь ключи (см. ниже где брать).

---

## Шаг 6 — Запуск

```powershell
# Режим с подтверждением (рекомендуется сначала)
python main.py run

# Один тестовый цикл без реальных сделок
python main.py run --once

# Дашборд открывается автоматически на http://localhost:8080
```

---

## Где брать ключи

### DeepSeek API (главный ключ, нужен обязательно)
1. Зайди на https://platform.deepseek.com
2. Регистрация (email)
3. API Keys → Create API Key
4. Пополни на $5 — хватит на несколько месяцев

### Polymarket
1. Зайди на https://polymarket.com
2. Подключи кошелёк Rabby
3. Settings → API → Generate Key
4. Скопируй Key, Secret, Passphrase

### Rabby Wallet + USDC
1. Установи Rabby: https://rabby.io (расширение Chrome/Edge)
2. Создай новый кошелёк → **сохрани seed-фразу в надёжном месте**
3. Экспорт приватного ключа: Rabby → иконка аккаунта → Export Private Key
4. Пополни USDC через сеть **Polygon**:
   - Binance/Bybit → вывод → USDC → сеть Polygon → адрес кошелька
   - Минимум $25–30

---

## Структура .env

```env
DEEPSEEK_API_KEY=sk-xxxxxxxxxxxxxxxx

POLYMARKET_API_KEY=xxxxxxxx
POLYMARKET_SECRET=xxxxxxxx
POLYMARKET_PASSPHRASE=xxxxxxxx

WALLET_PRIVATE_KEY=0xxxxxxxваш_приватный_ключ

AUTO_MODE=false
CONFIDENCE_THRESHOLD=0.75
MAX_TRADE_USD=3
NEWS_INTERVAL_MIN=30
```

---

## Автозапуск при включении компа (опционально)

Создай файл `start_bot.bat` в папке `trading-bot`:

```bat
@echo off
cd /d %~dp0
call venv\Scripts\activate
python main.py run
pause
```

Потом можно добавить в Планировщик задач Windows.

---

## Если что-то не работает

```powershell
# Посмотреть логи
python main.py run --once

# Только дашборд (без торговли)
python dashboard.py

# Тест подключения к DeepSeek
python -c "from ai.analyzer import _get_client; print(_get_client().models.list())"
```
