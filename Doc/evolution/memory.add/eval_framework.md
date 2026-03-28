# add() 评估框架设计

> 本文档设计了 `Memory.add()` 各核心能力的可量化评估体系，
> 支持独立能力评估和端到端回归测试，用于驱动迭代优化。

---

## 1. 设计原则

- **能力独立**：修改 extraction 的 prompt 时，只需跑 extraction 评估
- **量化指标**：每个阶段有明确的数值指标和目标值
- **可迭代**：评估结果存档，修改前后可对比
- **数据驱动**：JSON 数据集描述测试用例，与代码解耦
- **可复现**：固定 temperature=0，相同输入应产生一致结果
- **数据集分焦点**：按 atomicity / exclusion / temporal / multiturn 等测试重点拆分数据集
- **覆盖优先于数量**：每类重点只保留 2 到 3 个平行实例，避免靠堆数量制造表面稳定性
- **报告可诊断**：输出不仅要有总分，还要能指出漏提、乱提、数量失控、空 case 污染等具体短板

当前实践建议：

- 每个 extraction 数据集维持在 10 个 case 左右
- 每个数据集内部按 3 到 5 个子问题组织，每个子问题 2 到 3 个平行实例
- case 扩充的目标是补边界，不是重复证明已经覆盖的能力

---

## 2. 目录结构

```
tests/
├── eval/
│   ├── datasets/
│   │   ├── extraction_cases.json     # extraction smoke 测试集
│   │   ├── extraction_atomicity_cases.json
│   │   ├── extraction_exclusion_cases.json
│   │   ├── extraction_temporal_cases.json
│   │   └── extraction_multiturn_cases.json
│   │   ├── retrieval_cases.json      # retrieval 测试集
│   │   ├── decision_cases.json       # decision 测试集
│   │   └── e2e_golden.json           # 端到端测试集
│   ├── runners/
│   │   ├── eval_extraction.py        # extraction 评估脚本
│   │   ├── eval_retrieval.py         # retrieval 评估脚本
│   │   ├── eval_decision.py          # decision 评估脚本
│   │   └── eval_e2e.py               # 端到端评估脚本
│   └── reports/
│       └── {timestamp}_report.json   # 评估结果存档
```

---

## 3. Extraction 评估

### 3.1 数据集格式

```json
{
  "name": "extraction_atomicity_cases",
  "focus": "atomic splitting",
  "description": "Checks whether one user turn is decomposed into the right number of fact-shaped items.",
  "cases": [
    {
      "id": "atomicity-001",
      "description": "多事实简单陈述",
      "input": "我叫张三，今年28岁，在网易工作，喜欢喝黑咖啡",
      "expected_facts": [
        {"text_contains": "张三", "confidence_range": [0.9, 1.0]},
        {"text_contains": "28", "confidence_range": [0.9, 1.0]}
      ],
      "should_not_extract": ["assistant"],
      "expected_count_range": [2, 4],
      "difficulty": "easy"
    }
  ]
}
```

### 3.2 字段说明

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | string | 唯一标识 |
| `description` | string | 用例描述 |
| `input` | string | 输入对话（User/Assistant 格式） |
| `expected_facts` | array | 期望提取到的 facts，每个含 `text_contains` 或 `match_any`，以及可选 `confidence_range` |
| `should_not_extract` | array | 不应出现在提取结果中的关键词 |
| `expected_count_range` | [min, max] | 期望的 fact 数量范围 |
| `difficulty` | string | easy / medium / hard / tricky |

数据集元信息：

- `name`：数据集名字，用于报告展示
- `focus`：该数据集的测试重点，例如 atomicity / exclusion / temporal
- `description`：对该数据集目的的简短说明
- `cases`：该数据集包含的 case 列表

补充说明：

- `text_contains`：适用于输出表述较稳定的场景
- `match_any`：适用于跨语言、同义改写、允许多种合理表述的场景
- 对真实 LLM 评估，优先推荐在存在改写空间的 case 中使用 `match_any`，否则容易把“语义正确但措辞不同”的结果误判为失败

### 3.3 评估指标

| 指标 | 计算方式 | 目标 |
|------|---------|------|
| **Recall** | 匹配到的 expected_facts / 总 expected_facts | ≥ 90% |
| **Precision** | 合理 facts / 总提取 facts | ≥ 85% |
| **No-Extract Accuracy** | 不应提取的 case 中返回空的比例 | ≥ 95% |
| **Confidence Accuracy** | 置信度落在 confidence_range 的比例 | ≥ 70% |
| **Count Accuracy** | fact 数量在 expected_count_range 内的比例 | ≥ 80% |
| **Normalization Stability** | 重复、空文本、非法 confidence 被正确清洗的比例 | 100% |

建议同时关注以下诊断参数：

- `case_pass_rate`：完全无失败 case 的比例
- `missing_expectation_rate`：漏提期望 fact 的比例
- `forbidden_case_rate`：出现不应提取内容的 case 比例
- `under_count_rate`：提取数量低于最小值的 case 比例
- `over_count_rate`：提取数量高于最大值的 case 比例
- `avg_extracted_facts`：每个 case 平均提取多少条
- `avg_extracted_facts_on_empty_cases`：本该为空的 case 平均被提取多少条

