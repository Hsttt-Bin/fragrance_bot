"""命令行客服问答：python search.py "问题" [-k 5] [--verbose] [--no-answer] [--no-rewrite] [--no-rerank] [--web/--no-web] [--no-recommend]

无参数运行进入交互会话（欢迎引导 + 循环 + 「退出」结束），可在会话内累计星座 / MBTI / 场景 / 性格喜好信息，
凑齐两个维度即做香气推荐；普通问题照常走 RAG。默认只打印大模型生成的回复；--verbose 显示完整检索调试。
"""
import argparse

from knowledge_base import config
from knowledge_base.answerer import answer_from_chunks, generate_answer
from knowledge_base.recommender import (
    build_followup,
    extract_dims,
    is_recommend_intent,
    merge_dims,
    recommend,
    _filled_count,
    _has_info,
)
from knowledge_base.retriever import HybridRetriever
from knowledge_base.websearch import web_search

# 交互会话欢迎引导（「问题引导处」文案）
_WELCOME = (
    "你好，我是雾歇香薰的在线顾问。\n"
    "想找适合你的香，可以告诉我：星座、MBTI、使用场景（任意两项以上），我来帮你选；\n"
    "也可以直接问香薰使用、商品、物流类的问题。（输入「退出」结束）"
)

_EXIT_WORDS = {"退出", "exit", "quit", "q", "再见"}


def _print_retrieval(retriever, results, args, query):
    """打印检索调试信息（问题/改写/精排 + 每块标题与分数；--verbose 附加正文与关键词）。"""
    print(f"\n问题：{query}")
    if retriever.rewritten_queries:
        print("改写后：" + " ｜ ".join(retriever.rewritten_queries))
    rerank_on = bool(retriever.rerank_scores)
    if rerank_on:
        print(f"精排：{config.RERANK_MODEL}（候选池 {config.RERANK_TOP_N}）")
    print(f"知识库：{retriever.kb.meta['n_chunks']} 块，模型 {retriever.kb.meta['model']}\n")
    for rank, r in enumerate(results, 1):
        if rerank_on:
            print(f"[{rank}] 精排 {r.rerank_score:.3f} | 综合(RRF) {r.final_score:.3f} | 向量 {r.vector_score:.3f} | 关键词 {r.keyword_score:.3f}")
        else:
            print(f"[{rank}] 综合 {r.final_score:.3f} | 向量 {r.vector_score:.3f} | 关键词 {r.keyword_score:.3f}")
        print(f"    【{r.chunk['category']}】{r.chunk['title']}")
        if args.verbose:
            print(f"    内容：{r.chunk['content'][:200]}")
            print(f"    关键词：{'、'.join(r.chunk['keywords'])}")
        print()
    if not args.verbose:
        print("（加 --verbose 查看完整内容）")


def _run_rag(query, args, retriever):
    """原有 RAG 流程：改写 → 混合检索 → 精排 → 生成回复 → 联网兜底。"""
    results = retriever.search(
        query, k=args.k, rewrite=not args.no_rewrite, rerank=not args.no_rerank
    )

    # 联网兜底判断（top-1 置信度：精排分优先，否则向量分）
    top1 = results[0] if results else None
    if top1 is None:
        confidence = 0.0
    elif retriever.rerank_scores:
        confidence = top1.rerank_score
    else:
        confidence = top1.vector_score
    need_web = (
        config.WEB_SEARCH_ENABLED
        and not args.no_web
        and (args.web or top1 is None or confidence < config.WEB_SEARCH_THRESHOLD)
    )

    # 只打印检索结果（不生成回复）
    if args.no_answer:
        _print_retrieval(retriever, results, args, query)
        return

    # 默认：只打印客服回复；生成失败时回退打印检索结果
    answer = answer_from_chunks(query, [r.chunk for r in results[:args.k]])
    if answer:
        if args.verbose:
            _print_retrieval(retriever, results, args, query)
            print("【客服回复】")
        print(answer)
    else:
        _print_retrieval(retriever, results, args, query)

    # 联网兜底补充
    if need_web:
        web_results = web_search(query)
        if web_results:
            web_answer = generate_answer(query, web_results)
            if args.verbose:
                print(f"\n本地置信度 {confidence:.3f} 低于阈值，触发联网（{config.WEB_SEARCH_SERVICE}）")
            if web_answer:
                print(f"\n{web_answer}")
            else:
                print("\n（联网回答生成失败，仅列出抓取结果）")
                for r in web_results[:3]:
                    print(f"  - {r['title'] or r['url']}")


