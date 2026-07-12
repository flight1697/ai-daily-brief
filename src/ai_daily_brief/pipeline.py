from __future__ import annotations

import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, time as dt_time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from .collectors import collect_github, collect_rss
from .config import Settings, load_sources
from .database import Database
from .deepseek import enrich_articles
from .delivery import render_digest, send_email
from .metrics_store import persist_remote_metrics
from .models import Article, RunStats, SourceRunStats
from .processors import classify, deduplicate, rank
from .quality import DigestQualityError, assess_quality

logger = logging.getLogger(__name__)


def _persist_run(database: Database, stats: RunStats, source_runs: list[SourceRunStats],
                 quality: dict, settings: Settings) -> None:
    database.save_run(stats, source_runs)
    database.save_quality(stats.run_id, stats.target_date, quality)
    database.close()
    persist_remote_metrics(
        settings.supabase_url, settings.supabase_service_role_key,
        stats, source_runs, settings.email_to, quality,
    )


def _timed_collect_rss(source: dict) -> tuple[list[Article], float]:
    started = time.monotonic()
    articles = collect_rss(source)
    return articles, round(time.monotonic() - started, 3)


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
                 max_items: int = 20, quality_output_path: str | None = None
                 ) -> tuple[list[Article], RunStats, str]:
    started = time.monotonic()
    stats = RunStats(target_date=target_date.isoformat(), started_at=datetime.now(timezone.utc).isoformat())
    window_start, window_end = _window(target_date, settings.timezone)
    articles: list[Article] = []
    source_runs: list[SourceRunStats] = []
    deduplication_config: dict = {}
    quality_config: dict = {}

    if sample_path:
        articles = _sample_articles(sample_path)
    else:
        config = load_sources(source_path)
        deduplication_config = config.get("deduplication", {})
        quality_config = config.get("quality", {})
        enabled_sources = [source for source in config.get("rss", []) if source.get("enabled", True)]
        max_workers = min(int(config.get("collection", {}).get("rss_concurrency", 5)), len(enabled_sources) or 1)
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(_timed_collect_rss, source): (source, time.monotonic())
                for source in enabled_sources
            }
            for future in as_completed(futures):
                source, submitted_at = futures[future]
                try:
                    collected, source_duration = future.result()
                    articles.extend(collected)
                    source_runs.append(SourceRunStats(
                        run_id=stats.run_id, target_date=stats.target_date,
                        source_name=source["name"], source_type="rss",
                        collected_count=len(collected),
                        duration_seconds=source_duration,
                    ))
                except Exception as exc:  # One broken source must not abort the daily run.
                    stats.source_errors += 1
                    logger.warning("Source %s failed: %s", source.get("name"), exc)
                    source_runs.append(SourceRunStats(
                        run_id=stats.run_id, target_date=stats.target_date,
                        source_name=source.get("name", "unknown"), source_type="rss",
                        status="error", error_message=str(exc)[:1000],
                        duration_seconds=round(time.monotonic() - submitted_at, 3),
                    ))
        github_started = time.monotonic()
        try:
            collected = collect_github(config.get("github", {}), settings.github_token,
                                       window_start, window_end)
            articles.extend(collected)
            source_runs.append(SourceRunStats(
                run_id=stats.run_id, target_date=stats.target_date,
                source_name="GitHub", source_type="github",
                collected_count=len(collected),
                duration_seconds=round(time.monotonic() - github_started, 3),
            ))
        except Exception as exc:
            stats.source_errors += 1
            logger.warning("GitHub collection failed: %s", exc)
            source_runs.append(SourceRunStats(
                run_id=stats.run_id, target_date=stats.target_date,
                source_name="GitHub", source_type="github", status="error",
                error_message=str(exc)[:1000],
                duration_seconds=round(time.monotonic() - github_started, 3),
            ))

    stats.collected = len(articles)
    articles = [item for item in articles if window_start <= item.published_at.astimezone(timezone.utc) < window_end]
    stats.in_window = len(articles)
    articles = deduplicate(
        articles,
        title_threshold=float(deduplication_config.get("title_threshold", 0.88)),
        content_threshold=float(deduplication_config.get("content_threshold", 0.72)),
    )
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
    quality = assess_quality(
        selected,
        min_items=int(quality_config.get("min_items", 3)),
        min_sources=int(quality_config.get("min_sources", 2)),
        min_categories=int(quality_config.get("min_categories", 2)),
        min_summary_completeness=float(quality_config.get("min_summary_completeness", 0.8)),
    )
    logger.info("Quality assessment: %s", json.dumps(quality.to_dict(), ensure_ascii=False))

    database = Database(settings.database_path)
    database.save_articles(selected)
    stats.duration_seconds = round(time.monotonic() - started, 2)
    html = render_digest(selected, target_date, stats)
    if output_path:
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(html, encoding="utf-8")
    if quality_output_path:
        quality_output = Path(quality_output_path)
        quality_output.parent.mkdir(parents=True, exist_ok=True)
        quality_output.write_text(
            json.dumps(quality.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
        )

    if send:
        if not quality.passed:
            stats.email_status = "blocked:quality"
            stats.duration_seconds = round(time.monotonic() - started, 2)
            stats.finished_at = datetime.now(timezone.utc).isoformat()
            _persist_run(database, stats, source_runs, quality.to_dict(), settings)
            raise DigestQualityError(quality)
        try:
            message_id = send_email(settings.resend_api_key, settings.email_from, settings.email_to,
                                    f"AI行业日报｜{target_date.isoformat()}", html)
            stats.email_status = f"sent:{message_id}"
        except Exception:
            stats.email_status = "failed"
            stats.duration_seconds = round(time.monotonic() - started, 2)
            stats.finished_at = datetime.now(timezone.utc).isoformat()
            _persist_run(database, stats, source_runs, quality.to_dict(), settings)
            raise
    else:
        stats.email_status = "dry_run"
    stats.duration_seconds = round(time.monotonic() - started, 2)
    stats.finished_at = datetime.now(timezone.utc).isoformat()
    _persist_run(database, stats, source_runs, quality.to_dict(), settings)
    return selected, stats, html
