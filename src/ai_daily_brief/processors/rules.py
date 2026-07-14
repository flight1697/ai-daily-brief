from __future__ import annotations

import math
import re

from ..models import Article

CATEGORIES: dict[str, tuple[str, ...]] = {
    "AI开发工具与Agent": ("codex", "claude code", "coding agent", "developer agent", "agentic coding", "编程智能体", "代码智能体"),
    "模型与产品发布": ("launch", "release", "model", "模型", "发布", "api", "智能体", "多模态"),
    "企业与商业动态": ("company", "partnership", "revenue", "企业", "合作", "商业", "客户"),
    "投融资与并购": ("funding", "raised", "acquire", "investment", "融资", "收购", "投资", "估值"),
    "开源项目": ("github", "open source", "repository", "开源", "release", "stars:"),
    "研究与论文": ("arxiv", "paper", "research", "benchmark", "论文", "研究", "评测"),
    "政策与监管": ("regulation", "law", "policy", "government", "监管", "政策", "法规", "政府"),
    "AI应用案例": ("application", "deploy", "customer", "应用", "落地", "部署", "案例"),
}

TAG_WORDS = ("OpenAI", "Anthropic", "Codex", "Claude Code", "大模型", "多模态", "Agent", "智能体", "具身智能", "算力", "芯片", "开源", "融资")

STRATEGIC_ENTITIES = (
    "openai", "chatgpt", "anthropic", "claude", "codex", "google deepmind", "gemini",
    "xai", "grok", "meta ai", "llama", "mistral", "deepseek", "qwen", "kimi",
)
MODEL_SIGNALS = (
    "new model", "model launch", "launches model", "unveils model", "reasoning model",
    "multimodal model", "frontier model", "新模型", "模型发布", "推理模型", "多模态模型",
)
CODING_SIGNALS = ("claude code", "coding agent", "agentic coding", "编程智能体", "代码智能体")
BUSINESS_SIGNALS = (
    "launch", "unveil", "partnership", "pricing", "lawsuit", "acquire", "funding",
    "billion", "regulation", "enterprise", "market", "发布", "合作", "定价", "诉讼",
    "收购", "融资", "监管", "企业客户",
)
LOW_VALUE_SIGNALS = (
    "bug fix", "bugfix", "dependency update", "maintenance release", "patch release",
    "changelog", "minor release", "文档更新", "依赖更新", "修复若干问题",
)
VERSION_ONLY = re.compile(r"(?:^|\s)(?:v|version\s*)?\d+\.\d+(?:\.\d+)?(?:[-\w.]*)?$", re.I)
RELEASE_TAG_ONLY = re.compile(r"发布\s+(?:v?\d+(?:\.\d+)*|[a-z]\d{3,})(?:[-\w.]*)?$", re.I)


def _is_routine_release(article: Article, text: str) -> bool:
    if article.source != "GitHub Release":
        return False
    return bool(VERSION_ONLY.search(article.title) or RELEASE_TAG_ONLY.search(article.title)) \
        or any(signal in text for signal in LOW_VALUE_SIGNALS)


def _is_coding_news(text: str) -> bool:
    if any(signal in text for signal in CODING_SIGNALS):
        return True
    if "codex" not in text or any(word in text for word in ("alimentarius", "food standard", "fao")):
        return False
    return any(word in text for word in ("openai", "coding", "code", "developer", "software", "agent", "chatgpt"))


def editorial_entity(article: Article) -> str:
    text = f"{article.title} {article.content}".lower()
    groups = {
        "OpenAI": ("openai", "chatgpt"),
        "Anthropic": ("anthropic", "claude"),
        "Google": ("google deepmind", "deepmind", "gemini"),
        "xAI": ("xai", "grok"),
        "Meta": ("meta ai", "llama"),
        "DeepSeek": ("deepseek",),
        "Mistral": ("mistral",),
        "阿里": ("qwen", "通义千问"),
        "月之暗面": ("kimi", "moonshot ai"),
    }
    for name, aliases in groups.items():
        if any(alias in text for alias in aliases):
            return name
    if "codex" in text and _is_coding_news(text):
        return "OpenAI"
    return ""


def editorial_priority(article: Article) -> int:
    """Return an editorial tier: 2 must-cover, 1 useful, 0 routine."""
    text = f"{article.title} {article.content}".lower()
    if _is_routine_release(article, text):
        return 0
    if any(signal in text for signal in MODEL_SIGNALS) or _is_coding_news(text):
        return 2
    entity = editorial_entity(article)
    if entity and (article.official or any(signal in text for signal in BUSINESS_SIGNALS)):
        return 2
    if article.category in {"政策与监管", "投融资与并购"}:
        return 1
    return 0


def classify(article: Article) -> Article:
    text = f"{article.title} {article.content}".lower()
    scores = {category: sum(1 for word in words if word.lower() in text) for category, words in CATEGORIES.items()}
    article.category = max(scores, key=scores.get) if max(scores.values(), default=0) else "其他"
    if article.category == "AI开发工具与Agent" and not _is_coding_news(text):
        scores["AI开发工具与Agent"] = 0
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
        "AI开发工具与Agent": 10, "政策与监管": 8, "模型与产品发布": 7, "投融资与并购": 6,
        "企业与商业动态": 3, "开源项目": 2,
    }.get(article.category, 0)
    priority = editorial_priority(article)
    article.score += {2: 18, 1: 5}.get(priority, 0)
    if any(signal in text for signal in MODEL_SIGNALS):
        article.score += 12
    routine_release = _is_routine_release(article, text)
    if _is_coding_news(text) and not routine_release:
        article.score += 10
    if article.source == "GitHub":
        article.score -= 20
    elif article.source == "GitHub Release" and priority == 0:
        article.score -= 12
    if routine_release:
        article.score -= 30
    elif any(signal in text for signal in LOW_VALUE_SIGNALS) or VERSION_ONLY.search(article.title):
        article.score -= 18 if priority == 0 else 7
    if article.category == "研究与论文" and priority == 0:
        article.score -= 6
    if article.category == "其他" and priority == 0:
        article.score -= 12
    article.score = round(min(article.score, 100), 1)
    # Unverified stories never become a top story solely through keyword density.
    if article.verification == "单一信源" and not article.official:
        article.score = min(article.score, 60.0)
    return article
