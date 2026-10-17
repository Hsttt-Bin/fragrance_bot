"""回答生成：把上下文（本地知识块 / 联网搜索结果）交给对话模型归纳为客服回复。

与 rewriter 一致走 httpx 直连 /v1/chat/completions；deepseek 系列为推理模型，
content 为空时回退 reasoning_content。任何异常/空结果都返回 None，调用方降级打印原文。
"""
import httpx

from . import config

_URL = f"{config.AGICTO_BASE_URL}/chat/completions"

# 联网搜索回答的系统提示词（与本地知识块回复的 ANSWER_SYSTEM_PROMPT 区分）
_WEB_SYSTEM_PROMPT = (
    "你是香薰客服助手。基于提供的联网搜索结果回答用户问题，要求："
    "1) 回答简洁、口语化、中文；2) 优先采用最新、最权威的信息；"
    "3) 在正文中用 [1][2] 标注信息来源序号；"
    "4) 若搜索结果与问题无关或信息不足，直接说明无法从联网结果确认，不要编造。"
)


def _chat(messages: list, model: str | None = None, timeout: int | None = None, max_tokens: int | None = None) -> str | None:
    """调用对话模型；content 为空时回退 reasoning_content；失败返回 None。

    model/timeout/max_tokens 缺省时走 config.ANSWER_*；recommender 等调用方可传入自己的取值。
    """
    try:
        resp = httpx.post(
            _URL,
            headers={"Authorization": f"Bearer {config.AGICTO_API_KEY}"},
            json={
                "model": model or config.ANSWER_MODEL,
                "messages": messages,
                "temperature": config.ANSWER_TEMPERATURE,
                "max_tokens": max_tokens or config.ANSWER_MAX_TOKENS,
            },
            timeout=timeout or config.ANSWER_TIMEOUT,
        )
        resp.raise_for_status()
        msg = (resp.json().get("choices") or [{}])[0].get("message", {})
        content = (msg.get("content") or "").strip()
        if not content:
            content = (msg.get("reasoning_content") or "").strip()
        return content or None
    except Exception as e:
        print(f"[answer] 回答生成失败：{e}")
        return None


def answer_from_chunks(query: str, chunks: list) -> str | None:
    """基于本地召回的知识块生成客服回复；chunks 为 [{title, content}, ...]。"""
    if not chunks:
        return None
    parts = []
    for c in chunks:
        title = (c.get("title") or "").strip()
        content = (c.get("content") or "").strip()
        parts.append(f"【{title}】\n{content}" if title else content)
    context = "\n\n".join(parts)
    messages = [
        {"role": "system", "content": config.ANSWER_SYSTEM_PROMPT},
        {"role": "user", "content": f"以下是检索到的产品资料，请只依据这些资料回答：\n\n{context}\n\n用户问题：{query}"},
    ]
    return _chat(messages)


def generate_answer(query: str, web_results: list) -> str | None:
    """基于联网搜索结果生成回答；web_results 为 [{title, url, content}, ...]。"""
    lines = []
    for i, r in enumerate(web_results, 1):
        head = r["title"] or r["url"] or f"来源{i}"
        lines.append(f"[{i}] {head}\n{r['content']}")
    messages = [
        {"role": "system", "content": _WEB_SYSTEM_PROMPT},
        {"role": "user", "content": f"用户问题：{query}\n\n联网搜索结果：\n" + "\n\n".join(lines)},
    ]
    return _chat(messages)
