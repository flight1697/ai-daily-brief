from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any
from uuid import uuid4


@dataclass(slots=True)
class SourceLink:
    name: str
    url: str
    official: bool = False


@dataclass(slots=True)
class Article:
    title: str
    url: str
    source: str
    published_at: datetime
    content: str = ""
    language: str = "unknown"
    source_weight: int = 50
    official: bool = False
    category: str = "其他"
    tags: list[str] = field(default_factory=list)
    score: float = 0.0
    summary: str = ""
    why_it_matters: str = ""
    verification: str = "单一信源"
    related_sources: list[SourceLink] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["published_at"] = self.published_at.isoformat()
        return data


@dataclass(slots=True)
class RunStats:
    target_date: str
    started_at: str
    run_id: str = field(default_factory=lambda: str(uuid4()))
    finished_at: str = ""
    collected: int = 0
    in_window: int = 0
    deduplicated: int = 0
    selected: int = 0
    source_errors: int = 0
    llm_used: bool = False
    email_status: str = "not_requested"
    duration_seconds: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class SourceRunStats:
    run_id: str
    target_date: str
    source_name: str
    source_type: str
    collected_count: int = 0
    status: str = "success"
    error_message: str = ""
    duration_seconds: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
