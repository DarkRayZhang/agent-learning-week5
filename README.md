# Week 5 卫星项目：语义检索小程序

> **一句话卖点：100 篇文档切块检索 + 可溯源 + 诚实拒答**

第 5 周周末项目（详细拆解见 `../week5-daily-plan.md`）。检索能力 W7 起并入主线「效率助手」的备忘录检索（V3 D7）。

## 功能

- 100 篇语料 → 切块（chunk 500 / overlap 50）→ embedding → 入库（Chroma 持久化）
- 输入一句话 → 返回最相关 **Top-3（含原文全文 + 来源 metadata + 相似度）**
- 库中没有相关内容时**诚实拒答**，不拿训练知识硬答

## 两阶段分工（脚本各管一段，数据源唯一）

| 阶段 | 脚本 | 时机 | 干什么 |
|---|---|:--:|---|
| **A · 离线入库** | `make_docs.py` → `build_index.py` | 跑一次（约 13s / 20 次 API） | 生成语料 → `chunk_text()` 切块 → embedding → 落盘 `chroma_db/` |
| **B · 在线查询** | `retrieval_app.py` | 每次提问 | 读现成索引 → Top-3 → 拒答判定 |

⚠️ **检索端只读库、不建库**。若 `chroma_db/` 不存在，`retrieval_app.py` 会**直接报错并提示先跑 `build_index.py`**。
这不是缺陷而是刻意设计：**数据源唯一**——否则同一份 `docs/` 会被两套切块策略各建一份索引，检索结果忽好忽坏且原因难查。

## 拒答机制（本项目最容易踩的坑）

Chroma 的 `distances` 是**距离**不是相似度（`hnsw:space=cosine` 时 `distance = 1 - similarity`，**越小越像**）：

| 场景 | distance | similarity |
|---|:--:|:--:|
| 库内「发版前必须确认什么」 | 0.289 | **0.711** |
| 库外「量子计算的量子比特怎么实现」 | 0.703 | **0.297** |

→ 判据必须是 `if distance > 阈值: 拒答`。**反着写会把最相关的全部拒掉、把不相关的全部放行**，两种事故正好颠倒。

当前 `REJECT_DISTANCE = 0.55`（≈ 相似度 0.45）是**经验起点**、不是标定结果 —— W6 要用 30 条用例的误拒 / 漏放分布来标定。

## Embedding 路线（为什么不用 DeepSeek）

DeepSeek 官方 API 不提供 embedding 端点（2026-08 实测 `/embeddings` 返回 404），因此 embedding 走第三方 OpenAI 兼容服务：默认阿里云百炼 `text-embedding-v4`（维度 1024），备选硅基流动 `BGE-M3`（见 `.env.example`）。**chat 模型厂商 ≠ 一定有 embedding 服务**——这本身就是一条面试素材。

## 运行步骤

1. `cd G:\agent学习\week5`
2. 激活 venv + `pip install -r requirements.txt`
3. `cp .env.example .env`，填 `EMBEDDING_API_KEY` / `EMBEDDING_BASE_URL` / `EMBEDDING_MODEL`
4. `python make_docs.py` — ① 生成 100 篇语料
5. `python build_index.py` — ② 切块 + 向量化 + 入库 → `chroma_db/`（200 块）
6. `python retrieval_app.py` — ③ 交互检索，输入 `exit` 退出

验收自测（一条命令跑完验收 2 + 验收 3，不用手打 5 遍）：

```bash
python retrieval_app.py --selftest            # 自动跑 5 种说法 + 2 个库外话题
python retrieval_app.py "发版前必须确认什么"    # 单次查询
```

## 流程

```
【阶段 A · 离线入库】
  docs/*.md → chunk_text() 切块(500/50) → embedding(批量) → chroma_db/ 落盘

【阶段 B · 在线查询】
  query → embedding(1 次) → 向量检索 Top-3（带 metadata）
                                │
                        最高相似度 < 阈值 0.45 ?
                          ├─ 否 → 返回 Top-3（原文全文 + source/chunk_index + 相似度）
                          └─ 是 → 诚实拒答「库中没有相关内容」
```

## 向量库选型（V3 D5）

- **Chroma**（本周用）：轻量、嵌入 Python、上手快
- **Qdrant**：独立服务、性能好、适合更大规模
- **pgvector**：Postgres 插件，与关系库同源——**你有 Java/数据库背景，值得对照**

## 验收

| # | 验收项 | 结果 |
|:--:|---|:--:|
| 1 | 100 篇入库 + 重启后仍可检索（持久化） | ✅ 200 块；新进程 `get_collection` 读回 count=200 |
| 2 | 换 5 种说法问同一主题，Top-1 稳定相关 | ✅ **5/5** 落在「发布值班」主题（相似度 0.56~0.71） |
| 3 | 无相关内容时诚实返回 | ✅ 库外话题相似度 0.30 < 阈值 0.45 → 拒答 **2/2** |
| 4 | README 一句话卖点 | ✅ |
| 5 | commit | ⬜ |

> ⚠️ 验收 2 的 **5/5 只说明「主题级稳定」，不等于上下文干净**。实测 Top-1 块常混着 2~5 个小节
> （例：`doc_082.md` 的命中块含「事故复盘 / 灰度策略 / 发版窗口 / 回滚预案 / **通勤路线**」——
> 最后一个小节是完全无关的次主题）。这是 09-15「**hit@1 会骗人**」的第二个实证，也是 W7 的优化靶子。
