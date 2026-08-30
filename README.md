# Week 5 卫星项目：语义检索小程序

> **一句话卖点：100 篇文档切块检索**

第 5 周周末项目（详细拆解见 `../week5-daily-plan.md`）。检索能力 W7 起并入主线「效率助手」的备忘录检索（V3 D7）。

## 功能

- 100 篇模拟文档 → 切块 → embedding → 入库（Chroma 持久化）
- 输入一句话 → 返回最相关 Top-3 片段（含来源 metadata）
- 无匹配时诚实返回"无匹配"

## Embedding 路线（为什么不用 DeepSeek）

DeepSeek 官方 API 不提供 embedding 端点（2026-08 实测 `/embeddings` 返回 404），因此 embedding 走第三方 OpenAI 兼容服务：默认阿里云百炼 `text-embedding-v4`，备选硅基流动 `BGE-M3`（见 `.env.example`）。chat 模型厂商 ≠ 一定有 embedding 服务——这本身就是一条面试素材。

## 运行步骤

1. `cd G:\agent学习\week5`
2. 激活 venv + `pip install -r requirements.txt`
3. `cp .env.example .env`，填 `EMBEDDING_API_KEY` / `EMBEDDING_BASE_URL` / `EMBEDDING_MODEL`（百炼或硅基流动注册拿 key）
4. `python make_docs.py` 生成 100 篇文档
5. `python retrieval_app.py` 启动检索，输入 `exit` 退出

## 流程

```
文档 → 切块 → embedding → Chroma 入库（持久化）
query → embedding → 相似度排序 → Top-3 返回（带来源）
```

## 向量库选型（V3 D5）

- **Chroma**（本周用）：轻量、嵌入 Python、上手快
- **Qdrant**：独立服务、性能好、适合更大规模
- **pgvector**：Postgres 插件，与关系库同源——**你有 Java/数据库背景，值得对照**

## 验收

1. 100 篇文档全部入库，重启后仍可检索（持久化）
2. 换 5 种说法问同一主题，Top-1 稳定相关
3. 无相关文档时诚实返回"无匹配"
