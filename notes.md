# Week 5 学习笔记 — Embedding + 向量库

> 每晚看 20min + 写 30min，卡住也至少写两行，不断更。
> 本周卫星项目：语义检索小程序（100 篇文档切块检索），检索能力 W7 起并入主线「备忘录检索」（V3 D7）。

## 评估趋势线（V3 D3，每周日更新）
| 周 | 用例数 | 通过率 | 本周改动 | 备注 |
|----|--------|--------|----------|------|
| W5 | 10 | __% | 检索命中率基线 | Top-1 命中率 |

## 成本记录（V3，每周日更新）
| 周 | 模型 | 调用次数 | 花费 | 备注 |
|----|------|----------|------|------|
| W5 | text-embedding-v4 / BGE-M3（embedding，第三方） | — | — | 100 篇文档切块向量化调用较多，免费额度内也要记账（DeepSeek 无 embedding 端点，另选厂商） |

## 面试题库（V3 D10，通勤每周攒 2 题）
- 题 1（embedding 原理）：
- 题 2（向量检索 vs 关键词检索）：

## 周一：Embedding 概念
- embedding 和 token 的关系：
- 向量维度是什么：
- 相似度算法（cosine / dot / euclidean）区别：
- `embed_demo.py` 实测（3 句话向量维度 + 两两 cosine 相似度）：
  →

## 周二：向量相似度 + 简单检索
- cosine 相似度怎么算、归一化作用：
- `search(text)` 原型：query 转向量 → 相似度排序 → Top-K
- 近义 query 测试（"猫粮" vs "宠物食品"）结果：
  →

## 周三：向量库选型 + 落地
- Chroma / Qdrant / pgvector 三选一对比结论（为什么本周选 Chroma；pgvector 与你 Java 背景的关联）：
- collection / document / metadata / persist 四个概念：
- **【亲手画】文本 → 切块 → embedding → 入库 → 查询 完整流程：**

```
（在这里画）
```

- 重启后数据还在吗（persist 验证）：
  →

## 周五：切块 + Java 对照
- 切块（chunking）概念：为什么不能整篇 embedding；按字符/按句子/按语义区别：
- 100 篇文档切块统计（多少块）：
- Java 对照输出物：`week5/java/` 下 Spring AI `EmbeddingModel` / `VectorStore` 片段
- 对照笔记（Python Chroma ↔ Spring AI VectorStore）：
  →

## 周末项目：语义检索小程序（卫星）
- 验收 1（100 篇入库 + 持久化）/ 2（5 种说法 Top-1 稳定）/ 3（无匹配诚实返回）结果：
- README 一句话卖点「100 篇文档切块检索」写了吗？
- 空白页测验结果（重写 search 核心）：
- 与主线衔接：`docs/sample_retrieval.json` 存了吗（W7 并入主线「备忘录检索」用）？

## 本周复盘（3 句话）
- 收获：
- 卡点：
- 下周重点（W6 RAG 基础流程：检索→拼上下文→生成 + 30 条用例）：
