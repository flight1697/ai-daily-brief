from datetime import datetime, timezone

from ai_daily_brief.schedule_guard import FALLBACK_SCHEDULE, PRIMARY_SCHEDULE, should_send


NOW = datetime(2026, 7, 12, 1, 15, tzinfo=timezone.utc)


def test_primary_schedule_always_attempts_delivery() -> None:
    assert should_send("schedule", PRIMARY_SCHEDULE, 2, [], NOW) is True


def test_delayed_primary_skips_after_fallback_succeeded() -> None:
    runs = [{
        "id": 1, "event": "schedule", "conclusion": "success",
        "created_at": "2026-07-12T01:16:00Z",
    }]
    assert should_send("schedule", PRIMARY_SCHEDULE, 2, runs, NOW) is False


def test_manual_dispatch_always_attempts_delivery() -> None:
    assert should_send("workflow_dispatch", "", 2, [], NOW) is True


def test_fallback_skips_after_successful_scheduled_run_today() -> None:
    runs = [{
        "id": 1, "event": "schedule", "conclusion": "success",
        "created_at": "2026-07-12T00:47:00Z",
    }]
    assert should_send("schedule", FALLBACK_SCHEDULE, 2, runs, NOW) is False


def test_fallback_runs_after_failure_or_previous_day_success() -> None:
    runs = [
        {"id": 1, "event": "schedule", "conclusion": "failure", "created_at": "2026-07-12T00:47:00Z"},
        {"id": 3, "event": "schedule", "conclusion": "success", "created_at": "2026-07-11T00:47:00Z"},
    ]
    assert should_send("schedule", FALLBACK_SCHEDULE, 2, runs, NOW) is True
