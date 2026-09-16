# -*- coding: utf-8 -*-
"""
Week 5 收口② · 语义检索小程序（完整版）
=======================================
职责**单一**：只做「在线查询」——读现成索引 → Top-3（原文 + metadata + 相似度）→ 过低则诚实拒答。

【两阶段分工】（09-15 收口① 确立，本文件是阶段 B）
    阶段 A · 离线入库   build_index.py : docs/ → chunk_text() 切块 → embedding → chroma_db/
    阶段 B · 在线查询   本文件          :  query → embedding → 读库 → Top-3 → 拒答判定

【为什么本文件不切块、不建索引】
切块是**构建产物**的生成动作，属于入库阶段。若检索端自己兜底建库，一旦 chroma_db 丢失，
它会静默按另一套策略（段落切）建出一个新库 → 同一份 docs/ 出现两套切块策略，
检索结果忽好忽坏且原因难查。**数据源必须唯一**：库不在 → 报错并提示先跑 build_index.py。
（旧脚手架的 chunk_docs() + build_index() 已删除，正是这个原因。）

【⚠️ 本文件最容易踩的一个坑：Chroma 的 distances 是「距离」不是「相似度」】
collection 的 hnsw:space = cosine 时，distance = 1 - cosine_similarity → **越小越相似**。
本项目实测（2026-09-16）：
    库内问题「发版前必须确认什么」  distance ≈ 0.289  →  相似度 0.711
    库外问题「量子计算…」           distance ≈ 0.703  →  相似度 0.297
所以拒答判据必须是 `if distance > REJECT_DISTANCE: 拒答`。
**反着写会把最相关的全部拒掉、把不相关的全部放行**——诚信事故与可用性事故正好颠倒。
本文件在 retrieve() 出口统一把 distance 换算成 similarity 再往上层传，避免这个坑漏给调用方。

【拒答阈值】
REJECT_DISTANCE = 0.55（≈ 相似度 0.45）是本周的**经验起点**，落在实测分离度（0.29 / 0.70）中间。
它**不是标定结果**——W6 要用 30 条用例的误拒/漏放分布来标定：
    阈值偏低 → 漏放 → 库里没有也编 → 诚信事故
    阈值偏高 → 误拒 → 能答却说不会 → 可用性事故
"""
import os
import sys

import chromadb
from dotenv import load_dotenv
from openai import OpenAI

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# 显式指路径，而不是 os.chdir()——本模块被 persist_check.py import
# （`from retrieval_app import embed, EMBEDDING_MODEL`），import 时改 cwd 会污染调用方。
load_dotenv(os.path.join(BASE_DIR, ".env"))

COLLECTION = "week5_docs"
PERSIST_DIR = os.path.join(BASE_DIR, "chroma_db")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-v4")

# 拒答阈值（距离口径）。0.55 ≈ 相似度 0.45，取在实测分离度 0.29 / 0.70 中间。
REJECT_DISTANCE = 0.55
SIM_FLOOR = 1.0 - REJECT_DISTANCE      # 对外展示用的相似度阈值

_client = OpenAI(
    api_key=os.getenv("EMBEDDING_API_KEY"),
    base_url=os.getenv("EMBEDDING_BASE_URL"),
)


def embed(text: str):
    """向量化。

    沿用原名，不要改：persist_check.py 有 `from retrieval_app import embed, EMBEDDING_MODEL`。
    查询侧每次检索只调 1 次（文档侧 0 次——入库时已算好存进去了）。
    """
    resp = _client.embeddings.create(model=EMBEDDING_MODEL, input=[text])
    return resp.data[0].embedding


