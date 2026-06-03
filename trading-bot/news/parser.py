import re
from dataclasses import dataclass
from datetime import datetime


@dataclass
class Article:
    source: str
    title: str
    summary: str
    url: str
    published: datetime
    lang: str

    def to_text(self) -> str:
        return f"[{self.source}] {self.title}\n{self.summary}"

    def to_dict(self) -> dict:
        return {
            "source": self.source,
            "title": self.title,
            "summary": self.summary,
            "url": self.url,
            "published": self.published.isoformat(),
            "lang": self.lang,
        }


def clean_html(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def truncate(text: str, max_chars: int = 500) -> str:
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rsplit(" ", 1)[0] + "…"
