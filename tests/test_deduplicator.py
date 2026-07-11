from datetime import datetime, timezone

from ai_daily_brief.models import Article
from ai_daily_brief.processors.deduplicator import deduplicate


def article(title: str, url: str, source: str, official: bool = False) -> Article:
    return Article(title=title, url=url, source=source,
                   published_at=datetime(2026, 7, 10, tzinfo=timezone.utc),
                   content="Aurora 2 多模态模型正式发布并开放开发者 API",
                   source_weight=90 if official else 70, official=official)


def test_url_and_event_deduplication_prefers_official() -> None:
    items = [
        article("Aurora 2 多模态模型正式发布", "https://media.example/a", "媒体"),
        article("正式发布多模态模型 Aurora 2", "https://official.example/a", "官网", True),
        article("完全不同的芯片项目", "https://example.com/chip", "其他"),
    ]
    result = deduplicate(items, content_threshold=0.65)
    assert len(result) == 2
    merged = next(item for item in result if item.official)
    assert merged.source == "官网"
    assert merged.verification == "官方来源"
    assert len(merged.related_sources) == 1

