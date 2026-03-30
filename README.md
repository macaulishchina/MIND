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
- **操作历史**：支持同库 Postgres history，也保留 SQLite history backend
- **多协议 LLM**：支持 OpenAI / Anthropic / Google 三协议，可自定义 provider
- **TOML 配置**：所有配置集中在 `mind.toml`，支持构造时 override

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置 mind.toml

在项目根目录的 `mind.toml` 中填入你的 API Key 和 Embedding 服务地址：

```toml
[llm]
provider = "deepseek"            # 选择要用的 provider

[llm.deepseek]
template = "llm.openai"          # 使用 OpenAI 协议
api_key  = "sk-your-key"
base_url = "https://api.deepseek.com"
model    = "deepseek-chat"

[embedding]
protocols = "openai-embedding"
model     = "text-embedding-3-small"
api_key   = "sk-your-key"
base_url  = "https://api.openai.com"
dimensions = 1536
```

### 3. 测试连接

```bash
python -c "from mind.config import ConfigManager; from mind.llms.factory import LlmFactory; cfg = ConfigManager().get(); llm = LlmFactory.create(cfg.llm); print(llm.generate([{'role':'user','content':'say hi'}]))"
```

### 4. 基本用法

```python
from mind import Memory
from mind.config import OwnerContext

# 零配置初始化（读取 mind.toml）
m = Memory()

# 写入记忆（兼容旧接口）
m.add(
    messages=[{"role": "user", "content": "我喜欢黑咖啡"}],
    user_id="alice",
)

# 写入记忆（owner-centered 新接口）
m.add(
    messages=[{"role": "user", "content": "My friend Green is a football player"}],
    owner=OwnerContext(
        external_user_id="alice",
        display_name="Alice",
        channel="web",
    ),
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

### 5. 构造时 Override

`Memory` 构造函数支持 `overrides` 参数，一次性覆盖 TOML 配置：

```python
# 构造时指定不同的模型
m = Memory(overrides={"llm": {"provider": "openai"}})

# 构造时调高 temperature
m = Memory(overrides={"llm": {"temperature": 0.5}})
```

所有依赖对象（LLM、Embedder 等）在构造时创建并固定，后续方法调用不再接受配置变更。
若需不同配置，请创建新的 `Memory` 实例。

当前 `add()` 流程会先把对话提取成原子事实，再归一化为 owner-centered 的结构化 envelope，
最终以结构标签式文本落库，例如：

- `[self] name=John`
- `[self] preference:general=black coffee`
- `[friend:green] relation_to_owner=friend`
- `[friend:green] occupation=football player`

## 配置说明

所有配置集中在 `mind.toml`，无环境变量依赖。

```
mind.toml
├── [llm]                    ← 通用设置：provider + temperature
│   ├── [llm.extraction]     ← 可选：抽取阶段覆盖
│   ├── [llm.normalization]  ← 可选：归一化阶段覆盖
│   ├── [llm.decision]       ← 可选：决策阶段覆盖
│   ├── [llm.openai]         ← 完整 provider 定义
│   ├── [llm.anthropic]      ← 完整 provider 定义
│   ├── [llm.google]         ← 完整 provider 定义
│   └── [llm.deepseek]       ← template 继承 llm.openai + 覆盖差异
├── [embedding]              ← Embedding 独立配置
├── [vector_store]           ← 向量存储配置（支持 pgvector / Qdrant）
├── [history_store]          ← 历史记录配置（支持 Postgres / SQLite）
└── [retrieval]              ← 检索参数
```

切换 LLM 只需改一行：`provider = "openai"` / `"anthropic"` / `"deepseek"` 等。

## 运行测试

```bash
# 离线单元测试（无需 API Key）
python -m pytest tests/test_storage.py -v

# Memory 流程测试（由 mindt.toml 切换到 fake LLM / fake embedding，无需 API Key）
python -m pytest tests/test_memory.py -v

# Extraction 评估
python tests/eval/runners/eval_extraction.py --toml mindt.toml --pretty
```

说明：
- 更详细的 extraction 评估说明、真实 LLM 运行方式和报告归档建议见 `Doc/evolution/memory.add/eval_framework.md`。

## 项目结构

```
mind.toml                         # 所有配置的唯一来源
mind/
├── __init__.py                   # 包导出
├── memory.py                     # Memory 主类（系统入口）
├── prompts.py                    # LLM Prompt 模板
├── storage.py                    # History store 实现与工厂
├── utils.py                      # 工具函数
├── config/                       # 配置子系统（独立模块）
│   ├── manager.py                #   ConfigManager（加载、合并、解析）
│   ├── schema.py                 #   配置结构定义
│   └── models.py                 #   数据模型（MemoryItem 等）
├── llms/                         # LLM 层（OpenAI / Anthropic / Google）
├── embeddings/                   # Embedding 层（OpenAI）
└── vector_stores/                # 向量存储层（pgvector / Qdrant）
tests/
├── conftest.py                   # 共享 fixtures
├── test_storage.py               # SQLite 测试
└── test_memory.py                # 端到端测试
```

## 技术栈

| 组件 | 选择 |
|------|------|
| 语言 | Python |
| LLM | OpenAI / Anthropic / Google 三协议 + 自定义 provider |
| Embedding | OpenAI 兼容协议 |
| 向量存储 | PostgreSQL + pgvector（默认） / Qdrant |
| 历史记录 | PostgreSQL / SQLite |
| 配置 | TOML（mind.toml） |

## 路线图

- **v1（当前）**：最小闭环 — CRUD + 置信度 + 来源追踪 + 版本追踪
- **v1.5**：质量增强 — confidence 降权、时间衰减、记忆合并
- **v2**：检索增强 — 查询分解、混合检索、完整状态机
- **v2.5**：批处理与评估成本优化 — 支持供应商 Batch API 接入，用于 extraction / decision 的离线评估、批量回灌和大规模实验，降低 token 成本并提升吞吐
- **v3**：关系增强 — 图记忆、实体关系、记忆压缩

## License

MIT
