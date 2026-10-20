"""检索质量闭环评测：读检索评测集.json，跑检索，按 entry_id 自动判定命中率。

用法：python eval_retrieval.py [-k 5] [--no-rewrite] [--no-rerank]

产物：
  - 检索评测报告.csv     逐条明细（问题/期望ID/命中top-k的entry_id/各项分数/是否命中）
  - 检索评测报告.json    汇总指标（Top1/Top5 命中率、MRR，按意图分类）

命中判定：
  - 普通问题（期望ID 非空）：top-k 结果里出现任一期望 entry_id 即判命中。
  - 范围外问题（期望ID 为空）：top-1 置信度低于 WEB_SEARCH_THRESHOLD 即判「正确拒答」。
"""
import argparse
import csv
import json
from datetime import datetime

from knowledge_base import config
from knowledge_base.retriever import HybridRetriever

EVAL_FILE = "检索评测集.json"


def load_cases(path: str) -> list:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return data["测试问题集"]


def judge_hit(topk_ids: list, expected: list) -> bool:
    """普通问题命中判定：top-k 结果的 entry_id 与期望 ID 有交集即命中。"""
    if not expected:
        return False
    return any(eid in topk_ids for eid in expected)


def main():
    parser = argparse.ArgumentParser(description="检索质量闭环评测")
    parser.add_argument("-k", type=int, default=5, help="判定命中的 top-k（默认 5）")
    parser.add_argument("--no-rewrite", action="store_true", help="关闭 query 改写")
    parser.add_argument("--no-rerank", action="store_true", help="关闭 rerank 精排")
    args = parser.parse_args()

    retriever = HybridRetriever()
    cases = load_cases(EVAL_FILE)

    rows = []
    # 分类统计：每类意图累计 hit / total / mrr 之和 / 拒答正确数
    stats = {}  # 意图 -> {"total", "hit1", "hitk", "mrr_sum", "reject_ok", "reject_total"}

    for case in cases:
        q = case["问题"]
        expected = case["期望ID"]
        intent = case["意图"]

        # 跑检索，取 top-k
        results = retriever.search(
            q, k=args.k, rewrite=not args.no_rewrite, rerank=not args.no_rerank
        )
        topk_ids = [r.chunk.get("entry_id", "") for r in results if r.chunk.get("entry_id")]

        # 置信度（用于范围外拒答判定）：精排分优先，否则向量分
        top1 = results[0] if results else None
        if top1 is None:
            confidence = 0.0
        elif retriever.rerank_scores:
            confidence = top1.rerank_score
        else:
            confidence = top1.vector_score

        s = stats.setdefault(intent, {"total": 0, "hit1": 0, "hitk": 0, "mrr_sum": 0.0, "reject_ok": 0, "reject_total": 0})
        s["total"] += 1

        if expected:
            # 普通问题：算 Top1/Top5 命中 + MRR
            hit1 = topk_ids[:1] and (topk_ids[0] in expected)
            hitk = judge_hit(topk_ids, expected)
            # MRR：期望 ID 在 top-k 里的最早命中位置（rank 从 1 开始）
            rr = 0.0
            for rank, eid in enumerate(topk_ids, 1):
                if eid in expected:
                    rr = 1.0 / rank
                    break
            s["hit1"] += int(hit1)
            s["hitk"] += int(hitk)
            s["mrr_sum"] += rr
            rows.append({
                "ID": case["id"],
                "意图": intent,
                "问题": q,
                "期望ID": "、".join(expected),
                "命中top-k的ID": "、".join(topk_ids[:args.k]),
                "top1ID": topk_ids[0] if topk_ids else "",
                "是否命中(top{})".format(args.k): "命中" if hitk else "未命中",
                "是否Top1": "是" if hit1 else "否",
                "精排分": round(top1.rerank_score, 4) if top1 else 0.0,
                "向量分": round(top1.vector_score, 4) if top1 else 0.0,
            })
        else:
            # 范围外问题（期望ID 空）：正确行为是低分拒答/转联网
            rejected = confidence < config.WEB_SEARCH_THRESHOLD
            s["reject_total"] += 1
            s["reject_ok"] += int(rejected)
            rows.append({
                "ID": case["id"],
                "意图": intent,
                "问题": q,
                "期望ID": "（无，应拒答）",
                "命中top-k的ID": "、".join(topk_ids[:args.k]),
                "top1ID": topk_ids[0] if topk_ids else "",
                "是否命中(top{})".format(args.k): "正确拒答" if rejected else "误召回",
                "是否Top1": "-",
                "精排分": round(top1.rerank_score, 4) if top1 else 0.0,
                "向量分": round(top1.vector_score, 4) if top1 else 0.0,
            })

        print(f"[{case['id']}] {q[:24]:<24} → {topk_ids[:3]}")

    # 汇总
    summary = {"generated_at": datetime.now().isoformat(timespec="seconds"), "k": args.k, "kb": retriever.kb.meta, "total": len(cases), "by_intent": {}}
    overall = {"total": 0, "hit1": 0, "hitk": 0, "mrr_sum": 0.0, "reject_ok": 0, "reject_total": 0}
    for intent, s in sorted(stats.items()):
        summary["by_intent"][intent] = {
            "总数": s["total"],
            "Top1命中数": s["hit1"],
            "Top{}命中数".format(args.k): s["hitk"],
            "Top1命中率": round(s["hit1"] / s["total"], 4) if s["total"] else 0.0,
            "Top{}命中率".format(args.k): round(s["hitk"] / s["total"], 4) if s["total"] else 0.0,
            "MRR": round(s["mrr_sum"] / s["total"], 4) if s["total"] else 0.0,
            "拒答正确数": s["reject_ok"],
            "拒答总数": s["reject_total"],
        }
        overall["total"] += s["total"]
        overall["hit1"] += s["hit1"]
        overall["hitk"] += s["hitk"]
        overall["mrr_sum"] += s["mrr_sum"]
        overall["reject_ok"] += s["reject_ok"]
        overall["reject_total"] += s["reject_total"]

    # 普通问题（期望ID非空）的净指标
    normal_total = overall["total"] - overall["reject_total"]
    summary["整体"] = {
        "普通问题数": normal_total,
        "范围外问题数": overall["reject_total"],
        "Top1命中率": round(overall["hit1"] / normal_total, 4) if normal_total else 0.0,
        "Top{}命中率".format(args.k): round(overall["hitk"] / normal_total, 4) if normal_total else 0.0,
        "MRR": round(overall["mrr_sum"] / normal_total, 4) if normal_total else 0.0,
        "范围外拒答正确率": round(overall["reject_ok"] / overall["reject_total"], 4) if overall["reject_total"] else 0.0,
    }

    # 写 CSV
    csv_path = "检索评测报告.csv"
    fields = ["ID", "意图", "问题", "期望ID", "命中top-k的ID", "top1ID", "是否命中(top{})".format(args.k), "是否Top1", "精排分", "向量分"]
    with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)

    # 写 JSON
    json_path = "检索评测报告.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump({"summary": summary, "results": rows}, f, ensure_ascii=False, indent=2)

    # 打印汇总
    print("\n" + "=" * 56)
    print("检索质量评测汇总（top-{} 判定）".format(args.k))
    print("=" * 56)
    print(f"知识库：{retriever.kb.meta['n_chunks']} 块 / 模型 {retriever.kb.meta['model']}")
    print(f"测试用例：{len(cases)} 条（普通 {normal_total} 条 + 范围外 {overall['reject_total']} 条）")
    print()
    for intent in sorted(stats.keys()):
        s = stats[intent]
        if intent == "范围外问题":
            print(f"  [{intent}] 拒答正确率 {s['reject_ok']}/{s['reject_total']} = {s['reject_ok']/s['reject_total']:.1%}")
        else:
            print(f"  [{intent}] Top1 {s['hit1']}/{s['total']} = {s['hit1']/s['total']:.1%} | Top{args.k} {s['hitk']}/{s['total']} = {s['hitk']/s['total']:.1%} | MRR {s['mrr_sum']/s['total']:.3f}")
    print()
    print(f"  【整体普通问题】Top1 {overall['hit1']}/{normal_total} = {overall['hit1']/normal_total:.1%} | Top{args.k} {overall['hitk']}/{normal_total} = {overall['hitk']/normal_total:.1%} | MRR {overall['mrr_sum']/normal_total:.3f}")
    if overall["reject_total"]:
        print(f"  【范围外拒答】正确 {overall['reject_ok']}/{overall['reject_total']} = {overall['reject_ok']/overall['reject_total']:.1%}")
    print(f"\n产物：{csv_path}、{json_path}")


if __name__ == "__main__":
    main()
