from datetime import date

import pytest

from ai_daily_brief.weekly_report import render_weekly_report, summarize_week


def test_weekly_report_uses_latest_run_per_day() -> None:
    runs = [
        {
            "target_date": "2026-07-10", "finished_at": "2026-07-11T03:00:00Z",
            "email_status": "dry_run", "collected": 5, "selected": 1,
        },
        {
            "target_date": "2026-07-10", "finished_at": "2026-07-11T02:00:00Z",
            "email_status": "sent:new", "collected": 120, "in_window": 30,
            "deduplicated": 20, "selected": 10, "duration_seconds": 20, "llm_used": True,
        },
        {
            "target_date": "2026-07-10", "finished_at": "2026-07-11T01:00:00Z",
            "email_status": "failed", "collected": 10, "selected": 0,
        },
        {
            "target_date": "2026-07-11", "finished_at": "2026-07-12T01:00:00Z",
            "email_status": "sent:next", "collected": 80, "in_window": 20,
            "deduplicated": 10, "selected": 8, "duration_seconds": 10, "llm_used": False,
        },
    ]
    sources = [
        {"source_name": "OpenAI", "status": "success"},
        {"source_name": "Broken RSS", "status": "error"},
    ]
    deliveries = [
        {"target_date": "2026-07-10", "status": "delivered"},
        {"target_date": "2026-07-11", "status": "delivered"},
    ]
    quality = [
        {
            "passed": True, "official_ratio": 0.6, "multi_source_ratio": 0.3,
            "summary_completeness": 1, "average_score": 65, "warnings": [],
        },
        {
            "passed": False, "official_ratio": 0.2, "multi_source_ratio": 0.1,
            "summary_completeness": 0.7, "average_score": 45, "warnings": ["low"],
        },
    ]
    metrics = summarize_week(date(2026, 7, 11), 7, runs, sources, deliveries, quality)
    assert metrics.attempts == 4
    assert metrics.active_days == 2
    assert metrics.successful_send_days == 2
    assert metrics.delivered_days == 2
    assert metrics.delivery_success_rate == 28.57
    assert metrics.average_collected == 100
    assert metrics.average_selected == 9
    assert metrics.llm_usage_rate == 50
    assert metrics.source_success_rate == 50
    assert metrics.problem_sources == [{"source": "Broken RSS", "errors": 1}]
    assert metrics.quality_pass_rate == 50
    assert metrics.average_official_ratio == 40
    assert metrics.average_multi_source_ratio == 20
    assert metrics.average_summary_completeness == 85
    assert metrics.average_quality_score == 55
    assert metrics.quality_warning_runs == 1


def test_weekly_report_handles_empty_period() -> None:
    metrics = summarize_week(date(2026, 7, 11), 7, [], [], [])
    assert metrics.active_days == 0
    assert metrics.delivery_success_rate == 0
    assert metrics.source_success_rate == 0
    assert "0/7" in render_weekly_report(metrics)


def test_weekly_report_rejects_invalid_period() -> None:
    with pytest.raises(ValueError):
        summarize_week(date(2026, 7, 11), 0, [], [], [])


def test_weekly_report_escapes_source_names() -> None:
    metrics = summarize_week(
        date(2026, 7, 11), 7, [],
        [{"source_name": "<script>", "status": "error"}], [],
    )
    rendered = render_weekly_report(metrics)
    assert "&lt;script&gt;" in rendered
    assert "<script>" not in rendered
