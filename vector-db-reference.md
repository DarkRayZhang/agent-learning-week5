# 向量库精简参考（20min 阅读）

> 周三任务：Chroma / Qdrant / pgvector 三选一 + collection/document/metadata/persist 四概念。
> 读完合上去 notes.md 用自己的话写。不要抄。
> 脚手架已经默认选 Chroma（`retrieval_app.py`、`requirements.txt` 已就位），今晚重点是**说清为什么选它**，不是重新做选型。

---

## 1. 一句话定义

**向量库 = 存"文本 + 向量 + metadata"三元组、并支持"给一个向量找最相似 Top-K"的数据库。**

类比你的经验：

| 你熟的存储 | 索引结构 | 查询方式 |
|---|---|---|
| MySQL / PostgreSQL | B-Tree | 精确匹配、范围查询 |
| Elasticsearch | 倒排索引 | 关键词匹配、全文检索 |
| Redis | Hash / Sorted Set | KV / 排行榜 |
| **向量库** | **HNSW / IVF** | **语义相似 Top-K** |

**核心区别**：前三个都在做"精确匹配"（值相等、词包含、key 存在），向量库在做"相似度排序"——**没有"对/错"，只有"多近/多远"**。

---

## 2. 三选一对比（本周为什么选 Chroma）

### 2.1 三个候选

| 维度 | **Chroma** | **Qdrant** | **pgvector** |
|---|---|---|---|
| 形态 | Python 嵌入式库（进程内） | 独立服务（Rust，gRPC/HTTP） | PostgreSQL 扩展 |
| 部署 | `pip install chromadb` 就能用 | Docker 起一个容器 | 现有 PG 加插件 |
| 持久化 | 本地目录（SQLite + 二进制向量文件） | RocksDB / 自研存储 | PG 表 |
| 数据规模上限 | 十万~百万级（单机） | 亿级（分布式） | 千万级（受 PG 限制） |
| 索引 | HNSW（默认） | HNSW + 量化 + 分布式 | HNSW / IVFFlat |
| 元数据过滤 | 支持（where 子句） | 支持（strong filter，性能好） | 支持（就是 SQL WHERE） |
| 语言生态 | Python 优先（有 JS/Java client） | 全语言 client | 所有能连 PG 的语言 |
| 运维复杂度 | 极低（就是一个目录） | 中（独立服务） | 低（复用现有 PG） |

### 2.2 本周为什么选 Chroma

按你的实际情况（100 篇文档 + 学习周 + 一个人 + Windows）：

1. **零运维**：`pip install` 完就能用，不用起 Docker，不用配 PG。学习周精力应该花在概念上，不是环境上。
2. **持久化就是一个目录**：`./chroma_db/` 存所有东西，删了就重置，备份就是拷走。调试友好度接近 SQLite。
3. **规模够用**：十万级以下 Chroma 完全撑得住，本周 100 篇 × 10 块 = 1000 条向量，是它的舒适区。
4. **脚手架已经用好了**：`retrieval_app.py` 里 `chromadb.PersistentClient(path="./chroma_db")` 就是它。

### 2.3 什么时候不选 Chroma

- **数据量上亿 / QPS 上千** → Qdrant（Rust 写的，性能和分布式能力都更强）
- **公司已有 PG 集群 / 需要 SQL 联合查询** → pgvector（一条 SQL 里既能 WHERE user_id=xxx 又能 ORDER BY embedding <-> query_vec，业务侧最省事）
- **要跨语言服务化** → Qdrant（Chroma 主要还是 Python 生态）

### 2.4 你 Java 背景的关联：pgvector 值得单独看一眼

你做 Java 平台 11 年，PG/MySQL 是最熟的地盘。pgvector 的用法就是加一列：

