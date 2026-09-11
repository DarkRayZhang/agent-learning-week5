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
- embedding 和 token 的关系：Token 是将一段输入做分词（切片后的最小单位），Embedding 是将这些 token 序列经过模型计算后输出的一组固定长度浮点数向量。Token 是原料/输入，Embedding 是产物/输出。注意：输出不是每个 token 各一个向量，而是整段文本经 pooling 压成一个向量。
- 向量维度是什么：就是输出浮点数数组的长度（如 1024 维 = 1024 个浮点数）。由 embedding 模型本身决定，与输入文本长度无关。维度越大语义表达越精准，但存储压力和检索压力也越大。
- 相似度算法（cosine / dot / euclidean）区别：余弦只看两个向量的方向（夹角），不管长度；点积同时看方向和长度；欧氏距离是空间直线距离（越小越相似，和前两个方向相反）。当向量做了归一化（模=1）时，点积和余弦结果一样。本周用余弦，因为 embedding 输出向量长度不一定归一化，余弦自动忽略长度差异最稳定。
- `embed_demo.py` 实测（3 句话向量维度 + 两两 cosine 相似度）：
  → 模型：text-embedding-v4（阿里云百炼），维度：1024
  → cosine(狗是人类的好朋友, 宠物需要主人的关爱) = 0.5955 ← 语义近，最高
  → cosine(宠物需要主人的关爱, 汽车是现代交通工具) = 0.3562
  → cosine(狗是人类的好朋友, 汽车是现代交通工具) = 0.3180 ← 语义远，最低
- 为什么语义近的向量距离近：对比学习（Contrastive Learning）——训练时用大量正样本对（语义近）拉近、负样本对（语义远）推远，数十亿对训练后模型学会了"意思近 = 坐标近"的映射。不是硬编码规则，是统计学习的结果。

## 周二：向量相似度 + 简单检索
- cosine 相似度怎么算、归一化作用：公式三步（点积→算模→除），归一化后模=1，点积直接等价余弦。
- `search(text)` 原型：query 转向量 → 相似度排序 → Top-K（暴力检索 O(N)，10 万以下够用）
- 近义 query 测试（"猫粮" vs "宠物食品"）结果：
  → 延迟到周末项目一起写（retrieval_app.py 是完整版）

### 平台思考（碎片 5min）

**Q：LLM 平台有没有"检索"类能力？**
上游业务方在调 LLM 平台之前已经完成了知识库检索，到我们这里时知识内容已通过上下文带过来了，平台本身不做检索。但上游经常因为召回率低或时延高出问题——这恰好说明检索层是 Agent/RAG 系统的关键瓶颈。

**Q：100 个业务方共用 vs 各自部署向量检索服务？**
- 共用：成本低、运维简单，但问题明显——不同业务线的内容容易产生相似召回结果导致串数据、向量库内容过多检索效率下降、数据难以有效隔离。
- 各自部署：成本和运维高，但数据隔离干净、不会串召回、数据量小检索效率高。
- 结论倾向：大租户独立部署，小租户共享池 + metadata filter 隔离（和 LLM 平台多业务线隔离方案同构）。

**Q：和模型路由的相似之处？**
有。ASR/TTS/大模型部署的服务实例都非常多，为了最大化底层 GPU 资源使用率，根据用户实际输入参数做动态路由，在超卖的情况下保证用户响应及时。向量检索服务的"根据 query 特征选最匹配的索引/分片"和模型路由的"根据请求特征选最匹配的模型实例"是同一类问题。

## 周三：向量库选型 + 落地

> **AI 草稿（09-09 深夜）**：根据 `vector-db-oral-quiz.md` 的口述 + 补漏整理，明天精神好时改成自己版本再勾 daily-plan。
> 综合评级 B（Q1 选型 B / Q2 四概念 B- / Q3 metadata B / Q4 完整流程 B+ / Q5 持久化 B）。

### 三选一对比结论

**记忆锚点：Chroma 10 万 / pgvector 千万 / Qdrant 亿级。**

