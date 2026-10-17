"""中文 BM25 关键词倒排索引。"""
import math
from collections import Counter

import jieba

from .chunker import CUSTOM_WORDS  # 确保自定义词典已注册

# 停用词：中文功能字/词 + 高频无判别力的域内动词。单字不做长度过滤，
# 只靠停用词表兜底，以保留「坑、烧、钱、元、蜡」等有意义的单字。
_STOPWORDS = (
    # 单字停用词：原为无空格拼接，须用 set(字符串) 拆成单字（拆错会导致整串失效）
    set(
        "的了和与及或在对于为是有不这那个等很都会可可能被把我们你们他们它中大小更最"
        "就也还而但从向往用要将让使只才又再已曾经着每各几一二三四五六七八九十"
    )
    # 多字停用词：须用空格分隔后再 split()（原写法对整段无空格字符串 .split() 会塌缩成一个超长串）
    | set(
        "请问 一下 什么 怎么 怎么办 为什么 哪个 哪些 有没有 能不能 可以 "
        "还是 因为 所以 但是 如果 一个 出来 这个 那个 使用 建议 推荐 适用 "
        "避免 需要 保持 进行 以及 根据 对于 关于 其他 如何 多少".split()
    )
    | {
        "吗", "呢", "吧", "啊", "哦", "呀", "的", "得", "地", "了", "着", "过",
    }
)


def tokenize(text: str) -> list:
    return [
        t for t in jieba.cut_for_search(text)
        if t.strip() and not t.isspace() and t not in _STOPWORDS
    ]


class BM25Index:
    """经典 BM25（k1=1.5, b=0.75），chunk 命中自带 keywords 字段时加权。"""

    def __init__(self, chunks: list, k1: float = 1.5, b: float = 0.75, keyword_boost: float = 1.5):
        self.k1, self.b, self.keyword_boost = k1, b, keyword_boost
        self.chunks = chunks
        self.doc_tokens = []
        self.doc_keywords = []
        for c in chunks:
            self.doc_tokens.append(tokenize(c.title + " " + c.content))
            self.doc_keywords.append([t for t in c.keywords if t.strip()])
        self.doc_len = [len(t) for t in self.doc_tokens]
        self.avg_len = sum(self.doc_len) / max(len(self.doc_len), 1)
        self.df = Counter()
        for toks in self.doc_tokens:
            self.df.update(set(toks))
        for kws in self.doc_keywords:
            self.df.update(set(kws))
        self.n = len(chunks)

    def _idf(self, term: str) -> float:
        df = self.df.get(term, 0)
        return math.log((self.n - df + 0.5) / (df + 0.5) + 1.0)

    def score(self, query: str) -> list:
        """返回每个 chunk 的 BM25 原始分数列表。"""
        q_tokens = tokenize(query)
        scores = [0.0] * self.n
        for qi, (toks, kws, dlen) in enumerate(zip(self.doc_tokens, self.doc_keywords, self.doc_len)):
            tf = Counter(toks)
            kw = set(kws)
            s = 0.0
            for term in set(q_tokens):
                f = tf.get(term, 0)
                if f == 0 and term in kw:
                    f = 1  # 关键词字段命中按 1 次计
                if f == 0:
                    continue
                norm = f * (self.k1 + 1) / (f + self.k1 * (1 - self.b + self.b * dlen / self.avg_len))
                w = self.keyword_boost if term in kw else 1.0
                s += self._idf(term) * norm * w
            scores[qi] = s
        return scores

    @staticmethod
    def normalize(scores: list, tau: float = 3.0) -> list:
        """饱和归一化：score/(score+tau)，弱匹配保持低分，避免 min-max 把 argmax 顶到 1.0。"""
        return [s / (s + tau) for s in scores]
