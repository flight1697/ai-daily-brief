from __future__ import annotations

import os
from datetime import date, datetime, time, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

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


def supabase_has_sent(url: str, service_role_key: str, target_date: date) -> bool:
    """Return whether the target day's email was already accepted by Resend."""
    response = httpx.get(
        f"{url.rstrip('/')}/rest/v1/runs",
        headers={
            "apikey": service_role_key,
            "Authorization": f"Bearer {service_role_key}",
        },
        params={
            "target_date": f"eq.{target_date.isoformat()}",
            "email_status": "like.sent:*",
            "select": "run_id",
            "limit": "1",
        },
        timeout=15,
    )
    response.raise_for_status()
    return bool(response.json())


def resolve_target_date(value: str, now: datetime | None = None) -> date:
    if value:
        return date.fromisoformat(value)
    shanghai_now = (now or datetime.now(timezone.utc)).astimezone(ZoneInfo("Asia/Shanghai"))
    return shanghai_now.date() - timedelta(days=1)


def main() -> None:
    event_name = os.getenv("GITHUB_EVENT_NAME", "workflow_dispatch")
    schedule = os.getenv("GITHUB_EVENT_SCHEDULE", "")
    externally_scheduled = os.getenv("INPUT_SCHEDULED_RUN", "false").lower() == "true"
    scheduled_like = event_name == "schedule" or externally_scheduled
    if not scheduled_like:
        print("true")
        return

    supabase_url = os.getenv("SUPABASE_URL", "")
    supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
    if supabase_url and supabase_key:
        try:
            target_date = resolve_target_date(os.getenv("TARGET_DATE", ""))
            if supabase_has_sent(supabase_url, supabase_key, target_date):
                print("false")
                return
        except (httpx.HTTPError, ValueError) as exc:
            print(f"Supabase delivery lookup failed; using GitHub fallback: {type(exc).__name__}", file=__import__("sys").stderr)

    # An external dispatch has no useful native schedule history. On lookup
    # failure it is safer to attempt delivery; the persistence layer remains
    # the final record of the outcome.
    if externally_scheduled:
        print("true")
        return
    repository = os.environ["GITHUB_REPOSITORY"]
    token = os.environ["GITHUB_TOKEN"]
    current_run_id = int(os.environ["GITHUB_RUN_ID"])
    try:
        runs = github_runs(repository, token)
    except httpx.HTTPError as exc:
        print(f"GitHub run lookup failed; allowing delivery: {type(exc).__name__}", file=__import__("sys").stderr)
        runs = []
    print("true" if should_send(event_name, schedule, current_run_id, runs) else "false")


if __name__ == "__main__":
    main()
