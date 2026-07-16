from __future__ import annotations

import argparse
import html
import json
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import httpx

from .config import Settings
from .delivery import send_email


@dataclass(slots=True)
class HealthStatus:
    target_date: str
    healthy: bool = True
    runs_count: int = 0
    delivery_status: str = "missing"
    selected: int = 0
    source_errors: int = 0
    issues: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def evaluate_health(target_date: date, runs: list[dict[str, Any]],
                    deliveries: list[dict[str, Any]],
                    quality_rows: list[dict[str, Any]] | None = None) -> HealthStatus:
    status = HealthStatus(target_date=target_date.isoformat(), runs_count=len(runs))
    if not runs:
        status.issues.append("未找到日报运行记录")
    else:
        latest = runs[0]
        status.selected = int(latest.get("selected") or 0)
        status.source_errors = int(latest.get("source_errors") or 0)
        if not any(str(run.get("email_status", "")).startswith("sent:") for run in runs):
            status.issues.append("日报生成任务没有成功发送邮件")
        if status.selected == 0:
            status.warnings.append("最终入选新闻数量为 0")
        if status.source_errors:
            status.warnings.append(f"有 {status.source_errors} 个信息源采集失败")

    delivery_states = [str(item.get("status", "")) for item in deliveries]
    if "delivered" in delivery_states:
        status.delivery_status = "delivered"
    elif any(item in {"bounced", "complained"} for item in delivery_states):
        status.delivery_status = next(
            item for item in delivery_states if item in {"bounced", "complained"}
        )
        status.issues.append(f"邮件投递异常：{status.delivery_status}")
    elif "sent" in delivery_states:
        status.delivery_status = "sent"
        status.issues.append("邮件已发送，但尚未确认送达")
    else:
        status.issues.append("未找到邮件投递回调记录")

    quality_rows = quality_rows or []
    target_quality = next(
        (row for row in quality_rows if str(row.get("target_date")) == target_date.isoformat()),
        None,
    )
    if target_quality:
        if not target_quality.get("passed"):
            status.issues.append("内容质量门禁未通过")
        status.warnings.extend(str(item) for item in (target_quality.get("warnings") or []))
    elif quality_rows:
        status.warnings.append("昨日没有质量评估记录")

    daily_quality: dict[str, dict[str, Any]] = {}
    for row in quality_rows:
        target = str(row.get("target_date") or "")
        if target:
            daily_quality.setdefault(target, row)
    recent_quality = [daily_quality[key] for key in sorted(daily_quality, reverse=True)[:3]]
    if len(recent_quality) == 3:
        if all(float(row.get("multi_source_ratio") or 0) < 0.2 for row in recent_quality):
            status.warnings.append("连续3天交叉核验比例低于20%")
        if all(float(row.get("official_ratio") or 0) == 0 for row in recent_quality):
            status.warnings.append("连续3天没有官方来源入选")

    status.healthy = not status.issues
    return status


def check_health(url: str, service_role_key: str, target_date: date) -> HealthStatus:
    if not url or not service_role_key:
        raise ValueError("Supabase health-check credentials are required")
    headers = {
        "apikey": service_role_key,
        "Authorization": f"Bearer {service_role_key}",
    }
    day = target_date.isoformat()
    with httpx.Client(base_url=url.rstrip("/"), headers=headers, timeout=30) as client:
        runs_response = client.get(
            "/rest/v1/runs",
            params={
                "target_date": f"eq.{day}",
                "select": "run_id,email_status,source_errors,selected,finished_at",
                "order": "finished_at.desc",
            },
        )
        runs_response.raise_for_status()
        deliveries_response = client.get(
            "/rest/v1/deliveries",
            params={
                "target_date": f"eq.{day}",
                "select": "status,last_event_at",
                "order": "last_event_at.desc",
            },
        )
        deliveries_response.raise_for_status()
        quality_response = client.get(
            "/rest/v1/run_quality",
            params=[
                ("target_date", f"gte.{(target_date - timedelta(days=2)).isoformat()}"),
                ("target_date", f"lte.{day}"),
                ("select", "target_date,passed,official_ratio,multi_source_ratio,warnings"),
                ("order", "target_date.desc"),
            ],
        )
        quality_response.raise_for_status()
    return evaluate_health(
        target_date, runs_response.json(), deliveries_response.json(), quality_response.json()
    )


def render_alert(status: HealthStatus) -> str:
    issues = "".join(f"<li>{html.escape(item)}</li>" for item in status.issues)
    warnings = "".join(f"<li>{html.escape(item)}</li>" for item in status.warnings)
    warning_section = f"<h3>同时需要关注</h3><ul>{warnings}</ul>" if warnings else ""
    return f"""<!doctype html>
<html lang="zh-CN"><body style="font-family:Arial,sans-serif;line-height:1.6;color:#222">
<h2>AI 日报运行告警</h2>
<p><strong>日报日期：</strong>{html.escape(status.target_date)}</p>
<ul>{issues}</ul>
{warning_section}
<p>运行次数：{status.runs_count}；入选新闻：{status.selected}；
信息源错误：{status.source_errors}；投递状态：{html.escape(status.delivery_status)}</p>
<p>请检查 GitHub Actions、Supabase 指标和 Resend Webhook。</p>
</body></html>"""


def parser() -> argparse.ArgumentParser:
    command = argparse.ArgumentParser(description="Check the latest AI Daily Brief delivery health")
    command.add_argument("--date", help="Target date in YYYY-MM-DD; defaults to yesterday")
    command.add_argument("--alert", action="store_true", help="Email an alert when unhealthy")
    return command


def main() -> None:
    args = parser().parse_args()
    settings = Settings.from_env()
    target = date.fromisoformat(args.date) if args.date else (
        datetime.now(ZoneInfo(settings.timezone)).date() - timedelta(days=1)
    )
    try:
        status = check_health(settings.supabase_url, settings.supabase_service_role_key, target)
    except (httpx.HTTPError, ValueError) as exc:
        status = HealthStatus(target_date=target.isoformat(), healthy=False)
        status.issues.append(f"监控指标查询失败：{type(exc).__name__}")

    if not status.healthy and args.alert:
        send_email(
            settings.resend_api_key,
            settings.email_from,
            settings.email_to,
            f"AI日报运行告警｜{target.isoformat()}",
            render_alert(status),
            idempotency_key=f"health-alert/{target.isoformat()}",
        )
    print(json.dumps(status.to_dict(), ensure_ascii=False, indent=2))
    if not status.healthy:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
