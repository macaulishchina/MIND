# Change Proposal: add() Phase Evaluation, Extraction Hardening, and Black-Box Holdout

> Change ID: **add-phase-optimization**
> Status: **Completed** · Date: 2026-03-28 · Author: agent
> Type: **feature** · Spec impact: **update required** · Verification: **feature**
>
> 本变更在不扩大 MVP 产品边界的前提下，完成两件事：
> 1. 把 `Memory.add()` 的阶段划分和评估方式写清楚
> 2. 先落一批 extraction 阶段的稳健性增强：prompt 重构、结果规范化、单次调用温度控制
> 3. 增加一个独立的 50 条 extraction 黑盒 holdout 数据集，用于定期评估整体表现而不是日常 case-by-case 调参

## Reality Check

- 提取阶段可以独立优化，但它的收益会受到后续 decision 逐条处理模式的限制
- 当前 `confidence` 仍主要用于记录，不参与 decision，因此本轮只做校准增强，不扩大其运行时职责
- 本轮不引入新的 first-class memory types，也不改变主返回 schema，避免把 prompt 优化和数据模型扩张绑死
- 黑盒 holdout 集必须与默认难度分层回归集隔离，否则每次真实 LLM 全量回归的成本会显著上升，也会削弱它作为独立表现观测集的价值

## Acceptance Signals

- extraction 可通过单独测试验证温度覆盖和结果规范化行为
- prompt 重构后不破坏现有 `add/search/update/delete` 基本回归
- `Memory.add()` 仍保持 `{text, confidence}` 的兼容输出契约
- 50 条黑盒数据集覆盖 easy / medium / hard / tricky 各层难度与主要 case 类型，并可通过显式 `--dataset` 运行而不进入默认 top-level 扫描

## Verification Plan

- 运行聚焦测试：`tests/test_extraction.py`、`tests/test_eval_extraction.py` 与 `tests/test_memory.py`
- 手工检查 `Doc/evolution/memory.add/` 下文档是否与实现一致
- 对独立黑盒数据集做至少一次 runner smoke，确认 schema、路径和报告输出正常

## Approval

- [x] Proposal reviewed
- [x] Important conflicts and feasibility risks surfaced
- [x] Spec impact confirmed
- [x] Ready to finalize tasks and implement

---

## 1. add() 的阶段划分

add 方法可以清晰地分为 **4 个阶段**，每个阶段有独立的职责和可观测的输入/输出：

```
add(messages, user_id)
│
├─ Stage 1: EXTRACTION（事实提取）
│  输入: 原始对话 messages
│  执行: 1× LLM 调用（FACT_EXTRACTION_SYSTEM_PROMPT）
│  输出: [{text, confidence}, ...]
│  关键质量维度: 提取的完整性、粒度、置信度准确性
│
├─ Stage 2: RETRIEVAL（相似记忆检索）
│  输入: 每个 fact 的文本
│  执行: N× EMB + N× VEC.search（并发）
│  输出: 每个 fact 对应的 top-K 相似记忆列表
│  关键质量维度: 召回率、相关性排序
│
├─ Stage 3: DECISION（操作决策）
│  输入: 每个 fact + 其相似记忆列表
│  执行: N× LLM 调用（UPDATE_DECISION_SYSTEM_PROMPT）
│  输出: 每个 fact 的 action（ADD/UPDATE/DELETE/NONE）+ reason
│  关键质量维度: 决策准确率、冲突处理能力
│
└─ Stage 4: EXECUTION（执行写入）
    输入: action 列表
    执行: VEC.insert/update/delete + DB.insert（并发）
    输出: List[MemoryItem]
    关键质量维度: 数据一致性、写入正确性
```

### 各阶段代码位置

| Stage | 方法 | 行号 | LLM调用 | 可并发 |
|-------|------|------|---------|--------|
| 1. EXTRACTION | `_extract_facts()` | 405-418 | 1次 | 否（串行） |
| 2. RETRIEVAL | `_process_fact()` 前半 | 427-439 | 0次 | ✅ 已并发 |
| 3. DECISION | `_process_fact()` 后半 | 441-489 | N次 | ✅ 已并发 |
| 4. EXECUTION | `_execute_add/update` | 491-540 | 0次 | ✅ 已并发 |

### ⚠️ 当前耦合问题

Stage 2+3+4 被绑在 `_process_fact()` 方法内，无法独立评估。
**阶段解耦是优化的前提**——需要先拆分方法，才能对单个阶段做精确的基准测试。

---

## 2. 各阶段的测试评估体系

### 核心原则

- **每个阶段独立评估**：修改 Stage 1 的 prompt 时，不需要跑全流程
- **量化指标**：每个阶段有明确的数值指标和目标值
- **可迭代**：评估结果存档，修改前后可对比
- **数据驱动**：用 JSON 数据集描述测试用例，与代码解耦

