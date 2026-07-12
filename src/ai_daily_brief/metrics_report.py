from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path


def build_report(database_path: str) -> dict:
    path = Path(database_path)
    if not path.exists():
        return {"attempts": 0, "successful_deliveries": 0, "days": 0}
    connection = sqlite3.connect(path)
    rows = connection.execute("SELECT target_date, stats FROM runs ORDER BY started_at").fetchall()
    source_rows = connection.execute(
        "SELECT status, COUNT(*), AVG(duration_seconds) FROM source_runs GROUP BY status"
    ).fetchall()
    connection.close()
    stats = [json.loads(row[1]) for row in rows]
    return {
        "attempts": len(stats),
        "days": len({row[0] for row in rows}),
        "successful_deliveries": sum(str(item.get("email_status", "")).startswith("sent:") for item in stats),
        "average_collected": round(sum(item.get("collected", 0) for item in stats) / len(stats), 2) if stats else 0,
        "average_selected": round(sum(item.get("selected", 0) for item in stats) / len(stats), 2) if stats else 0,
        "average_duration_seconds": round(sum(item.get("duration_seconds", 0) for item in stats) / len(stats), 2) if stats else 0,
        "source_status": {
            status: {"count": count, "average_duration_seconds": round(average or 0, 3)}
            for status, count, average in source_rows
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Summarize AI Daily Brief run metrics")
    parser.add_argument("--database", default="data/ai_daily.db")
    args = parser.parse_args()
    print(json.dumps(build_report(args.database), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

