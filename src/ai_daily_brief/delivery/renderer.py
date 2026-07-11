from __future__ import annotations

from datetime import date
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from ..models import Article, RunStats


def render_digest(articles: list[Article], target_date: date, stats: RunStats,
                  template_dir: str | Path = "templates") -> str:
    environment = Environment(
        loader=FileSystemLoader(str(template_dir)),
        autoescape=select_autoescape(["html", "xml"]),
    )
    template = environment.get_template("daily_email.html")
    top = articles[:3]
    rest = articles[3:]
    grouped: dict[str, list[Article]] = {}
    for article in rest:
        grouped.setdefault(article.category, []).append(article)
    return template.render(target_date=target_date, top=top, grouped=grouped, stats=stats)

