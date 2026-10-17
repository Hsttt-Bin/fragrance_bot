"""构建知识库：解析 Markdown → 切块 → AGICTO embedding → FAISS 落盘。

用法：python build_kb.py [--force]
"""
import argparse

from knowledge_base import config
from knowledge_base.chunker import parse_markdown
from knowledge_base.embedder import embed_texts
from knowledge_base.store import save


def main():
    parser = argparse.ArgumentParser(description="构建香薰客服知识库")
    parser.add_argument("--force", action="store_true", help="已存在时强制重建")
    args = parser.parse_args()

    if (config.KB_DATA_DIR / "index.faiss").exists() and not args.force:
        print(f"知识库已存在（{config.KB_DATA_DIR}），如需重建请加 --force")
        return

    print(f"[1/3] 解析文档：{config.SOURCE_DOC}")
    chunks = parse_markdown(str(config.SOURCE_DOC))
    print(f"    共切出 {len(chunks)} 个知识块")

    print(f"[2/3] 调用 embedding 模型：{config.EMBEDDING_MODEL}（via {config.AGICTO_BASE_URL}）")
    vectors = embed_texts([c.embed_text() for c in chunks], show_progress=True)
    print(f"    向量维度：{vectors.shape[1]}")

    print("[3/3] 写入 FAISS 索引与元数据…")
    meta = save(chunks, vectors)
    print(f"完成 ✓ {meta['n_chunks']} 块 / 维度 {meta['dim']} / 构建时间 {meta['built_at']}")
    print(f"产物目录：{config.KB_DATA_DIR}")


if __name__ == "__main__":
    main()
