from __future__ import annotations

import calendar
import logging
import time
from datetime import datetime, timezone
from html import unescape
from typing import Any

import feedparser
import httpx

from ..models import Article

logger = logging.getLogger(__name__)


def _entry_time(entry: Any) -> datetime | None:
    value = entry.get("published_parsed") or entry.get("updated_parsed")
    if value:
        return datetime.fromtimestamp(calendar.timegm(value), tz=timezone.utc)
    return None


def collect_rss(source: dict[str, Any], timeout: float = 20.0) -> list[Article]:
    feed = None
    last_error: Exception | None = None
    for attempt in range(2):
        try:
            response = httpx.get(
                source["url"], headers={"User-Agent": "AI-Daily-Brief/0.1"},
                timeout=timeout, follow_redirects=True,
            )
            response.raise_for_status()
            candidate = feedparser.parse(response.content)
            if getattr(candidate, "bozo", False) and not candidate.entries:
                raise RuntimeError(f"RSS parse failed: {getattr(candidate, 'bozo_exception', 'unknown error')}")
            feed = candidate
            break
        except Exception as exc:
            last_error = exc
            if attempt == 0:
                time.sleep(1)
    if feed is None:
        raise RuntimeError(f"RSS failed after 2 attempts: {last_error}") from last_error

    articles: list[Article] = []
    for entry in feed.entries:
        published_at = _entry_time(entry)
        link = entry.get("link", "").strip()
        title = unescape(entry.get("title", "")).strip()
        if not published_at or not link or not title:
            continue
        content = entry.get("summary", "")
        if entry.get("content"):
            content = entry.content[0].get("value", content)
        articles.append(Article(
            title=title,
            url=link,
            source=source["name"],
            published_at=published_at,
            content=content,
            language=source.get("language", "unknown"),
            source_weight=int(source.get("weight", 50)),
            official=bool(source.get("official", False)),
        ))
    logger.info("RSS %-24s %d items", source["name"], len(articles))
    return articles
