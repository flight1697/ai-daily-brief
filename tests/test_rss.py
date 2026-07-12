import httpx
import pytest

from ai_daily_brief.collectors.rss import collect_rss


RSS = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel><title>Test</title>
<item><title>AI model released</title><link>https://example.com/news</link>
<pubDate>Sat, 11 Jul 2026 01:00:00 GMT</pubDate><description>Details</description></item>
</channel></rss>"""


def test_collect_rss_from_http_response(monkeypatch: pytest.MonkeyPatch) -> None:
    response = httpx.Response(
        200, content=RSS, request=httpx.Request("GET", "https://example.com/feed"),
    )
    monkeypatch.setattr(httpx, "get", lambda *args, **kwargs: response)
    articles = collect_rss({"name": "Test", "url": "https://example.com/feed", "official": True})
    assert len(articles) == 1
    assert articles[0].title == "AI model released"
    assert articles[0].official is True