### 3.4 评估方法

```python
# _extract_facts 是 staticmethod，直接调用
from mind.memory import Memory
from mind.llms.factory import LlmFactory

llm = LlmFactory.create(config.llm)
facts = Memory._extract_facts(
  llm,
  conversation,
  temperature=config.llm.extraction_temperature,
)
```

> 注意：`_extract_facts()` 当前不仅负责 JSON 解析，也负责提取结果规范化。
> 因此 extraction 评估应直接检查最终输出，而不是只检查 LLM 原始返回。

### 3.4.1 实际运行脚本

当前 extraction 评估脚本默认会扫描 `tests/eval/datasets/` 下所有 `extraction*_cases.json` 文件，并为每个数据集分别输出一份报告。

```bash
python tests/eval/runners/eval_extraction.py --toml mindt.toml
```

如果只想跑某一个数据集，可显式指定：

```bash
python tests/eval/runners/eval_extraction.py \
  --toml mind.toml \
  --dataset tests/eval/datasets/extraction_temporal_cases.json
```

如果要使用真实 LLM 评估 extraction，而不是 fake backend，使用：

```bash
python tests/eval/runners/eval_extraction.py --toml mind.toml
```

建议说明：

- `mindt.toml`：用于本地回归、流程完整性验证、数据集和 runner 健康检查，不代表真实模型质量
- `mind.toml`：用于真实 LLM 质量评估，会实际消耗模型调用和 token
- 若不指定 `--output`，默认按数据集名字输出，例如：`tests/eval/reports/extraction_temporal_cases_report.json`
- 脚本默认会输出面向人阅读的 summary；如果还需要查看完整 JSON，可加 `--pretty`
- 如果要把 stdout 作为机器输入而不是人读摘要，可加 `--json-only`
- 如果希望在指标未达标时直接返回非零退出码，可加 `--fail-on-targets`
- 若要保留多次实验结果，应显式指定输出路径，例如：

```bash
python tests/eval/runners/eval_extraction.py \
  --toml mind.toml \
  --output tests/eval/reports/2026-03-28_real_llm_extraction_report.json \
  --pretty
```

### 3.5 推荐测试用例类型

| 类型 | 示例 | 测试重点 |
|------|------|---------|
| 简单陈述 | "我叫张三，在网易工作" | 基础提取 |
| 假设性语句 | "如果我去日本的话…" | 应不提取 |
| 时态区分 | "之前在网易，刚跳到字节" | past vs current |
| AI 回复过滤 | "User: xxx\nAssistant: yyy" | 不提取 AI 的话 |
| 多轮对话 | 3-5轮对话 | 上下文理解 |
| 隐含信息 | "我每天写 Python 10 年了" | 推断 "是程序员" |
| 空对话 | "你好" | 应返回空 |
| 规范化回归 | 重复行、脏标点、非法 confidence | 输出洁净度 |

---

## 4. Retrieval 评估

### 4.1 数据集格式

```json
{
  "seed_memories": [
    {"id": "mem-1", "content": "用户喜欢喝黑咖啡", "user_id": "test"},
    {"id": "mem-2", "content": "用户在网易工作", "user_id": "test"}
  ],
  "queries": [
    {
      "id": "ret-001",
      "fact_text": "用户喜欢冰美式",
      "expected_relevant": ["mem-1"],
      "expected_irrelevant": ["mem-2"]
    }
  ]
}
```

### 4.2 评估指标

| 指标 | 计算方式 | 目标 |
|------|---------|------|
| **Recall@K** | top-K 中包含 expected_relevant 的比例 | ≥ 80% |
| **Precision@K** | top-K 中真正相关的比例 | ≥ 50% |
| **MRR** | 第一个相关结果排名的倒数平均 | ≥ 0.7 |
| **Irrelevant Exclusion** | expected_irrelevant 不在 top-3 的比例 | ≥ 90% |

### 4.3 评估方法

```python
# 1. Seed 记忆到 vector store
for mem in seed_memories:
    vector = embedder.embed(mem["content"])
    vector_store.insert(id=mem["id"], vector=vector, payload={...})

# 2. 独立调用 _retrieve_similar()
fact_vector, similar, temp_to_real = m._retrieve_similar(
    fact_text="用户喜欢冰美式",
    user_id="test",
    embedder=embedder,
    config=config,
)

# 3. 检查 similar 中是否包含 expected_relevant
```

---

## 5. Decision 评估

