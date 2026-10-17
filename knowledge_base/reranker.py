"""Rerank 精排：经 AGICTO /v1/rerank 对候选块与用户原 query 逐对打分重排。

协议为 Cohere 风格（非 DashScope 原生）：请求 {model, query, documents}，
响应 results[{index, relevance_score}]，已按相关性降序。
任何异常/超时/空结果都降级为空列表，调用方回退为 RRF 顺序。
"""
import httpx

from . import config

_URL = f"{config.AGICTO_BASE_URL}/rerank"


def rerank(query: str, documents: list) -> list:
    """返回 [(doc_index, relevance_score)]，按相关性降序；失败返回空列表。"""
    try:
        resp = httpx.post(
            _URL,
            headers={"Authorization": f"Bearer {config.AGICTO_API_KEY}"},
            json={"model": config.RERANK_MODEL, "query": query, "documents": documents},
            timeout=config.RERANK_TIMEOUT,
        )
        resp.raise_for_status()
        body = resp.json()
        results = body.get("results")
        if not results:
            err = body.get("error") or body.get("message") or "空结果"
            print(f"[rerank] 精排失败，回退为 RRF 顺序：{err}")
            return []
        return [(int(item["index"]), float(item["relevance_score"])) for item in results]
    except Exception as e:
        print(f"[rerank] 精排失败，回退为 RRF 顺序：{e}")
        return []
