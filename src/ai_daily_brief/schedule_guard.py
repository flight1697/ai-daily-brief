from __future__ import annotations

import os
from datetime import datetime, time, timezone
from typing import Any

import httpx

PRIMARY_SCHEDULE = "45 0 * * *"
FALLBACK_SCHEDULE = "15 1 * * *"


def should_send(
    event_name: str,
    schedule: str,
    current_run_id: int,
    runs: list[dict[str, Any]],
    now: datetime | None = None,
) -> bool:
    """Prevent any delayed scheduled run from delivering twice on the same UTC day."""
    if event_name != "schedule":
        return True

    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    day_start = datetime.combine(now.date(), time.min, tzinfo=timezone.utc)
    for run in runs:
        if int(run.get("id", 0)) == current_run_id:
            continue
        if run.get("event") != "schedule" or run.get("conclusion") != "success":
            continue
        created_at = datetime.fromisoformat(run["created_at"].replace("Z", "+00:00"))
        if created_at >= day_start:
            return False
    return True


def github_runs(repository: str, token: str, workflow: str = "daily.yml") -> list[dict[str, Any]]:
    response = httpx.get(
        f"https://api.github.com/repos/{repository}/actions/workflows/{workflow}/runs",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
        params={"per_page": 20},
        timeout=30,
    )
    response.raise_for_status()
    return response.json().get("workflow_runs", [])


def main() -> None:
    event_name = os.getenv("GITHUB_EVENT_NAME", "workflow_dispatch")
    schedule = os.getenv("GITHUB_EVENT_SCHEDULE", "")
    if event_name != "schedule":
        print("true")
        return
    repository = os.environ["GITHUB_REPOSITORY"]
    token = os.environ["GITHUB_TOKEN"]
    current_run_id = int(os.environ["GITHUB_RUN_ID"])
    runs = github_runs(repository, token)
    print("true" if should_send(event_name, schedule, current_run_id, runs) else "false")


if __name__ == "__main__":
    main()