def load_index():
    """打开已建好的索引。

    ⚠️ 用 get_collection 而不是 get_or_create_collection：
       前者拿不到就抛异常（真检验）；后者会「帮我」建一个空库——
       假通过、而且静默换掉切块策略。同款注释见 persist_check.py:110。

    ⚠️ 必须先判「目录是否存在」再构造 PersistentClient —— 09-16 验收时踩到：
       PersistentClient(path=...) 本身**会创建目录**，于是「报错」这个动作留下了副作用
       （一个 188KB 的空 chroma_db/），真库要恢复回来时反被这个空目录挡在门外。
       → **报错也应当是只读的**。所以先 os.path.isdir 拦一道。
    """
    if not os.path.isdir(PERSIST_DIR):
        raise SystemExit(
            f"[错误] 索引目录不存在：{PERSIST_DIR}\n"
            f"       本程序只读库、不建库（数据源唯一）→ 请先跑：\n"
            f"           python build_index.py"
        )

    chroma = chromadb.PersistentClient(path=PERSIST_DIR)
    try:
        col = chroma.get_collection(COLLECTION)
    except Exception as e:
        raise SystemExit(
            f"[错误] 索引目录里找不到 collection「{COLLECTION}」"
            f"（目录在，但里面是别的库，或索引没建完）\n"
            f"       请跑：python build_index.py\n"
            f"       原始错误：{e}"
        )
    if col.count() == 0:
        raise SystemExit(
            f"[错误] collection「{COLLECTION}」是空的 → 请先跑：python build_index.py"
        )
    return col


def retrieve(col, query: str, top_k: int = 3):
    """检索 Top-K → [(原文, metadata, 相似度)]，按相似度降序。

    这里是「距离 → 相似度」唯一换算点：Chroma 的 distances 是距离（越小越像），
    上层一律只见 similarity（越大越像），别把这个坑漏出去。
    """
    res = col.query(query_embeddings=[embed(query)], n_results=top_k)
    docs = res["documents"][0]
    metas = res["metadatas"][0]
    dists = res["distances"][0]
    return [(doc, meta, 1.0 - dist) for doc, meta, dist in zip(docs, metas, dists)]


def section_of(text: str) -> str:
    """从块文本里抽出 markdown 小节标题，用于人眼判断「命中在哪一小节」。

    上一周 A/B 实测发现：块大时常把 2 个以上小节混进同一块（A 方案 70% 的块如此），
    所以命中率本身看不出上下文纯度 —— 把命中的小节打出来，纯度一眼可见。
    """
    titles = [ln.lstrip("#").strip() for ln in text.splitlines() if ln.startswith("## ")]
    return " / ".join(titles) if titles else "(无小节标题)"


def decide(hits) -> str:
    """**拒答判据的唯一实现**：返回 '命中' / '拒答' / '无匹配'。

    ⚠️ 只此一处。早先 search_and_print() 与 selftest() 各写了一遍 `sim < SIM_FLOOR`,
       结果「自测」只验了数值、没验程序行为 —— 把 search_and_print() 的拒答分支删掉，
       selftest 依然报 2/2（假通过）。
       → 与「数据源唯一」同一条原则：**判据也要唯一**，否则两处会悄悄漂移。
    """
    if not hits:
        return "无匹配"
    return "拒答" if hits[0][2] < SIM_FLOOR else "命中"


def print_hits(query: str, hits, brief=False):
    """打印 Top-K：原文 + metadata + 相似度（验收要求「含原文与 metadata」）。"""
    if not hits:
        print(f"  无匹配：检索结果为 0 条（诚实返回，不硬凑）")
        return
    for i, (doc, meta, sim) in enumerate(hits, 1):
        low = "  ⚠️ 低于阈值" if sim < SIM_FLOOR else ""
        print(f"  [{i}] 相似度 {sim:.4f} | {meta.get('source', '?')} "
              f"第 {meta.get('chunk_index', '?')} 块 / {meta.get('n_chars', '?')} 字符 "
              f"| 小节：{section_of(doc)}{low}")
        body = doc if not brief else doc[:120] + ("…" if len(doc) > 120 else "")
        for ln in body.splitlines():
            print(f"      {ln}")
        print()


