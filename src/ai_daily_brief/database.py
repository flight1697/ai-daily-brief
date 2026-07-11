from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from .models import Article, RunStats


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
  target_date TEXT NOT NULL,
  started_at TEXT NOT NULL,
  finished_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  stats TEXT NOT NULL
);
"""


class Database:
    def __init__(self, path: str):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.path)
        self.connection.executescript(SCHEMA)

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

    def save_run(self, stats: RunStats) -> None:
        self.connection.execute(
            "INSERT INTO runs(target_date,started_at,stats) VALUES(?,?,?)",
            (stats.target_date, stats.started_at, json.dumps(stats.__dict__ if hasattr(stats, '__dict__') else {
                name: getattr(stats, name) for name in stats.__dataclass_fields__
            }, ensure_ascii=False)),
        )
        self.connection.commit()

    def close(self) -> None:
        self.connection.close()

