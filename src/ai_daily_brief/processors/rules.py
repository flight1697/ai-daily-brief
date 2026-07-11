from __future__ import annotations

import math
import re

from ..models import Article

CATEGORIES: dict[str, tuple[str, ...]] = {
    "模型与产品发布": ("launch", "release", "model", "模型", "发布", "api", "agent", "智能体", "多模态"),
    "企业与商业动态": ("company", "partnership", "revenue", "企业", "合作", "商业", "客户"),
    "投融资与并购": ("funding", "raised", "acquire", "investment", "融资", "收购", "投资", "估值"),
    "开源项目": ("github", "open source", "repository", "开源", "release", "stars:"),
    "研究与论文": ("arxiv", "paper", "research", "benchmark", "论文", "研究", "评测"),
    "政策与监管": ("regulation", "law", "policy", "government", "监管", "政策", "法规", "政府"),
    "AI应用案例": ("application", "deploy", "customer", "应用", "落地", "部署", "案例"),
}

TAG_WORDS = ("大模型", "多模态", "Agent", "智能体", "具身智能", "算力", "芯片", "开源", "融资", "教育", "医疗", "金融", "汽车")


def classify(article: Article) -> Article:
    text = f"{article.title} {article.content}".lower()
    scores = {category: sum(1 for word in words if word.lower() in text) for category, words in CATEGORIES.items()}
    article.category = max(scores, key=scores.get) if max(scores.values(), default=0) else "其他"
    if article.source.startswith("GitHub"):
        article.category = "开源项目"
    elif article.source.lower().startswith("arxiv"):
        article.category = "研究与论文"
    article.tags = [tag for tag in TAG_WORDS if tag.lower() in text][:4]
    return article


def rank(article: Article) -> Article:
    text = f"{article.title} {article.content}".lower()
    impact_words = ("launch", "release", "acquire", "billion", "regulation", "发布", "收购", "亿", "监管", "开源")
    novelty_words = ("new", "first", "首次", "最新", "突破")
    authority = article.source_weight
    impact = min(100, 40 + 12 * sum(word in text for word in impact_words))
    novelty = min(100, 45 + 15 * sum(word in text for word in novelty_words))
    corroboration = min(100, 40 + len(article.related_sources) * 20 + (20 if article.official else 0))
    relevance = 95 if article.category != "其他" else 35
    article.score = round(authority * .25 + impact * .25 + novelty * .20 + corroboration * .15 + relevance * .15, 1)
    article.score += {
        "政策与监管": 8, "模型与产品发布": 7, "投融资与并购": 6,
        "企业与商业动态": 3, "开源项目": 2,
    }.get(article.category, 0)
    article.score = round(min(article.score, 100), 1)
    # Unverified stories never become a top story solely through keyword density.
    if article.verification == "单一信源" and not article.official:
        article.score = min(article.score, 60.0)
    return article
