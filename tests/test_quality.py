from datetime import datetime, timezone

from ai_daily_brief.models import Article, SourceLink
from ai_daily_brief.quality import assess_quality


def article(source: str, category: str, *, official: bool = False,
            related: bool = False, score: float = 70) -> Article:
    return Article(
        title=f"{source} story", url=f"https://example.com/{source}", source=source,
        published_at=datetime.now(timezone.utc), category=category, official=official,
        score=score, summary="摘要", why_it_matters="影响",
        verification="多源报道" if related else "单一信源",
        related_sources=[SourceLink("Related", "https://related.example.com")] if related else [],
    )


def test_diverse_digest_passes_quality_gate() -> None:
    assessment = assess_quality([
        article("Official", "模型与产品发布", official=True, related=True),
        article("Media", "企业与商业动态"),
        article("GitHub", "开源项目", official=True),
    ])
    assert assessment.passed is True
    assert assessment.item_count == 3
    assert assessment.source_count == 4
    assert assessment.category_count == 3
    assert assessment.summary_completeness == 1


def test_thin_digest_is_blocked() -> None:
    assessment = assess_quality([article("Only", "其他")])
    assert assessment.passed is False
    assert len(assessment.blocking_reasons) == 3


def test_weak_verification_produces_warning_without_blocking() -> None:
    assessment = assess_quality([
        article("A", "模型与产品发布", score=40),
        article("B", "企业与商业动态", score=40),
        article("C", "开源项目", score=40),
    ])
    assert assessment.passed is True
    assert any("官方来源比例" in warning for warning in assessment.warnings)
    assert any("交叉核验比例" in warning for warning in assessment.warnings)
    assert any("平均重要性评分" in warning for warning in assessment.warnings)


def test_related_item_from_the_same_source_is_not_cross_verification() -> None:
    first = article("A", "模型与产品发布")
    first.related_sources = [SourceLink("A", "https://example.com/a-duplicate")]
    assessment = assess_quality([
        first,
        article("B", "企业与商业动态", official=True),
        article("C", "开源项目", official=True),
    ])
    assert assessment.multi_source_count == 0
    assert assessment.multi_source_ratio == 0


def test_related_item_from_an_independent_source_counts_as_verification() -> None:
    first = article("A", "模型与产品发布")
    first.related_sources = [SourceLink("Independent", "https://independent.example/story")]
    assessment = assess_quality([
        first,
        article("B", "企业与商业动态", official=True),
        article("C", "开源项目", official=True),
    ])
    assert assessment.multi_source_count == 1
    assert assessment.source_count == 4
