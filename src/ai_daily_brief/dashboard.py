from __future__ import annotations

import argparse
import html
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from .config import Settings
from .metrics_remote import fetch_period_rows
from .weekly_report import WeeklyMetrics, representative_daily_runs, summarize_week


@dataclass(slots=True)
class DailyStatus:
    target_date: str
    collected: int
    in_window: int
    deduplicated: int
    selected: int
    source_errors: int
    llm_used: bool
    delivery_status: str
    duration_seconds: float


def build_dashboard_data(end_date: date, days: int, runs: list[dict[str, Any]],
                         source_runs: list[dict[str, Any]],
                         deliveries: list[dict[str, Any]]) -> tuple[WeeklyMetrics, list[DailyStatus]]:
    metrics = summarize_week(end_date, days, runs, source_runs, deliveries)
    delivery_by_day: dict[str, set[str]] = {}
    for delivery in deliveries:
        target = str(delivery.get("target_date") or "")
        if target:
            delivery_by_day.setdefault(target, set()).add(str(delivery.get("status") or ""))

    def delivery_status(target: str, run: dict[str, Any]) -> str:
        states = delivery_by_day.get(target, set())
        for state in ("delivered", "complained", "bounced", "sent"):
            if state in states:
                return state
        return "sent" if str(run.get("email_status", "")).startswith("sent:") else "missing"

    daily = [
        DailyStatus(
            target_date=str(run.get("target_date")),
            collected=int(run.get("collected") or 0),
            in_window=int(run.get("in_window") or 0),
            deduplicated=int(run.get("deduplicated") or 0),
            selected=int(run.get("selected") or 0),
            source_errors=int(run.get("source_errors") or 0),
            llm_used=bool(run.get("llm_used")),
            delivery_status=delivery_status(str(run.get("target_date")), run),
            duration_seconds=round(float(run.get("duration_seconds") or 0), 2),
        )
        for run in representative_daily_runs(runs)
    ]
    daily.sort(key=lambda item: item.target_date, reverse=True)
    return metrics, daily


def _status_label(status: str) -> str:
    return {
        "delivered": "已送达",
        "sent": "已发送",
        "bounced": "退信",
        "complained": "投诉",
        "missing": "缺失",
    }.get(status, status)


def render_dashboard(metrics: WeeklyMetrics, daily: list[DailyStatus],
                     generated_at: datetime | None = None) -> str:
    generated_at = generated_at or datetime.now(timezone.utc)
    max_collected = max((item.collected for item in daily), default=1)
    daily_rows = "".join(
        f"""<tr>
<td>{html.escape(item.target_date)}</td>
<td><span class="status status-{html.escape(item.delivery_status)}">{html.escape(_status_label(item.delivery_status))}</span></td>
<td><div class="bar"><i style="width:{round(item.collected / max_collected * 100, 1)}%"></i></div>{item.collected}</td>
<td>{item.in_window}</td><td>{item.deduplicated}</td><td>{item.selected}</td>
<td>{item.source_errors}</td><td>{'是' if item.llm_used else '否'}</td><td>{item.duration_seconds}s</td>
</tr>"""
        for item in daily
    ) or '<tr><td colspan="9" class="empty">尚无生产运行数据</td></tr>'
    problem_sources = "".join(
        f"<li><span>{html.escape(str(item['source']))}</span><strong>{item['errors']} 次</strong></li>"
        for item in metrics.problem_sources
    ) or "<li><span>最近周期没有故障信源</span><strong>正常</strong></li>"
    return f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="description" content="AI Daily Brief automated operations dashboard">
