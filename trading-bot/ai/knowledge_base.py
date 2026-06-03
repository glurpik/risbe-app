"""Vector store (ChromaDB) for RAG — stores news + trade history for context."""

import chromadb
from chromadb.utils.embedding_functions import DefaultEmbeddingFunction
from pathlib import Path
from typing import List
from datetime import datetime

from config import CHROMA_DB_PATH


_client = None
_collection = None


def _get_collection():
    global _client, _collection
    if _collection is None:
        Path(CHROMA_DB_PATH).mkdir(parents=True, exist_ok=True)
        _client = chromadb.PersistentClient(path=CHROMA_DB_PATH)
        _collection = _client.get_or_create_collection(
            name="trading_knowledge",
            embedding_function=DefaultEmbeddingFunction(),
        )
    return _collection


def add_articles(articles: list):
    col = _get_collection()
    docs, ids, metas = [], [], []
    for art in articles:
        doc_id = f"{art.source}::{art.url or art.title[:60]}"
        docs.append(art.to_text())
        ids.append(doc_id)
        metas.append({"source": art.source, "ts": art.published.isoformat(), "lang": art.lang})
    if docs:
        col.upsert(documents=docs, ids=ids, metadatas=metas)


def add_trade_outcome(market: str, analysis: str, outcome: str, confidence: float):
    col = _get_collection()
    doc_id = f"trade::{market}::{datetime.utcnow().isoformat()}"
    col.upsert(
        documents=[f"TRADE OUTCOME — {market}: predicted={outcome}, confidence={confidence:.2f}\n{analysis}"],
        ids=[doc_id],
        metadatas=[{"type": "trade", "market": market, "outcome": outcome}],
    )


def query(text: str, n_results: int = 8) -> List[str]:
    col = _get_collection()
    try:
        results = col.query(query_texts=[text], n_results=n_results)
        return results["documents"][0] if results["documents"] else []
    except Exception:
        return []


def load_documents(texts: List[str], source: str = "manual"):
    """Load arbitrary text chunks into the knowledge base."""
    col = _get_collection()
    docs, ids, metas = [], [], []
    for i, text in enumerate(texts):
        docs.append(text)
        ids.append(f"{source}::{i}::{hash(text)}")
        metas.append({"source": source, "ts": datetime.utcnow().isoformat()})
    col.upsert(documents=docs, ids=ids, metadatas=metas)
    return len(docs)