```sql
CREATE EXTENSION vector;

CREATE TABLE docs (
    id SERIAL PRIMARY KEY,
    content TEXT,
    embedding vector(1024),   -- ← 就这一列
    created_at TIMESTAMP,
    tenant_id VARCHAR(64)
);

-- 建 HNSW 索引
CREATE INDEX ON docs USING hnsw (embedding vector_cosine_ops);

-- 查询：找和 [0.1, 0.2, ...] 最相似的 5 条，且限定 tenant_id
SELECT id, content, 1 - (embedding <=> '[0.1, 0.2, ...]') AS similarity
FROM docs
WHERE tenant_id = 'biz-A'
ORDER BY embedding <=> '[0.1, 0.2, ...]'
LIMIT 5;
```

**为什么这个片段值得记住**：面试时如果被问"你们平台怎么给业务方提供向量检索能力"，pgvector 是**最容易讲清楚的方案**——因为它就是数据库，不用引入新组件，业务方零学习成本。你在 LLM 平台侧推方案时，这种"复用现有基建"的路径通常比"上一个新中间件"更容易过评审。

---

## 3. 四个核心概念

以 Chroma 术语为例（Qdrant/pgvector 概念一样，只是叫法不同）：

### 3.1 Collection（集合）

**是什么**：向量库里的"表"。一个 collection 装一批同类的向量。

**类比**：MySQL 的 table、ES 的 index、Redis 的 db。

**关键属性**：
- 名字（`week5_docs`）
- 相似度算法（cosine / L2 / dot，建集合时定，之后不能改）
- 维度（隐式，第一条向量插入时确定，之后不能混维度）

**本周用法**：一个 collection 就够（`week5_docs`）。平台级会按租户 / 业务线拆多个 collection 做隔离。

### 3.2 Document（文档 / 记录）

**是什么**：collection 里的一条数据，包含三部分：

```
{
  "id": "doc-001-chunk-3",          ← 唯一标识（自己给或用 UUID）
  "embedding": [0.12, -0.34, ...],  ← 向量（1024 维浮点数）
  "document": "原始文本内容...",     ← 原文（可选，但强烈建议存）
  "metadata": {...}                 ← 附加信息（下一节展开）
}
```

**关键认知**：向量库不只是存向量，**原文一般也一起存**——因为检索命中后要回显给用户看，如果只存向量，你还得再拿 id 去别的库查原文，多一跳。

### 3.3 Metadata（元数据）

**是什么**：附加在这条记录上的键值对，用来**过滤 + 溯源 + 展示**。

```python
metadata = {
    "source": "docs/2026-09-01.md",   # 溯源：来自哪个文件
    "chunk_index": 3,                  # 溯源：文件的第几块
    "author": "zhang",                 # 过滤：按作者
    "created_at": "2026-09-01",        # 过滤：按时间
    "tenant_id": "biz-A",              # 过滤：按租户（平台场景必备）
    "title": "..."                     # 展示：结果卡片标题
}
```

**metadata 的三种用途（周三自检答案）**：

| 用途 | 具体做什么 | 例子 |
|---|---|---|
| **过滤** | 缩小搜索范围（先 WHERE 再算相似度） | `where={"tenant_id": "biz-A"}` 只搜 A 租户的向量 |
| **溯源** | 命中后能定位回原文位置 | 结果里带 `source + chunk_index`，能翻回原文件 |
| **回显原文** | 直接展示 metadata 里的字段，不用回表 | 结果卡片显示 title / author / date |

**平台视角**：多租户隔离**首选方案就是 metadata filter**（`tenant_id=xxx`），而不是给每个租户开一个 collection。原因：collection 数量爆炸后管理成本高，而 filter 是查询期动态决定的。这就是你笔记里 09-08 写的"小租户共享池 + metadata filter 隔离"的落地手段。

**⚠️ 注意**：metadata 的值只能是**基本类型**（str/int/float/bool/list），不能嵌套 dict。存 JSON 得先 flatten 或序列化。

### 3.4 Persist（持久化）

**是什么**：向量库的数据存到磁盘，重启后还在。

**Chroma 的两种模式**：

```python
# 内存模式（重启就没）—— 测试用
client = chromadb.EphemeralClient()

# 持久化模式（存本地目录）—— 本周用
client = chromadb.PersistentClient(path="./chroma_db")
```

