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

    def save(self, stats: RunStats, source_runs: list[SourceRunStats], recipient: str = "",
             quality: dict | None = None) -> None:
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
            if quality is not None:
                response = client.post(
                    f"{self.url}/rest/v1/run_quality?on_conflict=run_id",
                    json={"run_id": stats.run_id, "target_date": stats.target_date, **quality},
                )
                response.raise_for_status()
            if stats.email_status.startswith("sent:"):
                message_id = stats.email_status.split(":", 1)[1]
                response = client.post(
                    f"{self.url}/rest/v1/deliveries?on_conflict=message_id",
                    json={
                        "message_id": message_id,
                        "run_id": stats.run_id,
                        "target_date": stats.target_date,
                        "recipient": recipient,
                        "status": "sent",
                        "sent_at": stats.finished_at,
                        "last_event_at": stats.finished_at,
                    },
                )
                response.raise_for_status()


def persist_remote_metrics(url: str, key: str, stats: RunStats,
                           source_runs: list[SourceRunStats], recipient: str = "",
                           quality: dict | None = None) -> bool:
    store = SupabaseMetricsStore(url, key)
    if not store.enabled:
        return False
    try:
        store.save(stats, source_runs, recipient, quality)
        return True
    except httpx.HTTPError as exc:
        # Metrics must not block a successfully generated or delivered digest.
        logger.exception("Remote metrics persistence failed: %s", exc)
        return False
