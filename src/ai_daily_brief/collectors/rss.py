from __future__ import annotations

import calendar
import logging
import re
import time
from datetime import datetime, timezone
from html import unescape
from typing import Any
from urllib.parse import unquote, urlparse
from xml.etree import ElementTree

import feedparser
import httpx

from ..models import Article

logger = logging.getLogger(__name__)


def _sitemap_time(value: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        return parsed.replace(tzinfo=parsed.tzinfo or timezone.utc).astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None


def _page_metadata(html: str, fallback: str) -> tuple[str, str]:
    def meta(name: str) -> str:
        patterns = (
            rf'<meta[^>]+(?:property|name)=["\']{re.escape(name)}["\'][^>]+content=["\'](.*?)["\']',
            rf'<meta[^>]+content=["\'](.*?)["\'][^>]+(?:property|name)=["\']{re.escape(name)}["\']',
        )
        for pattern in patterns:
            match = re.search(pattern, html, re.I | re.S)
            if match:
                return unescape(re.sub(r"\s+", " ", match.group(1))).strip()
        return ""

    title = meta("og:title") or meta("twitter:title")
    if not title:
        match = re.search(r"<title[^>]*>(.*?)</title>", html, re.I | re.S)
        title = unescape(re.sub(r"\s+", " ", match.group(1))).strip() if match else fallback
    return title or fallback, meta("og:description") or meta("description")


def _collect_sitemap(source: dict[str, Any], content: bytes, timeout: float) -> list[Article]:
    root = ElementTree.fromstring(content)
    include_path = source.get("include_path", "")
    now = datetime.now(timezone.utc)
    recent_seconds = int(source.get("recent_days", 7)) * 86400
    candidates: list[tuple[str, datetime]] = []
    for node in root.findall("{*}url"):
        location = node.findtext("{*}loc", "").strip()
        modified = _sitemap_time(node.findtext("{*}lastmod", ""))
        if not location or not modified or include_path not in urlparse(location).path:
            continue
        if abs((now - modified).total_seconds()) <= recent_seconds:
            candidates.append((location, modified))

    articles: list[Article] = []
    for location, modified in candidates[:12]:
        slug = unquote(urlparse(location).path.rstrip("/").split("/")[-1]).replace("-", " ")
        title, description = slug.title(), ""
        try:
            page = httpx.get(
                location, headers={"User-Agent": "AI-Daily-Brief/0.1"},
                timeout=timeout, follow_redirects=True,
            )
            page.raise_for_status()
            title, description = _page_metadata(page.text, title)
        except Exception as exc:
            logger.warning("Sitemap page failed %s: %s", location, exc)
        articles.append(Article(
            title=title, url=location, source=source["name"], published_at=modified,
            content=description, language=source.get("language", "unknown"),
            source_weight=int(source.get("weight", 50)), official=bool(source.get("official", False)),
        ))
    return articles


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
            if source.get("format") == "sitemap":
                articles = _collect_sitemap(source, response.content, timeout)
                logger.info("Sitemap %-20s %d items", source["name"], len(articles))
                return articles
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