| | Chroma | pgvector | Qdrant |
|---|---|---|---|
| 形态 | 嵌入式库（也可起 server） | PG 扩展（非独立数据库） | 独立服务（Rust） |
| 量级 | 10 万舒服（官方称百万） | 千万 | 亿级 |
| 分布式 | ✗ | ✗（靠 PG 分区 / Citus） | ✓ 原生 |
| 事务 / JOIN | ✗ | ✓ 与业务数据同库 | ✗ |
| 运维成本 | 几乎为零 | 取决于是否已有 PG | 最高（独立集群） |
| 生产成熟度 | 低（原型为主） | 中高（RDS/Supabase/Neon 均支持） | 高 |
| 典型场景 | 本地学习 / 原型 / 单机小工具 | 已有 PG、千万内、要事务+复杂过滤 | 大规模、高并发、独立向量服务 |

**选型决策树**：
- 已有 PG + 千万内 + 要事务 → pgvector
- 没有 PG + 亿级 + 要独立扩展 → Qdrant
- 本地学习 / 原型 / 单机小项目 → Chroma

**本周为什么选 Chroma（面试常问，必须会论证）**：
1. W5 目标是学 RAG 编排链（chunk → embed → store → retrieve → 拼 prompt），不是学运维。零服务 = 零环境摩擦。
2. 同进程：和脚手架代码跑在一个 Python 进程里，省掉网络/序列化/连接池这些与本周目标无关的干扰项。
3. MySQL 经验可平移：`add / query / get / delete` 与表操作几乎一一对应，学习成本最低。
4. 概念同构：collection / metadata filter 与 Qdrant、pgvector 通用，后面换库只是换 client，概念不用重学。
5. 迁移触发点（到点就换）：数据 > 50 万 / 需要多进程并发写 / 上生产 → Qdrant；项目已有 Postgres → pgvector。

**pgvector 与我 Java 背景的关联**：
- 就是 PG 加一列 `embedding vector(1024)` + 一个 HNSW 索引，SQL 一条搞定"WHERE tenant_id=? ORDER BY embedding <=> ? LIMIT k"。
- 面试时讲"平台怎么给业务方提供向量检索能力"，pgvector 最容易讲清楚——复用现有基建，业务方零学习成本，比"上一个新中间件"更容易过评审。
- **但 pgvector 有硬伤**：① HNSW 索引常驻内存、构建慢；② 向量列与普通列混表 → TOAST / 表膨胀、vacuum 压力大；③ 没有原生分片；④ 过滤+向量混合时 PG planner 可能选错索引，要调 `hnsw.ef_search`；⑤ 索引参数（m / ef_construction / ef_search）要自己调。

### collection / document / metadata / persist 四个概念

| 概念 | 是什么 | MySQL 类比 | 关键坑 |
|---|---|---|---|
| **Collection** | 向量库里的"表"，装一批同类向量 | 表 | **自带语义空间约束**：create 时就绑定 embedding 函数 + 距离度量（cosine/l2/ip），不同模型的向量**不能混进同一个 collection** |
| **Document** | 一条记录里的**原始文本字段** | 行里的一个"文本列" | 精确说，Chroma 一行是四元组 `(id, document, embedding, metadata)`，document 只是其中之一，不是整行 |
| **Metadata** | 附加在这条记录上的 KV | **JSON 列**（不是普通列） | schema-less、只支持 str/int/float/bool、**不能嵌套 dict/list** |
| **Persist** | **动作**——把内存状态序列化落盘 | `COMMIT` + `fsync` | `chromadb.PersistentClient(path=...)` 每次写自动落盘；老的 `Client() + client.persist()` 要手动，别用 |

**⚠️ embedding 列在 MySQL 里没有对应物**：MySQL 索引是 B+ 树（精确匹配 / 范围扫描），向量库索引是 HNSW / IVFFlat（近似最近邻 ANN）。ANN 只保证近似（召回率 ~95-99%），是"用一点点准确率换数量级加速"。SQL 里 `WHERE embedding = ?` 没意义，得写 `ORDER BY embedding <=> ? LIMIT k`。

**metadata 的用途（自检答案）**：
1. **过滤（Filter）**：检索时缩小候选集，等价 SQL 的 WHERE。典型字段：`tenant_id`、`user_id`、`doc_type`、`lang`、`acl`。
2. **溯源（Provenance）**：记录 chunk 从哪来，回答时给出处、能回链原文。典型字段：`source`、`page`、`chunk_index`、`url`、`doc_id`。
3. **排序 / 后处理加权（Rerank 特征）**：检索只是"语义相似"，最终排序还要叠加业务信号。典型字段：`created_at`（时间衰减）、`importance`（权重）、`view_count`。
4. **幂等去重 / 增量更新**（实践中极重要、容易忽略）：用 `doc_id + chunk_index + content_hash` 判断是否已入库，**重复跑 ingestion 不会重复 embed → 直接省 API 钱**。
5. **调试可观测性**：结果不对时能打印"命中了哪篇、第几页、什么时间入库的"。

