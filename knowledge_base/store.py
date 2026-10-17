"""知识库持久化：FAISS 索引 + chunks.json + meta.json。"""
import json
from datetime import datetime

import faiss
import numpy as np

from . import config


def save(chunks: list, vectors: np.ndarray):
    config.KB_DATA_DIR.mkdir(parents=True, exist_ok=True)

    # FAISS 内积索引（向量已 L2 归一化，内积 = 余弦相似度）
    dim = vectors.shape[1]
    index = faiss.IndexFlatIP(dim)
    index.add(vectors)
    faiss.write_index(index, str(config.KB_DATA_DIR / "index.faiss"))

    with open(config.KB_DATA_DIR / "chunks.json", "w", encoding="utf-8") as f:
        json.dump([c.to_dict() for c in chunks], f, ensure_ascii=False, indent=2)

    meta = {
        "model": config.EMBEDDING_MODEL,
        "dim": dim,
        "n_chunks": len(chunks),
        "built_at": datetime.now().isoformat(timespec="seconds"),
        "source": str(config.SOURCE_DOC),
    }
    with open(config.KB_DATA_DIR / "meta.json", "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    return meta


class KnowledgeBase:
    """加载已构建的知识库，供检索使用。"""

    def __init__(self):
        if not (config.KB_DATA_DIR / "index.faiss").exists():
            raise FileNotFoundError(
                "知识库尚未构建：请先运行 python build_kb.py"
            )
        self.index = faiss.read_index(str(config.KB_DATA_DIR / "index.faiss"))
        with open(config.KB_DATA_DIR / "chunks.json", encoding="utf-8") as f:
            self.chunks = json.load(f)
        with open(config.KB_DATA_DIR / "meta.json", encoding="utf-8") as f:
            self.meta = json.load(f)

    def search_vectors(self, query_vec: np.ndarray, k: int):
        """返回 (相似度数组, chunk 索引数组)，已按内积降序。"""
        q = np.asarray(query_vec, dtype=np.float32).reshape(1, -1)
        k = min(k, self.index.ntotal)
        scores, ids = self.index.search(q, k)
        return scores[0], ids[0]
