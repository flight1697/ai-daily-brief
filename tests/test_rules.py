from datetime import datetime, timezone

from ai_daily_brief.models import Article
from ai_daily_brief.processors.rules import classify, editorial_priority, rank


def test_policy_classification_and_score_cap() -> None:
    item = Article(
        title="监管机构发布人工智能管理法规", url="https://media.example/policy",
        source="媒体", published_at=datetime.now(timezone.utc), content="政府公布新政策",
        source_weight=75, official=False,
    )
    rank(classify(item))
    assert item.category == "政策与监管"
    assert item.score <= 60


def test_strategic_model_news_outranks_routine_github_release() -> None:
    strategic = Article(
        title="Anthropic launches a new Claude reasoning model", url="https://anthropic.com/news/model",
        source="Anthropic News", published_at=datetime.now(timezone.utc),
        content="A new model for coding and enterprise workloads", source_weight=95, official=True,
    )
    routine = Article(
        title="example/tool 发布 v1.2.3", url="https://github.com/example/tool/releases/1.2.3",
        source="GitHub Release", published_at=datetime.now(timezone.utc),
        content="Bug fix and dependency update", source_weight=80, official=True,
    )
    rank(classify(strategic))
    rank(classify(routine))
    assert editorial_priority(strategic) == 2
    assert strategic.score > routine.score + 20


def test_codex_is_classified_as_ai_developer_tool() -> None:
    item = Article(
        title="OpenAI Codex adds a new coding agent workflow", url="https://openai.com/codex",
        source="OpenAI News", published_at=datetime.now(timezone.utc), source_weight=95, official=True,
    )
    rank(classify(item))
    assert item.category == "AI开发工具与Agent"
    assert editorial_priority(item) == 2


def test_codex_alimentarius_is_not_treated_as_openai_codex() -> None:
    item = Article(
        title="New standards added to the Codex Alimentarius", url="https://fao.example/standards",
        source="AI Coding Monitor", published_at=datetime.now(timezone.utc),
        content="FAO food standards", source_weight=88,
    )
    rank(classify(item))
    assert item.category != "AI开发工具与Agent"
    assert editorial_priority(item) == 0


def test_codex_patch_release_is_not_a_must_cover_story() -> None:
    item = Article(
        title="openai/codex 发布 0.144.3", url="https://github.com/openai/codex/releases/0.144.3",
        source="GitHub Release", published_at=datetime.now(timezone.utc),
        content="Patch release", source_weight=80, official=True,
    )
    rank(classify(item))
    assert editorial_priority(item) == 0
    assert item.score < 52
