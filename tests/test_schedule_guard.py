from datetime import datetime, timezone

import httpx

from ai_daily_brief import schedule_guard
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


def test_external_schedule_skips_when_supabase_has_sent(monkeypatch, capsys) -> None:
    monkeypatch.setenv("GITHUB_EVENT_NAME", "workflow_dispatch")
    monkeypatch.setenv("INPUT_SCHEDULED_RUN", "true")
    monkeypatch.setenv("TARGET_DATE", "2026-07-12")
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "secret")
    monkeypatch.setattr(schedule_guard, "supabase_has_sent", lambda *_: True)
    schedule_guard.main()
    assert capsys.readouterr().out.strip() == "false"


def test_external_schedule_runs_when_supabase_has_no_send(monkeypatch, capsys) -> None:
    monkeypatch.setenv("GITHUB_EVENT_NAME", "workflow_dispatch")
    monkeypatch.setenv("INPUT_SCHEDULED_RUN", "true")
    monkeypatch.setenv("TARGET_DATE", "2026-07-12")
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "secret")
    monkeypatch.setattr(schedule_guard, "supabase_has_sent", lambda *_: False)
    schedule_guard.main()
    assert capsys.readouterr().out.strip() == "true"


def test_normal_manual_dispatch_bypasses_remote_guard(monkeypatch, capsys) -> None:
    monkeypatch.setenv("GITHUB_EVENT_NAME", "workflow_dispatch")
    monkeypatch.setenv("INPUT_SCHEDULED_RUN", "false")
    monkeypatch.setattr(schedule_guard, "supabase_has_sent", lambda *_: (_ for _ in ()).throw(AssertionError()))
    schedule_guard.main()
    assert capsys.readouterr().out.strip() == "true"


def test_native_schedule_uses_github_fallback_when_remote_lookup_fails(monkeypatch, capsys) -> None:
    monkeypatch.setenv("GITHUB_EVENT_NAME", "schedule")
    monkeypatch.setenv("GITHUB_EVENT_SCHEDULE", FALLBACK_SCHEDULE)
    monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")
    monkeypatch.setenv("GITHUB_TOKEN", "token")
    monkeypatch.setenv("GITHUB_RUN_ID", "2")
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "secret")
    monkeypatch.setattr(schedule_guard, "supabase_has_sent", lambda *_: (_ for _ in ()).throw(httpx.ConnectError("down")))
    today = datetime.now(timezone.utc).replace(hour=0, minute=47, second=0, microsecond=0)
    monkeypatch.setattr(schedule_guard, "github_runs", lambda *_: [{
        "id": 1, "event": "schedule", "conclusion": "success",
        "created_at": today.isoformat().replace("+00:00", "Z"),
    }])
    schedule_guard.main()
    assert capsys.readouterr().out.strip() == "false"


def test_github_lookup_failure_degrades_safely(monkeypatch, capsys) -> None:
    monkeypatch.setenv("GITHUB_EVENT_NAME", "schedule")
    monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")
    monkeypatch.setenv("GITHUB_TOKEN", "token")
    monkeypatch.setenv("GITHUB_RUN_ID", "2")
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.setattr(schedule_guard, "github_runs", lambda *_: (_ for _ in ()).throw(httpx.ConnectError("down")))
    schedule_guard.main()
    assert capsys.readouterr().out.strip() == "true"
