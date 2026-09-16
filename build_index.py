# -*- coding: utf-8 -*-
"""
Week 5 · 收口①：100 篇文档 → 切块 → 批量 embedding → 入库 Chroma
================================================================
跑通（在 week5/ 目录下）：
    python make_docs.py      # ① 生成 100 篇语料
    python build_index.py    # ② 切块 + 向量化 + 入库 + 统计

对应加速计划 09-15「W5 收口①」的四件事：
    ① 生成 100 篇模拟文档                    → make_docs.py
    ② 写切块函数（chunk 500 / overlap 50）    → chunk_text()
    ③ batch embedding 入库                   → build()
    ④ 统计块数                                → 控制台报告 + index_build_report.txt

【为什么固定长度切块，而不是按段落切】
段落长度完全不可控（20 字到 800 字都有）→ 向量语义密度不均、召回不可预期。
固定长度 + 重叠是**可控基线**；W7 再上「按标题 / 语义切块」做 A/B 对比 ——
**没有基线就没有"优化了多少"**。

【关于重叠】切点会正好落在句子中间。重叠 50 字符让被切断的语义在两块里各出现
一次，避免关键信息正好掉进缝里、两块都检索不到。

【设计取舍（可面试讲）】
- 块小 → 语义集中、精度高，但上下文碎片化、可能丢前提
- 块大 → 上下文完整，但语义被稀释、向量变"平均"，召回变差
- 500/50 是中文备忘类短文档的经验起点，不是最优解，最终要靠 W7 的召回率评估定
"""
import glob
import json
import os
import time
from collections import Counter

import chromadb

# 从任何工作目录运行都能找到 docs/ 与 .env
os.chdir(os.path.dirname(os.path.abspath(__file__)))

from embed_batch import EMBEDDING_MODEL, embed_batch  # 复用批量逻辑，不写第二套

COLLECTION = "week5_docs"
PERSIST_DIR = "./chroma_db"
DOCS_DIR = "./docs"
CHUNK_SIZE = 500      # 每块最大字符数
CHUNK_OVERLAP = 50    # 相邻块重叠字符数
EMBED_BATCH = 10      # 端点单次上限（超了会报错）
EMBED_DELAY = 0.12    # 批间隔限速，防 429


def chunk_text(text, size=CHUNK_SIZE, overlap=CHUNK_OVERLAP):
    """固定长度切块（带重叠）→ 返回切块列表。

    步长 step = size - overlap，所以相邻两块共享 overlap 个字符。
    最后一块不足 size 时按剩余长度截断（不足 overlap 也算一块，不做丢弃）。
    """
    if not 0 <= overlap < size:
        raise ValueError("overlap 必须满足 0 <= overlap < size")
    step = size - overlap
    chunks, start = [], 0
    while start < len(text):
        piece = text[start:start + size]
        if piece.strip():                      # 纯空白块不入库（会污染向量空间）
            chunks.append(piece)
        if start + size >= len(text):          # 已经覆盖到文末
            break
        start += step
    return chunks


def collect_chunks():
    """遍历 docs/*.md → 切块并附 metadata，返回 (文档路径列表, [(文本, metadata)])。"""
    paths = sorted(glob.glob(os.path.join(DOCS_DIR, "*.md")))
    chunks = []
    for path in paths:
        text = open(path, encoding="utf-8").read()
        for i, piece in enumerate(chunk_text(text)):
            chunks.append((piece, {
                "source": os.path.basename(path),   # 溯源：这条来自哪篇
                "chunk_index": i,                   # 篇内第几块（回显时可给段落定位）
                "n_chars": len(piece),
            }))
    return paths, chunks


def build(reset=True):
    paths, chunks = collect_chunks()
    if not paths:
        print("docs/ 是空的 → 先跑 python make_docs.py")
        return None

    texts = [c[0] for c in chunks]
    metas = [c[1] for c in chunks]
    lens = [m["n_chars"] for m in metas]
    per_doc = Counter(m["source"] for m in metas)

    print("=" * 60)
    print(f"① 语料：{len(paths)} 篇文档")
    print(f"② 切块：chunk={CHUNK_SIZE} / overlap={CHUNK_OVERLAP} → {len(chunks)} 块")
    print(f"   块长  最短 {min(lens)} / 平均 {sum(lens) // len(lens)} / 最长 {max(lens)} 字符")
    print(f"   每篇  最少 {min(per_doc.values())} / 平均 {len(chunks) / len(paths):.2f} / "
          f"最多 {max(per_doc.values())} 块")
    print(f"③ 向量化：{len(texts)} 条 → 单批 {EMBED_BATCH} 条 → 需 "
          f"{(len(texts) + EMBED_BATCH - 1) // EMBED_BATCH} 次 API 调用")
    print("=" * 60)

    chroma = chromadb.PersistentClient(path=PERSIST_DIR)
    if reset:
        try:
            chroma.delete_collection(COLLECTION)
            print(f"[reset] 旧 collection「{COLLECTION}」已删除 → 幂等重建")
        except Exception:
            print(f"[reset] collection「{COLLECTION}」尚不存在 → 直接新建")

    # ⚠️ 必须在建集合时声明 cosine：Chroma 默认 l2，与本周「用余弦」的结论冲突；
    #    space 绑在 collection 元数据上，**建完改不了**（persist_check 已实测过）。
    col = chroma.get_or_create_collection(
        COLLECTION, metadata={"hnsw:space": "cosine"}
    )

    print("[embed] 向量化中（分批 + 失败重试 + 限速）...")
    t0 = time.time()
    vectors = embed_batch(texts, batch_size=EMBED_BATCH,
                          delay=EMBED_DELAY, max_retry=3, verbose=True)
    dt = time.time() - t0
    assert all(v is not None for v in vectors), "有位置没被回填 → index 对齐有问题"
    dim = len(vectors[0])
    print(f"[embed] 完成：{len(vectors)} 个向量，维度 {dim}，耗时 {dt:.1f}s")

    col.add(
        ids=[f"c{i:04d}" for i in range(len(texts))],
        documents=texts,
        metadatas=metas,
        embeddings=vectors,
    )
    count = col.count()
    print(f"[add]   入库完成：collection count = {count}")
    assert count == len(texts), f"入库数 {count} ≠ 切块数 {len(texts)}"

    report = {
        "built_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "collection": COLLECTION,
        "hnsw_space": "cosine",
        "docs": len(paths),
        "chunks": len(chunks),
        "chunk_size": CHUNK_SIZE,
        "chunk_overlap": CHUNK_OVERLAP,
        "chunk_len_min": min(lens),
        "chunk_len_avg": sum(lens) // len(lens),
        "chunk_len_max": max(lens),
        "chunks_per_doc_avg": round(len(chunks) / len(paths), 2),
        "embedding_model": EMBEDDING_MODEL,
        "embedding_dim": dim,
        "api_calls": (len(texts) + EMBED_BATCH - 1) // EMBED_BATCH,
        "embed_seconds": round(dt, 1),
    }
    with open("index_build_report.txt", "w", encoding="utf-8") as f:
        f.write("Week 5 · 索引构建报告（W5 收口①）\n")
        f.write("=" * 44 + "\n")
        for k, v in report.items():
            f.write(f"{k:22s} = {v}\n")
    print(f"[report] 已落盘 index_build_report.txt")
    print("=" * 60)
    print("④ 块数统计：" + json.dumps(
        {k: report[k] for k in ("docs", "chunks", "chunk_len_avg", "chunks_per_doc_avg", "embedding_dim")},
        ensure_ascii=False))
    return col


if __name__ == "__main__":
    build()
