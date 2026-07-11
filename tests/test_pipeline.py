from datetime import date
from pathlib import Path

from ai_daily_brief.config import Settings
from ai_daily_brief.pipeline import run_pipeline


def test_sample_pipeline_without_external_keys(tmp_path: Path) -> None:
    project = Path(__file__).parents[1]
    settings = Settings(database_path=str(tmp_path / "daily.db"))
    output = tmp_path / "brief.html"
    articles, stats, html = run_pipeline(
        settings=settings,
        target_date=date(2026, 7, 10),
        sample_path=str(project / "data" / "sample_articles.json"),
        output_path=str(output),
    )
    assert stats.collected == 4
    assert stats.selected == 3
    assert stats.llm_used is False
    assert stats.email_status == "dry_run"
    assert output.exists()
    assert "AI行业日报" in html
    assert any(item.verification == "官方来源" for item in articles)