### 5.1 数据集格式

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
    "expected_text_contains": [],
    "expected_id": null,
    "difficulty": "easy"
  }
]
```

### 5.2 字段说明

| 字段 | 说明 |
|------|------|
| `new_fact` | 新提取的事实 |
| `existing_memories` | 模拟的已有记忆列表（含 id 和 content） |
| `expected_action` | 最佳决策 |
| `acceptable_actions` | 所有可接受的决策（含次优） |
| `expected_text_contains` | UPDATE/ADD 时，生成文本应包含的关键词 |
| `expected_id` | UPDATE/DELETE 时，应引用的临时 ID |

### 5.3 评估指标

| 指标 | 计算方式 | 目标 |
|------|---------|------|
| **Action Accuracy** | action == expected_action 的比例 | ≥ 80% |
| **Action Acceptable** | action in acceptable_actions 的比例 | ≥ 90% |
| **ID Accuracy** | 引用的 ID == expected_id 的比例 | ≥ 95% |
| **Text Quality** | 生成文本包含 expected_text_contains 的比例 | ≥ 85% |
| **Parse Success** | JSON 解析成功的比例 | ≥ 99% |
| **Reason Quality** | reason 非空且语义相关的比例 | ≥ 90% |

### 5.4 评估方法

```python
# _decide_action 是 staticmethod，可直接调用
from mind.memory import Memory

# 构造模拟的搜索结果
similar_results = [
    {"id": "real-id-1", "payload": {"content": "用户喜欢喝黑咖啡"}},
    {"id": "real-id-2", "payload": {"content": "用户在网易工作"}},
]

decision = Memory._decide_action(
    fact_text="用户现在不喝咖啡了",
    similar_results=similar_results,
    llm=llm,
)
# decision = {"action": "DELETE", "id": "0", "text": "", "reason": "..."}
```

### 5.5 推荐测试用例类型

| 类型 | 预期决策 | 难度 |
|------|---------|------|
| 完全重复 | NONE | easy |
| 语义重复（跨语言） | NONE / UPDATE | medium |
| 全新信息 | ADD | easy |
| 信息更新 | UPDATE | medium |
| 信息细化 | UPDATE / ADD | medium |
| 直接矛盾 | DELETE / UPDATE | hard |
| 无已有记忆 | ADD | easy |
| 多条相关记忆 | UPDATE 最相关的 | hard |

---

## 6. Execution 评估

### 6.1 测试方法

此阶段是**确定性的**（不涉及 LLM），用标准 pytest 单元测试。

### 6.2 测试矩阵

| Case | Input | Assert |
|------|-------|--------|
| ADD 正常 | `action=ADD, text="xxx"` | VEC 有新记录，DB 有 ADD 历史 |
| UPDATE 正常 | `action=UPDATE, id=mem-1` | 新记录创建，version_of=mem-1 |
| DELETE 正常 | `action=DELETE, id=mem-1` | status=deleted，DB 有 DELETE 历史 |
| NONE | `action=NONE` | 无写入，返回 None |
| Bad ID fallback | `action=UPDATE, id=999` | 回退到 ADD，日志 warning |
| 并发安全 | 10 个并发 ADD | 无重复 ID，无数据丢失 |

---

## 7. 端到端 Golden Test

### 7.1 数据集格式

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
  }
]
```

### 7.2 执行方式

1. 按 `depends_on` 拓扑排序执行
2. 每个 case 执行 `m.add()` 或 `m.search()`
3. 检查结果是否满足期望

---

## 8. 评估报告格式

```json
{
  "timestamp": "2026-03-27T21:00:00+08:00",
  "commit": "abc1234",
  "stages": {
    "extraction": {
      "total_cases": 10,
      "recall": 0.92,
      "precision": 0.88,
      "no_extract_accuracy": 1.0,
      "confidence_accuracy": 0.75,
      "count_accuracy": 0.85,
      "failures": ["ext-003"]
    },
    "decision": {
      "total_cases": 15,
      "action_accuracy": 0.82,
      "action_acceptable": 0.93,
      "id_accuracy": 0.96,
      "text_quality": 0.87,
      "parse_success": 1.0,
      "failures": ["dec-005", "dec-008"]
    }
  }
}
```

---

## 9. 迭代工作流

```
┌─────────────────────────────────────────┐
│            迭代优化循环                    │
│                                         │
│  1. 建立 baseline                       │
│     └─ 运行所有 eval → 存档初始 report    │
│                                         │
│  2. 识别最弱阶段                         │
│     └─ 哪个阶段的指标最低 / 离目标最远？   │
│                                         │
│  3. 针对性修改                           │
│     ├─ 改 prompt（最常见）                │
│     ├─ 改检索策略（K值、阈值）             │
│     ├─ 改架构（如 batch decision）        │
│     └─ 补充数据集（发现新边界 case）       │
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

## 10. 实施优先级

| 优先级 | 任务 | 状态 |
|--------|------|------|
| **P0** | 解耦核心能力为独立方法 | ✅ 已完成 |
| **P0** | 创建评估数据集 | 待开始 |
| **P1** | 实现 extraction eval runner | 待开始 |
| **P1** | 实现 decision eval runner | 待开始 |
| **P2** | 实现 retrieval eval runner | 待开始 |
| **P2** | 实现端到端 eval runner | 待开始 |
| **P3** | 开始优化迭代 | 依赖 P1+P2 |
