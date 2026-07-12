from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from .models import Article


@dataclass(slots=True)
class QualityAssessment:
    passed: bool
    item_count: int
    source_count: int
    category_count: int
    official_count: int
    multi_source_count: int
    official_ratio: float
    multi_source_ratio: float
    summary_completeness: float
    average_score: float
    blocking_reasons: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class DigestQualityError(RuntimeError):
    def __init__(self, assessment: QualityAssessment):
        self.assessment = assessment
        super().__init__("Digest did not pass the pre-delivery quality gate")


def assess_quality(articles: list[Article], min_items: int = 3, min_sources: int = 2,
                   min_categories: int = 2,
                   min_summary_completeness: float = 0.8) -> QualityAssessment:
    item_count = len(articles)
    all_sources = {
        source
        for article in articles
        for source in [article.source, *(link.name for link in article.related_sources)]
    }
    source_count = len(all_sources)
    category_count = len({article.category for article in articles})
    official_count = sum(article.official for article in articles)
    multi_source_count = sum(
        len({article.source, *(link.name for link in article.related_sources)}) >= 2
        for article in articles
    )
    completed_summaries = sum(
        bool(article.summary.strip()) and bool(article.why_it_matters.strip())
        for article in articles
    )
    official_ratio = round(official_count / item_count, 3) if item_count else 0.0
    multi_source_ratio = round(multi_source_count / item_count, 3) if item_count else 0.0
    summary_completeness = round(completed_summaries / item_count, 3) if item_count else 0.0
    average_score = round(sum(article.score for article in articles) / item_count, 2) if item_count else 0.0

    blocking_reasons: list[str] = []
    if item_count < min_items:
        blocking_reasons.append(f"入选内容不足：{item_count} < {min_items}")
    if source_count < min_sources:
        blocking_reasons.append(f"独立来源不足：{source_count} < {min_sources}")
    if category_count < min_categories:
        blocking_reasons.append(f"分类覆盖不足：{category_count} < {min_categories}")
    if summary_completeness < min_summary_completeness:
        blocking_reasons.append(
            f"摘要完整率不足：{summary_completeness:.1%} < {min_summary_completeness:.1%}"
        )

    warnings: list[str] = []
    if official_ratio < 0.2:
        warnings.append(f"官方来源比例偏低：{official_ratio:.1%}")
    if multi_source_ratio < 0.2:
        warnings.append(f"交叉核验比例偏低：{multi_source_ratio:.1%}")
    if average_score < 50:
        warnings.append(f"平均重要性评分偏低：{average_score}")
    return QualityAssessment(
        passed=not blocking_reasons,
        item_count=item_count,
        source_count=source_count,
        category_count=category_count,
        official_count=official_count,
        multi_source_count=multi_source_count,
        official_ratio=official_ratio,
        multi_source_ratio=multi_source_ratio,
        summary_completeness=summary_completeness,
        average_score=average_score,
        blocking_reasons=blocking_reasons,
        warnings=warnings,
    )
