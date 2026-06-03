import asyncio
import feedparser
import aiohttp
from datetime import datetime, timezone
from typing import List

from .parser import Article, clean_html, truncate
from .sources import SOURCES


FETCH_TIMEOUT = 15
MAX_ARTICLES_PER_SOURCE = 5


async def _fetch_feed(session: aiohttp.ClientSession, source: dict) -> List[Article]:
    articles = []
    try:
        async with session.get(source["url"], timeout=aiohttp.ClientTimeout(total=FETCH_TIMEOUT)) as resp:
            content = await resp.read()
        feed = feedparser.parse(content)
        for entry in feed.entries[:MAX_ARTICLES_PER_SOURCE]:
            title = clean_html(entry.get("title", ""))
            summary = truncate(clean_html(entry.get("summary", entry.get("description", ""))))
            url = entry.get("link", "")
            published = _parse_date(entry)
            if title:
                articles.append(Article(
                    source=source["name"],
                    title=title,
                    summary=summary,
                    url=url,
                    published=published,
                    lang=source["lang"],
                ))
    except Exception:
        pass
    return articles


def _parse_date(entry) -> datetime:
    try:
        import time
        t = entry.get("published_parsed") or entry.get("updated_parsed")
        if t:
            return datetime.fromtimestamp(time.mktime(t), tz=timezone.utc)
    except Exception:
        pass
    return datetime.now(tz=timezone.utc)


async def fetch_all_news() -> List[Article]:
    connector = aiohttp.TCPConnector(limit=20, ssl=False)
    async with aiohttp.ClientSession(connector=connector) as session:
        tasks = [_fetch_feed(session, src) for src in SOURCES]
        results = await asyncio.gather(*tasks, return_exceptions=True)
    articles = []
    for r in results:
        if isinstance(r, list):
            articles.extend(r)
    articles.sort(key=lambda a: a.published, reverse=True)
    return articles
