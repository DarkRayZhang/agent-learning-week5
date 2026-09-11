"""
Week 5 · 周三任务收尾 —— Chroma 持久化验证（persist check）
==========================================================
周三「做什么」要求：建集合 → 插入文档（带 metadata）→ 查询 → **确认重启后数据还在**。

用法（两个独立进程，中间的进程退出就是"重启"）：
    python persist_check.py phase1     # 进程 A：建集合 + 插入 + 查询
    python persist_check.py phase2     # 进程 B：重新打开（只读）→ 验证数据还在 → 再查询

结果同时写到 persist_check_result.txt（UTF-8），便于回看/贴进 notes.md。
"""
import sys, os, io, json

# 保证无论从哪个目录调用，都在 week5/ 下运行（.env 与 ./chroma_db 都相对此处）
os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.getcwd())

import chromadb
from retrieval_app import embed, EMBEDDING_MODEL

PERSIST_DIR = "./chroma_db"
COLLECTION = "week5_persist_check"
RESULT_FILE = "persist_check_result.txt"

SAMPLES = [
    ("提醒我明天9点开会",            {"source": "schedule.md", "kind": "reminder"}),
    ("牛奶和鸡蛋要买",              {"source": "shopping.md", "kind": "todo"}),
    ("docker 部署要加健康检查",      {"source": "coding.md",   "kind": "note"}),
    ("跑步要坚持每周三次",           {"source": "health.md",   "kind": "habit"}),
    ("去成都的机票比较便宜",          {"source": "travel.md",   "kind": "note"}),
]
QUERY_A = "我想买点牛奶和鸡蛋"
QUERY_B = "部署的时候要注意什么"

LOG = []


def log(s=""):
    LOG.append(str(s))
    print(s)


def write_result():
    with open(RESULT_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(LOG))


def _new_client():
    # 关键：PersistentClient(path=...) 每次写自动落盘（不是老的 Client()+persist() 手动模式）
    return chromadb.PersistentClient(path=PERSIST_DIR)


def _show_col(path):
    """打印 collection 的距离度量配置——确认到底是 cosine 还是默认 l2。"""
    try:
        c = _new_client().get_collection(path)
        log(f"  collection metadata = {c.metadata}")
        log(f"  → hnsw:space = {c.metadata.get('hnsw:space') if c.metadata else '(未设置，Chroma 默认 l2)'}")
    except Exception as ex:
        log(f"  (读取 collection metadata 失败: {ex!r})")


def phase1():
    log("=" * 56)
    log("PHASE 1 · 进程 A：建集合 → 插入 5 条（带 metadata）→ 查询")
    log("=" * 56)
    log(f"embedding 模型  = {EMBEDDING_MODEL}")
    log(f"persist 目录    = {os.path.abspath(PERSIST_DIR)}")
    log(f"chroma 版本     = {chromadb.__version__}")

    client = _new_client()
    # 显式声明 cosine —— 与 notes.md「本周用余弦」一致（Chroma 默认是 l2）
    col = client.get_or_create_collection(
        COLLECTION, metadata={"hnsw:space": "cosine"}
    )
    log(f"collection      = {COLLECTION}")
    log(f"初始 count      = {col.count()}")

    vecs = [embed(t) for t, _ in SAMPLES]
    log(f"embedding 维度  = {len(vecs[0])}")

    col.add(
        ids=[f"s{i}" for i in range(len(SAMPLES))],
        documents=[t for t, _ in SAMPLES],
        metadatas=[m for _, m in SAMPLES],
        embeddings=vecs,
    )
    log(f"写入后 count    = {col.count()}  (期望 {len(SAMPLES)})")

    log(f"\n[查询] query = {QUERY_A!r}  → 相似度距离越小越相似")
    res = col.query(query_embeddings=[embed(QUERY_A)], n_results=3)
    for d, m, dist in zip(res["documents"][0], res["metadatas"][0], res["distances"][0]):
        log(f"  {dist:.4f} | [{m['source']}/{m['kind']}] {d}")

    log("\n[磁盘目录]")
    for root, dirs, files in os.walk(PERSIST_DIR):
        for fn in files:
            fp = os.path.join(root, fn)
            log(f"  {os.path.relpath(fp, PERSIST_DIR)}  ({os.path.getsize(fp)} B)")

    log("\n→ 进程 A 即将退出。接下来用【新进程】验证数据是否真的落盘。")
    write_result()


def phase2():
    log("=" * 56)
    log("PHASE 2 · 进程 B：模拟重启后重新打开（只读，不重新入库）")
    log("=" * 56)

    # 关键：用 get_collection（不是 get_or_create）——它不会帮我们凭空建库，
    # 拿得到就说明磁盘上确实有；拿不到就说明持久化失败。
    try:
        client = _new_client()
        col = client.get_collection(COLLECTION)
    except Exception as ex:
        log(f"❌ 打开 collection 失败：{ex!r}")
        log("持久化判定：❌ 失败（新进程读不到）")
        write_result()
        return

    n = col.count()
    ok = (n == len(SAMPLES))
    log(f"重启后 count    = {n}")
    log(f"持久化判定      = {'✅ 通过（数据还在，进程退出没丢）' if ok else f'❌ 失败（期望 {len(SAMPLES)}，实际 {n}）'}")
    _show_col(COLLECTION)

    log(f"\n[再查询] query = {QUERY_B!r}")
    res = col.query(query_embeddings=[embed(QUERY_B)], n_results=3)
    for d, m, dist in zip(res["documents"][0], res["metadatas"][0], res["distances"][0]):
        log(f"  {dist:.4f} | [{m['source']}/{m['kind']}] {d}")

    log(f"\n[metadata 回显] {json.dumps(res['metadatas'][0], ensure_ascii=False)}")
    log("→ metadata 三用途现场验证：① 溯源(source) ② 过滤(kind 可 where) ③ 排序加权特征")
    write_result()


if __name__ == "__main__":
    phase = sys.argv[1] if len(sys.argv) > 1 else "phase1"

    if phase == "reset":
        import shutil
        shutil.rmtree(PERSIST_DIR, ignore_errors=True)
        print(f"已删除 {os.path.abspath(PERSIST_DIR)}（重跑验证前清场）")
        sys.exit(0)

    try:
        {"phase1": phase1, "phase2": phase2}[phase]()
    except Exception as ex:
        import traceback
        LOG.append("!!! 异常 !!! " + repr(ex))
        LOG.append(traceback.format_exc())
        write_result()
        raise