**多租户隔离为什么优先 metadata filter 而不是拆 collection**：
1. **索引与内存开销**：每个 collection 维护一份独立的 HNSW 索引且常驻内存。1000 个租户 = 1000 份索引，内存爆炸。filter 只有一份索引。
2. **开销模型**：拆 collection = O(租户数)，filter = O(1)。SaaS 场景成千上万租户物理上不可能每个建 collection。
3. **跨租户查询**：全局搜索 / 管理员视角 / 数据迁移要跨租户，拆了就得发 N 次查询手动合并排序。
4. **运维复杂度 ×N**：schema 变更、重建索引、备份、监控全部乘以租户数。
5. **小租户浪费**：几十条数据也各维护一套索引结构，内存利用率极低。

**例外（该拆就拆）**：① 合规要求物理隔离（金融/医疗）；② 不同租户需要不同 embedding 模型 / 距离度量（collection 创建时绑定）；③ 单租户数据量超大需独立分片。

**⚠️ 安全红线（Java 经验秒懂）**：filter 是**逻辑隔离**——代码里漏写一个 where 就串数据。实践中必须**双重保险**：数据访问层强制注入 `tenant_id`，不让调用方自己传。类比 MyBatis 租户拦截器 / 多租户 SQL 改写。

**⚠️ Pre-filter vs Post-filter 陷阱**：
- Chroma 是 **post-filter**：先向量检索拿 top-k，再按 where 过滤。若某租户数据只占 1%，检索出的 50 条可能全是别人的，过滤完剩 0 条 → 明明有数据却答"没找到"。
- Qdrant 有 payload index 支持 **pre-filter**（先按条件圈定候选集再 ANN）。
- **Chroma 缓解办法**：k 取大一点（要 5 条就先取 50 条再过滤），留过滤损耗余量。

> 📎 **metadata 设计延伸**（09-11 晚讨论整理）→ `metadata-design.md`：四元组结构 / 两层同名 metadata / metadata ≠ 表字段（缺 DDL 兜底）/ 字段由 query pattern 反推 / 决策可逆性分层 / 成本不对称原则 / 「检索契约」三条款 / `build_metadata()` 模板。
> （⚠️ 该文与本节同为 AI 草稿，按 §5.6 需 2 天内改成自己版本）

### 【亲手画】文本 → 切块 → embedding → 入库 → 查询 完整流程

**⚠️ AI 草稿版，明天自己重画一遍**（对照 quiz Q4 补漏 1 的标准流程全景）：

```
【阶段 A：入库（离线，一次性，可重跑）】

  100 篇 docs/*.md
        │
        ▼
  ① Load 加载（读成文本）
        │
        ▼
  ② Chunk 切分：1000 个 chunk
     ⚠️ 必须带 overlap（典型 chunk_size=500 / overlap=50，10%）
     ⚠️ 为什么切分：a) embedding 模型有 max token 上限
                    b) 长文本语义被稀释，一整篇压成一个向量任何具体问题都匹配不准
        │
        ▼
  ③ 生成 ID：doc_id + chunk_index（保证幂等，配合 content_hash 判重）
        │
        ▼
  ④ Embedding：调 API 1000 次，要 batch 批量
        │
        ▼
  ⑤ Upsert 写库：一次性写入 (id, document, embedding, metadata)
        │
        ▼
  ⑥ Persist：./chroma_db/ 落盘


【阶段 B：查询（在线，每问一次都跑）】

  用户 query
        │
        ▼
  ① Embedding query：调 API 1 次
     ⚠️ 必须和入库时同一个模型，不同模型向量空间不对齐
        │
        ▼
  ② 向量检索 top-k：ANN + where={"tenant_id": ...} 强制隔离
        │
        ▼
  ③ 取回 document 原文（Chroma 直接返回文本，不需要"回原文查"）
        │
        ▼
  ④ 拼 Prompt：system + 检索到的 k 段文本 + 用户问题
        │
        ▼
  ⑤ LLM 生成答案：调 API 1 次   ← ⚠️ 我口述时漏了这一步！RAG 的 G
        │
        ▼
  ⑥ 返回给用户 + 附出处（出处来自 metadata 的 source / page）
```

