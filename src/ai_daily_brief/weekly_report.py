from __future__ import annotations

import argparse
import html
import json
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from .config import Settings
from .delivery import send_email
from .metrics_remote import fetch_period_rows


@dataclass(slots=True)
class WeeklyMetrics:
    start_date: str
    end_date: str
    expected_days: int
    active_days: int = 0
    attempts: int = 0
    successful_send_days: int = 0
    delivered_days: int = 0
    delivery_success_rate: float = 0.0
    average_collected: float = 0.0
    average_in_window: float = 0.0
    average_deduplicated: float = 0.0
    average_selected: float = 0.0
    average_duration_seconds: float = 0.0
    llm_usage_rate: float = 0.0
    source_checks: int = 0
    source_errors: int = 0
    source_success_rate: float = 0.0
    problem_sources: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _average(rows: list[dict[str, Any]], field_name: str) -> float:
    if not rows:
        return 0.0
    return round(sum(float(row.get(field_name) or 0) for row in rows) / len(rows), 2)


def representative_daily_runs(runs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Select one representative run per day, preferring a successful delivery attempt."""
    runs_by_day: dict[str, list[dict[str, Any]]] = {}
    for run in sorted(runs, key=lambda item: str(item.get("finished_at") or ""), reverse=True):
        target = str(run.get("target_date", ""))
        if target:
            runs_by_day.setdefault(target, []).append(run)
    return [
        next(
            (run for run in day_runs if str(run.get("email_status", "")).startswith("sent:")),
            day_runs[0],
        )
        for day_runs in runs_by_day.values()
    ]


def summarize_week(end_date: date, days: int, runs: list[dict[str, Any]],
                   source_runs: list[dict[str, Any]],
                   deliveries: list[dict[str, Any]]) -> WeeklyMetrics:
    if days < 1:
        raise ValueError("days must be at least 1")
    start_date = end_date - timedelta(days=days - 1)
    metrics = WeeklyMetrics(
        start_date=start_date.isoformat(),
        end_date=end_date.isoformat(),
        expected_days=days,
        attempts=len(runs),
    )

    # Prefer the most recent successful send so later manual dry-runs do not
    # hide a real delivery. If a day never sent, keep its latest attempt.
    daily_rows = representative_daily_runs(runs)
    metrics.active_days = len(daily_rows)
    metrics.successful_send_days = sum(
        str(row.get("email_status", "")).startswith("sent:") for row in daily_rows
    )
    delivered_dates = {
        str(row.get("target_date"))
        for row in deliveries
        if row.get("target_date") and row.get("status") == "delivered"
    }
    metrics.delivered_days = len(delivered_dates)
    metrics.delivery_success_rate = round(metrics.delivered_days / days * 100, 2)
    metrics.average_collected = _average(daily_rows, "collected")
    metrics.average_in_window = _average(daily_rows, "in_window")
    metrics.average_deduplicated = _average(daily_rows, "deduplicated")
    metrics.average_selected = _average(daily_rows, "selected")
    metrics.average_duration_seconds = _average(daily_rows, "duration_seconds")
    metrics.llm_usage_rate = round(
        sum(bool(row.get("llm_used")) for row in daily_rows) / len(daily_rows) * 100, 2
    ) if daily_rows else 0.0

    metrics.source_checks = len(source_runs)
    failed_sources = [row for row in source_runs if row.get("status") != "success"]
    metrics.source_errors = len(failed_sources)
    metrics.source_success_rate = round(
        (metrics.source_checks - metrics.source_errors) / metrics.source_checks * 100, 2
    ) if metrics.source_checks else 0.0
    error_counts = Counter(str(row.get("source_name", "unknown")) for row in failed_sources)
    metrics.problem_sources = [
        {"source": source, "errors": count}
        for source, count in sorted(error_counts.items(), key=lambda item: (-item[1], item[0]))
    ]
    return metrics


def fetch_weekly_metrics(url: str, service_role_key: str, end_date: date,
                         days: int = 7) -> WeeklyMetrics:
    if not url or not service_role_key:
        raise ValueError("Supabase weekly-report credentials are required")
    start_date = end_date - timedelta(days=days - 1)
    runs, source_runs, deliveries = fetch_period_rows(
        url, service_role_key, start_date, end_date
    )
    return summarize_week(end_date, days, runs, source_runs, deliveries)


def render_weekly_report(metrics: WeeklyMetrics) -> str:
    problem_rows = "".join(
        f"<li>{html.escape(str(item['source']))}：{item['errors']} 次</li>"
        for item in metrics.problem_sources
    ) or "<li>本周没有信息源错误</li>"
    coverage_note = ""
    if metrics.active_days < metrics.expected_days:
        coverage_note = (
            f"<p style=\"color:#9a6700\">当前仅积累 {metrics.active_days}/{metrics.expected_days} 天数据，"
            "成功率会随持续运行逐步稳定。</p>"
        )
    return f"""<!doctype html>
<html lang="zh-CN"><body style="font-family:Arial,sans-serif;line-height:1.6;color:#1f2328;max-width:760px;margin:auto">
<h1>AI 日报运营周报</h1>
<p>{html.escape(metrics.start_date)} 至 {html.escape(metrics.end_date)}</p>
{coverage_note}
<table style="border-collapse:collapse;width:100%">
<tr><td style="padding:10px;border:1px solid #ddd">实际运行天数</td><td style="padding:10px;border:1px solid #ddd"><strong>{metrics.active_days}/{metrics.expected_days}</strong></td></tr>
<tr><td style="padding:10px;border:1px solid #ddd">确认送达天数</td><td style="padding:10px;border:1px solid #ddd"><strong>{metrics.delivered_days}（{metrics.delivery_success_rate}%）</strong></td></tr>
<tr><td style="padding:10px;border:1px solid #ddd">日均采集 / 时间窗内 / 去重后</td><td style="padding:10px;border:1px solid #ddd">{metrics.average_collected} / {metrics.average_in_window} / {metrics.average_deduplicated}</td></tr>
<tr><td style="padding:10px;border:1px solid #ddd">日均最终输出</td><td style="padding:10px;border:1px solid #ddd">{metrics.average_selected}</td></tr>
<tr><td style="padding:10px;border:1px solid #ddd">LLM 摘要使用率</td><td style="padding:10px;border:1px solid #ddd">{metrics.llm_usage_rate}%</td></tr>
<tr><td style="padding:10px;border:1px solid #ddd">信息源成功率</td><td style="padding:10px;border:1px solid #ddd">{metrics.source_success_rate}%（{metrics.source_errors}/{metrics.source_checks} 次失败）</td></tr>
<tr><td style="padding:10px;border:1px solid #ddd">平均耗时</td><td style="padding:10px;border:1px solid #ddd">{metrics.average_duration_seconds} 秒</td></tr>
</table>
<h2>需要维护的信息源</h2><ul>{problem_rows}</ul>
<p style="color:#57606a">数据来自 Supabase 长期指标和 Resend 投递回调。</p>
</body></html>"""


def parser() -> argparse.ArgumentParser:
    command = argparse.ArgumentParser(description="Generate an operational weekly AI Daily Brief report")
    command.add_argument("--end-date", help="Report end date; defaults to yesterday")
    command.add_argument("--days", type=int, default=7)
    command.add_argument("--send", action="store_true", help="Send the report through Resend")
    command.add_argument("--output", default="data/weekly_report.html")
    return command


def main() -> None:
    args = parser().parse_args()
    settings = Settings.from_env()
    end_date = date.fromisoformat(args.end_date) if args.end_date else (
        datetime.now(ZoneInfo(settings.timezone)).date() - timedelta(days=1)
    )
    metrics = fetch_weekly_metrics(
        settings.supabase_url, settings.supabase_service_role_key, end_date, args.days
    )
    report_html = render_weekly_report(metrics)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(report_html, encoding="utf-8")
    if args.send:
        send_email(
            settings.resend_api_key,
            settings.email_from,
            settings.email_to,
            f"AI日报运营周报｜{metrics.start_date}—{metrics.end_date}",
            report_html,
            idempotency_key=f"weekly-report/{metrics.start_date}/{metrics.end_date}",
        )
    print(json.dumps(metrics.to_dict(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
