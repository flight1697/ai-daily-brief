from datetime import date, datetime, timezone

from ai_daily_brief.dashboard import build_dashboard_data, render_dashboard


def test_dashboard_contains_only_aggregate_daily_data() -> None:
    runs = [{
        "target_date": "2026-07-11", "finished_at": "2026-07-12T01:00:00Z",
        "collected": 200, "in_window": 40, "deduplicated": 20, "selected": 10,
        "source_errors": 0, "llm_used": True, "email_status": "sent:private-message-id",
        "duration_seconds": 18,
    }]
    deliveries = [{
        "target_date": "2026-07-11", "status": "delivered",
        "recipient": "private@example.com", "subject": "private subject",
    }]
    metrics, daily = build_dashboard_data(date(2026, 7, 11), 30, runs, [], deliveries)
    rendered = render_dashboard(
        metrics, daily, generated_at=datetime(2026, 7, 12, tzinfo=timezone.utc)
    )
    assert "已送达" in rendered
    assert "200" in rendered
    assert "private-message-id" not in rendered
    assert "private@example.com" not in rendered
    assert "private subject" not in rendered


def test_dashboard_marks_missing_delivery() -> None:
    runs = [{
        "target_date": "2026-07-11", "finished_at": "2026-07-12T01:00:00Z",
        "email_status": "failed",
    }]
    _, daily = build_dashboard_data(date(2026, 7, 11), 30, runs, [], [])
    assert daily[0].delivery_status == "missing"


def test_dashboard_escapes_problem_source() -> None:
    metrics, daily = build_dashboard_data(
        date(2026, 7, 11), 30, [],
        [{"source_name": "<script>", "status": "error"}], [],
    )
    rendered = render_dashboard(metrics, daily)
    assert "&lt;script&gt;" in rendered
    assert "<script>" not in rendered
