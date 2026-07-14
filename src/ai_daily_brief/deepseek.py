from __future__ import annotations

import json
import logging
import re
import time

import httpx

from .models import Article

logger = logging.getLogger(__name__)

ALLOWED_CATEGORIES = {
    "AI开发工具与Agent", "模型与产品发布", "企业与商业动态", "投融资与并购", "开源项目",
    "研究与论文", "政策与监管", "AI应用案例", "其他",
}

SYSTEM_PROMPT = """你是严谨的AI行业新闻编辑。只能依据用户提供的材料工作，不能补充模型记忆中的事实。
输出必须是JSON对象，不要使用Markdown。对象只有items字段，items是数组；每个元素包含id、category、summary、why_it_matters、tags。
summary用60-100个中文字符陈述事实；why_it_matters用30-60个中文字符具体说明它对竞争格局、产品用户或商业决策的影响。
保留公司名、模型名、金额、日期等关键事实；不使用“震撼、重磅、赋能”等营销词。
材料不足时明确写“来源未披露更多细节”，不得编造数字或结论。
禁止使用“值得关注、建议持续关注、进入候选列表”之类空话；材料不足就说明缺少什么。
category只能是：AI开发工具与Agent、模型与产品发布、企业与商业动态、投融资与并购、开源项目、研究与论文、政策与监管、AI应用案例、其他。"""


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


def _post_completion(base_url: str, api_key: str, request: dict) -> httpx.Response:
    last_error: Exception | None = None
    for attempt in range(3):
        response: httpx.Response | None = None
        try:
            response = httpx.post(
                f"{base_url.rstrip('/')}/chat/completions",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json=request, timeout=90,
            )
            if response.status_code != 429 and response.status_code < 500:
                response.raise_for_status()
                return response
            last_error = httpx.HTTPStatusError(
                f"Retryable DeepSeek status {response.status_code}",
                request=response.request, response=response,
            )
        except httpx.TransportError as exc:
            last_error = exc
        if attempt < 2:
            retry_after = response.headers.get("Retry-After") if response is not None else None
            delay = float(retry_after) if retry_after and retry_after.isdigit() else 2 ** attempt
            time.sleep(delay)
    raise RuntimeError("DeepSeek failed after 3 attempts") from last_error


def _apply_row(article: Article, row: object) -> bool:
    if not isinstance(row, dict):
        return False
    summary = row.get("summary")
    why_it_matters = row.get("why_it_matters")
    tags = row.get("tags", [])
    if not isinstance(summary, str) or not summary.strip():
        return False
    if not isinstance(why_it_matters, str) or not isinstance(tags, list):
        return False
    if not all(isinstance(tag, str) for tag in tags):
        return False
    category = row.get("category")
    if isinstance(category, str) and category in ALLOWED_CATEGORIES:
        article.category = category
    article.summary = summary.strip()
    article.why_it_matters = why_it_matters.strip()
    article.tags = list(dict.fromkeys(article.tags + tags))[:5]
    return True


def enrich_articles(articles: list[Article], api_key: str, base_url: str,
                    model: str, batch_size: int = 8) -> bool:
    if not api_key:
        for article in articles:
            _fallback(article)
        logger.warning("DEEPSEEK_API_KEY is absent; using extractive summaries")
        return False

    enriched_count = 0
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
            response = _post_completion(base_url, api_key, request)
            rows = _json_payload(response.json()["choices"][0]["message"]["content"])
            indexed: dict[int, dict] = {}
            for row in rows:
                if not isinstance(row, dict) or "id" not in row:
                    continue
                try:
                    indexed[int(row["id"])] = row
                except (TypeError, ValueError):
                    continue
            for index, article in enumerate(batch):
                if _apply_row(article, indexed.get(start + index)):
                    enriched_count += 1
                else:
                    _fallback(article)
        except (httpx.HTTPError, KeyError, ValueError, TypeError, json.JSONDecodeError, RuntimeError) as exc:
            logger.exception("DeepSeek batch failed; falling back: %s", exc)
            for article in batch:
                _fallback(article)
    return enriched_count > 0
