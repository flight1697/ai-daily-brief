from __future__ import annotations

import json
import logging
import re

import httpx

from .models import Article

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """你是严谨的AI行业新闻编辑。只能依据用户提供的材料工作，不能补充模型记忆中的事实。
输出必须是JSON对象，不要使用Markdown。对象只有items字段，items是数组；每个元素包含id、category、summary、why_it_matters、tags。
summary用60-100个中文字符陈述事实；why_it_matters用30-60个中文字符说明影响。
保留公司名、模型名、金额、日期等关键事实；不使用“震撼、重磅、赋能”等营销词。
材料不足时明确写“来源未披露更多细节”，不得编造数字或结论。
category只能是：模型与产品发布、企业与商业动态、投融资与并购、开源项目、研究与论文、政策与监管、AI应用案例、其他。"""


def _fallback(article: Article) -> None:
    body = article.content.strip()
    article.summary = (body[:117] + "…") if len(body) > 118 else (body or article.title)
    article.why_it_matters = "该动态进入当日候选列表，建议结合原始来源判断其后续行业影响。"


def _json_payload(text: str) -> list[dict]:
    text = text.strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if fenced:
        text = fenced.group(1)
    value = json.loads(text)
    if isinstance(value, dict):
        value = value.get("items")
    if not isinstance(value, list):
        raise ValueError("DeepSeek response must contain an items array")
    return value


def enrich_articles(articles: list[Article], api_key: str, base_url: str,
                    model: str, batch_size: int = 8) -> bool:
    if not api_key:
        for article in articles:
            _fallback(article)
        logger.warning("DEEPSEEK_API_KEY is absent; using extractive summaries")
        return False

    for start in range(0, len(articles), batch_size):
        batch = articles[start:start + batch_size]
        materials = [{
            "id": start + index,
            "title": item.title,
            "source": item.source,
            "published_at": item.published_at.isoformat(),
            "content": item.content[:3000],
            "current_category": item.category,
        } for index, item in enumerate(batch)]
        request = {
            "model": model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": json.dumps(materials, ensure_ascii=False)},
            ],
            "temperature": 0.1,
            "response_format": {"type": "json_object"},
        }
        try:
            response = httpx.post(
                f"{base_url.rstrip('/')}/chat/completions",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json=request, timeout=90,
            )
            response.raise_for_status()
            rows = _json_payload(response.json()["choices"][0]["message"]["content"])
            indexed = {int(row["id"]): row for row in rows}
            for index, article in enumerate(batch):
                row = indexed.get(start + index, {})
                article.category = row.get("category", article.category)
                article.summary = row.get("summary", "").strip()
                article.why_it_matters = row.get("why_it_matters", "").strip()
                article.tags = list(dict.fromkeys(article.tags + row.get("tags", [])))[:5]
                if not article.summary:
                    _fallback(article)
        except (httpx.HTTPError, KeyError, ValueError, json.JSONDecodeError) as exc:
            logger.exception("DeepSeek batch failed; falling back: %s", exc)
            for article in batch:
                _fallback(article)
    return True
