import httpx
import pytest

from ai_daily_brief.delivery.email import send_email


def response(status: int, body: dict | None = None) -> httpx.Response:
    return httpx.Response(status, request=httpx.Request("POST", "https://api.resend.com/emails"), json=body or {})


def test_retry_uses_same_idempotency_key(monkeypatch: pytest.MonkeyPatch) -> None:
    responses = iter([response(500), response(200, {"id": "message-1"})])
    headers: list[str] = []

    def fake_post(*args, **kwargs):
        headers.append(kwargs["headers"]["Idempotency-Key"])
        return next(responses)

    monkeypatch.setattr(httpx, "post", fake_post)
    monkeypatch.setattr("ai_daily_brief.delivery.email.time.sleep", lambda _: None)
    message_id = send_email("key", "from@example.com", "to@example.com", "subject", "<p>body</p>")
    assert message_id == "message-1"
    assert len(headers) == 2
    assert headers[0] == headers[1]


def test_non_retryable_4xx_fails_immediately(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = 0

    def fake_post(*args, **kwargs):
        nonlocal calls
        calls += 1
        return response(401)

    monkeypatch.setattr(httpx, "post", fake_post)
    with pytest.raises(httpx.HTTPStatusError):
        send_email("bad-key", "from@example.com", "to@example.com", "subject", "body")
    assert calls == 1