### 目录结构

```
tests/
├── eval/
│   ├── datasets/
│   │   ├── extraction_easy_cases.json
│   │   ├── extraction_medium_cases.json
│   │   ├── extraction_hard_cases.json
│   │   ├── extraction_tricky_cases.json
│   │   ├── retrieval_cases.json      # Stage 2 测试集
│   │   ├── decision_cases.json       # Stage 3 测试集
│   │   └── e2e_golden.json           # 端到端测试集
│   ├── runners/
│   │   ├── eval_extraction.py        # Stage 1 评估脚本
│   │   ├── eval_retrieval.py         # Stage 2 评估脚本
│   │   ├── eval_decision.py          # Stage 3 评估脚本
│   │   └── eval_e2e.py               # 端到端评估脚本
│   └── reports/
│       └── {timestamp}_report.json   # 评估结果存档
```

---

### 2.1 Stage 1: EXTRACTION 评估

**评估目标**：给定对话，提取出的 facts 是否完整、准确、粒度合理。

#### 数据集结构

```json
[
  {
    "id": "ext-001",
    "description": "多事实简单陈述",
    "input": "我叫张三，今年28岁，在网易工作，喜欢喝黑咖啡",
    "expected_facts": [
      {"text_contains": "张三", "confidence_range": [0.9, 1.0]},
      {"text_contains": "28", "confidence_range": [0.9, 1.0]},
      {"text_contains": "网易", "confidence_range": [0.9, 1.0]},
      {"text_contains": "咖啡", "confidence_range": [0.9, 1.0]}
    ],
    "should_not_extract": ["AI", "assistant"],
    "expected_count_range": [3, 5],
    "difficulty": "easy"
  },
  {
    "id": "ext-002",
    "description": "假设性陈述不应提取",
    "input": "如果我以后去日本的话，可能会尝试寿司",
    "expected_facts": [],
    "expected_count_range": [0, 0],
    "difficulty": "tricky"
  },
  {
    "id": "ext-003",
    "description": "时态区分（过去 vs 现在）",
    "input": "User: 之前在网易做后端，上个月刚跳到字节做AI\nAssistant: 恭喜跳槽！",
    "expected_facts": [
      {"text_contains": "网易", "temporal_hint": "past"},
      {"text_contains": "字节", "temporal_hint": "current"}
    ],
    "expected_count_range": [1, 3],
    "difficulty": "medium"
  },
  {
    "id": "ext-004",
    "description": "不应将 AI 回复提取为用户事实",
    "input": "User: 你觉得Python好学吗？\nAssistant: Python是很好的入门语言",
    "expected_facts": [],
    "expected_count_range": [0, 1],
    "difficulty": "tricky"
  },
  {
    "id": "ext-005",
    "description": "多轮对话中提取",
    "input": "User: 我最近开始学吉他了\nAssistant: 太棒了\nUser: 每天练一个小时，还挺难的\nAssistant: 坚持就好",
    "expected_facts": [
      {"text_contains": "吉他"},
      {"text_contains": "一个小时", "optional": true}
    ],
    "expected_count_range": [1, 3],
    "difficulty": "medium"
  }
]
```

#### 量化指标

| 指标 | 计算方式 | 目标 |
|------|---------|------|
| **Recall** | 期望 facts 中被成功提取的比例 | ≥ 90% |
| **Precision** | 提取的 facts 中属于合理事实的比例 | ≥ 85% |
| **No-Extract Accuracy** | 不应提取的 case 中，空结果的比例 | ≥ 95% |
| **Confidence Accuracy** | 置信度落在期望范围内的比例 | ≥ 70% |
| **Count Accuracy** | 提取数量在期望范围内的比例 | ≥ 80% |
| **Granularity** | 每条 fact 是否为单一原子事实（非复合句）| Manual review |

#### 评估方法

独立调用 `_extract_facts()`，不涉及后续阶段。每个 case 运行 1 次，收集结果与 expected 对比。

---

### 2.2 Stage 2: RETRIEVAL 评估

**评估目标**：给定一个 fact，检索回的相似记忆是否相关。

**前提**：需要一个预置的记忆库（seed memories）。

#### 数据集结构

