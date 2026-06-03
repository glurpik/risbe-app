"""EVM wallet wrapper (Polygon/Ethereum) using web3.py."""

from typing import Optional
from config import WALLET_PRIVATE_KEY, RPC_URL

try:
    from web3 import Web3
    WEB3_AVAILABLE = True
except ImportError:
    WEB3_AVAILABLE = False


_w3: Optional["Web3"] = None
_account = None


def _get_web3():
    global _w3, _account
    if not WEB3_AVAILABLE:
        return None, None
    if _w3 is None:
        _w3 = Web3(Web3.HTTPProvider(RPC_URL))
        if WALLET_PRIVATE_KEY:
            _account = _w3.eth.account.from_key(WALLET_PRIVATE_KEY)
    return _w3, _account


def get_balance_matic() -> float:
    w3, account = _get_web3()
    if not w3 or not account:
        return 0.0
    try:
        bal_wei = w3.eth.get_balance(account.address)
        return float(w3.from_wei(bal_wei, "ether"))
    except Exception:
        return 0.0


def get_address() -> str:
    _, account = _get_web3()
    if account:
        return account.address
    return "0x0000000000000000000000000000000000000000"


def send_matic(to: str, amount_matic: float) -> dict:
    w3, account = _get_web3()
    if not w3 or not account:
        return {"status": "error", "message": "Wallet not configured"}
    try:
        nonce = w3.eth.get_transaction_count(account.address)
        tx = {
            "nonce": nonce,
            "to": to,
            "value": w3.to_wei(amount_matic, "ether"),
            "gas": 21000,
            "gasPrice": w3.eth.gas_price,
            "chainId": w3.eth.chain_id,
        }
        signed = account.sign_transaction(tx)
        tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
        return {"status": "ok", "tx_hash": tx_hash.hex()}
    except Exception as e:
        return {"status": "error", "message": str(e)}
