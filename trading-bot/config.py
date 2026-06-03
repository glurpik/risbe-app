import os
from dotenv import load_dotenv

load_dotenv()

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
POLYMARKET_API_KEY = os.getenv("POLYMARKET_API_KEY", "")
POLYMARKET_SECRET = os.getenv("POLYMARKET_SECRET", "")
POLYMARKET_PASSPHRASE = os.getenv("POLYMARKET_PASSPHRASE", "")

WALLET_PRIVATE_KEY = os.getenv("WALLET_PRIVATE_KEY", "")
RPC_URL = os.getenv("RPC_URL", "https://polygon-rpc.com")

AUTO_MODE = os.getenv("AUTO_MODE", "false").lower() == "true"
CONFIDENCE_THRESHOLD = float(os.getenv("CONFIDENCE_THRESHOLD", "0.72"))
MAX_TRADE_USD = float(os.getenv("MAX_TRADE_USD", "50"))
NEWS_INTERVAL_MIN = int(os.getenv("NEWS_INTERVAL_MIN", "20"))

CHROMA_DB_PATH = "./data/chroma_db"
SQLITE_PATH = "./data/trading_bot.db"