```json
{
  "seed_memories": [
    {"id": "mem-1", "content": "用户喜欢喝黑咖啡", "user_id": "test"},
    {"id": "mem-2", "content": "用户在网易工作", "user_id": "test"},
    {"id": "mem-3", "content": "用户叫张三", "user_id": "test"},
    {"id": "mem-4", "content": "用户每天早上跑步5公里", "user_id": "test"},
    {"id": "mem-5", "content": "用户女朋友叫小红", "user_id": "test"},
    {"id": "mem-6", "content": "用户觉得Rust很好", "user_id": "test"}
  ],
  "queries": [
    {
      "id": "ret-001",
      "fact_text": "用户喜欢冰美式",
      "expected_relevant": ["mem-1"],
      "expected_irrelevant": ["mem-4", "mem-5"]
    },
    {
      "id": "ret-002",
      "fact_text": "用户跳槽到字节了",
      "expected_relevant": ["mem-2"],
      "expected_irrelevant": ["mem-1", "mem-4"]
    },
    {
      "id": "ret-003",
      "fact_text": "用户开始学Go语言",
      "expected_relevant": ["mem-6"],
      "expected_irrelevant": ["mem-5"]
    },
    {
      "id": "ret-004",
      "fact_text": "用户和小红分手了",
      "expected_relevant": ["mem-5"],
      "expected_irrelevant": ["mem-1"]
    }
  ]
}
```

#### 量化指标

| 指标 | 计算方式 | 目标 |
|------|---------|------|
| **Recall@K** | top-K 结果中包含期望相关记忆的比例 | ≥ 80% |
| **Precision@K** | top-K 结果中真正相关的比例 | ≥ 50% |
| **MRR** | 第一个相关结果的排名倒数的平均值 | ≥ 0.7 |
| **Irrelevant Exclusion** | 期望不相关的记忆不在 top-3 中的比例 | ≥ 90% |

#### 评估方法

1. Seed 记忆到 vector store
2. 独立调用 `embedder.embed()` + `vector_store.search()`
3. 对比搜索结果与期望

---

### 2.3 Stage 3: DECISION 评估

**评估目标**：给定 fact + 已有记忆列表，LLM 决策是否正确。

**这是最关键也最复杂的阶段**——正确答案有时有多个可接受选项。

#### 数据集结构

```json
[
  {
    "id": "dec-001",
    "description": "完全重复 → NONE",
    "new_fact": "用户喜欢喝黑咖啡",
    "existing_memories": [
      {"id": "0", "content": "用户喜欢喝黑咖啡"}
    ],
    "expected_action": "NONE",
    "acceptable_actions": ["NONE"],
    "difficulty": "easy"
  },
  {
    "id": "dec-002",
    "description": "语义重复（跨语言）→ NONE",
    "new_fact": "The user likes black coffee",
    "existing_memories": [
      {"id": "0", "content": "用户喜欢喝黑咖啡"}
    ],
    "expected_action": "NONE",
    "acceptable_actions": ["NONE", "UPDATE"],
    "difficulty": "medium"
  },
  {
    "id": "dec-003",
    "description": "信息更新 → UPDATE",
    "new_fact": "用户刚跳槽到字节",
    "existing_memories": [
      {"id": "0", "content": "用户在网易工作"}
    ],
    "expected_action": "UPDATE",
    "acceptable_actions": ["UPDATE"],
    "expected_text_contains": ["字节"],
    "expected_id": "0",
    "difficulty": "medium"
  },
  {
    "id": "dec-004",
    "description": "全新信息 → ADD",
    "new_fact": "用户养了一只猫",
    "existing_memories": [
      {"id": "0", "content": "用户在网易工作"},
      {"id": "1", "content": "用户喜欢咖啡"}
    ],
    "expected_action": "ADD",
    "acceptable_actions": ["ADD"],
    "difficulty": "easy"
  },
  {
    "id": "dec-005",
    "description": "直接矛盾 → DELETE 或 UPDATE",
    "new_fact": "用户现在不喝咖啡了",
    "existing_memories": [
      {"id": "0", "content": "用户喜欢喝黑咖啡"}
    ],
    "expected_action": "DELETE",
    "acceptable_actions": ["DELETE", "UPDATE"],
    "difficulty": "hard"
  },
  {
    "id": "dec-006",
    "description": "细化现有信息 → UPDATE",
    "new_fact": "用户每天早上喝冰美式",
    "existing_memories": [
      {"id": "0", "content": "用户喜欢咖啡"}
    ],
    "expected_action": "UPDATE",
    "acceptable_actions": ["UPDATE", "ADD"],
    "expected_text_contains": ["冰美式"],
    "difficulty": "medium"
  },
  {
    "id": "dec-007",
    "description": "无已有记忆 → ADD",
    "new_fact": "用户叫张三",
    "existing_memories": [],
    "expected_action": "ADD",
    "acceptable_actions": ["ADD"],
    "difficulty": "easy"
  }
]
```

#### 量化指标

