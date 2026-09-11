# metadata 设计专题 —— 从「表字段」到「检索契约」

> **来源**：2026-09-11 晚（W5 周三 persist 验证后延伸讨论）整理
> **适用**：W5 向量库落地、W6 RAG 基础流程（chunk + metadata 是 RAG 的地基）
> **状态**：⚠️ **AI 草稿**——按 v3 §5.6 规则需在 2 天内改成自己的版本（见文末「清偿清单」）

---

## 一、metadata 在一条记录里的位置

Chroma（以及多数向量库）里一条记录 = **四元组**：

| 字段 | 内容 | 谁产出 |
|---|---|---|
| `id` | `"s0"` | 你 |
| `document` | 原文 / 正文 | 你 |
| `embedding` | `[0.021, -0.13, ...]`，1024 维 | embedding 模型 |
| **`metadata`** | `{"source": "schedule.md", "kind": "reminder"}` | **你** |

**关键前提：`source` / `kind` 不是 Chroma 生成的，是你代码里填的。** Chroma 不知道 `schedule.md` 是什么、也不认识 `reminder` 的含义——它只做 KV 搬运。

对照两处代码就能看清「自动」是假象：

```python
# persist_check.py —— 硬编码的测试数据（schedule.md 这个文件其实不存在）
SAMPLES = [("提醒我明天9点开会", {"source": "schedule.md", "kind": "reminder"}), ...]

# retrieval_app.py —— 从文件名自动填（看起来"自动"，本质仍是你的代码在填）
chunks.append((para.strip(), {"source": os.path.basename(path)}))
```

**唯一约束**：value 只能是 `str / int / float / bool`，**不能嵌套 dict / list**。

---

## 二、两层同名物，别混

| | 是什么 | 在哪 | 谁关心 |
|---|---|---|---|
| **业务 metadata** | 你填的附加信息：`source` / `kind` / `tenant_id` | 跟着每条记录走 | 你的检索代码（过滤、溯源） |
| **管理型 metadata** | collection 定义、segment 映射、embedding queue | `chroma.sqlite3` 里 | Chroma 自己 |

> `chroma_db/chroma.sqlite3` **不是**业务 metadata——文件名叫 sqlite3 容易让人误以为"数据都在里面"。

---

## 三、metadata ≠ 表字段：缺了 DDL 兜底

| 维度 | MySQL 表字段 | 向量库 metadata |
|---|---|---|
| 类型系统 | `date` / `decimal` / `enum` / `NOT NULL` / `FK`，写错当场报错 | 只有 `str/int/float/bool`，**无 date 类型**（时间存 int 时间戳），**不能嵌套** |
| 是否强制 | DDL 强制，不合规进不去 | **schema-less —— 没人拦你** |
| 变更成本 | `ALTER TABLE` 秒级 | metadata 还能 update，但 **embedding 改不了**（换模型 = 整库重建） |
| 索引 | 不建索引最多慢，结果还是对的 | 多数实现过滤走 **post-filter**，无 payload index 时在内存筛；**Qdrant 才有 pre-filter** |
| 隔离 | 可用 DB 层 RLS / 视图兜底 | **只能靠代码自觉** |
| 约束 | `CHECK` / 默认值 / 外键 | 无 |

**一句话**：

> **表的错误是「编译期错误」，metadata 的错误是「运行期且静默」的。**

—— 笔记里那条安全红线「filter 是逻辑隔离，漏写一个 where 就串数据」，根因就在这。表时代有 MyBatis 租户拦截器兜底；向量库没有那层，**兜底得自己在数据访问层造一个**。

---

## 四、字段从哪来：由 query pattern 反推（不是实体属性）

| 你会怎么查（query pattern） | 所以必须存什么字段 |
|---|---|
| 只看某个租户的数据 | `tenant_id` |
| 按时间衰减排序 | `created_at`（int 时间戳） |
| 重复入库不重复付费 | `content_hash` |
| 回答时能给出处 | `source` / `page` / `chunk_index` |
| 只搜某一类文档 | `doc_type` / `kind` |

**分水岭在这里**：`content_hash` 这个字段，任何「文档实体」的属性描述里都不会有它——它纯粹为工程目标（幂等判重、省 embedding 的 API 钱）存在。

| | 描述的是 | 谁驱动 |
|---|---|---|
| 表字段 | **数据模型**（实体是什么样） | 业务实体 |
| metadata | **检索契约 + 运维抓手**（我打算怎么用它） | 查询模式 + 工程约束 |

> 更准的定位：**metadata 不是「表字段的弱化版」，而是「表字段 + 应用层查询逻辑的合并体」。** 表时代这两件事分居 DDL 和 SQL；向量库时代它们挤进了同一个地方。

---

## 五、它为什么是核心：可逆性分层

| 层级 | 包含 | 有没有标准答案 |
|---|---|---|
| **不可逆**（错了要重建全库） | `id 设计` · `chunk 边界` · `metadata schema` | **无参考**，只能靠业务理解 |
| **半可逆**（要重灌一遍） | embedding 模型 · chunk 参数 · 距离度量 | 弱参考，有经验区间 |
| **可逆**（随时能改） | 向量库选型 · HNSW 参数 · top-k · rerank | 有参考，能查 benchmark |

**关键纠正**：metadata 是核心，**不是因为它"影响性能"**。

