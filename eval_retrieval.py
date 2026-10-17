"""检索测试用例评测：50 条客服提问 → 记录 top-1 chunk 及各项分数，保存 CSV / JSON。

用法：python eval_retrieval.py
产物：检索测试用例结果.csv、检索测试用例结果.json
"""
import csv
import json
from datetime import datetime

from knowledge_base.retriever import HybridRetriever

# 50 条测试用例（覆盖使用说明 / 商品信息 / 香型 / 成分安全 / 物流售后）
TEST_CASES = [
    "蜡烛烧出来一个坑怎么办",
    "第一次点蜡烛要烧多久",
    "点蜡烛之前烛芯要剪多短",
    "蜡烛冒黑烟是什么原因",
    "蜡烛点不着怎么办",
    "怎么正确熄灭蜡烛",
    "蜡烛火焰一直晃是怎么回事",
    "蜡烛表面有白霜正常吗",
    "蜡烛和杯壁分开了还能用吗",
    "蜡烛香味越来越淡了怎么办",
    "单次燃烧不能超过多久",
    "蜡烛熄灭后多久能再点",
    "蜡烛烧到剩多少就不能用了",
    "蜡烛要离窗帘多远才安全",
    "蜡烛平时怎么存放",
    "造型蜡烛和容器蜡烛有什么区别",
    "造型蜡烛多少钱",
    "试香小杯蜡多少钱",
    "陶瓷容器蜡烛多少克",
    "玩具蜡烛价格多少",
    "装饰蜡烛多少钱",
    "你们一共有多少种香型",
    "99元档位有哪些香型",
    "檀木香是什么调性",
    "乌木适合什么场景",
    "送女朋友推荐什么香型",
    "卧室适合什么香型",
    "有什么果香调的蜡烛",
    "抹茶青柚多少钱",
    "椰子糯米是什么味道",
    "木质调都有哪些",
    "蜡烛是用什么蜡做的",
    "香精是不是天然的",
    "棉芯含铅吗",
    "大豆蜡燃烧会有黑烟吗",
    "蜡烛有没有检测报告",
    "孕妇能用香薰蜡烛吗",
    "家里有婴儿能点蜡烛吗",
    "养猫能用什么香型",
    "养狗家庭点蜡烛要注意什么",
    "过敏体质能用香薰蜡烛吗",
    "蜡烛能吃吗",
    "多久能发货",
    "默认发什么快递",
    "蜡烛可以退换吗",
    "收到货蜡烛破了怎么办",
    "蜡烛保质期多久",
    "能开发票吗",
    "蜡烛烧完的罐子能回收吗",
    "续蜡怎么收费",
]

FIELDS = ["序号", "查询", "chunk_id", "分类", "标题", "精排分", "综合分", "向量分", "关键词分", "备注"]


def main():
    retriever = HybridRetriever()
    rows = []
    for idx, q in enumerate(TEST_CASES, 1):
        try:
            results = retriever.search(q, k=1)
            if not results:
                rows.append({"序号": idx, "查询": q, "备注": "无结果"})
                print(f"[{idx:2d}/{len(TEST_CASES)}] 无结果：{q}")
                continue
            r = results[0]
            rows.append({
                "序号": idx,
                "查询": q,
                "chunk_id": r.chunk["id"],
                "分类": r.chunk["category"],
                "标题": r.chunk["title"],
                "精排分": round(r.rerank_score, 4),
                "综合分": round(r.final_score, 4),
                "向量分": round(r.vector_score, 4),
                "关键词分": round(r.keyword_score, 4),
                "备注": "",
            })
            print(f"[{idx:2d}/{len(TEST_CASES)}] chunk#{r.chunk['id']:>2d} {r.chunk['title'][:18]} ← {q}")
        except Exception as e:
            rows.append({"序号": idx, "查询": q, "备注": f"错误：{e}"})
            print(f"[{idx:2d}/{len(TEST_CASES)}] 错误：{q} → {e}")

    csv_path = "检索测试用例结果.csv"
    with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)

    json_path = "检索测试用例结果.json"
    payload = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "kb": retriever.kb.meta,
        "total": len(TEST_CASES),
        "results": rows,
    }
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    print(f"\n完成：{len(rows)} 条用例，已保存到 {csv_path} 和 {json_path}")


if __name__ == "__main__":
    main()
