from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


def _load_dotenv(path: Path = Path(".env")) -> None:
    """Small dotenv reader; environment variables always win."""
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


@dataclass(slots=True)
class Settings:
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-chat"
    resend_api_key: str = ""
    email_from: str = "AI Daily <daily@example.com>"
    email_to: str = ""
    github_token: str = ""
    database_path: str = "data/ai_daily.db"
    timezone: str = "Asia/Shanghai"
    log_level: str = "INFO"

    @classmethod
    def from_env(cls) -> "Settings":
        _load_dotenv()
        return cls(
            deepseek_api_key=os.getenv("DEEPSEEK_API_KEY", ""),
            deepseek_base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
            deepseek_model=os.getenv("DEEPSEEK_MODEL", "deepseek-chat"),
            resend_api_key=os.getenv("RESEND_API_KEY", ""),
            email_from=os.getenv("EMAIL_FROM", "AI Daily <daily@example.com>"),
            email_to=os.getenv("EMAIL_TO", ""),
            github_token=os.getenv("GITHUB_TOKEN", ""),
            database_path=os.getenv("DATABASE_PATH", "data/ai_daily.db"),
            timezone=os.getenv("TIMEZONE", "Asia/Shanghai"),
            log_level=os.getenv("LOG_LEVEL", "INFO"),
        )


def load_sources(path: str | Path = "config/sources.yaml") -> dict[str, Any]:
    with Path(path).open(encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}

