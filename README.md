# MIND

> **Memory Is Never Done**

MIND 是一个面向 LLM 智能体的记忆系统，建立在一个核心信念之上：

**模型的训练可以结束，但它的记忆不应该停止生长。**

MIND 不把记忆看成一个静态数据库，也不把它仅仅看成一个简单的检索层。相反，MIND 将记忆视作一个**外部的、可演化的世界**：智能体可以读取它、写入它、组织它、重构它，并在长期交互中不断改进它。

---

## 为什么是 MIND

大语言模型很强大，但它们的参数在训练完成后通常是固定的。

这意味着，它们的长期能力提升不能只依赖内部权重。  
MIND 试图探索另一条路径：

- 让模型接触原始经验
- 提供一组基础记忆操作
- 让智能体自行组织记忆
- 通过长期反馈持续优化记忆系统

一句话概括：

**训练会结束，但记忆会继续演化。**

---

## 核心思想

MIND 不只是一个 memory store。

它是一套框架，在这套框架中，记忆具有以下特征：

- **外部性（external）** —— 位于模型权重之外
- **可塑性（plastic）** —— 可以随着时间不断重组
- **可操作性（operational）** —— 可以通过基础原语被直接作用
- **自改进性（self-improving）** —— 可以根据未来任务表现持续优化
- **开放性（open-ended）** —— 为持续成长而设计

---

## 设计原则

### 1. 原始经验优先
MIND 倾向于保留原始交互轨迹、事件、工具使用记录和任务历史，而不是过早地把记忆工程化为固定 schema。

### 2. 简单原语，复杂涌现
MIND 不希望把高层记忆功能全部手工写死，而是提供一组基础操作，例如：

- write_raw（写入原始记录）
- read（按引用读取）
- retrieve（检索候选）
- summarize（生成摘要）
- link（建立关联）
- reflect（生成反思）
- reorganize_simple（执行轻量重组）

复杂的记忆结构应当从这些简单操作的组合中涌现出来。

### 3. 成长发生在权重之外
模型本身也许不能自我修改，但它的外部记忆环境可以持续变化和成长。

### 4. 记忆应由“未来 usefulness”来衡量
好的记忆系统，不是存得最多的系统，而是在真实成本约束下，最能提升未来任务表现的系统。

---

## MIND 想构建什么

MIND 旨在支持这样一类智能体，它们能够：

- 在很长的时间跨度上保持记忆
- 在需要时主动重组记忆结构
- 从持续交互中累积经验
- 在测试时学习更好的记忆使用方式
- 在不改变模型参数的前提下持续变强

---

## MIND 不是什么

MIND **不是**：

- 一个普通的向量数据库
- 一条简单的 RAG 流水线
- 一种只依赖超长上下文的提示方法
- 一个只保存用户偏好的记忆层

MIND 的目标是构建一个面向通用智能体的**可自演化外部记忆系统**。

---

## 研究方向

MIND 当前聚焦于四个核心问题：

1. 面向开放式成长，最小但完备的记忆原语集合是什么？
2. 智能体应如何在不过度手工设计结构的前提下操作原始记忆？
3. 应当用什么统一目标来衡量长期任务中的记忆质量？
4. 在模型训练结束之后，外部记忆如何继续提升系统能力？

---

## 当前状态

这个项目目前已有一套 **通过本地 Phase C gate 的实现基线**。

当前落地包括：

- 冻结 Phase A 规范与验收标准
- 落地 Phase B 最小记忆内核
- 构建可追溯、可回放、可版本化的对象存储
- 落地 Phase C typed primitive contract、结构化日志、预算约束与失败原子性
- 建立 `PrimitiveGoldenCalls v1` 与本地 Phase C gate

当前实现包括：

- `mind/kernel/schema.py`：8 类核心对象的 schema validator
- `mind/kernel/store.py`：基于 SQLite 的 append-only version store
- `mind/kernel/integrity.py`：trace / cycle / version chain 完整性检查
- `mind/kernel/replay.py`：golden episode replay 与事件顺序 hash
- `mind/fixtures/golden_episode_set.py`：`20` 个 golden episodes 与 8 类对象样例
- `mind/primitives/contracts.py` / `runtime.py` / `service.py`：Phase C primitive contract、运行时包装与服务实现
- `mind/fixtures/primitive_golden_calls.py`：`200` 条 primitive 调用样例
- `scripts/run_phase_b_gate.py` / `scripts/run_phase_c_gate.py`：本地 gate 检查入口
- `tests/test_phase_b_gate.py` / `tests/test_phase_c_gate.py`：阶段 gate 测试

---

## 文档结构

- [文档索引](./docs/README.md)
- [阶段 A 正式规范](./docs/foundation/spec.md)
- [设计拆解与实施主文档](./docs/design/design_breakdown.md)
- [Phase C 启动清单](./docs/design/phase_c_startup_checklist.md)
- [阶段验收与 phase gates](./docs/foundation/phase_gates.md)
- [实现技术栈冻结文档](./docs/foundation/implementation_stack.md)
- [初始讨论文档](./docs/research/research_notes.md)
- [Phase B 验收报告](./docs/reports/phase_b_acceptance_report.md)
- [Phase C 独立审计报告](./docs/reports/phase_c_independent_audit.md)
- [Phase C Golden Calls 独立审计报告](./docs/reports/phase_c_golden_calls_audit.md)
- [PostgreSQL Store 审核报告](./docs/reports/postgres_store_audit.md)
- [Phase C 验收报告](./docs/reports/phase_c_acceptance_report.md)

## 运行方式

推荐从 Phase C 起统一使用 `pyproject.toml` + `uv`：

```bash
uv sync --extra dev
uv run pytest -q
uv run mind-phase-b-gate
uv run mind-phase-c-gate
uv run mind-postgres-regression --dsn postgresql+psycopg://postgres:postgres@127.0.0.1:5432/postgres
uv run ruff check mind tests scripts
uv run mypy
```

如果本地还没有 `uv`，当前仓库仍兼容项目虚拟环境下的脚本执行方式：

```bash
.venv/bin/python -m pytest -q
.venv/bin/python scripts/run_phase_b_gate.py
.venv/bin/python scripts/run_phase_c_gate.py
.venv/bin/python scripts/run_postgres_regression.py --dsn postgresql+psycopg://postgres:postgres@127.0.0.1:5432/postgres
```

当前本地 gate 基线输出应满足：

- Phase B：`phase_b_gate=PASS`
- Phase C：`phase_c_gate=PASS`

---

## 路线图

- [ ] 正式化 MIND 框架
- [ ] 定义记忆环境与原子动作
- [ ] 设计统一的 memory utility objective
- [ ] 构建第一版实验原型
- [ ] 与标准 RAG 和 memory-agent baseline 做对比
- [ ] 探索可自演化的记忆策略

---

## 项目宣言

> **Memory Is Never Done.**

---

## License

尚未指定 License。