def _new_session():
    """一份空的推荐会话状态。"""
    return {
        "texts": [],          # 本次推荐对话里用户的原话（供 LLM 理解性格/喜好描述）
        "dims": {"星座": None, "mbti": None, "场景": [], "性格": False},
        "followup_asked": False,  # 是否已追问过一轮
    }


def _try_read_line():
    """读一行补充信息；管道/脚本读不到输入时返回空串（调用方按已有信息直接推荐）。"""
    try:
        return input().strip()
    except (EOFError, KeyboardInterrupt):
        return ""


def _recommend_once(texts, dims, args):
    """调用 LLM 出推荐；成功打印并返回 True，失败返回 False（调用方降级回原 RAG）。"""
    reply = recommend(texts, dims)
    if reply:
        if args.verbose:
            print("【香气推荐】")
        print(reply)
        return True
    return False


def _run_single(query, args, retriever):
    """单问模式：先做推荐前置分流，命中且成功则跳过检索；否则走原 RAG。"""
    if config.RECOMMEND_ENABLED and not args.no_recommend and is_recommend_intent(query):
        texts = [query]
        dims = extract_dims(query)
        if _filled_count(dims) >= 2:
            if _recommend_once(texts, dims, args):
                return
            # 推荐失败 → 降级回 RAG
        else:
            followup = build_followup(dims)
            if followup:
                print(followup)
            extra = _try_read_line()
            if extra:
                texts.append(extra)
                dims = merge_dims(dims, extract_dims(extra))
            # 最多追问一轮：无论是否补齐，都按已有信息直接推荐；失败再降级 RAG
            if _recommend_once(texts, dims, args):
                return
    _run_rag(query, args, retriever)


def _run_interactive(args, retriever):
    """交互会话：欢迎引导 + 循环，会话内累计推荐信息，混问普通问题，输入「退出」结束。"""
    print(_WELCOME + "\n")
    session = _new_session()
    while True:
        try:
            line = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not line:
            continue
        if line.lower() in _EXIT_WORDS:
            print("再见，有需要随时找我～")
            break

        new_dims = extract_dims(line)
        mid = _filled_count(session["dims"]) >= 1  # 是否正处于追问中
        if mid and not _has_info(new_dims):
            # 追问中但用户没在回答（改问别的问题）→ 清空推荐状态，走普通问答
            session = _new_session()
            recommend_related = False
        elif mid:
            recommend_related = True  # 继续累计追问信息
        else:
            recommend_related = is_recommend_intent(line)

        if recommend_related and config.RECOMMEND_ENABLED and not args.no_recommend:
            session["texts"].append(line)
            session["dims"] = merge_dims(session["dims"], new_dims)
            if _filled_count(session["dims"]) >= 2 or session["followup_asked"]:
                # 凑齐，或已追问一轮仍不足 → 直接推荐；失败降级回 RAG
                if not _recommend_once(session["texts"], session["dims"], args):
                    _run_rag(session["texts"][0] or line, args, retriever)
                session = _new_session()
            else:
                followup = build_followup(session["dims"])
                if followup:
                    print(followup)
                session["followup_asked"] = True
        else:
            _run_rag(line, args, retriever)
            session = _new_session()  # 普通问答后清空推荐状态


def main():
    parser = argparse.ArgumentParser(description="香薰客服知识库问答")
    parser.add_argument("query", nargs="?", default=None, help="问题（缺省进入交互会话）")
    parser.add_argument("-k", type=int, default=5, help="返回条数（默认 5）")
    parser.add_argument("--verbose", action="store_true", help="显示完整检索调试信息")
    parser.add_argument("--no-answer", action="store_true", help="不生成回复，仅打印检索结果")
    parser.add_argument("--no-rewrite", action="store_true", help="关闭 query 改写")
    parser.add_argument("--no-rerank", action="store_true", help="关闭 rerank 精排")
    parser.add_argument("--web", action="store_true", help="强制联网搜索")
    parser.add_argument("--no-web", action="store_true", help="关闭联网搜索兜底")
    parser.add_argument("--no-recommend", action="store_true", help="关闭香气推荐前置分流")
    args = parser.parse_args()

    # 检索器只构造一次（构造含读文件 + BM25 重建，约 168ms），交互模式复用
    retriever = HybridRetriever()

    if args.query:
        _run_single(args.query, args, retriever)
    else:
        _run_interactive(args, retriever)


if __name__ == "__main__":
    main()
