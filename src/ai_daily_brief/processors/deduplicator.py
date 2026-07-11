from __future__ import annotations

import math
import re
from collections import Counter
from difflib import SequenceMatcher

from ..models import Article, SourceLink
from .cleaner import canonical_url, clean_text, normalize_title


def _tokens(text: str) -> list[str]:
    text = clean_text(text).lower()
    english = re.findall(r"[a-z0-9][a-z0-9._-]+", text)
    chinese = [text[i:i + 2] for i in range(len(text) - 1)
               if "\u4e00" <= text[i] <= "\u9fff" and "\u4e00" <= text[i + 1] <= "\u9fff"]
    return english + chinese


def _cosine(left: str, right: str) -> float:
    a, b = Counter(_tokens(left)), Counter(_tokens(right))
    if not a or not b:
        return 0.0
    dot = sum(value * b.get(key, 0) for key, value in a.items())
    return dot / (math.sqrt(sum(v * v for v in a.values())) * math.sqrt(sum(v * v for v in b.values())))


def _same_event(left: Article, right: Article, title_threshold: float, content_threshold: float) -> bool:
    if canonical_url(left.url) == canonical_url(right.url):
        return True
    title_score = SequenceMatcher(None, normalize_title(left.title), normalize_title(right.title)).ratio()
    if title_score >= title_threshold:
        return True
    title_token_score = _cosine(left.title, right.title)
    combined_left = f"{left.title} {left.content[:800]}"
    combined_right = f"{right.title} {right.content[:800]}"
    if title_score >= 0.40 and title_token_score >= 0.58:
        # Handles the same named entities/phrases presented in a different word order.
        return True
    return title_score >= 0.40 and _cosine(combined_left, combined_right) >= content_threshold


def deduplicate(articles: list[Article], title_threshold: float = 0.88,
                content_threshold: float = 0.72) -> list[Article]:
    groups: list[list[Article]] = []
    for article in sorted(articles, key=lambda item: (item.official, item.source_weight), reverse=True):
        article.title = clean_text(article.title)
        article.content = clean_text(article.content)
        article.url = canonical_url(article.url)
        for group in groups:
            if _same_event(group[0], article, title_threshold, content_threshold):
                group.append(article)
                break
        else:
            groups.append([article])

    output: list[Article] = []
    for group in groups:
        representative = max(group, key=lambda item: (item.official, item.source_weight, len(item.content)))
        representative.related_sources = [
            SourceLink(item.source, item.url, item.official)
            for item in group if item.url != representative.url
        ]
        if representative.official:
            representative.verification = "官方来源"
        elif len({item.source for item in group}) >= 2:
            representative.verification = "多源交叉核验"
        else:
            representative.verification = "单一信源"
        output.append(representative)
    return output