**查询阶段调几次 embedding API？1 次。**
- 文档侧：0 次（入库时算好存进去了，查询绝不重算，重算 = 烧冤枉钱）
- Query 侧：1 次（只把用户这一句话向量化）

**单次查询的成本大头 = LLM，不是 embedding**。优化顺序：先想怎么缩短喂给 LLM 的上下文（k 别贪大、chunk 别太肥），别纠结 embedding 那点钱。

**进阶变体（不是主流程，知道即可）**：
- **Small-to-Big / Parent Chunk**：小 chunk 检索（准），返回时给 LLM 它所属的大 chunk（上下文足）。解决 chunk 切小了准但信息不够、切大了够但不准的两难。
- **只存指针不存全文**：Chroma 只存 id + 向量 + 指针，原文放 MySQL/S3。适合省向量库空间或原文需频繁更新的场景。

### 重启后数据还在吗（persist 验证）✅ 已实测（09-11 补做）

**验证方式**：`persist_check.py`——用**两个不同进程**模拟真实「重启」（比在一个进程里读写更有说服力）：
```bash
python persist_check.py reset      # 清场（删掉 chroma_db）
python persist_check.py phase1     # 进程 A：建集合 → 插入 5 条（带 metadata）→ 查询
python persist_check.py phase2     # 进程 B：只读重开 → 验证数据还在 → 再查询
```

**实测结果**：

| 项 | 结果 |
|---|---|
| 环境 | chromadb **1.5.9** / text-embedding-v4 / 维度 **1024** |
| 进程 A | 初始 count = **0** → 写入后 count = **5** |
| 进程 B（新进程） | count = **5** → **✅ 持久化通过**（进程退出，数据没丢） |
| 距离度量 | `hnsw:space = cosine`（建库时显式指定） |
| 查询 1 | `我想买点牛奶和鸡蛋` → **0.0990** `牛奶和鸡蛋要买`（次位 0.6095 → 区分度很大） |
| 查询 2 | `部署的时候要注意什么` → **0.3837** `docker 部署要加健康检查` |

**磁盘结构（推演 → 实测确认，一模一样）**：
```
chroma_db/
├── chroma.sqlite3                        (208,896 B)
└── 712e565b-16b8-4745-8256-ce1981cbe87b/
    ├── data_level0.bin                   (423,600 B) ← HNSW 索引（向量 + 图结构）
    ├── header.bin                        (100 B)
    ├── length.bin                        (400 B)
    └── link_lists.bin                    (0 B)
```

**结论（周三自检的答案）**：
1. `PersistentClient(path=...)` **每次写自动落盘**，进程退出再开数据还在——这就是 W4 跨轮记忆 `SqliteSaver` 的同款心智：**状态必须落到进程之外**，进程内存靠不住。
2. **验证持久化必须用 `get_collection` 而不是 `get_or_create_collection`**——前者拿不到就报错（真检验），后者拿不到会帮你新建一个空库（假通过）。这是本次实测最实用的一条。

**⚠️ 实测顺带发现脚手架一个坑（已修）**：
`retrieval_app.py` 原本写 `get_or_create_collection(COLLECTION)` **没指定距离度量** → Chroma 默认 **l2**（实测 `col.configuration = {'hnsw': {'space': 'l2', 'ef_construction': 100, 'ef_search': 100, 'max_neighbors': 16, ...}}`），与笔记「本周用余弦」矛盾。
→ 已改为显式 `metadata={"hnsw:space": "cosine"}`。
→ **通用教训**：space 是 **collection 的元数据、建库时绑死**，事后改不了；一个 collection 里的向量必须同模型、同 space。

**metadata 过滤现场验证（顺手把自检答了）**：

| 查询 | 结果 |
|---|---|
| 不带 where | 5 条（按相似度） |
| `where={'kind':'note'}` | 只剩 2 条 `coding.md` / `travel.md` ✅ 过滤生效 |
| `where={'source':'shopping.md'}` | 只剩 1 条 ✅ |
| `where={'kind':'not_exist'}` | `documents=[]` ✅ **诚实返回空，不硬凑** |

