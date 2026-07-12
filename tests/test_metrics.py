import json
import sqlite3
from pathlib import Path

from ai_daily_brief.database import Database
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
    database.close()
    report = build_report(str(path))
    assert report["attempts"] == 1
    assert report["successful_deliveries"] == 1
    assert report["average_collected"] == 100
    assert report["source_status"]["success"]["count"] == 1


def test_supabase_store_is_disabled_without_credentials() -> None:
    assert SupabaseMetricsStore("", "").enabled is False
