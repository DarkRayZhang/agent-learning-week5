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
7. `python export_samples.py` — ④ 导出检索样例 → `docs/sample_retrieval.json`（W7 对照基准，见下）

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
| 5 | commit | ✅ `dba6480` 收口① / `ddd2ead` 收口② / `fc6482b` persist 补记（已 push） |

## 测试资产：`docs/sample_retrieval.json`

```bash
python export_samples.py     # 17 条用例跑一遍 → docs/sample_retrieval.json（63 KB）
```

两个用途：**W7 跨实现对照**（Java 版 Spring AI `VectorStore` 应能复现同一批 Top-3）、
**W6 拼上下文的输入样例**（`cases[].hits[].text` 就是可直接拼进 prompt 的原文块，
`context_chars` 是拼完的字符量级）。
它**不写第二套检索逻辑** —— 用例 / 检索 / 判定全部复用 `retrieval_app`，
否则 W6 标定阈值时会出现两个真相。

### ⚠️ 它同时暴露了本周最真的一条问题：判定 ≠ 内容

| 维度 | 成绩 | 含义 |
|---|:--:|---|
| 判定（命中 / 拒答） | **16/16** | 阈值的方向与量级都对 |
| **内容（Top-1 命中的小节对不对）** | **8/11** | **这才是「检索真的答对了吗」** |

3 条「判定命中、内容跑偏」的样本：

| 用例 | 相似度 | Top-1 实际命中 | 期望小节 |
|---|:--:|---|---|
| 怎么防止重复扣款 | 0.5506 | 通勤路线 / 机场值机 | 接口幂等 |
| 线上出故障了怎么快速止损 | 0.5352 | 灰度策略 | 回滚预案 / 事故复盘 |
| 晚上老醒睡不踏实怎么办 | 0.5688 | (无小节标题，续块) | 睡眠 |

**而且相似度区分不了这两类**：判对的 8 条落在 0.5565~0.7113，判错的 3 条落在 0.5352~0.5688，
两段区间**重叠**（0.5688 是错的、0.5565 是对的）
→ **单靠调阈值解决不了**，必须改善切块 / 上 rerank —— 这正是 W7 的靶子。

> 这与 09-15 的「**hit@1 会骗人**」是同一问题的两面：
> ① **上下文不纯**——Top-1 块混 ≥3 个小节的有 3/17 条（例 `doc_082.md` 的命中块含
> 「事故复盘 / 灰度策略 / 发版窗口 / 回滚预案 / **通勤路线**」，最后一个小节完全无关）；
> ② **命中主题都可能错**——上表 3 条。
> 另：`boundary` 用例（「显示器该买多大的」）相似度 **0.4403**，距阈值 0.45 仅 **0.01**
> —— 灰区确实贴着阈值，W6 必须用 30 条用例的误拒 / 漏放分布重标。