- 性能的直接杠杆是**向量维度 / HNSW 的 m·ef / 量化 PQ·SQ / 分片**——这些**反而都有参考**
- metadata 影响性能的**唯一路径是「过滤策略」**：post-filter（Chroma，选择性高时大量浪费）vs pre-filter（Qdrant payload index）
- 所以准确说法：**metadata 决定「过滤效率」，而过滤只是检索链路的一环**

它真正的核心地位来自 **「不可逆 × 无参考」这个交集的唯一住户**。

**另一个要防的陷阱**：「其他选项都有参考」≠ 可以抄。MTEB 排行榜是在**通用语料**上测的，你的场景是中文备忘录检索——**有参考降低的是决策成本，不是决策责任**。

---

## 六、成本不对称原则（最实用的一条）

| 判断失误 | 代价 |
|---|---|
| **漏存一个字段** | 全量重跑 ingestion + **重新花一次 embedding 的钱** |
| 多存一个字段 | 几字节存储 + 一点点写入开销 |

> **原则：不确定要不要存的字段，一律存。**

这个不对称，才是 metadata「不可逆」的真正来源——**选错向量库你能换，调错 HNSW 参数你能调，但漏了字段你得重新掏钱。**

---

## 七、收敛：向量库工程的核心 = 定义「检索契约」

> 契约有三条：
> 1. **chunk** —— 检索的原子单位是什么（**比 metadata 更前置**）
> 2. **metadata** —— 按什么维度过滤、排序、溯源
> 3. **评估** —— 怎么判定前两条选对了

三条都在「不可逆 + 无参考」层。

**chunk 为什么更前置**：chunk 决定「检索单元是什么」，metadata 只是「给这个单元贴标签」。如果把「问题」和「答案」切进了不同 chunk，metadata 再完美也检索不到正确答案——而「按段落 / 按标题层级 / 按语义 / 固定长度」这个选择，同样**没有标准答案**。

**评估为什么是第三条**：**它是唯一能把「没有参考」变成「有自己的参考」的手段。** 这就是为什么计划从 W2 的 10 条用例一路堆到 W9 的 50+ 条 + Langfuse——它从来不是为了"留个记录"，而是为了**给这些无参考决策提供判据**。没有它，前两条契约就只能靠感觉拍。

---

## 八、落地：`build_metadata()` 模板

因为 schema-less，「设计」这件事从 DDL 挪到了代码里。要自己把 DDL 补回来：

```python
SCHEMA_VERSION = 1

METADATA_SCHEMA = {
    # 字段名          (类型,  必填)   —— 这就是"没有 DDL 的 DDL"
    "doc_id":         (str,  True),
    "chunk_index":    (int,  True),
    "content_hash":   (str,  True),
    "source":         (str,  True),
    "tenant_id":      (str,  True),
    "created_at":     (int,  True),   # ⚠️ 无 date 类型 → 统一 int 时间戳
    "schema_version": (int,  True),   # 未来做"无 DDL 迁移"的唯一抓手
    "doc_type":       (str,  False),
}


def build_metadata(tenant_id, **kw):
    """metadata 的唯一构造入口——把缺失的 DDL 用代码补回来。

    tenant_id 由数据访问层强制注入，**调用方无权自行指定**：
    这一层就是向量库版的"多租户拦截器"（对应 MyBatis 租户插件）。
    """
    kw["tenant_id"] = tenant_id

    for name, (typ, required) in METADATA_SCHEMA.items():
        if required and name not in kw:
            raise ValueError(f"[metadata] 缺必填字段 {name!r}（schema v{SCHEMA_VERSION}）")
        if name in kw and not isinstance(kw[name], typ):
            raise TypeError(f"[metadata] {name!r} 应为 {typ.__name__}，"
                            f"实际 {type(kw[name]).__name__}")

    return {"schema_version": SCHEMA_VERSION, **kw}
```

**四条配套约定**：
1. **唯一入口**：所有 ingestion 必须走 `build_metadata()`，不许各处自己拼 dict
2. **必填字段强制注入**：`tenant_id` 绝不让调用方自己传
3. **命名与取值约定写死**：统一 `snake_case`、时间统一 int 时间戳、枚举用白名单常量
4. **`schema_version` 必带**：将来加字段时能识别哪些是旧数据

---

## 九、清偿清单（我自己要做的事）

> 按 v3 §5.6：本文是 AI 草稿，**2 天内**改成自己的版本。建议优先改这几处：

- [ ] **第一节**：用自己的话讲清「metadata 是你填的、不是库生成的」，并换成我自己的场景例子（不要用 schedule.md/reminder 这种测试数据）
- [ ] **第三节**：把「编译期 vs 运行期且静默」这个对比，用我在 LLM 平台遇到的真实案例替代（配置漏填导致的静默串数据）
- [ ] **第五节**：自己画一遍「可逆性分层」三层，判断我自己的项目里哪些决策落在哪层
- [ ] **第六节**：把「成本不对称」拆成具体数字（100 篇文档重跑一次 embedding ≈ 多少次调用 / 多少钱）
- [ ] **第八节**：`build_metadata()` 自己手写一遍（可参照，但不许复制粘贴），并说出每一行为什么要这么写
- [ ] 确认自己能否不看文档、口头讲出「检索契约三条款」，讲不全就补进 `考核/薄弱点台账.md`
