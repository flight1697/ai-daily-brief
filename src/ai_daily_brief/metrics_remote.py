from __future__ import annotations

from datetime import date
from typing import Any

import httpx


def fetch_period_rows(url: str, service_role_key: str, start_date: date,
                      end_date: date) -> tuple[
                          list[dict[str, Any]],
                          list[dict[str, Any]],
                          list[dict[str, Any]],
                      ]:
    """Fetch only fields that are safe to aggregate into operational reports."""
    if not url or not service_role_key:
        raise ValueError("Supabase metrics credentials are required")
    headers = {
        "apikey": service_role_key,
        "Authorization": f"Bearer {service_role_key}",
    }
    filters = [
        ("target_date", f"gte.{start_date.isoformat()}"),
        ("target_date", f"lte.{end_date.isoformat()}"),
    ]
    with httpx.Client(base_url=url.rstrip("/"), headers=headers, timeout=30) as client:
        runs_response = client.get(
            "/rest/v1/runs",
            params=filters + [
                ("select", "target_date,finished_at,collected,in_window,deduplicated,selected,source_errors,llm_used,email_status,duration_seconds"),
                ("order", "finished_at.desc"),
            ],
        )
        runs_response.raise_for_status()
        sources_response = client.get(
            "/rest/v1/source_runs",
            params=filters + [("select", "target_date,source_name,status")],
        )
        sources_response.raise_for_status()
        deliveries_response = client.get(
            "/rest/v1/deliveries",
            params=filters + [("select", "target_date,status")],
        )
        deliveries_response.raise_for_status()
    return runs_response.json(), sources_response.json(), deliveries_response.json()