def search_and_print(col, query: str, top_k: int = 3, brief=False) -> str:
    """一次完整查询：检索 → 展示 → 拒答判定。返回 '命中' / '拒答' / '无匹配'。"""
    print(f"\n查> {query}")
    hits = retrieve(col, query, top_k=top_k)
    verdict = decide(hits)              # ← 唯一判据，与 selftest 共用同一个函数

    if verdict == "无匹配":
        print("  无匹配：检索结果为 0 条（诚实返回，不硬凑）")
        return verdict

    print(f"  最高相似度 {hits[0][2]:.4f}（拒答阈值 {SIM_FLOOR:.2f}）\n")
    print_hits(query, hits, brief=brief)

    if verdict == "拒答":
        print(f"  ⛔ 拒答：库内最高相似度仅 {hits[0][2]:.4f} < 阈值 {SIM_FLOOR:.2f}"
              f" → 库里没有相关内容，不拿训练知识硬答（这就是 W6 要压的幻觉）。")
    return verdict


# ── 验收自测 ────────────────────────────────────────────────────────────
# 验收 2：同一主题换 5 种说法 → Top-1 是否稳定落在「发布值班」主题
SAME_TOPIC_QUERIES = [
    "发版前必须确认什么",           # 最直白
    "上线之前要做哪些检查",
    "回滚方案要满足什么条件",
    "怎么保证发布不出事故",
    "发布当天要注意些什么",         # 口语化、绕弯
]

# 验收 3：语料故意没写的话题（见 make_docs.py 第 15 行）→ 正确行为是拒答
OUT_OF_SCOPE_QUERIES = [
    "量子计算的量子比特怎么实现",
    "宠物猫得了猫瘟怎么治",
]

# 「发布值班」主题的 6 个小节（make_docs.py ENTRIES["发布值班"]）
PUBLISH_SECTIONS = {"发版窗口", "灰度策略", "回滚预案", "变更评审", "监控告警", "事故复盘"}


def selftest(col):
    """自动跑验收 2 + 验收 3，结果如实打印（不美化）。"""
    print("\n" + "=" * 74)
    print("验收 2：同一主题换 5 种说法 → Top-1 是否稳定落在「发布值班」主题")
    print("=" * 74)
    hit_n = 0
    for q in SAME_TOPIC_QUERIES:
        doc, meta, sim = retrieve(col, q, top_k=1)[0]
        secs = section_of(doc).split(" / ")
        ok = any(s in PUBLISH_SECTIONS for s in secs)
        hit_n += ok
        print(f"  {'✅' if ok else '❌'} {q:<14s} 相似度 {sim:.4f}  "
              f"{meta.get('source', '?')}  小节：{section_of(doc)}")
    print(f"\n  → Top-1 落在「发布值班」主题：{hit_n}/{len(SAME_TOPIC_QUERIES)}")

    print("\n" + "=" * 74)
    print("验收 3：库外话题 → 是否诚实拒答（不幻觉）")
    print("=" * 74)
    rej_n = 0
    for q in OUT_OF_SCOPE_QUERIES:
        hits = retrieve(col, q, top_k=1)
        sim = hits[0][2]
        rejected = decide(hits) == "拒答"     # ← 走程序真正的判据，不是自己重算
        rej_n += rejected
        print(f"  {'✅' if rejected else '❌'} {q:<14s} 相似度 {sim:.4f}  "
              f"→ {'拒答（诚实）' if rejected else '未拒答 ⚠️ 会拿训练知识硬答'}")
    print(f"\n  → 正确拒答：{rej_n}/{len(OUT_OF_SCOPE_QUERIES)}")
    print(f"\n  拒答阈值 {SIM_FLOOR:.2f}（距离口径 {REJECT_DISTANCE}）"
          f"｜ ⚠️ 经验值，W6 用 30 条用例标定")
    print("=" * 74)


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    col = load_index()
    print(f"语义检索小程序 ｜ collection「{COLLECTION}」{col.count()} 块 ｜ "
          f"模型 {EMBEDDING_MODEL}")

    if argv and argv[0] == "--selftest":
        selftest(col)
        return
    if argv:
        for q in argv:
            search_and_print(col, q)
        return

    print("输入一句话检索 Top-3，exit 退出（--brief 只看前 120 字符）")
    brief = False
    while True:
        try:
            q = input("\n查> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if q.lower() in {"exit", "q"}:
            break
        if q == "--brief":
            brief = not brief
            print(f"  brief 模式 = {brief}")
            continue
        if q:
            search_and_print(col, q, brief=brief)


if __name__ == "__main__":
    main()
