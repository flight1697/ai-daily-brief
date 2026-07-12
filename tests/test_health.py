from datetime import date

from ai_daily_brief.health import HealthStatus, evaluate_health, render_alert


def test_health_is_green_after_confirmed_delivery() -> None:
    status = evaluate_health(
        date(2026, 7, 11),
        [{"email_status": "sent:message", "selected": 12, "source_errors": 0}],
        [{"status": "delivered"}],
    )
    assert status.healthy is True
    assert status.delivery_status == "delivered"
    assert status.issues == []


def test_health_reports_missing_run_and_delivery() -> None:
    status = evaluate_health(date(2026, 7, 11), [], [])
    assert status.healthy is False
    assert "未找到日报运行记录" in status.issues
    assert "未找到邮件投递回调记录" in status.issues


def test_health_reports_bounce_and_source_warning() -> None:
    status = evaluate_health(
        date(2026, 7, 11),
        [{"email_status": "sent:message", "selected": 10, "source_errors": 2}],
        [{"status": "bounced"}],
    )
    assert status.healthy is False
    assert status.delivery_status == "bounced"
    assert status.warnings == ["有 2 个信息源采集失败"]


def test_alert_html_escapes_external_text() -> None:
    status = HealthStatus(target_date="2026-07-11", healthy=False)
    status.issues.append("bad <script>")
    rendered = render_alert(status)
    assert "bad &lt;script&gt;" in rendered
    assert "bad <script>" not in rendered
