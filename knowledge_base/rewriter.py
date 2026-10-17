"""Query 多路改写：经 AGICTO 对话模型（deepseek-flash）生成多条规范查询。

与 embedder 一致，走 httpx 直连 OpenAI 兼容的 /v1/chat/completions。
任何异常/超时/空结果都降级为空列表，保证检索永远可用。
"""
import json
import re

import httpx

from . import config

_URL = f"{config.AGICTO_BASE_URL}/chat/completions"


def _parse_queries(text: str, n: int) -> list:
    """解析模型输出为 n 条 query：优先 JSON 数组，失败则提取引号串/按行拆分。"""
    if not text:
        return []
    text = text.strip()
    # 去掉 ```json ... ``` 包裹
    m = re.match(r"^```[a-zA-Z]*\s*(.*?)\s*```$", text, re.S)
    if m:
        text = m.group(1).strip()

    queries = None
    try:
        parsed = json.loads(text)
        if isinstance(parsed, list):
            queries = [str(q).strip() for q in parsed if str(q).strip()]
        elif isinstance(parsed, str):
            queries = [parsed.strip()]
    except (json.JSONDecodeError, ValueError):
        queries = None

    if queries is None:
        # 截断/不完整 JSON：提取所有双引号包裹的内容
        queries = re.findall(r'"([^"]+)"', text)
        if not queries:
            # 最后兜底：按行拆分并清理编号/列表符/括号
            queries = []
            for line in text.splitlines():
                line = line.strip().strip('[]"\' ,\t')
                line = re.sub(r"^\d+[\.、\)]\s*", "", line)
                line = line.strip('"\'[] ')
                if line:
                    queries.append(line)

    # 去空、去重、截断
    seen, result = set(), []
    for q in queries:
        q = q.strip().strip('"\'[] ')
        if q and q not in seen:
            seen.add(q)
            result.append(q)
        if len(result) >= n:
            break
    return result


def rewrite_queries(query: str, n: int = None) -> list:
    """返回 n 条改写 query；失败时返回空列表（调用方回退为仅用原 query）。"""
    # 空/纯空白 query 直接返回空列表：否则会把空消息发给模型，模型会反问
    # 「请提供提问内容」，而 _parse_queries 又会把这句话当成一条「改写」传回，污染检索。
    if not query or not query.strip():
        return []
    n = n or config.REWRITE_NUM
    try:
        resp = httpx.post(
            _URL,
            headers={"Authorization": f"Bearer {config.AGICTO_API_KEY}"},
            json={
                "model": config.REWRITE_MODEL,
                "messages": [
                    {"role": "system", "content": config.REWRITE_SYSTEM_PROMPT.format(n=n)},
                    {"role": "user", "content": query},
                ],
                "temperature": config.REWRITE_TEMPERATURE,
                "max_tokens": config.REWRITE_MAX_TOKENS,
            },
            timeout=config.REWRITE_TIMEOUT,
        )
        resp.raise_for_status()
        msg = (resp.json().get("choices") or [{}])[0].get("message", {})
        content = msg.get("content") or ""
        if not content.strip():
            # 推理模型被截断时 content 为空，退而取 reasoning_content 兜底
            content = msg.get("reasoning_content") or ""
        return _parse_queries(content, n)
    except Exception as e:
        print(f"[rewrite] 改写失败，回退为原 query：{e}")
        return []