→ 这是 metadata 用途①（**过滤**）的现场证据，也**提前验证了周末验收标准 3**（无匹配诚实返回）。

**另一个观察（容易踩）**：不指定 `embedding_function` 时，Chroma 会挂一个 `DefaultEmbeddingFunction`（本地 all-MiniLM-L6-v2）。
本流程全程传 `embeddings=` / `query_embeddings=`，所以没触发；但**若哪天只传 `query_texts=`，它会去下载本地模型**，且维度 384 ≠ 库里的 1024，直接报错。**结论：显式传向量，别依赖默认 EF。**

### 补充：Chroma 持久化目录里存了什么（Q5）

**新版（Chroma 0.4+ / 0.5+，本周用的）**：

```
chroma_db/
├── chroma.sqlite3           ← 管理型元数据（collection 定义 / segment 映射 / embedding queue）
│                               ⚠️ 不是业务 metadata！
└── <collection-uuid>/       ← 每个 collection 一个目录
    ├── data_level0.bin      ← HNSW 索引（向量 + 图结构）
    ├── header.bin
    ├── length.bin
    └── link_lists.bin
```

**为什么向量和 metadata / 原文分开存（按重要性排序）**：

1. **索引结构特殊：HNSW 图必须整体序列化**。hnswlib 把内存里的图整个 dump 成 bin，加载时整个 mmap 回内存。这种"整体存取"结构天然该独立成文件，没法跟行式数据混。
2. **访问模式完全不同（最关键）**：
   - 向量（HNSW 索引）：大块、连续、整体加载，常驻内存，一次 IO 几百 MB
   - 原文 / metadata：小、随机、按需读 k 条，冷数据，几十字节 × k
   - 混在一起 → 为了读 3 条原文得把整个大文件拖进内存
3. **写放大**（DB 经验秒懂）：向量几乎不变（只有换 embedding 模型才重建），原文/metadata 可能常改（加 tag、改 source、更新权限）。分开存 = 改一条 metadata 不用重写几百 MB 向量文件。类比 MySQL 里 BLOB 列和主表分开存。
4. **空间效率**（口述答对的那条，但排最后）：1024 维 float32 二进制 4 KB/条，文本形式 `[0.123, -0.456, ...]` 约 10~20 KB/条，差 3~5 倍且文本还要解析开销。

**检索时的精确读取顺序（两阶段）**：

```
① 加载 HNSW 索引到内存 → ANN 图遍历 → 得到候选 id + 距离
② 按 id 读 metadata → 做 tenant_id / 权限过滤   ← post-filter（Chroma 典型行为）
③ 按 id 读 document 原文 → 只取 k 条
④ 拼 Prompt → LLM
```

**工程常识**：
- `chroma_db/` 不入库（bin 大且二进制 diff 无意义），加进 `.gitignore`
- 但要提交**重建脚本**——向量是**可重建产物**（有原文 + embedding 模型 + 脚本就能重算）
- 区分**源数据**和**构建产物**，和 Java 里 `target/` 不入库但 `pom.xml` 入库同一条规则

### 回炉清单（本次测验暴露的 5 个洞，按优先级）

1. ⚠️ **persist 机制**（Q2 完全没答出来）—— W4/W5 跨轮记忆的命门。记住：`PersistentClient(path=...)` 自动落盘。
2. ⚠️ **RAG 的 G**（Q4 漏了 LLM 生成）—— 检索出 k 段文本 ≠ 答案，中间必须有拼 Prompt + LLM 生成。**本次最大的洞**。
3. **metadata 的排序加权 + 幂等去重**（Q3 漏）—— 幂等去重（content_hash）直接省 API 钱。
4. **多租户的开销模型**（Q3 论据未展开）—— 拆 collection = O(租户数) 内存，filter = O(1)。架构决策题要能讲出**代价**。
5. **分开存的真正原因**（Q5 只答到"省空间"这个最次要理由）—— 访问模式 / HNSW 图结构 / 写放大，空间效率排最后。

**共性诊断**：回答稳定停在"是什么"这一层，很少往下推到"所以呢 / 代价是什么"。下次口述强制自己每个概念后面补一句"**所以呢？代价是什么？**"——这就是 B 到 A 的差距。

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
