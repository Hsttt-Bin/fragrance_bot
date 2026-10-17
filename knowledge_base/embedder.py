"""调用 AGICTO 的 tongyi-embedding-vision-flash（DashScope 原生多模态协议）。

该模型不走 OpenAI 兼容的 /v1/embeddings 响应格式（data[]），而是返回
DashScope 原生结构 ``output.embeddings[]``，输入要求 ``input.contents`` 对象数组，
因此这里直接用 httpx 调用，不依赖 openai SDK。
"""
import time

import httpx
import numpy as np

from . import config

_URL = f"{config.AGICTO_BASE_URL}/embeddings"


def _embed_one_batch(client: httpx.Client, batch: list) -> list:
    payload = {
        "model": config.EMBEDDING_MODEL,
        "input": {"contents": [{"type": "text", "text": t} for t in batch]},
    }
    resp = client.post(
        _URL,
        headers={"Authorization": f"Bearer {config.AGICTO_API_KEY}"},
        json=payload,
    )
    resp.raise_for_status()
    body = resp.json()
    embs = body.get("output", {}).get("embeddings") or []
    if len(embs) != len(batch):
        raise RuntimeError(f"返回 embedding 数量异常：期望 {len(batch)}，实际 {len(embs)}")
    embs = sorted(embs, key=lambda e: e.get("index", 0))
    return [e["embedding"] for e in embs]


def embed_texts(texts: list, show_progress: bool = False) -> np.ndarray:
    """批量将文本转为向量矩阵 (n, dim)，L2 归一化。"""
    all_vecs = []
    with httpx.Client(timeout=120) as client:
        for start in range(0, len(texts), config.EMBED_BATCH_SIZE):
            batch = texts[start: start + config.EMBED_BATCH_SIZE]
            for attempt in range(1, config.EMBED_MAX_RETRIES + 1):
                try:
                    all_vecs.extend(_embed_one_batch(client, batch))
                    break
                except Exception as e:
                    if attempt == config.EMBED_MAX_RETRIES:
                        raise
                    wait = config.EMBED_RETRY_SLEEP * attempt
                    print(f"[embed] 第 {attempt} 次失败：{e}，{wait}s 后重试")
                    time.sleep(wait)
            if show_progress:
                done = min(start + config.EMBED_BATCH_SIZE, len(texts))
                print(f"[embed] {done}/{len(texts)}")
            time.sleep(0.2)  # 温和限速
    mat = np.asarray(all_vecs, dtype=np.float32)
    # L2 归一化（内积 = 余弦相似度）
    norms = np.linalg.norm(mat, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return mat / norms