| 指标 | 计算方式 | 目标 |
|------|---------|------|
| **Action Accuracy** | 决策与 expected_action 一致的比例 | ≥ 80% |
| **Action Acceptable** | 决策在 acceptable_actions 内的比例 | ≥ 90% |
| **ID Accuracy** | UPDATE/DELETE 引用的 ID 正确的比例 | ≥ 95% |
| **Text Quality** | UPDATE/ADD 生成的文本包含关键信息的比例 | ≥ 85% |
| **Parse Success** | JSON 解析成功率 | ≥ 99% |
| **Reason Quality** | reason 字段是否有意义（非空且相关）| ≥ 90% |

#### 评估方法

构造 messages（system=UPDATE_DECISION_SYSTEM_PROMPT, user=格式化的记忆+fact），直接调用 `llm.generate()`。不涉及 embed 和 search。

---

### 2.4 Stage 4: EXECUTION 评估

**评估目标**：给定决策，写入操作是否正确执行。

此阶段是**确定性的**（不涉及 LLM），用传统单元测试即可。

#### 测试矩阵

| Case | Input | Assert |
|------|-------|--------|
| ADD 正常 | `action=ADD, text="xxx"` | VEC 有新记录，DB 有 ADD 历史，返回 MemoryItem |
| UPDATE 正常 | `action=UPDATE, id=mem-1, text="yyy"` | 新记录创建，version_of=mem-1，DB 有两条历史 |
| DELETE 正常 | `action=DELETE, id=mem-1` | 旧记录 status=deleted，DB 有 DELETE 历史 |
| NONE | `action=NONE` | 无任何写入，返回 None |
| Bad ID fallback | `action=UPDATE, id=999` | 回退到 ADD 逻辑，日志 warning |
| 并发安全 | 10 个并发 ADD | 无重复 ID，无数据丢失 |

#### 评估方法

标准 pytest 单元测试，不需要 LLM API。

---

### 2.5 端到端 Golden Test

覆盖完整流程的回归测试，用于防止阶段间交互引入的 bug。

#### 数据集结构

```json
[
  {
    "id": "e2e-001",
    "scenario": "首次添加基本信息",
    "messages": [{"role": "user", "content": "我叫张三，在网易工作"}],
    "user_id": "golden-user",
    "expected_memories_after": [
      {"content_contains": "张三"},
      {"content_contains": "网易"}
    ],
    "expected_count_range": [1, 3]
  },
  {
    "id": "e2e-002",
    "scenario": "重复添加不应产生新记忆",
    "depends_on": "e2e-001",
    "messages": [{"role": "user", "content": "我叫张三"}],
    "expected_new_memories": 0
  },
  {
    "id": "e2e-003",
    "scenario": "偏好更新应触发 UPDATE",
    "depends_on": "e2e-001",
    "messages": [{"role": "user", "content": "我跳槽到字节了"}],
    "expected_memories_after": [
      {"content_contains": "字节"}
    ],
    "expect_version_of_exists": true
  },
  {
    "id": "e2e-004",
    "scenario": "搜索能召回相关记忆",
    "depends_on": "e2e-001",
    "search_query": "这个人在哪工作？",
    "expected_search_contains": ["网易"]
  }
]
```

---

## 3. 评估迭代工作流

```
┌─────────────────────────────────────────┐
│            迭代优化循环                    │
│                                         │
│  1. 建立 baseline                       │
│     └─ 运行所有 eval → 记录当前指标       │
│                                         │
│  2. 识别最弱阶段                         │
│     └─ 哪个阶段的指标最低 / 差距最大？     │
│                                         │
│  3. 针对性修改                           │
│     ├─ 改 prompt（最常见）                │
│     ├─ 改检索策略（K值、过滤器）           │
│     ├─ 改架构（如 batch decision）        │
│     └─ 加数据集 case（发现新边界）         │
│                                         │
│  4. 运行该阶段 eval                      │
│     └─ 只跑被修改阶段的评估               │
│                                         │
│  5. 对比 report                         │
│     ├─ 指标提升 → 跑端到端回归 → 合入     │
│     └─ 指标下降 → 回滚分析                │
│                                         │
│  6. 存档 report → 回到 step 2            │
└─────────────────────────────────────────┘
```

---

## 4. 实施优先级

| 优先级 | 任务 | 依赖 |
|--------|------|------|
| **P0** | 解耦 `_process_fact()` 为独立的 retrieval / decision / execution 方法 | 无 |
| **P0** | 创建评估数据集（从简单 case 开始，逐步扩充） | 无 |
| **P1** | 实现 Stage 1 (EXTRACTION) eval runner + 建立 baseline | P0 |
| **P1** | 实现 Stage 3 (DECISION) eval runner + 建立 baseline | P0 |
| **P2** | 实现 Stage 2 (RETRIEVAL) eval runner | P0 |
| **P2** | 实现端到端 eval runner | P1 |
| **P3** | 开始优化迭代（从 baseline 指标最低的阶段开始） | P1+P2 |
