from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from .models import Article, RunStats, SourceRunStats


SCHEMA = """
CREATE TABLE IF NOT EXISTS articles (
  url_hash TEXT PRIMARY KEY,
  url TEXT NOT NULL,
  title TEXT NOT NULL,
  source TEXT NOT NULL,
  published_at TEXT NOT NULL,
  payload TEXT NOT NULL,
  first_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS runs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id TEXT NOT NULL UNIQUE,
  target_date TEXT NOT NULL,
  started_at TEXT NOT NULL,
  finished_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  stats TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS source_runs (
  run_id TEXT NOT NULL,
  target_date TEXT NOT NULL,
  source_name TEXT NOT NULL,
  source_type TEXT NOT NULL,
  collected_count INTEGER NOT NULL,
  status TEXT NOT NULL,
  error_message TEXT NOT NULL,
  duration_seconds REAL NOT NULL,
  PRIMARY KEY (run_id, source_name)
);
CREATE TABLE IF NOT EXISTS run_quality (
  run_id TEXT PRIMARY KEY,
  target_date TEXT NOT NULL,
  assessment TEXT NOT NULL
);
"""


class Database:
    def __init__(self, path: str):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.path)
        self.connection.executescript(SCHEMA)
        columns = {row[1] for row in self.connection.execute("PRAGMA table_info(runs)")}
        if "run_id" not in columns:
            self.connection.execute("ALTER TABLE runs ADD COLUMN run_id TEXT")
        self.connection.execute("CREATE UNIQUE INDEX IF NOT EXISTS runs_run_id_idx ON runs(run_id)")
        self.connection.commit()

    def save_articles(self, articles: list[Article]) -> None:
        import hashlib

        rows = []
        for article in articles:
            digest = hashlib.sha256(article.url.encode("utf-8")).hexdigest()
            rows.append((digest, article.url, article.title, article.source,
                         article.published_at.isoformat(), json.dumps(article.to_dict(), ensure_ascii=False)))
        self.connection.executemany(
            "INSERT OR IGNORE INTO articles(url_hash,url,title,source,published_at,payload) VALUES(?,?,?,?,?,?)",
            rows,
        )
        self.connection.commit()

    def save_run(self, stats: RunStats, source_runs: list[SourceRunStats] | None = None) -> None:
        self.connection.execute(
            "INSERT OR REPLACE INTO runs(run_id,target_date,started_at,stats) VALUES(?,?,?,?)",
            (stats.run_id, stats.target_date, stats.started_at,
             json.dumps(stats.to_dict(), ensure_ascii=False)),
        )
        if source_runs:
            self.connection.executemany(
                """INSERT OR REPLACE INTO source_runs(
                run_id,target_date,source_name,source_type,collected_count,status,error_message,duration_seconds
                ) VALUES(?,?,?,?,?,?,?,?)""",
                [(item.run_id, item.target_date, item.source_name, item.source_type,
                  item.collected_count, item.status, item.error_message, item.duration_seconds)
                 for item in source_runs],
            )
        self.connection.commit()

    def save_quality(self, run_id: str, target_date: str, assessment: dict) -> None:
        self.connection.execute(
            "INSERT OR REPLACE INTO run_quality(run_id,target_date,assessment) VALUES(?,?,?)",
            (run_id, target_date, json.dumps(assessment, ensure_ascii=False)),
        )
        self.connection.commit()

    def close(self) -> None:
        self.connection.close()
