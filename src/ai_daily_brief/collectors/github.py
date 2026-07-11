from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import httpx

from ..models import Article

logger = logging.getLogger(__name__)


def _headers(token: str) -> dict[str, str]:
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "AI-Daily-Brief/0.1"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def collect_github(config: dict[str, Any], token: str, start: datetime, end: datetime) -> list[Article]:
    articles: list[Article] = []
    start_date = start.date().isoformat()
    query = config.get("search_query", "topic:artificial-intelligence")
    params = {"q": f"{query} pushed:{start_date}", "sort": "stars", "order": "desc", "per_page": 20}
    with httpx.Client(timeout=20, headers=_headers(token), follow_redirects=True) as client:
        response = client.get("https://api.github.com/search/repositories", params=params)
        response.raise_for_status()
        for repo in response.json().get("items", []):
            pushed = datetime.fromisoformat(repo["pushed_at"].replace("Z", "+00:00"))
            if not start <= pushed < end:
                continue
            description = repo.get("description") or ""
            articles.append(Article(
                title=f"{repo['full_name']}：{description[:120]}" if description else repo["full_name"],
                url=repo["html_url"], source="GitHub", published_at=pushed,
                content=f"Stars: {repo['stargazers_count']}; Language: {repo.get('language')}; {description}",
                language="en", source_weight=65, official=True,
            ))

        for repository in config.get("watch_releases", []):
            response = client.get(f"https://api.github.com/repos/{repository}/releases", params={"per_page": 5})
            if response.status_code == 404:
                logger.warning("GitHub repository not found: %s", repository)
                continue
            response.raise_for_status()
            for release in response.json():
                timestamp = release.get("published_at") or release.get("created_at")
                if not timestamp:
                    continue
                published = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                if start <= published < end:
                    articles.append(Article(
                        title=f"{repository} 发布 {release.get('name') or release.get('tag_name')}",
                        url=release["html_url"], source="GitHub Release", published_at=published,
                        content=(release.get("body") or "")[:4000], language="en",
                        source_weight=80, official=True,
                    ))
    logger.info("GitHub collected %d items", len(articles))
    return articles

