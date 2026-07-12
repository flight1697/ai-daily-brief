import json
import sqlite3
from datetime import date
from pathlib import Path

import pytest

from ai_daily_brief.database import Database
from ai_daily_brief.metrics_remote import fetch_period_rows, fetch_quality_rows
from ai_daily_brief.metrics_report import build_report
from ai_daily_brief.metrics_store import SupabaseMetricsStore
from ai_daily_brief.models import RunStats, SourceRunStats


def test_database_migrates_old_runs_table(tmp_path: Path) -> None:
    path = tmp_path / "old.db"
    connection = sqlite3.connect(path)
    connection.execute("CREATE TABLE runs(id INTEGER PRIMARY KEY, target_date TEXT, started_at TEXT, finished_at TEXT DEFAULT CURRENT_TIMESTAMP, stats TEXT)")
    connection.commit()
    connection.close()
    database = Database(str(path))
    columns = {row[1] for row in database.connection.execute("PRAGMA table_info(runs)")}
    database.close()
    assert "run_id" in columns


def test_metrics_schema_includes_deliveries_migration() -> None:
    sql = Path("supabase/migrations/001_metrics.sql").read_text(encoding="utf-8")
    assert "create table if not exists public.deliveries" in sql
    assert "delivered_at timestamptz" in sql
    quality_sql = Path("supabase/migrations/002_run_quality.sql").read_text(encoding="utf-8")
    assert "create table if not exists public.run_quality" in quality_sql
    assert "alter table public.run_quality enable row level security" in quality_sql


def test_metrics_are_persisted_and_reported(tmp_path: Path) -> None:
    path = tmp_path / "metrics.db"
    stats = RunStats(
        target_date="2026-07-11", started_at="2026-07-12T00:00:00+00:00",
        finished_at="2026-07-12T00:01:00+00:00", collected=100,
        selected=10, email_status="sent:message", duration_seconds=60,
    )
    source = SourceRunStats(
        run_id=stats.run_id, target_date=stats.target_date,
        source_name="OpenAI", source_type="rss", collected_count=20,
        duration_seconds=1.5,
    )
    database = Database(str(path))
    database.save_run(stats, [source])
    database.save_quality(stats.run_id, stats.target_date, {"passed": True})
    saved_quality = json.loads(
        database.connection.execute("SELECT assessment FROM run_quality").fetchone()[0]
    )
    database.close()
    report = build_report(str(path))
    assert report["attempts"] == 1
    assert report["successful_deliveries"] == 1
    assert report["average_collected"] == 100
    assert report["source_status"]["success"]["count"] == 1
    assert saved_quality["passed"] is True


def test_supabase_store_is_disabled_without_credentials() -> None:
    assert SupabaseMetricsStore("", "").enabled is False


def test_remote_period_query_uses_bounded_filters(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, list[tuple[str, str]]]] = []
    payloads = {
        "/rest/v1/runs": [{"target_date": "2026-07-11", "selected": 10}],
        "/rest/v1/source_runs": [{"target_date": "2026-07-11", "status": "success"}],
        "/rest/v1/deliveries": [{"target_date": "2026-07-11", "status": "delivered"}],
    }

    class FakeResponse:
        def __init__(self, payload: list[dict]):
            self.payload = payload

        def raise_for_status(self) -> None:
            return None

        def json(self) -> list[dict]:
            return self.payload

    class FakeClient:
        def __init__(self, **_: object):
            pass

        def __enter__(self) -> "FakeClient":
            return self

        def __exit__(self, *_: object) -> None:
            return None

        def get(self, path: str, params: list[tuple[str, str]]) -> FakeResponse:
            calls.append((path, params))
            return FakeResponse(payloads[path])

    monkeypatch.setattr("ai_daily_brief.metrics_remote.httpx.Client", FakeClient)
    runs, sources, deliveries = fetch_period_rows(
        "https://example.supabase.co", "secret", date(2026, 7, 5), date(2026, 7, 11)
    )
    assert runs[0]["selected"] == 10
    assert sources[0]["status"] == "success"
    assert deliveries[0]["status"] == "delivered"
    for _, params in calls:
        assert ("target_date", "gte.2026-07-05") in params
        assert ("target_date", "lte.2026-07-11") in params


def test_remote_period_query_requires_credentials() -> None:
    with pytest.raises(ValueError):
        fetch_period_rows("", "", date(2026, 7, 5), date(2026, 7, 11))


def test_supabase_store_persists_quality_row(monkeypatch: pytest.MonkeyPatch) -> None:
    posts: list[tuple[str, object]] = []

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

    class FakeClient:
        def __init__(self, **_: object):
            pass

        def __enter__(self) -> "FakeClient":
            return self

        def __exit__(self, *_: object) -> None:
            return None

        def post(self, url: str, json: object) -> FakeResponse:
            posts.append((url, json))
            return FakeResponse()

    monkeypatch.setattr("ai_daily_brief.metrics_store.httpx.Client", FakeClient)
    stats = RunStats(
        target_date="2026-07-11", started_at="2026-07-12T00:00:00+00:00",
        finished_at="2026-07-12T00:01:00+00:00", email_status="dry_run",
    )
    source = SourceRunStats(
        run_id=stats.run_id, target_date=stats.target_date,
        source_name="OpenAI", source_type="rss",
    )
    SupabaseMetricsStore("https://example.supabase.co", "secret").save(
        stats, [source], quality={"passed": True, "official_ratio": 0.5}
    )
    quality_post = next(item for item in posts if "/run_quality" in item[0])
    assert quality_post[1]["run_id"] == stats.run_id
    assert quality_post[1]["passed"] is True


def test_fetch_quality_rows(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> list[dict]:
            return [{"target_date": "2026-07-11", "passed": True}]

    class FakeClient:
        def __init__(self, **_: object):
            pass

        def __enter__(self) -> "FakeClient":
            return self

        def __exit__(self, *_: object) -> None:
            return None

        def get(self, path: str, params: object) -> FakeResponse:
            captured.update(path=path, params=params)
            return FakeResponse()

    monkeypatch.setattr("ai_daily_brief.metrics_remote.httpx.Client", FakeClient)
    rows = fetch_quality_rows(
        "https://example.supabase.co", "secret", date(2026, 7, 5), date(2026, 7, 11)
    )
    assert rows[0]["passed"] is True
    assert captured["path"] == "/rest/v1/run_quality"
