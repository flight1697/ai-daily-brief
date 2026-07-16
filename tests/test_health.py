from datetime import date

import pytest

from ai_daily_brief.health import HealthStatus, check_health, evaluate_health, render_alert


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


def test_three_day_low_quality_trend_is_warning_only() -> None:
    quality_rows = [
        {
            "target_date": f"2026-07-{day:02d}", "passed": True,
            "official_ratio": 0, "multi_source_ratio": 0.1, "warnings": [],
        }
        for day in (9, 10, 11)
    ]
    status = evaluate_health(
        date(2026, 7, 11),
        [{"email_status": "sent:message", "selected": 10, "source_errors": 0}],
        [{"status": "delivered"}], quality_rows,
    )
    assert status.healthy is True
    assert status.issues == []
    assert "连续3天交叉核验比例低于20%" in status.warnings
    assert "连续3天没有官方来源入选" in status.warnings


def test_health_check_fetches_delivery_and_quality(monkeypatch: pytest.MonkeyPatch) -> None:
    requested_paths: list[str] = []
    payloads = {
        "/rest/v1/runs": [
            {"email_status": "sent:message", "selected": 10, "source_errors": 0}
        ],
        "/rest/v1/deliveries": [{"status": "delivered"}],
        "/rest/v1/run_quality": [{
            "target_date": "2026-07-11", "passed": True,
            "official_ratio": 0.5, "multi_source_ratio": 0.3, "warnings": [],
        }],
    }

    class FakeResponse:
        def __init__(self, payload: list[dict]):
            self.payload = payload

        def raise_for_status(self) -> None:
            return None

        def json(self) -> list[dict]:
            return self.payload

    class FakeClient:
        def __init__(self, **_: object):
            pass

        def __enter__(self) -> "FakeClient":
            return self

        def __exit__(self, *_: object) -> None:
            return None

        def get(self, path: str, params: object) -> FakeResponse:
            requested_paths.append(path)
            return FakeResponse(payloads[path])

    monkeypatch.setattr("ai_daily_brief.health.httpx.Client", FakeClient)
    status = check_health("https://example.supabase.co", "secret", date(2026, 7, 11))
    assert status.healthy is True
    assert requested_paths == [
        "/rest/v1/runs", "/rest/v1/deliveries", "/rest/v1/run_quality",
    ]
