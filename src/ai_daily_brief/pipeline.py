from __future__ import annotations

import json
import logging
import time
from datetime import date, datetime, time as dt_time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from .collectors import collect_github, collect_rss
from .config import Settings, load_sources
from .database import Database
from .deepseek import enrich_articles
from .delivery import render_digest, send_email
from .models import Article, RunStats
from .processors import classify, deduplicate, rank

logger = logging.getLogger(__name__)


def _window(target_date: date, tz_name: str) -> tuple[datetime, datetime]:
    zone = ZoneInfo(tz_name)
    start = datetime.combine(target_date, dt_time.min, tzinfo=zone)
    return start.astimezone(timezone.utc), (start + timedelta(days=1)).astimezone(timezone.utc)


def _sample_articles(path: str | Path) -> list[Article]:
    rows = json.loads(Path(path).read_text(encoding="utf-8"))
    return [Article(
        title=row["title"], url=row["url"], source=row["source"],
        published_at=datetime.fromisoformat(row["published_at"]), content=row.get("content", ""),
        language=row.get("language", "unknown"), source_weight=row.get("source_weight", 50),
        official=row.get("official", False),
    ) for row in rows]


def run_pipeline(settings: Settings, target_date: date, source_path: str = "config/sources.yaml",
                 sample_path: str | None = None, send: bool = False, output_path: str | None = None,
                 max_items: int = 20) -> tuple[list[Article], RunStats, str]:
    started = time.monotonic()
    stats = RunStats(target_date=target_date.isoformat(), started_at=datetime.now(timezone.utc).isoformat())
    window_start, window_end = _window(target_date, settings.timezone)
    articles: list[Article] = []

    if sample_path:
        articles = _sample_articles(sample_path)
    else:
        config = load_sources(source_path)
        for source in config.get("rss", []):
            if not source.get("enabled", True):
                continue
            try:
                articles.extend(collect_rss(source))
            except Exception as exc:  # One broken source must not abort the daily run.
                stats.source_errors += 1
                logger.warning("Source %s failed: %s", source.get("name"), exc)
        try:
            articles.extend(collect_github(config.get("github", {}), settings.github_token,
                                           window_start, window_end))
        except Exception as exc:
            stats.source_errors += 1
            logger.warning("GitHub collection failed: %s", exc)

    stats.collected = len(articles)
    articles = [item for item in articles if window_start <= item.published_at.astimezone(timezone.utc) < window_end]
    stats.in_window = len(articles)
    articles = deduplicate(articles)
    stats.deduplicated = len(articles)
    for article in articles:
        rank(classify(article))
    articles.sort(key=lambda item: (item.score, item.source_weight), reverse=True)
    # Reserve the first three positions for distinct categories when possible.
    selected: list[Article] = []
    category_counts: dict[str, int] = {}
    for article in articles:
        if article.category in category_counts:
            continue
        selected.append(article)
        category_counts[article.category] = 1
        if len(selected) >= min(3, max_items):
            break
    for article in articles:
        if article in selected:
            continue
        if category_counts.get(article.category, 0) >= 6:
            continue
        selected.append(article)
        category_counts[article.category] = category_counts.get(article.category, 0) + 1
        if len(selected) >= max_items:
            break
    stats.selected = len(selected)
    stats.llm_used = enrich_articles(selected, settings.deepseek_api_key,
                                      settings.deepseek_base_url, settings.deepseek_model)

    database = Database(settings.database_path)
    database.save_articles(selected)
    stats.duration_seconds = round(time.monotonic() - started, 2)
    html = render_digest(selected, target_date, stats)
    if output_path:
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(html, encoding="utf-8")

    if send:
        try:
            message_id = send_email(settings.resend_api_key, settings.email_from, settings.email_to,
                                    f"AI行业日报｜{target_date.isoformat()}", html)
            stats.email_status = f"sent:{message_id}"
        except Exception:
            stats.email_status = "failed"
            stats.duration_seconds = round(time.monotonic() - started, 2)
            database.save_run(stats)
            database.close()
            raise
    else:
        stats.email_status = "dry_run"
    stats.duration_seconds = round(time.monotonic() - started, 2)
    database.save_run(stats)
    database.close()
    return selected, stats, html
