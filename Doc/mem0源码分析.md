# mem0 源码分析

基于 mem0 项目源码（vendor/mem0）的深度分析，不是基于文档或猜测。

## 1. 项目概况

- 149 个 Python 文件
- 核心 Memory 类约 2500 行（`mem0/memory/main.py`）
- 支持 27 种向量库、15+ LLM、15 种 Embedding、5 种图数据库、5 种 Reranker

## 2. 核心架构

### 目录结构

```
mem0/
├── memory/          # 核心记忆系统
│   ├── main.py      # Memory 主类（2500+ 行）
│   ├── base.py      # MemoryBase 抽象类
│   ├── graph_memory.py   # Neo4j 图记忆
│   ├── storage.py        # SQLite 历史追踪
│   └── utils.py          # 事实解析工具
├── configs/         # 配置与 prompt
│   ├── base.py      # MemoryConfig, MemoryItem 模型
│   ├── prompts.py   # 核心 prompt 模板
│   └── enums.py     # 记忆类型枚举
├── llms/            # 15+ LLM 实现
├── embeddings/      # 15 种 Embedding 实现
├── vector_stores/   # 27 种向量库实现
├── graphs/          # 图数据库工具和配置
├── reranker/        # 5 种 Reranker 实现
└── utils/           # Factory 模式
    └── factory.py   # LlmFactory, EmbedderFactory, VectorStoreFactory...
```

### 数据模型

MemoryItem 极其简洁（`mem0/configs/base.py`）：

```python
class MemoryItem(BaseModel):
    id: str
    memory: str                       # 记忆内容（纯文本）
    hash: Optional[str]              # MD5 去重
    metadata: Optional[Dict]         # 自由元数据
    score: Optional[float]           # 搜索相关度
    created_at: Optional[str]
    updated_at: Optional[str]
```

元数据中提升到顶层的字段：`user_id`、`agent_id`、`run_id`、`actor_id`、`role`。

没有 status 状态机，没有 confidence，没有 importance，没有 version_of，没有 source 追踪。

### 记忆类型

```python
class MemoryType(Enum):
    SEMANTIC = "semantic_memory"
    EPISODIC = "episodic_memory"
    PROCEDURAL = "procedural_memory"
```

实际使用中，只有 `procedural_memory` 作为特殊类型处理（Agent 执行历史），其余不做区分。

## 3. 核心流程

### 写入流程（add）

```
消息输入
  → parse_messages() 格式化对话
  → LLM 调用：USER_MEMORY_EXTRACTION_PROMPT 提取事实（JSON 数组）
  → 对每条新事实：
      → embedding_model.embed(fact)
      → vector_store.search(fact, limit=5)  # 搜索相似旧记忆
      → LLM 调用：get_update_memory_messages()
        → 返回 ADD / UPDATE / DELETE / NONE 决策
      → 执行决策
  → 并行：如果启用了图记忆，同时写入图数据库
```

关键设计：**两次 LLM 调用**完成提取 + 去重 + 冲突处理。

### 检索流程（search）

```
查询
  → embedding_model.embed(query, "search")
  → vector_store.search(query, vectors, limit, filters)
  → 可选：reranker.rerank(query, results, limit)
  → 并行：如果启用图记忆，同时搜索图
  → 返回结果
```

纯向量相似度 + 可选重排。没有查询分解、没有类型感知、没有多路径召回。

### 更新流程（update）

```
update(memory_id, new_data)
  → embedding_model.embed(new_data, "update")
  → vector_store.update(memory_id, new_vector, new_payload)
```

直接覆盖，旧内容只在 SQLite history 表留日志。无版本链。

### 删除流程（delete）

```
delete(memory_id)
  → 清理图数据库中的相关实体
  → vector_store.delete(memory_id)
```

物理删除，不可恢复（除了 SQLite history）。

## 4. Prompt 工程

mem0 最有价值的部分。位于 `mem0/configs/prompts.py`。

### 事实提取 Prompt

分两种：
- `USER_MEMORY_EXTRACTION_PROMPT`：从用户消息中提取（偏好、个人信息、计划、健康、职业等）
- `AGENT_MEMORY_EXTRACTION_PROMPT`：从 AI 回复中提取（Agent 能力、风格、知识领域等）

输出格式：`{"facts": ["fact1", "fact2", ...]}`

### 更新决策 Prompt

`DEFAULT_UPDATE_MEMORY_PROMPT` 是核心中的核心：

- 给 LLM 提供已有记忆列表（用临时 ID 防止 UUID 幻觉）
- 给 LLM 提供新提取的事实
- LLM 返回操作列表：

```json
{"memory": [
  {"id": "0", "text": "...", "event": "ADD"},
  {"id": "1", "text": "...", "event": "UPDATE", "old_memory": "..."},
  {"id": "2", "text": "...", "event": "DELETE"},
  {"id": "3", "text": "...", "event": "NONE"}
]}
```

