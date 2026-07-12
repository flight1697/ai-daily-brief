from __future__ import annotations

import logging

import httpx

from .models import RunStats, SourceRunStats

logger = logging.getLogger(__name__)


class SupabaseMetricsStore:
    def __init__(self, url: str, service_role_key: str):
        self.url = url.rstrip("/")
        self.headers = {
            "apikey": service_role_key,
            "Authorization": f"Bearer {service_role_key}",
            "Content-Type": "application/json",
            "Prefer": "resolution=merge-duplicates,return=minimal",
        }

    @property
    def enabled(self) -> bool:
        return bool(self.url and self.headers["apikey"])

    def save(self, stats: RunStats, source_runs: list[SourceRunStats]) -> None:
        if not self.enabled:
            return
        with httpx.Client(timeout=30, headers=self.headers) as client:
            response = client.post(
                f"{self.url}/rest/v1/runs?on_conflict=run_id",
                json=stats.to_dict(),
            )
            response.raise_for_status()
            if source_runs:
                response = client.post(
                    f"{self.url}/rest/v1/source_runs?on_conflict=run_id,source_name",
                    json=[item.to_dict() for item in source_runs],
                )
                response.raise_for_status()


def persist_remote_metrics(url: str, key: str, stats: RunStats,
                           source_runs: list[SourceRunStats]) -> bool:
    store = SupabaseMetricsStore(url, key)
    if not store.enabled:
        return False
    try:
        store.save(stats, source_runs)
        return True
    except httpx.HTTPError as exc:
        # Metrics must not block a successfully generated or delivered digest.
        logger.exception("Remote metrics persistence failed: %s", exc)
        return False

