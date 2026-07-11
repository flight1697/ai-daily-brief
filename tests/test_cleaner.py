from ai_daily_brief.processors.cleaner import canonical_url, clean_text, normalize_title


def test_clean_text_and_title() -> None:
    assert clean_text("<p>AI&nbsp; News</p>") == "AI News"
    assert normalize_title("模型发布：Aurora 2！") == "模型发布aurora2"


def test_canonical_url_removes_tracking() -> None:
    result = canonical_url("HTTPS://Example.com/news/?utm_source=x&id=2#section")
    assert result == "https://example.com/news?id=2"

