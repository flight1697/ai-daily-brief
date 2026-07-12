from __future__ import annotations

import argparse
import html
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from .config import Settings
from .metrics_remote import fetch_period_rows, fetch_quality_rows
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
                         deliveries: list[dict[str, Any]],
                         quality_rows: list[dict[str, Any]] | None = None
                         ) -> tuple[WeeklyMetrics, list[DailyStatus]]:
    metrics = summarize_week(
        end_date, days, runs, source_runs, deliveries, quality_rows
    )
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
<td><time>{html.escape(item.target_date)}</time></td>
<td><span class="status status-{html.escape(item.delivery_status)}">{html.escape(_status_label(item.delivery_status))}</span></td>
<td><div class="bar"><i style="--bar-width:{round(item.collected / max_collected * 100, 1)}%"></i></div><span class="tabular">{item.collected}</span></td>
<td>{item.in_window}</td><td>{item.deduplicated}</td><td>{item.selected}</td>
<td>{item.source_errors}</td><td>{'是' if item.llm_used else '否'}</td><td>{item.duration_seconds}s</td>
</tr>""".replace("<tr>", f'<tr data-status="{html.escape(item.delivery_status)}">', 1)
        for item in daily
    ) or '<tr><td colspan="9" class="empty">尚无生产运行数据</td></tr>'
    problem_sources = "".join(
        f"<li><span>{html.escape(str(item['source']))}</span><strong>{item['errors']} 次</strong></li>"
        for item in metrics.problem_sources
    ) or "<li><span>最近周期没有故障信源</span><strong>正常</strong></li>"
    return f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="description" content="AI Daily Brief automated operations dashboard"><meta name="theme-color" content="#edf4ef">
<title>AI Daily Brief · 运行状态</title>
<style>
:root{{--paper:#f1f5f1;--paper-deep:#e6eee8;--glass:rgba(255,255,255,.64);--glass-strong:rgba(255,255,255,.82);--ink:#21332b;--muted:#718078;--line:rgba(55,86,70,.13);--moss:#557f6a;--moss-deep:#345b48;--mint:#a9c9b5;--sage:#dbe9df;--amber:#a97737;--red:#a95b55;--shadow:0 24px 70px rgba(47,75,61,.10)}}
*{{box-sizing:border-box}}html{{scroll-behavior:smooth}}body{{margin:0;min-height:100vh;color:var(--ink);font:15px/1.65 -apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif;background:var(--paper);overflow-x:hidden}}
body:before,body:after{{content:"";position:fixed;z-index:-2;border-radius:50%;filter:blur(12px);pointer-events:none}}body:before{{width:52vw;height:52vw;left:-18vw;top:-24vw;background:radial-gradient(circle,rgba(159,201,176,.48),rgba(159,201,176,0) 68%)}}body:after{{width:48vw;height:48vw;right:-16vw;bottom:-26vw;background:radial-gradient(circle,rgba(199,219,207,.55),rgba(199,219,207,0) 70%)}}
.grain{{position:fixed;inset:0;z-index:-1;pointer-events:none;opacity:.22;background-image:url("data:image/svg+xml,%3Csvg viewBox='0 0 180 180' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='.95' numOctaves='3' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)' opacity='.035'/%3E%3C/svg%3E")}}
main{{max-width:1240px;margin:auto;padding:34px 28px 76px}}.topbar{{display:flex;align-items:center;justify-content:space-between;margin-bottom:64px}}.brand{{display:flex;align-items:center;gap:11px;font-weight:650;letter-spacing:.01em}}.mark{{display:grid;place-items:center;width:34px;height:34px;border:1px solid rgba(63,99,80,.16);border-radius:11px;background:rgba(255,255,255,.6);box-shadow:inset 0 1px 0 rgba(255,255,255,.9)}}.mark svg{{width:18px;color:var(--moss-deep)}}.toplink{{color:var(--muted);text-decoration:none;font-size:13px;transition:color .25s}}.toplink:hover{{color:var(--moss-deep)}}
.hero{{display:grid;grid-template-columns:minmax(0,1.45fr) minmax(240px,.55fr);align-items:end;gap:48px;margin-bottom:34px}}.eyebrow{{display:flex;align-items:center;gap:9px;color:var(--moss-deep);font-size:13px;font-weight:600;margin-bottom:14px}}.pulse{{width:8px;height:8px;border-radius:50%;background:#6ca47f;box-shadow:0 0 0 0 rgba(108,164,127,.35);animation:pulse 2.8s infinite}}h1{{margin:0;max-width:680px;font:500 clamp(38px,6vw,72px)/1.04 ui-serif,"Songti SC",STSong,Georgia,serif;letter-spacing:-.045em}}.hero-copy{{color:var(--muted);max-width:420px;padding-bottom:6px}}.hero-copy strong{{display:block;color:var(--ink);font-weight:560;margin-bottom:5px}}p{{margin:0}}
.cards{{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin-bottom:20px}}.glass{{background:var(--glass);border:1px solid rgba(255,255,255,.76);box-shadow:var(--shadow);backdrop-filter:blur(18px) saturate(115%);-webkit-backdrop-filter:blur(18px) saturate(115%)}}.card{{position:relative;overflow:hidden;min-height:154px;padding:22px;border-radius:20px;transition:transform .35s cubic-bezier(.2,.75,.3,1),box-shadow .35s}}.card:after{{content:"";position:absolute;width:120px;height:120px;border-radius:50%;right:-52px;bottom:-64px;background:linear-gradient(145deg,rgba(126,173,146,.22),rgba(255,255,255,0));transition:transform .5s}}.card:hover{{transform:translateY(-4px);box-shadow:0 30px 75px rgba(47,75,61,.15)}}.card:hover:after{{transform:scale(1.25)}}.card-label{{display:block;color:var(--muted);font-size:12px;letter-spacing:.08em}}.card strong{{position:relative;display:block;margin:17px 0 3px;font:500 30px/1 ui-serif,Georgia,serif;font-variant-numeric:tabular-nums}}.card small{{color:var(--muted);font-size:12px}}
.quality-band{{display:grid;grid-template-columns:1.2fr repeat(4,1fr);gap:0;margin-bottom:20px;padding:17px 22px;border-radius:20px}}.quality-band>div{{padding:4px 18px;border-left:1px solid var(--line)}}.quality-band>div:first-child{{padding-left:0;border-left:0}}.quality-band span{{display:block;color:var(--muted);font-size:11px;margin-bottom:3px}}.quality-band strong{{font:500 20px ui-serif,Georgia,serif;font-variant-numeric:tabular-nums}}.quality-band p{{color:var(--muted);font-size:12px;max-width:190px}}
.layout{{display:grid;grid-template-columns:minmax(0,2.15fr) minmax(270px,.85fr);gap:20px}}.panel{{border-radius:24px;padding:24px;overflow:hidden}}.panel-head{{display:flex;align-items:center;justify-content:space-between;gap:20px;margin-bottom:17px}}h2{{margin:0;font:560 17px/1.3 -apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC",sans-serif}}.filters{{display:flex;gap:4px;padding:4px;background:rgba(102,130,115,.08);border-radius:11px}}.filter{{appearance:none;border:0;background:transparent;color:var(--muted);border-radius:8px;padding:6px 10px;font:12px inherit;cursor:pointer;transition:.25s}}.filter:hover{{color:var(--ink)}}.filter[aria-pressed="true"]{{color:var(--moss-deep);background:var(--glass-strong);box-shadow:0 3px 12px rgba(49,76,62,.08)}}
.table-wrap{{overflow:auto;margin:0 -8px -8px;padding:0 8px 8px;scrollbar-width:thin;scrollbar-color:rgba(84,117,99,.24) transparent}}table{{width:100%;border-collapse:collapse;min-width:720px}}th,td{{padding:13px 9px;text-align:left;border-bottom:1px solid var(--line);white-space:nowrap}}th{{color:var(--muted);font-size:11px;font-weight:560;letter-spacing:.06em}}td{{font-size:13px;font-variant-numeric:tabular-nums;transition:background .2s}}tbody tr{{transition:opacity .25s,transform .25s}}tbody tr:hover td{{background:rgba(255,255,255,.38)}}tbody tr.is-hidden{{display:none}}time{{font-weight:560;color:#3c5147}}.status{{display:inline-block;min-width:52px;text-align:center;padding:3px 8px;border-radius:999px;font-size:11px}}.status-delivered{{color:#376a4d;background:rgba(107,164,127,.13)}}.status-sent{{color:#557467;background:rgba(122,157,140,.12)}}.status-bounced,.status-complained,.status-missing{{color:var(--red);background:rgba(169,91,85,.10)}}.bar{{display:inline-block;width:50px;height:4px;background:rgba(84,117,99,.10);border-radius:4px;margin-right:7px;vertical-align:middle;overflow:hidden}}.bar i{{display:block;width:0;height:100%;background:linear-gradient(90deg,#7cac91,#accbb7);border-radius:4px;animation:grow 1s .25s cubic-bezier(.2,.75,.3,1) forwards}}.tabular{{font-variant-numeric:tabular-nums}}
.source-intro{{color:var(--muted);font-size:13px;margin:7px 0 20px}}.sources{{list-style:none;padding:0;margin:0}}.sources li{{display:flex;justify-content:space-between;gap:18px;padding:13px 0;border-bottom:1px solid var(--line)}}.sources strong{{color:var(--moss-deep);font-size:12px;font-weight:600}}.note-box{{margin-top:20px;padding:16px;border-radius:15px;background:linear-gradient(135deg,rgba(217,234,222,.72),rgba(255,255,255,.34));color:var(--muted);font-size:12px}}.note-box b{{display:block;color:var(--ink);font:500 20px ui-serif,Georgia,serif;margin-bottom:3px}}.empty{{text-align:center;color:var(--muted)}}
footer{{display:flex;justify-content:space-between;gap:24px;margin-top:24px;padding:0 4px;color:var(--muted);font-size:12px}}footer a{{color:var(--moss-deep);text-decoration:none;border-bottom:1px solid rgba(52,91,72,.2)}}
@keyframes pulse{{70%{{box-shadow:0 0 0 9px rgba(108,164,127,0)}}100%{{box-shadow:0 0 0 0 rgba(108,164,127,0)}}}}@keyframes grow{{to{{width:var(--bar-width)}}}}@keyframes rise{{from{{opacity:0;transform:translateY(12px)}}to{{opacity:1;transform:none}}}}.reveal{{animation:rise .7s both}}.cards .card:nth-child(2){{animation-delay:.07s}}.cards .card:nth-child(3){{animation-delay:.14s}}.cards .card:nth-child(4){{animation-delay:.21s}}
@media(max-width:900px){{.topbar{{margin-bottom:42px}}.hero{{grid-template-columns:1fr;gap:18px}}.cards{{grid-template-columns:repeat(2,1fr)}}.quality-band{{grid-template-columns:repeat(2,1fr);gap:12px}}.quality-band>div,.quality-band>div:first-child{{padding:5px 8px;border:0}}.quality-band>div:first-child{{grid-column:1/-1}}.layout{{grid-template-columns:1fr}}}}@media(max-width:560px){{main{{padding:24px 14px 56px}}.topbar{{margin-bottom:36px}}.hero{{margin-bottom:28px}}.cards{{gap:10px}}.card{{min-height:134px;padding:17px;border-radius:17px}}.card strong{{font-size:24px}}.quality-band{{padding:17px}}.panel{{padding:18px;border-radius:20px}}.panel-head{{align-items:flex-start;flex-direction:column}}table{{min-width:0}}th:nth-child(4),td:nth-child(4),th:nth-child(5),td:nth-child(5),th:nth-child(7),td:nth-child(7),th:nth-child(8),td:nth-child(8),th:nth-child(9),td:nth-child(9){{display:none}}th,td{{padding:12px 7px}}.bar{{width:34px}}footer{{flex-direction:column;gap:8px}}}}
@media(prefers-reduced-motion:reduce){{*,*:before,*:after{{animation-duration:.01ms!important;animation-iteration-count:1!important;scroll-behavior:auto!important;transition:none!important}}.bar i{{width:var(--bar-width)}}}}
</style></head><body><div class="grain"></div><main>
<nav class="topbar"><div class="brand"><span class="mark"><svg viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M5 15.5c4.8.3 8.7-2.2 11.8-7.2.1 5.2-1.6 9.5-6.3 10.3-2.4.4-4.3-.8-5.5-3.1Z" stroke="currentColor" stroke-width="1.5"/><path d="M8.2 17.3c1.5-3 3.8-5.3 7-6.9" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg></span>AI Daily Brief</div><a class="toplink" href="https://github.com/flight1697/ai-daily-brief">GitHub ↗</a></nav>
<header class="hero reveal"><div><div class="eyebrow"><span class="pulse"></span>自动化运行中</div><h1>一份安静运行的<br>AI 行业日报。</h1></div><div class="hero-copy"><strong>最近 {metrics.expected_days} 天运行概览</strong><p>{html.escape(metrics.start_date)} — {html.escape(metrics.end_date)}<br>更新于 {generated_at.astimezone(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}</p></div></header>
<section class="cards">
<article class="card glass reveal"><span class="card-label">运行覆盖</span><strong>{metrics.active_days}/{metrics.expected_days}</strong><small>累计尝试 {metrics.attempts} 次</small></article>
<article class="card glass reveal"><span class="card-label">确认送达率</span><strong>{metrics.delivery_success_rate}%</strong><small>{metrics.delivered_days} 天确认送达</small></article>
<article class="card glass reveal"><span class="card-label">日均处理</span><strong>{metrics.average_collected}</strong><small>最终输出 {metrics.average_selected} 条</small></article>
<article class="card glass reveal"><span class="card-label">信源成功率</span><strong>{metrics.source_success_rate}%</strong><small>{metrics.source_checks} 次检查</small></article>
</section>
<section class="quality-band glass reveal"><div><span>内容质量</span><p>基于每次发送前的匿名质量评估</p></div><div><span>门禁通过率</span><strong>{metrics.quality_pass_rate}%</strong></div><div><span>官方来源</span><strong>{metrics.average_official_ratio}%</strong></div><div><span>交叉核验</span><strong>{metrics.average_multi_source_ratio}%</strong></div><div><span>平均质量分</span><strong>{metrics.average_quality_score}</strong></div></section>
<section class="layout reveal"><div class="panel glass"><div class="panel-head"><h2>每日运行明细</h2><div class="filters" role="group" aria-label="筛选投递状态"><button class="filter" data-filter="all" aria-pressed="true">全部</button><button class="filter" data-filter="delivered" aria-pressed="false">已送达</button><button class="filter" data-filter="attention" aria-pressed="false">需关注</button></div></div><div class="table-wrap"><table><thead><tr><th>日期</th><th>投递</th><th>采集</th><th>时间窗</th><th>去重后</th><th>输出</th><th>源错误</th><th>LLM</th><th>耗时</th></tr></thead><tbody>{daily_rows}</tbody></table></div></div>
<aside class="panel glass"><h2>信息源健康</h2><p class="source-intro">只记录需要维护的来源；正常状态保持安静。</p><ul class="sources">{problem_sources}</ul><div class="note-box"><b>{metrics.llm_usage_rate}%</b>LLM 摘要使用率<br>平均运行 {metrics.average_duration_seconds} 秒</div></aside></section>
<footer><span>匿名聚合指标 · 不包含邮箱、密钥与新闻正文</span><span>由 Supabase 与 Resend 投递回调提供数据</span></footer>
</main><script>
const buttons=[...document.querySelectorAll('.filter')];const rows=[...document.querySelectorAll('tbody tr[data-status]')];
buttons.forEach(button=>button.addEventListener('click',()=>{{buttons.forEach(item=>item.setAttribute('aria-pressed','false'));button.setAttribute('aria-pressed','true');const filter=button.dataset.filter;rows.forEach(row=>{{const delivered=row.dataset.status==='delivered';row.classList.toggle('is-hidden',filter==='delivered'&&!delivered||filter==='attention'&&delivered)}})}}));
</script></body></html>"""


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
    quality_rows = fetch_quality_rows(
        settings.supabase_url, settings.supabase_service_role_key, start_date, end_date
    )
    metrics, daily = build_dashboard_data(end_date, args.days, *rows, quality_rows)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render_dashboard(metrics, daily), encoding="utf-8")


if __name__ == "__main__":
    main()
