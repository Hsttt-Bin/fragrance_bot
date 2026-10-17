"""混合检索：向量语义（FAISS）+ BM25 关键词 + query 多路改写 RRF 融合。"""
from dataclasses import dataclass

from . import config
from .embedder import embed_texts
from .keyword_index import BM25Index
from .reranker import rerank as rerank_docs
from .rewriter import rewrite_queries
from .store import KnowledgeBase

RRF_K = 60  # 倒数排名融合的平滑常数


@dataclass
class RetrievalResult:
    chunk: dict
    vector_score: float
    keyword_score: float
    final_score: float
    rerank_score: float = 0.0


class HybridRetriever:
    def __init__(self, vector_weight: float = None, keyword_weight: float = None):
        self.kb = KnowledgeBase()
        self.bm25 = BM25Index([_DictChunkAdapter(c) for c in self.kb.chunks])
        self.vector_weight = config.VECTOR_WEIGHT if vector_weight is None else vector_weight
        self.keyword_weight = config.KEYWORD_WEIGHT if keyword_weight is None else keyword_weight
        self.rewritten_queries = []
        self.rerank_scores = {}

    def _rank(self, query: str) -> list:
        """单路 query 的打分结果：(chunk_idx, vector_score, keyword_score, final_score)，按 final 降序。"""
        q_vec = embed_texts([query])[0]
        v_scores, ids = self.kb.search_vectors(q_vec, self.kb.index.ntotal)
        v_score_map = {int(i): float(s) for i, s in zip(ids, v_scores)}
        kw_scores = BM25Index.normalize(self.bm25.score(query))

        ranked = []
        for i in range(len(self.kb.chunks)):
            vs = min(max(v_score_map.get(i, 0.0), 0.0), 1.0)
            ks = kw_scores[i] if i < len(kw_scores) else 0.0
            final = self.vector_weight * vs + self.keyword_weight * ks
            ranked.append((i, vs, ks, final))
        ranked.sort(key=lambda t: t[3], reverse=True)
        return ranked

    def search(self, query: str, k: int = 5, rewrite: bool = True, rerank: bool = True) -> list:
        """多路检索：原 query + LLM 改写 query，RRF 融合后 rerank 精排取 top-k。"""
        queries = [query]
        if rewrite and config.REWRITE_ENABLED:
            self.rewritten_queries = rewrite_queries(query)
            queries += self.rewritten_queries
        else:
            self.rewritten_queries = []

        # 每路 query 排名：rank 从 0 开始；rrf 累加 1/(RRF_K + rank)
        rrf = {}
        best_vs = {}
        best_ks = {}
        for q in queries:
            ranked = self._rank(q)
            for rank, (i, vs, ks, _final) in enumerate(ranked):
                rrf[i] = rrf.get(i, 0.0) + 1.0 / (RRF_K + rank)
                best_vs[i] = max(best_vs.get(i, 0.0), vs)
                best_ks[i] = max(best_ks.get(i, 0.0), ks)

        results = [
            RetrievalResult(
                chunk=self.kb.chunks[i],
                vector_score=best_vs.get(i, 0.0),
                keyword_score=best_ks.get(i, 0.0),
                final_score=rrf[i],
            )
            for i in rrf
        ]
        results.sort(key=lambda r: r.final_score, reverse=True)

        # rerank 精排：取 RRF 前 RERANK_TOP_N 作为候选池，用原 query 逐对打分重排
        pool = results[: max(config.RERANK_TOP_N, k)]
        self.rerank_scores = {}
        if rerank and config.RERANK_ENABLED and len(pool) > 1:
            docs = [r.chunk["title"] + "\n" + r.chunk["content"] for r in pool]
            scored = rerank_docs(query, docs)  # [(doc_index, score)]，按相关性降序
            if scored:
                score_by_pos = {idx: s for idx, s in scored}
                for pos, r in enumerate(pool):
                    r.rerank_score = score_by_pos.get(pos, 0.0)
                pool.sort(key=lambda r: r.rerank_score, reverse=True)
                self.rerank_scores = score_by_pos

        return pool[:k]


class _DictChunkAdapter:
    """把 chunks.json 的 dict 适配成 BM25Index 需要的属性接口。"""

    def __init__(self, d: dict):
        self.title = d.get("title", "")
        self.content = d.get("content", "")
        self.keywords = d.get("keywords", [])
