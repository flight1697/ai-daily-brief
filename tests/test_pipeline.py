import json
import sqlite3
from datetime import date
from pathlib import Path

import pytest

from ai_daily_brief.config import Settings
from ai_daily_brief.pipeline import run_pipeline
from ai_daily_brief.quality import DigestQualityError


def test_sample_pipeline_without_external_keys(tmp_path: Path) -> None:
    project = Path(__file__).parents[1]
    settings = Settings(database_path=str(tmp_path / "daily.db"))
    output = tmp_path / "brief.html"
    quality_output = tmp_path / "quality.json"
    articles, stats, html = run_pipeline(
        settings=settings,
        target_date=date(2026, 7, 10),
        sample_path=str(project / "data" / "sample_articles.json"),
        output_path=str(output),
        quality_output_path=str(quality_output),
    )
    assert stats.collected == 4
    assert stats.selected == 3
    assert stats.llm_used is False
    assert stats.email_status == "dry_run"
    assert output.exists()
    assert quality_output.exists()
    assert '"passed": true' in quality_output.read_text(encoding="utf-8")
    assert "AI行业日报" in html
    assert any(item.verification == "官方来源" for item in articles)


def test_low_quality_digest_is_persisted_but_not_sent(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    sample = tmp_path / "thin.json"
    sample.write_text(json.dumps([{
        "title": "Only story",
        "url": "https://example.com/only",
        "source": "Only source",
        "published_at": "2026-07-10T02:30:00+00:00",
        "content": "A single item is not enough for a daily digest.",
    }]), encoding="utf-8")
    database_path = tmp_path / "daily.db"
    quality_output = tmp_path / "quality.json"
    settings = Settings(
        database_path=str(database_path), resend_api_key="configured",
        email_to="reader@example.com",
    )
    monkeypatch.setattr(
        "ai_daily_brief.pipeline.send_email",
        lambda *_args, **_kwargs: pytest.fail("quality-blocked digest must not be sent"),
    )
    with pytest.raises(DigestQualityError) as raised:
        run_pipeline(
            settings=settings, target_date=date(2026, 7, 10),
            sample_path=str(sample), send=True,
            quality_output_path=str(quality_output),
        )
    assert raised.value.assessment.passed is False
    assert json.loads(quality_output.read_text(encoding="utf-8"))["passed"] is False
    connection = sqlite3.connect(database_path)
    stored = json.loads(connection.execute("SELECT stats FROM runs").fetchone()[0])
    connection.close()
    assert stored["email_status"] == "blocked:quality"
