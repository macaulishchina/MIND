# MIND — AI Memory Quality Layer

MIND 是一个 AI 记忆质量层（Memory Quality Layer），核心目标不是"让 AI 有记忆"，
而是"让 AI 的记忆可靠、可控、长期可用"。

## 核心特性（MVP）

- **记忆 CRUD**：add / search / get / get_all / update / delete / history
- **LLM 两步决策**：从对话中提取事实 → 判断 ADD / UPDATE / DELETE / NONE
- **置信度标注**：每条记忆在写入时标注 confidence（0-1）
- **来源追踪**：记录原始对话片段（source_context）
- **版本追踪**：UPDATE 操作记录 version_of 关系
- **逻辑删除**：status=active/deleted，已删除记忆不参与检索
- **操作历史**：SQLite 记录完整操作日志

## 与 mem0 的差异

| 维度 | mem0 | MIND |
|------|------|------|
| 写入质量 | LLM 一次性判断 | LLM 判断 + confidence 标注 |
| 更新策略 | 直接覆盖 | 新建记忆 + version_of 引用 |
| 来源追踪 | 无 | source_context 保留原始对话 |
| 状态管理 | 无状态机 | active / deleted 两状态 |

## 快速开始

### 安装依赖

```bash
pip install -r requirements.txt
```

### 设置环境变量

```bash
# 通用 API Key（推荐，适用于所有 provider）
export MIND_API_KEY="your-api-key-here"

# 也支持 provider 专用变量（按 MIND_API_KEY → 专用变量 的优先级解析）
# export OPENAI_API_KEY="sk-xxx"
# export ANTHROPIC_API_KEY="sk-ant-xxx"
# export GOOGLE_API_KEY="AIza-xxx"

# 可选：自定义 API 域名（代理场景）
# export MIND_BASE_URL="https://my-proxy.com"
```

### 基本用法

```python
from mind import Memory, MemoryConfig

# 零配置：env 中设好 MIND_API_KEY 即可
m = Memory()

# 写入记忆
m.add(
    messages=[{"role": "user", "content": "我喜欢黑咖啡"}],
    user_id="alice",
)

# 检索记忆
results = m.search(query="饮品推荐", user_id="alice")
for r in results:
    print(f"[{r.score:.3f}] {r.content} (confidence={r.confidence})")

# 查看所有记忆
all_memories = m.get_all(user_id="alice")

# 手动更新
m.update(memory_id=results[0].id, content="我现在只喝美式")

# 删除（逻辑删除）
m.delete(memory_id=results[0].id)

# 查看操作历史
history = m.history(memory_id=results[0].id)
```

### 自定义配置

```python
from mind import Memory, MemoryConfig
from mind.config import LLMConfig

# 方式 1：顶层传 key，自动下沉到 llm 和 embedding
m = Memory(MemoryConfig(api_key="sk-xxx"))

# 方式 2：切换 LLM 协议
m = Memory(MemoryConfig(
    llm=LLMConfig(provider="anthropic"),     # 用 Claude
))

m = Memory(MemoryConfig(
    llm=LLMConfig(provider="google"),        # 用 Gemini
))

# 方式 3：LLM 和 Embedding 用不同的 key
from mind.config import EmbeddingConfig
m = Memory(MemoryConfig(
    llm=LLMConfig(provider="anthropic", api_key="sk-ant-xxx"),
    embedding=EmbeddingConfig(api_key="sk-openai-xxx"),
))

# 方式 4：自定义代理域名
m = Memory(MemoryConfig(
    base_url="https://my-proxy.com",         # 自动下沉到 llm + embedding
))
```

## 运行测试

```bash
# 仅运行不需要 API 的单元测试
pytest tests/test_storage.py -v

# 运行完整端到端测试（需要 API Key）
export MIND_API_KEY="your-key"
pytest tests/ -v
```

## 项目结构

```
mind/
├── __init__.py           # 包导出
├── memory.py             # Memory 主类（系统入口）
├── config.py             # 配置和数据模型
├── prompts.py            # LLM Prompt 模板
├── storage.py            # SQLite 历史记录
├── utils.py              # 工具函数
├── llms/                 # LLM 层（Factory + OpenAI / Anthropic / Google）
├── embeddings/           # Embedding 层（Factory + OpenAI）
└── vector_stores/        # 向量存储层（Factory + Qdrant）
tests/
├── conftest.py           # 共享 fixtures
├── test_storage.py       # SQLite 测试
└── test_memory.py        # 端到端测试
```

## 技术栈

| 组件 | 选择 |
|------|------|
| 语言 | Python |
| LLM | OpenAI / Anthropic / Google（三协议，默认 OpenAI） |
| Embedding | OpenAI text-embedding-3-small |
| 向量存储 | Qdrant（开发用 in-memory） |
| 历史记录 | SQLite |

## 路线图

- **v1（当前）**：最小闭环 — CRUD + 置信度 + 来源追踪 + 版本追踪
- **v1.5**：质量增强 — confidence 降权、时间衰减、记忆合并
- **v2**：检索增强 — 查询分解、混合检索、完整状态机
- **v3**：关系增强 — 图记忆、实体关系、记忆压缩

## License

MIT
