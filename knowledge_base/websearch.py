"""联网搜索：经 AGICTO /v1/tool/search 抓取网页结果，供本地 KB 低分兜底时生成回答。

返回 [{"title", "url", "content"}]，content 优先取抓取正文（bing 的 content 字段），
缺省回退 snippet（google 的 snippet 字段）。任何异常/超时/空结果都降级为空列表，
保证检索永远可用（与 reranker/rewriter 降级风格一致）。
"""
import httpx

from . import config

_URL = f"{config.AGICTO_BASE_URL}/tool/search"


def _to_result(item: dict) -> dict:
    """防御式解析单条搜索结果，兼容 google（link/title/snippet）与 bing（content 抓取正文）。"""
    title = (item.get("title") or "").strip()
    url = (item.get("link") or item.get("url") or "").strip()
    snippet = (item.get("snippet") or "").strip()
    content = (item.get("content") or "").strip() or snippet
    return {"title": title, "url": url, "content": content}


def web_search(query: str) -> list:
    """返回抓取结果列表；失败返回空列表。"""
    try:
        resp = httpx.post(
            _URL,
            headers={"Authorization": f"Bearer {config.AGICTO_API_KEY}"},
            json={
                "query": query,
                "search_service": config.WEB_SEARCH_SERVICE,
                "max_results": config.WEB_SEARCH_MAX_RESULTS,
                "crawl_results": config.WEB_SEARCH_CRAWL_RESULTS,
            },
            timeout=config.WEB_SEARCH_TIMEOUT,
        )
        resp.raise_for_status()
        body = resp.json()
        if body.get("error"):
            print(f"[web] 联网搜索失败：{body['error']}")
            return []
        results = body.get("results") or []
        parsed = [_to_result(x) for x in results if isinstance(x, dict)]
        parsed = [x for x in parsed if x["title"] or x["content"]]
        return parsed
    except Exception as e:
        print(f"[web] 联网搜索失败：{e}")
        return []
