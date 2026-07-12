from datetime import datetime, timezone

from ai_daily_brief.deepseek import _apply_row
from ai_daily_brief.models import Article


def article() -> Article:
    return Article("Title", "https://example.com", "Source", datetime.now(timezone.utc), category="研究与论文")


def test_valid_deepseek_row_is_applied() -> None:
    item = article()
    assert _apply_row(item, {
        "summary": "这是基于来源生成的事实摘要。",
        "why_it_matters": "这可能影响行业应用。",
        "category": "模型与产品发布",
        "tags": ["多模态"],
    }) is True
    assert item.category == "模型与产品发布"
    assert item.tags == ["多模态"]


def test_malformed_tags_are_rejected_without_crashing() -> None:
    item = article()
    assert _apply_row(item, {
        "summary": "摘要",
        "why_it_matters": "影响",
        "category": "不存在的分类",
        "tags": "not-a-list",
    }) is False
    assert item.summary == ""
    assert item.category == "研究与论文"

