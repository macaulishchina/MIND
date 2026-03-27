# add() 方法 — 流程与核心能力

> 本文档描述 `Memory.add()` 的完整执行流程。
> 该流程由 4 个**独立的核心能力方法**组成，每个方法有清晰的输入/输出边界，
> 可独立调用和测试，也可被其他流程复用。

---

## 总览

```
add(messages, user_id)
│
├─ Extraction（事实提取）
│  方法: _extract_facts()  [staticmethod]
│  输入: llm, conversation
│  输出: [{text, confidence}, ...]
│
├─ Retrieval（相似记忆检索）
│  方法: _retrieve_similar()
│  输入: fact_text, user_id, embedder, config
│  输出: (fact_vector, similar_results, temp_to_real)
│
├─ Decision（操作决策）
│  方法: _decide_action()  [staticmethod]
│  输入: fact_text, similar_results, llm
│  输出: decision_dict {action, id, text, reason}
│
└─ Execution（执行写入）
    方法: _execute_action()
    输入: decision, fact_vector, temp_to_real, ...
    输出: Optional[MemoryItem]
```

**编排层**: `_process_fact()` 按顺序组合 retrieval → decision → execution。
**并发层**: `add()` 通过线程池并发调用多个 `_process_fact()`。

---

## Extraction（事实提取）

### 职责
从对话中提取可记忆的事实，并评估置信度。

### 方法签名
```python
@staticmethod
def _extract_facts(llm, conversation: str) -> List[Dict[str, Any]]
```

> `staticmethod` — 可通过 `Memory._extract_facts(llm, conversation)` 直接调用。

### 使用的 Prompt
- `FACT_EXTRACTION_SYSTEM_PROMPT`
- `FACT_EXTRACTION_USER_TEMPLATE`

### 调用链
```
1× LLM 调用 → JSON 解析 → [{text, confidence}, ...]
```

### 关键质量维度
| 维度 | 说明 |
|------|------|
| 完整性 | 对话中所有可提取的事实都被发现 |
| 粒度 | 每条 fact 是单一原子事实，不是复合句 |
| 置信度准确性 | confidence 值与事实的确定程度匹配 |
| 过滤能力 | 假设性/条件性语句不被提取 |

---

## Retrieval（相似记忆检索）

### 职责
将 fact 转为向量，搜索已有的相似记忆，建立临时 ID 映射。

### 方法签名
```python
def _retrieve_similar(
    self,
    fact_text: str,
    user_id: str,
    embedder,
    config: MemoryConfig,
) -> tuple[list, list, dict[str, str]]
    # Returns: (fact_vector, similar_results, temp_to_real)
```

### 调用链
```
1× EMB (embed) + 1× VEC (search) → (vector, results, id_map)
```

### 关键质量维度
| 维度 | 说明 |
|------|------|
| 召回率 | 语义相关的已有记忆被检索到 |
| 排序质量 | 最相关的记忆排在前面 |
| 噪声控制 | 不相关的记忆不出现在 top-K |

---

## Decision（操作决策）

### 职责
基于 fact 和已有记忆，让 LLM 决定 ADD / UPDATE / DELETE / NONE。

### 方法签名
```python
@staticmethod
def _decide_action(
    fact_text: str,
    similar_results: list,
    llm,
) -> Optional[Dict[str, Any]]
    # Returns: {action, id, text, reason} or None
```

> **注意**: 这是 `staticmethod`，不依赖 Memory 实例状态，可完全独立调用和测试。

### 使用的 Prompt
- `UPDATE_DECISION_SYSTEM_PROMPT`
- `UPDATE_DECISION_USER_TEMPLATE`

### 调用链
```
格式化记忆列表 → 1× LLM 调用 → JSON 解析 → decision dict
```

### 关键质量维度
| 维度 | 说明 |
|------|------|
| 决策准确率 | action 与预期一致 |
| ID 准确率 | UPDATE/DELETE 引用的临时 ID 正确 |
| 文本质量 | ADD/UPDATE 生成的记忆文本包含关键信息 |
| 冲突处理 | 矛盾信息被正确处理（DELETE 或 UPDATE） |

---

## Execution（执行写入）

### 职责
根据决策执行实际的存储操作。

### 方法签名
```python
def _execute_action(
    self,
    decision: Dict[str, Any],
    fact_text: str,
    fact_vector: list,
    temp_to_real: Dict[str, str],
    embedder,
    confidence: float,
    user_id: str,
    session_id: Optional[str],
    source_context: str,
    metadata: Optional[Dict[str, Any]],
) -> Optional[MemoryItem]
```

### 调用链（按 action）
| Action | 操作 |
|--------|------|
| ADD | VEC.insert + DB.add_record(ADD) |
| UPDATE | EMB.embed + VEC.insert(new) + DB.add_record(ADD) + DB.add_record(UPDATE) |
| DELETE | VEC.update(status=deleted) + DB.add_record(DELETE) |
| NONE | 无操作 |

### 关键质量维度
| 维度 | 说明 |
|------|------|
| 数据一致性 | VEC 和 DB 数据同步 |
| version_of | UPDATE 时新记忆的 version_of 指向旧记忆 |
| 回退能力 | 无效 ID 时优雅回退到 ADD |

---

## 编排关系

```python
def _process_fact(self, llm, embedder, config, fact_text, ...):
    fact_vector, similar, temp_to_real = self._retrieve_similar(...)
    decision = self._decide_action(...)
    if decision is None:
        return None
    return self._execute_action(...)
```

**并发模型**: `add()` 中多个 `_process_fact()` 通过 `ThreadPoolExecutor` 并发执行，
每个 fact 独立走完 retrieval → decision → execution 流程。
