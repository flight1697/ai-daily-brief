from __future__ import annotations

import argparse
import json
import logging
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from .config import Settings
from .pipeline import run_pipeline


def parser() -> argparse.ArgumentParser:
    command = argparse.ArgumentParser(description="Generate and optionally email an AI industry daily brief")
    command.add_argument("--date", help="Target date in YYYY-MM-DD; defaults to yesterday in configured timezone")
    command.add_argument("--sample", action="store_true", help="Use bundled sample data instead of network sources")
    command.add_argument("--send", action="store_true", help="Send through Resend; default is dry-run")
    command.add_argument("--output", default="data/latest.html", help="HTML output path")
    command.add_argument("--max-items", type=int, default=20)
    return command


def main() -> None:
    args = parser().parse_args()
    settings = Settings.from_env()
    logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO),
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    target = date.fromisoformat(args.date) if args.date else (
        datetime.now(ZoneInfo(settings.timezone)).date() - timedelta(days=1)
    )
    sample_path = "data/sample_articles.json" if args.sample else None
    articles, stats, _ = run_pipeline(
        settings, target, sample_path=sample_path, send=args.send,
        output_path=args.output, max_items=args.max_items,
    )
    print(json.dumps({
        "stats": {name: getattr(stats, name) for name in stats.__dataclass_fields__},
        "headlines": [article.title for article in articles],
        "output": args.output,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