<title>AI Daily Brief · 运行状态</title>
<style>
:root{{--bg:#07111f;--panel:#0e1b2d;--line:#20334d;--text:#e8f0fb;--muted:#91a4bd;--blue:#55a8ff;--green:#35d07f;--amber:#ffbd59;--red:#ff6b6b}}
*{{box-sizing:border-box}}body{{margin:0;background:radial-gradient(circle at 15% 0,#153155 0,transparent 35%),var(--bg);color:var(--text);font:15px/1.55 Inter,Segoe UI,Arial,sans-serif}}
main{{max-width:1180px;margin:auto;padding:48px 24px 72px}}header{{display:flex;justify-content:space-between;gap:24px;align-items:end;margin-bottom:28px}}h1{{font-size:34px;margin:0 0 6px}}h2{{font-size:18px;margin:0 0 16px}}p{{margin:0;color:var(--muted)}}.live{{display:inline-flex;align-items:center;gap:8px;color:var(--green)}}.live:before{{content:'';width:9px;height:9px;border-radius:50%;background:var(--green);box-shadow:0 0 14px var(--green)}}
.cards{{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin-bottom:20px}}.card,.panel{{background:rgba(14,27,45,.92);border:1px solid var(--line);border-radius:14px;box-shadow:0 14px 40px rgba(0,0,0,.18)}}.card{{padding:20px}}.card span{{display:block;color:var(--muted);font-size:13px}}.card strong{{display:block;font-size:28px;margin-top:7px}}.card small{{color:var(--muted)}}
.grid{{display:grid;grid-template-columns:2fr 1fr;gap:20px}}.panel{{padding:22px;overflow:hidden}}table{{width:100%;border-collapse:collapse;min-width:760px}}th,td{{padding:12px 10px;text-align:left;border-bottom:1px solid var(--line);white-space:nowrap}}th{{font-size:12px;color:var(--muted);text-transform:uppercase}}td{{font-variant-numeric:tabular-nums}}.table-wrap{{overflow:auto}}.status{{display:inline-block;padding:3px 8px;border-radius:999px;font-size:12px;background:#26364a}}.status-delivered{{color:var(--green);background:rgba(53,208,127,.12)}}.status-sent{{color:var(--blue)}}.status-bounced,.status-complained,.status-missing{{color:var(--red);background:rgba(255,107,107,.12)}}.bar{{display:inline-block;width:64px;height:5px;background:#243750;border-radius:4px;margin-right:8px;vertical-align:middle}}.bar i{{display:block;height:100%;background:var(--blue);border-radius:4px}}
.sources{{list-style:none;padding:0;margin:0}}.sources li{{display:flex;justify-content:space-between;padding:12px 0;border-bottom:1px solid var(--line)}}.sources strong{{color:var(--green)}}.note{{margin-top:16px;font-size:13px}}footer{{margin-top:22px;color:var(--muted);font-size:13px}}a{{color:var(--blue)}}.empty{{text-align:center;color:var(--muted)}}
@media(max-width:850px){{.cards{{grid-template-columns:repeat(2,1fr)}}.grid{{grid-template-columns:1fr}}header{{align-items:start;flex-direction:column}}}}@media(max-width:520px){{main{{padding:28px 14px}}.cards{{grid-template-columns:1fr 1fr}}.card strong{{font-size:22px}}h1{{font-size:28px}}}}
</style></head><body><main>
<header><div><div class="live">自动化运行中</div><h1>AI Daily Brief</h1><p>最近 {metrics.expected_days} 天生产运行状态 · {html.escape(metrics.start_date)} — {html.escape(metrics.end_date)}</p></div><p>更新于 {generated_at.astimezone(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}</p></header>
<section class="cards">
<div class="card"><span>运行覆盖</span><strong>{metrics.active_days}/{metrics.expected_days}</strong><small>累计尝试 {metrics.attempts} 次</small></div>
<div class="card"><span>确认送达率</span><strong>{metrics.delivery_success_rate}%</strong><small>{metrics.delivered_days} 天确认送达</small></div>
<div class="card"><span>日均处理</span><strong>{metrics.average_collected}</strong><small>最终输出 {metrics.average_selected} 条</small></div>
<div class="card"><span>信源成功率</span><strong>{metrics.source_success_rate}%</strong><small>{metrics.source_checks} 次检查</small></div>
</section>
<section class="grid"><div class="panel"><h2>每日运行明细</h2><div class="table-wrap"><table><thead><tr><th>日期</th><th>投递</th><th>采集</th><th>时间窗</th><th>去重后</th><th>输出</th><th>源错误</th><th>LLM</th><th>耗时</th></tr></thead><tbody>{daily_rows}</tbody></table></div></div>
<aside class="panel"><h2>信息源健康</h2><ul class="sources">{problem_sources}</ul><p class="note">LLM 使用率 {metrics.llm_usage_rate}% · 平均耗时 {metrics.average_duration_seconds} 秒</p></aside></section>
<footer>仅展示匿名聚合指标，不包含邮箱、密钥、新闻正文或内部错误详情。 · <a href="https://github.com/flight1697/ai-daily-brief">查看项目源码</a></footer>
</main></body></html>"""


def parser() -> argparse.ArgumentParser:
    command = argparse.ArgumentParser(description="Generate a public AI Daily Brief status dashboard")
    command.add_argument("--end-date", help="Dashboard end date; defaults to yesterday")
    command.add_argument("--days", type=int, default=30)
    command.add_argument("--output", default="public/index.html")
    return command


def main() -> None:
    args = parser().parse_args()
    if args.days < 1:
        raise SystemExit("--days must be at least 1")
    settings = Settings.from_env()
    end_date = date.fromisoformat(args.end_date) if args.end_date else (
        datetime.now(ZoneInfo(settings.timezone)).date() - timedelta(days=1)
    )
    start_date = end_date - timedelta(days=args.days - 1)
    rows = fetch_period_rows(
        settings.supabase_url, settings.supabase_service_role_key, start_date, end_date
    )
    metrics, daily = build_dashboard_data(end_date, args.days, *rows)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render_dashboard(metrics, daily), encoding="utf-8")


if __name__ == "__main__":
    main()
