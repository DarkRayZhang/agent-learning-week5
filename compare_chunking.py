# -*- coding: utf-8 -*-
"""
Week 5 · 加餐：切块策略 A/B（固定长度 vs 按小节）
=================================================
跑通：python compare_chunking.py

【为什么要做这个】
2026-09-15 W5 收口① 入库 200 块后抽查检索，发现异常：
    Q「空调滤网多久洗一次」→ Top-1 命中的是「日志分级」，完全无关
    Q「周报什么时候交」    → Top-1 只沾到边，没拿到「每周五 17:00 前提交」
怀疑：固定长度切块把「一个小节」从中间切断 → 语义被劈成两半，
      两块都不完整 → 都召不回。本脚本把怀疑变成数据。

【两种策略】
A 固定长度 500 / 重叠 50   → 复用 week5_docs（W5 收口① 已建，不重复花钱）
B 按小节切（## 标题边界） → 每个小节一块，长度 130~230 字符

【判定口径】
命中 = Top-K 的块文本里含该问题的**关键短语**（人工指定的标准答案片段）。
hit@1 = Top-1 就含；hit@3 = 前三里任意一块含。

【这份数据的用处】
- W6：解释「为什么 W6 的 RAG 是能答但不够准」——不全是模型的问题，是数据切法的问题
- W7：加速计划 09-25 排的就是「切块策略 A/B」，本脚本可直接扩成召回率评估的骨架
"""
import os

import chromadb

os.chdir(os.path.dirname(os.path.abspath(__file__)))

from embed_batch import embed_batch  # noqa: E402

PERSIST_DIR = "./chroma_db"
COLLECTION_A = "week5_docs"      # 固定长度 500/50（build_index.py 建的）
COLLECTION_B = "ab_section"      # 按小节切（本脚本建）
DOCS_DIR = "./docs"

# (提问, 标准答案关键短语)  —— 关键短语必须能在语料里原样找到
CASES = [
    ("周报什么时候交",         "每周五 17:00 前提交"),
    ("发版前必须确认什么",     "回滚方案"),
    ("空调滤网多久洗一次",     "空调滤网每月洗一次"),
    ("缓存穿透怎么处理",       "查不到的数据也要缓存一个空值"),
    ("会议纪要多久发出来",     "会议纪要 24 小时内发出"),
    ("跑步一次跑多远",         "5 公里起步"),
    ("护照有效期要求",         "护照有效期必须剩 6 个月以上"),
    ("健康检查接口为什么必须加", "会把还没起来的实例也算进负载"),
]


def chunk_by_section(text):
    """按 markdown 二级标题（## ）切块：一个小节 = 一块。"""
    blocks, cur = [], []
    for line in text.splitlines():
        if line.startswith("## "):
            if cur:
                blocks.append("\n".join(cur).strip())
            cur = [line]
        else:
            cur.append(line)
    if cur:
        blocks.append("\n".join(cur).strip())
    return [b for b in blocks if b]


def build_section_index():
    import glob
    client = chromadb.PersistentClient(path=PERSIST_DIR)
    try:
        client.delete_collection(COLLECTION_B)
    except Exception:
        pass
    col = client.get_or_create_collection(
        COLLECTION_B, metadata={"hnsw:space": "cosine"}
    )

    texts, metas = [], []
    for path in sorted(glob.glob(os.path.join(DOCS_DIR, "*.md"))):
        body = open(path, encoding="utf-8").read()
        for blk in chunk_by_section(body):
            title = blk.splitlines()[0].replace("## ", "").strip()
            texts.append(blk)
            metas.append({"source": os.path.basename(path), "section": title})

    print(f"[B] 按小节切 → {len(texts)} 块（平均 {sum(len(t) for t in texts)//len(texts)} 字符）")
    vecs = embed_batch(texts, batch_size=10, delay=0.12, max_retry=3, verbose=False)
    col.add(ids=[f"s{i:04d}" for i in range(len(texts))],
            documents=texts, metadatas=metas, embeddings=vecs)
    print(f"[B] 入库完成 count = {col.count()}")
    return col


def evaluate(col, tag):
    rows = []
    for q, key in CASES:
        res = col.query(query_embeddings=[embed_batch([q])[0]], n_results=3)
        docs = res["documents"][0]
        hit1 = key in docs[0]
        hit3 = any(key in d for d in docs)
        rows.append((q, key, hit1, hit3, docs[0]))
    n1 = sum(r[2] for r in rows)
    n3 = sum(r[3] for r in rows)
    print(f"\n【策略 {tag}】hit@1 = {n1}/{len(rows)}   hit@3 = {n3}/{len(rows)}")
    for q, key, hit1, hit3, top1 in rows:
        mark = "✅" if hit1 else ("🔶" if hit3 else "❌")
        print(f"  {mark} {q}")
        print(f"      期望含：{key}")
        print(f"      Top-1 ：{top1[:64].replace(chr(10), ' / ')}...")
    return n1, n3, rows


def main():
    client = chromadb.PersistentClient(path=PERSIST_DIR)
    col_a = client.get_collection(COLLECTION_A)
    print(f"[A] 复用 {COLLECTION_A}，count = {col_a.count()}（固定长度 500/50）")
    col_b = build_section_index()

    print("\n" + "=" * 66)
    print("切块策略 A/B 对照")
    print("=" * 66)
    a1, a3, rows_a = evaluate(col_a, "A 固定长度 500/50")
    b1, b3, rows_b = evaluate(col_b, "B 按小节切")

    lines = ["Week 5 · 切块策略 A/B 对照结果", "=" * 40,
             f"A 固定长度 chunk=500/overlap=50 : hit@1 {a1}/{len(CASES)}  hit@3 {a3}/{len(CASES)}",
             f"B 按 markdown 小节切           : hit@1 {b1}/{len(CASES)}  hit@3 {b3}/{len(CASES)}",
             ""]
    for (q, key, h1a, _, _), (_, _, h1b, _, _) in zip(rows_a, rows_b):
        lines.append(f"{q:26s} A={'✅' if h1a else '❌'}  B={'✅' if h1b else '❌'}   期望含「{key}」")
    with open("chunk_strategy_ab_result.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print("\n→ 已落盘 chunk_strategy_ab_result.txt")
    print(f"\n结论：A hit@1 {a1}/{len(CASES)}  vs  B hit@1 {b1}/{len(CASES)}")


if __name__ == "__main__":
    main()