**持久化目录里有什么**（跑完 `retrieval_app.py` 后可以 `ls ./chroma_db/` 看）：

```
chroma_db/
├── chroma.sqlite3        # 存 metadata、document 原文、collection 信息
├── <uuid>/               # 每个 collection 一个目录
│   ├── data_level0.bin   # HNSW 索引 + 向量数据（二进制）
│   ├── header.bin
│   └── length.bin
└── ...
```

**关键认知**：Chroma 的持久化 = **SQLite 存元信息 + 二进制文件存向量**。这不是它独有的设计，Qdrant 也是"结构化元信息 + 二进制向量"分开存。原因：向量数据是 float32 数组，用 SQLite 存效率低（每行 4KB blob），直接写二进制文件更快。

**今晚的验证动作**：
1. 跑 `python retrieval_app.py` 生成 100 篇文档、入库
2. `ls ./chroma_db/` 看目录结构
3. **关掉进程，重新跑一次**（不重新入库，直接查询）
4. 查询结果和第一次一样 → 持久化验证通过

---

## 4. 完整流程：文本 → 切块 → embedding → 入库 → 查询

```
┌─────────────────────────────────────────────────────────────────────┐
│ 阶段 1：入库（离线，一次性 or 增量）                                    │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  docs/*.md                                                          │
│  （100 篇原始文档）                                                    │
│       │                                                             │
│       ▼                                                             │
│  ┌──────────┐                                                       │
│  │ 切块 chunk │  按段落 or 固定长度切成小片                              │
│  └──────────┘  每片 ~200-500 字（W5 用段落切，W7 优化）                  │
│       │                                                             │
│       ▼                                                             │
│  1000 条 chunk（假设每篇 10 块）                                       │
│       │                                                             │
│       ▼                                                             │
│  ┌──────────────┐                                                   │
│  │ embedding API │  调百炼 text-embedding-v4                          │
│  └──────────────┘  批量传（一次 20-100 条最省，注意限流）                 │
│       │                                                             │
│       ▼                                                             │
│  1000 个 1024 维向量 + 原文 + metadata(source, chunk_index, ...)     │
│       │                                                             │
│       ▼                                                             │
│  ┌────────────────┐                                                 │
│  │ Chroma 入库      │  collection.add(ids, embeddings, documents,     │
│  └────────────────┘                 metadatas)                      │
│       │                                                             │
│       ▼                                                             │
│  ./chroma_db/ （持久化目录，重启还在）                                   │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│ 阶段 2：查询（在线，每次用户提问）                                       │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  用户 query："怎么给宠物挑选合适的粮食？"                                │
│       │                                                             │
│       ▼                                                             │
│  ┌──────────────┐                                                   │
│  │ embedding API │  同一个模型（必须！不同模型的向量空间不兼容）           │
│  └──────────────┘  单次调用，得到一个 1024 维向量                       │
│       │                                                             │
│       ▼                                                             │
│  ┌────────────────┐                                                 │
│  │ Chroma 查询      │  collection.query(                              │
│  └────────────────┘      query_embeddings=[vec],                    │
│       │                  n_results=3,                               │
│       │                  where={"tenant_id": "biz-A"}  ← 可选过滤    │
│       │                )                                            │
│       ▼                                                             │
│  Top-3 结果：                                                        │
│  [                                                                  │
│    {id, document(原文), metadata, distance},                        │
│    {id, document, metadata, distance},                              │
│    {id, document, metadata, distance}                               │
│  ]                                                                  │
│       │                                                             │
│       ▼                                                             │
│  格式化输出给用户（原文 + source 溯源 + 相似度分数）                     │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

**你今晚要画的版本**（notes.md 里）：不用这么细，抓住 5 个节点 + 2 个阶段（入库 vs 查询）就够。**关键是画出来"查询也要过一次 embedding API"**——很多人以为只有入库要 embedding，忘了 query 也要变成向量才能比较。

---

## 5. 三个新手必踩的坑

### 坑 1：入库和查询用**不同**的 embedding 模型

**症状**：查询结果全是乱的，相似度分数看起来随机。

**原因**：不同模型的向量空间完全不兼容（就像把中文拼音塞进英文词典查）。text-embedding-v4 入库的向量，用 BGE-M3 编码 query 去查，结果 = 随机。

**避免**：`.env` 里 `EMBEDDING_MODEL` 一次定死，入库和查询都读同一个变量。**永远不要在项目中途换 embedding 模型**，除非清空重灌。

### 坑 2：以为持久化 = 每次自动加载

**症状**：重启进程后查询报错 "collection not found"。

**原因**：Chroma 的持久化目录存了数据，但**每次进程启动还是要显式 `get_or_create_collection("week5_docs")`**，不会自动挂载。

**避免**：`retrieval_app.py` 里用 `get_or_create_collection` 而不是 `create_collection`（后者已存在会报错）。

### 坑 3：metadata 存了嵌套 dict

**症状**：`add()` 报 `Expected metadata value to be a str, int, float or bool`。

**原因**：Chroma metadata 只接受扁平的基本类型。想存 `{"author": {"name": "zhang", "id": 1}}` 得拆成 `author_name`、`author_id` 两个 key。

**避免**：设计 metadata schema 时就按扁平结构写，别把 JSON 直接扔进去。

---

## 6. 和你已有经验的对照

| 向量库概念 | 你熟悉的类比 |
|---|---|
| Collection | ES 的 index、MySQL 的 table |
| Document | ES 的一条 doc、表里的一行 |
| Metadata | ES 的 fields、表的列 |
| Metadata filter | SQL WHERE / ES query filter |
| HNSW 索引 | ES 的倒排索引（都是加速检索的数据结构） |
| Persist 目录 | MySQL 的 data 目录、ES 的 shard 目录 |
| 相似度分数 | ES 的 _score |
| 批量 embedding 入库 | ES 的 bulk API |
| 向量库服务化（Qdrant） | ES 集群化 |
| pgvector | 就是 PG 加一列（对你最没学习成本的方案） |

**一句话总结**：向量库 = ES 换了个索引结构（HNSW 替代倒排），换了个查询语义（相似度替代关键词匹配），其他概念全部可以迁移。

---

## 7. 读完自检（合上文件，心里回答）

1. Chroma / Qdrant / pgvector 各自适合什么场景？本周为什么选 Chroma？
2. collection / document / metadata / persist 四个概念各是什么？和 MySQL 的哪些概念对应？
3. metadata 的三种用途是什么？多租户隔离为什么优先用 metadata filter 而不是拆 collection？
4. 完整流程从"100 篇文档"到"用户查询"要经过哪几个步骤？查询阶段还要不要调 embedding API？
5. Chroma 持久化目录里存了什么？为什么向量和 metadata 分开存？

**能答上来 3 题以上就去写 notes.md**，答不上来翻回对应章节再看一遍。

---

## 8. 今晚动手清单（30min）

按顺序做，做完打勾：

- [ ] 读这份参考 20min（现在）
- [ ] 关掉这份文件，打开 notes.md 周三小节
- [ ] **画流程图**（文本→切块→embedding→入库→查询，5 个节点 2 个阶段，ASCII 手绘即可）
- [ ] **写四概念**（collection/document/metadata/persist 各一句自己的话，别抄本文）
- [ ] **写选型结论**（为什么本周选 Chroma + pgvector 与你 Java 背景的关联，2-3 行）
- [ ] **跑 `python retrieval_app.py`**（应该已经能跑通，100 篇文档入库 + 交互查询）
- [ ] **`ls ./chroma_db/` 看目录**（截图或记下有哪些文件）
- [ ] **关掉进程重新跑一次**，直接查询看结果一样不一样（persist 验证）
- [ ] notes.md 里写"重启后数据还在吗"的答案（yes + 证据）

**做完这些再来问我**，我按你的 notes 检查错漏（先写后检协议）。