决策规则：
- **ADD**：全新信息
- **UPDATE**：同概念但更详细（"likes pizza" → "loves cheese and chicken pizza"）
- **DELETE**：矛盾或过时
- **NONE**：已存在或不相关

### Procedural Memory Prompt

`PROCEDURAL_MEMORY_SYSTEM_PROMPT`：专为 Agent 设计，记录执行历史，结构化为任务目标 → 操作序列 → 结果 → 元数据。

## 5. 图记忆实现

位于 `mem0/memory/graph_memory.py`，支持 Neo4j / Memgraph / Neptune / Kuzu / Apache AGE。

### 工作方式

1. LLM 从文本提取实体和关系（通过 `mem0/graphs/tools.py` 定义的工具）
2. 搜索图中已有相似实体（阈值 0.7）
3. 删除矛盾关系（设 `valid=false` 软删除）
4. 添加新实体和关系
5. 搜索时用 BM25 对关系重排

### 实体工具定义

```python
EXTRACT_ENTITIES_TOOL = {"entities": [{"entity": "...", "entity_type": "..."}]}
RELATIONS_TOOL = {"entities": [{"source": "...", "relationship": "...", "destination": "..."}]}
```

## 6. 设计模式

### Factory 模式

所有组件通过 Factory 动态创建（`mem0/utils/factory.py`）：

```python
class LlmFactory:
    provider_to_class = {
        "openai": ("mem0.llms.openai.OpenAILLM", OpenAIConfig),
        "anthropic": ("mem0.llms.anthropic.AnthropicLLM", AnthropicConfig),
        # ... 15+ providers
    }
```

`EmbedderFactory`、`VectorStoreFactory`、`GraphStoreFactory`、`RerankerFactory` 同理。

### 三维会话作用域

每个操作都可以用 `user_id` / `agent_id` / `run_id` 任意组合来限定范围。

### 历史追踪

SQLiteManager（`mem0/memory/storage.py`）记录每次 ADD/UPDATE/DELETE 操作，但只用于 `history()` 查询，不参与运行时决策。

## 7. mem0 做得好的地方

1. **LLM 做决策引擎** — 两次 LLM 调用解决提取 + 去重 + 冲突，不写规则引擎
2. **数据模型极简** — 7 个字段够用就行，复杂度推迟到需要时再加
3. **Factory 模式** — 换后端改一行配置，不改业务代码
4. **图记忆并行** — 向量记忆和图记忆用 concurrent.futures 并行执行
5. **Prompt 工程精细** — 提取 prompt 分类清晰、更新 prompt 用临时 ID 防幻觉
6. **会话作用域灵活** — user/agent/run 三维组合，天然支持多场景

## 8. mem0 的结构性缺陷

### 缺陷一：无纠错机制

LLM 提取错误的事实后，永远不会被自动修正。没有 confidence，没有来源上下文，无法事后验证。

### 缺陷二：无遗忘机制

翻遍源码，没有任何衰减、过期、主动遗忘逻辑。记忆只增不减（除非被新事实触发 DELETE）。长期运行后记忆污染不可避免。

### 缺陷三：更新即覆盖

UPDATE 操作直接覆盖旧内容。SQLite history 只是日志，不支持回滚。无法追踪信念演化。

### 缺陷四：检索过于简单

纯向量相似度 + 可选重排。没有查询分解，没有类型感知，没有任务意图理解。

### 缺陷五：去重依赖 Top-5

每次写入只搜索最相似的 5 条旧记忆做比对。如果同一事实的不同表述在向量空间中距离较远，就会产生重复。

## 9. 我们应该吸收什么

| mem0 的做法 | 吸收方式 |
|------------|---------|
| LLM 两步决策（提取 + 操作判断） | 作为 v1 基线流程 |
| ADD/UPDATE/DELETE/NONE 框架 | 直接采纳，在此基础上叠加版本记录 |
| 极简数据模型 | 核心层对齐 mem0 简洁度，增强层保留我们的字段 |
| Factory 模式 | 用于 LLM/Embedding/VectorStore 切换 |
| Prompt 中用临时 ID 防幻觉 | 直接借鉴 |
| 并行执行向量+图操作 | v2 引入图记忆时采纳 |

## 10. 我们不应该跟随什么

| mem0 的做法 | 不跟随的原因 |
|------------|------------|
| 无 confidence | 长期系统必须知道"有多确定" |
| UPDATE 直接覆盖 | 保留旧版本引用，成本极低收益长期 |
| 无 source 追踪 | 可解释性的基础 |
| 27 种向量库适配 | 我们不是平台产品，2-3 种够用 |
| 无遗忘机制 | 这正是我们的差异化方向 |
