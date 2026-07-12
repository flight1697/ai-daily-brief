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


def test_same_source_release_templates_with_different_versions_stay_separate() -> None:
    items = [
        article(
            "langchain-ai/langchain 发布 langchain==1.3.13",
            "https://github.com/langchain/releases/langchain-1.3.13", "GitHub Release", True,
        ),
        article(
            "langchain-ai/langchain 发布 langchain-openai==1.3.5",
            "https://github.com/langchain/releases/openai-1.3.5", "GitHub Release", True,
        ),
    ]
    assert len(deduplicate(items)) == 2


def test_cross_source_reports_with_the_same_version_can_merge() -> None:
    items = [
        article(
            "Acme releases Model 5.13.1 for developers",
            "https://official.example/model-5-13-1", "Acme", True,
        ),
        article(
            "Model 5.13.1 developer release from Acme",
            "https://media.example/model-5-13-1", "Media",
        ),
    ]
    result = deduplicate(items, title_threshold=0.75, content_threshold=0.65)
    assert len(result) == 1
    assert {link.name for link in result[0].related_sources} == {"Media"}


def test_cross_source_reports_with_different_versions_stay_separate() -> None:
    items = [
        article("Acme Model 5.13.1 released", "https://a.example/1", "A"),
        article("Acme Model 5.14.0 released", "https://b.example/2", "B"),
    ]
    assert len(deduplicate(items, title_threshold=0.70, content_threshold=0.60)) == 2


def test_entity_and_action_match_links_lawsuit_wording() -> None:
    items = [
        article(
            "Apple sues OpenAI for allegedly stealing hardware secrets",
            "https://wired.example/apple-openai", "WIRED",
        ),
        article(
            "Apple sues OpenAI over alleged trade secret theft",
            "https://techcrunch.example/apple-openai", "TechCrunch",
        ),
    ]
    result = deduplicate(items)
    assert len(result) == 1
    assert result[0].verification == "多源交叉核验"


def test_entity_and_action_match_links_feature_removal_wording() -> None:
    items = [
        article(
            "Meta turns off the Instagram feature that enabled AI deepfakes",
            "https://verge.example/meta-instagram", "The Verge",
        ),
        article(
            "Meta removes controversial AI feature on Instagram after backlash",
            "https://techcrunch.example/meta-instagram", "TechCrunch",
        ),
    ]
    assert len(deduplicate(items)) == 1


def test_shared_entities_without_a_shared_action_do_not_merge() -> None:
    items = [
        article("Apple partners with OpenAI", "https://a.example/story", "A"),
        article("Apple criticizes OpenAI pricing", "https://b.example/story", "B"),
    ]
    assert len(deduplicate(items)) == 2
