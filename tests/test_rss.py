import httpx
import pytest
from datetime import datetime, timezone

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


def test_collect_official_news_from_sitemap(monkeypatch: pytest.MonkeyPatch) -> None:
    modified = datetime.now(timezone.utc).isoformat()
    sitemap = f'''<?xml version="1.0"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
      <url><loc>https://www.anthropic.com/news/claude-model</loc><lastmod>{modified}</lastmod></url>
      <url><loc>https://www.anthropic.com/company</loc><lastmod>{modified}</lastmod></url>
    </urlset>'''.encode()
    responses = {
        "https://example.com/sitemap.xml": httpx.Response(
            200, content=sitemap, request=httpx.Request("GET", "https://example.com/sitemap.xml"),
        ),
        "https://www.anthropic.com/news/claude-model": httpx.Response(
            200, text='<meta property="og:title" content="Claude Model News"><meta name="description" content="Official details">',
            request=httpx.Request("GET", "https://www.anthropic.com/news/claude-model"),
        ),
    }
    monkeypatch.setattr(httpx, "get", lambda url, **kwargs: responses[url])
    articles = collect_rss({
        "name": "Anthropic News", "url": "https://example.com/sitemap.xml", "format": "sitemap",
        "include_path": "/news/", "recent_days": 7, "official": True, "weight": 95,
    })
    assert len(articles) == 1
    assert articles[0].title == "Claude Model News"
    assert articles[0].content == "Official details"
