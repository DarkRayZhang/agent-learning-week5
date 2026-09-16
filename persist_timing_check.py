# -*- coding: utf-8 -*-
"""
验证 persist 的**写入时机**：col.add() 返回时，数据到底在内存还是已在磁盘？
================================================================================
用法：
    python persist_timing_check.py run     # 自动编排（推荐）
    python persist_timing_check.py a       # 进程 A：add → 打印磁盘快照 → 保持存活 20s（不退出）
    python persist_timing_check.py b       # 进程 B：独立进程，只读，看能不能读到

【为什么要做这个实验】
2026-09-15 老张的口述推理是：「应该是异步写，先内存、达到一定量再刷盘，或者方法执行完落盘」。
这是**数据库的常规直觉**（MySQL InnoDB / WAL 确实是这样），但 Chroma 是不是这样？
不能靠推测 —— 用两条独立证据判定：
    证据 1（主）：同一进程内，add 前后对比磁盘文件的 size / mtime
    证据 2（辅）：**进程 A 不退出**，让独立的进程 B 去读
                 （如果 B 能读到 → 数据不在"进程退出时才落盘"）

【关键设计】进程 A add 完之后**故意 sleep 20 秒不退出**。
如果数据只是 A 的内存状态，B 此刻什么都读不到；如果 B 读得到，就证明落盘发生在 add 返回之前。
"""
import os
import subprocess
import sys
import time

import chromadb

os.chdir(os.path.dirname(os.path.abspath(__file__)))

PERSIST_DIR = "./chroma_db"
COL = "timing_check"
IDS = ["t1", "t2", "t3"]
DOCS = ["甲文档", "乙文档", "丙文档"]
VECS = [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]  # 假向量，只测持久化时机，不花钱


def db_files():
    out = []
    for root, _dirs, files in os.walk(PERSIST_DIR):
        for f in sorted(files):
            p = os.path.join(root, f)
            out.append((os.path.relpath(p, PERSIST_DIR), os.path.getsize(p), os.path.getmtime(p)))
    return out


def dump(tag):
    """只显示 chroma.sqlite3 与最近 20 秒被动过的文件。"""
    now = time.time()
    print(f"  [{tag}] 磁盘快照")
    for name, size, mt in db_files():
        fresh = (now - mt) < 20
        if fresh or name == "chroma.sqlite3":
            mark = "   ← 刚刚被写过" if fresh else ""
            print(f"      {name:52s} {size:>9d} B  {time.strftime('%H:%M:%S', time.localtime(mt))}{mark}")


def role_a():
    c = chromadb.PersistentClient(path=PERSIST_DIR)
    try:
        c.delete_collection(COL)
    except Exception:
        pass
    col = c.get_or_create_collection(COL, metadata={"hnsw:space": "cosine"})

    print(f"进程A · PID={os.getpid()}")
    print(f"  add 前 count = {col.count()}")
    dump("add 前")

    t0 = time.time()
    col.add(ids=IDS, documents=DOCS, embeddings=VECS)
    dt = time.time() - t0

    print(f"  ▶ col.add() 已返回，耗时 {dt:.3f}s —— 注意：**进程 A 此刻仍然活着，没有退出**")
    dump("add 后")

    print("  ▶ 进程 A 保持存活 20 秒。若数据只在其内存里，进程 B 此刻读不到任何东西。")
    sys.stdout.flush()
    time.sleep(20)
    print("  进程A 现在退出")


def role_b():
    print(f"进程B · PID={os.getpid()}（独立进程）")
    try:
        c = chromadb.PersistentClient(path=PERSIST_DIR)
        col = c.get_collection(COL)
        n = col.count()
        print(f"  get_collection 成功，读到 count = {n}")
        got = col.get(include=["documents"])
        print(f"  读到的原文 = {got['documents']}")
        print(f"  → {'✅ 数据在 col.add() 返回时就已落盘（同步写）' if n == len(IDS) else f'⚠️ 只读到 {n} 条'}")
    except Exception as e:
        print(f"  ❌ 打不开 collection：{type(e).__name__}: {e}")
        print("  → 说明此刻数据还没落盘")


def role_run():
    print("=" * 74)
    print("实验：col.add() 返回时，数据在内存还是已在磁盘？（进程 A 故意不退出）")
    print("=" * 74)
    a = subprocess.Popen([sys.executable, os.path.abspath(__file__), "a"],
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                         text=True, encoding="utf-8", errors="replace")
    time.sleep(8)   # 等 A 跑完 add 并进入 sleep
    print("\n--- 进程 A 仍在存活期间，用独立进程 B 去读 ---")
    b = subprocess.run([sys.executable, os.path.abspath(__file__), "b"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    print(b.stdout or b.stderr)

    a.wait(timeout=60)
    print("--- 进程 A 的完整输出 ---")
    print(a.stdout.read())

    try:
        chromadb.PersistentClient(path=PERSIST_DIR).delete_collection(COL)
        print("（实验用 collection timing_check 已清理）")
    except Exception:
        pass


if __name__ == "__main__":
    role = sys.argv[1] if len(sys.argv) > 1 else "run"
    {"a": role_a, "b": role_b, "run": role_run}[role]()
