from datetime import datetime, timezone

from ai_daily_brief.models import Article
from ai_daily_brief.processors.rules import classify, rank


def test_policy_classification_and_score_cap() -> None:
    item = Article(
        title="监管机构发布人工智能管理法规", url="https://media.example/policy",
        source="媒体", published_at=datetime.now(timezone.utc), content="政府公布新政策",
        source_weight=75, official=False,
    )
    rank(classify(item))
    assert item.category == "政策与监管"
    assert item.score <= 60

