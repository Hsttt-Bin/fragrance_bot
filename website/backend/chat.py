"""聊天接口：POST /api/chat/stream（SSE 流式输出）。

检索链路复用 knowledge_base.HybridRetriever；把命中的知识块组装成运行期 Prompt，
再流式调用对话模型生成回复，增量文本以 event: content 逐段下发。
"""

import asyncio
import json
import sys
from pathlib import Path
from typing import AsyncGenerator

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

# 让 knowledge_base 包可被导入：它位于项目根目录（backend 在其下两级）。
# 该包使用相对导入（from . import config），必须以 `knowledge_base` 包名导入。
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from knowledge_base import config  # noqa: E402  (只读：ANSWER_MODEL / API Key / 系统提示词等)
from knowledge_base.retriever import HybridRetriever  # noqa: E402

router = APIRouter()


class ChatRequest(BaseModel):
    message: str = ""


def init_retriever() -> HybridRetriever:
    """加载 FAISS 索引与 chunks，构建混合检索器。

    仅在应用启动时调用一次，整个进程复用同一实例，避免每次请求重新加载索引。
    API Key 由 knowledge_base.config 从项目根目录 .env 读取，此处不硬编码。
    """
    return HybridRetriever()


def _event(name: str, data: str) -> str:
    """构造一条 SSE 事件，data 为已序列化的字符串。"""
    return f"event: {name}\ndata: {data}\n\n"


def _build_messages(question: str, results: list) -> list:
    """把命中的知识块组装成运行期上下文，复用 config.ANSWER_SYSTEM_PROMPT（PRD 规则）。"""
    parts = []
    for r in results:
        title = (r.chunk.get("title") or "").strip()
        content = (r.chunk.get("content") or "").strip()
        parts.append(f"【{title}】\n{content}" if title else content)
    context = "\n\n".join(parts)
    return [
        {"role": "system", "content": config.ANSWER_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": f"以下是检索到的产品资料，请只依据这些资料回答：\n\n{context}\n\n用户问题：{question}",
        },
    ]


async def _stream_llm(messages: list) -> AsyncGenerator[str, None]:
    """流式调用对话模型，逐段 yield 增量回答文本。

    只取 delta.content（正文），忽略 delta.reasoning_content（思维链）。
    异常向上抛出，由上层发 event: error。
    """
    url = f"{config.AGICTO_BASE_URL}/chat/completions"
    payload = {
        "model": config.ANSWER_MODEL,
        "messages": messages,
        "temperature": config.ANSWER_TEMPERATURE,
        "max_tokens": config.ANSWER_MAX_TOKENS,
        "stream": True,
    }
    async with httpx.AsyncClient(timeout=config.ANSWER_TIMEOUT) as client:
        async with client.stream(
            "POST",
            url,
            headers={"Authorization": f"Bearer {config.AGICTO_API_KEY}"},
            json=payload,
        ) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line or not line.startswith("data:"):
                    continue
                data = line[len("data:"):].strip()
                if data == "[DONE]":
                    break
                try:
                    obj = json.loads(data)
                except (json.JSONDecodeError, ValueError):
                    continue
                delta = (obj.get("choices") or [{}])[0].get("delta") or {}
                text = delta.get("content")
                if text:
                    yield text


async def _stream(retriever: HybridRetriever, question: str) -> AsyncGenerator[str, None]:
    # 真实检索（阻塞调用放到线程池，避免卡住事件循环）。
    results = await asyncio.to_thread(retriever.search, question)

    # 1) event: retrieval —— 改写后的 query 列表 + 各命中块的向量分 / BM25 分
    # 注：RetrievalResult.keyword_score 即 BM25 关键词分。
    yield _event(
        "retrieval",
        json.dumps(
            {
                "query": question,
                "rewritten_queries": list(retriever.rewritten_queries),
                "results": [
                    {
                        "vector_score": round(r.vector_score, 4),
                        "bm25_score": round(r.keyword_score, 4),
                        "final_score": round(r.final_score, 6),
                    }
                    for r in results
                ],
            },
            ensure_ascii=False,
        ),
    )

    # 2) event: sources —— 命中的知识块原文与得分
    yield _event(
        "sources",
        json.dumps(
            [
                {
                    "id": r.chunk.get("id"),
                    "category": r.chunk.get("category"),
                    "title": r.chunk.get("title"),
                    "content": r.chunk.get("content"),
                    "source_path": r.chunk.get("source_path"),
                    "vector_score": round(r.vector_score, 4),
                    "bm25_score": round(r.keyword_score, 4),
                    "final_score": round(r.final_score, 6),
                    "rerank_score": round(r.rerank_score, 4),
                }
                for r in results
            ],
            ensure_ascii=False,
        ),
    )

    # 3) event: content —— LLM 流式生成（只依据检索资料回答）
    if results:
        try:
            yielded = False
            async for text in _stream_llm(_build_messages(question, results)):
                yielded = True
                yield _event("content", json.dumps({"text": text}, ensure_ascii=False))
            if not yielded:
                yield _event("error", json.dumps({"message": "AI 未返回内容，请稍后重试"}, ensure_ascii=False))
        except Exception as e:
            print(f"[chat] LLM 生成失败：{e}", flush=True)
            yield _event("error", json.dumps({"message": "AI 回复生成失败，请稍后重试"}, ensure_ascii=False))
    else:
        yield _event("error", json.dumps({"message": "没有检索到相关资料，换个问法试试"}, ensure_ascii=False))

    # 4) event: done
    yield _event("done", json.dumps({"status": "done"}, ensure_ascii=False))


@router.post("/api/chat/stream")
async def chat_stream(payload: ChatRequest, request: Request):
    if not payload.message or not payload.message.strip():
        raise HTTPException(status_code=422, detail="message 不能为空")
    retriever: HybridRetriever = request.app.state.retriever
    return StreamingResponse(
        _stream(retriever, payload.message),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
