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

### 5. 来源治理应独立于记忆优化
MIND 将对象 lineage 和来源 provenance 明确分开。

- `source_refs` 用于表达记忆对象之间的派生关系
- provenance 用于表达原始数据来自谁、何时、什么环境
- provenance 进入独立的治理通道，而不参与日常记忆优化

这使系统既能持续成长，也能在需要时执行高权限、可审计的主动遗忘与重塑。

### 6. 运行时记忆深度应可调
MIND 不假设所有场景都应该使用同样深的记忆访问流程。

- 简单对话可以走更浅、更快的回忆路径
- 高正确性任务可以走更深、更重的重建与校验路径
- 系统应支持固定档位和 `auto` 调度两种模式

这样才能在速度、成本和质量之间做场景化折中。

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

这个项目目前已有一套 **通过 Phase J 本地验收的实现基线**。

同时，文档层已经补充冻结了 provenance control plane、`support_unit` 和独立 `governance / reshape loop` 的语义。

文档层也已经补充冻结了运行时 `Flash / Recall / Reconstruct / Reflective`（内部名 `reflective_access`）访问档位与 `auto` 调度语义，并把“记忆如何长成人格层”纳入设计主线与研究问题。

当前文档已经把 `Phase H ~ O` 的 formal gate、阶段边界和启动清单补齐，用来约束 provenance foundation、runtime access、统一 CLI、统一模型能力层、开发态 telemetry、前端体验、governance reshape 和 persona projection 的实现顺序。

同时，产品化 addendum 已经完成首轮落地：现有 Phase J 形成的开发/验收 CLI 已迁移为 `mindtest`，而 `mind` 已切换为产品 CLI。正式产品化方案与完成态说明见 [产品化方案与验收蓝图](./docs/design/productization_program.md)。

这些内容里，`Phase H / I / J` 已经进入实现基线并通过本地 formal gate；产品化 `WP-0 ~ WP-6` 也已经完成，补上了应用服务层、用户状态、REST API、MCP、产品 CLI 和部署资产。`Phase K / L / M` 现在也都已进入实现基线：K 补上了统一 capability contract、provider adapter、failure/trace audit 和 gate/report，L 补上了开发态 telemetry、audit 与 formal gate，M 补上了轻量静态 frontend shell、frontend-facing transport、responsive audit、flow report 和 formal gate。更正式的 acceptance report 与后续 Phase N / O 的产品面仍在后续收口。

当前产品入口包括：

- `mindtest`：开发/验收 CLI
- `mind`：产品 CLI（`remember / recall / ask / history / session / status / config`）
- `mind-api`：FastAPI REST 服务
- `mind-mcp`：MCP Server v1
- `compose.yaml` + `Dockerfile.api` + `Dockerfile.worker`：本地联调与部署资产

当前落地包括：

- 冻结 Phase A 规范与验收标准
- 落地 Phase B 最小记忆内核
- 构建可追溯、可回放、可版本化的对象存储
- 落地 Phase C typed primitive contract、结构化日志、预算约束与失败原子性
- 建立 `PrimitiveGoldenCalls v1` 与本地 Phase C gate
- 落地 PostgreSQL store、Alembic 迁移、Phase B/C Postgres 回归
- 落地 Retrieval v1、Workspace builder v1、`RetrievalBenchmark v1`
- 落地 `pg_trgm / pgvector / object_embeddings`
- 建立 `EpisodeAnswerBench v1` 与 answer-level `D-5` A/B benchmark
- 完成本地 Phase D smoke、Phase D 验收与 PostgreSQL regression
- 建立 Phase E 离线维护基础层：`offline_jobs`、worker、promotion policy v0
- 建立 `LongHorizonDev v1`、`ReplayLift` baseline 与本地 Phase E startup baseline
- 完成本地 Phase E gate：`SchemaValidationPrecision`、`PromotionPrecision@10`、`PUS / PollutionRate` A/B dev eval
- 完成本地 Phase F gate：`LongHorizonEval v1`、3 个 baseline、`95% CI` report、`F-4 ~ F-7`
- 完成本地 Phase G gate：`fixed-rule budget baseline`、`optimized_v1`、`G-1 ~ G-5`
- 完成本地 Phase H gate：direct provenance、最小 governance control plane、online / offline conceal isolation、`H-1 ~ H-8`
- 完成本地 Phase I gate：runtime access modes、`auto` 调度、`AccessDepthBench v1`、`I-1 ~ I-8`
- 完成本地 Phase J gate：统一开发/验收 CLI 基线、8 个一级命令族、`MindCliScenarioSet v1`、config audit、`J-1 ~ J-6`

当前实现包括：

- `mind/kernel/schema.py`：8 类核心对象的 schema validator
- `mind/kernel/store.py`：基于 SQLite 的 reference store，用于基线、测试和 backend parity 校验
- `mind/kernel/postgres_store.py`：正式 PostgreSQL backend 与迁移辅助
- `mind/kernel/retrieval.py`：共享 retrieval 语义、search text 与 deterministic embedding 基线
- `mind/kernel/integrity.py`：trace / cycle / version chain 完整性检查
- `mind/kernel/replay.py`：golden episode replay 与事件顺序 hash
- `mind/fixtures/golden_episode_set.py`：`20` 个 golden episodes 与 8 类对象样例
- `mind/primitives/contracts.py` / `runtime.py` / `service.py`：Phase C primitive contract、运行时包装与服务实现
- `mind/fixtures/primitive_golden_calls.py`：`200` 条 primitive 调用样例
- `mind/workspace/builder.py` / `mind/workspace/context_protocol.py` / `mind/workspace/smoke.py`：Workspace builder、冻结的 Phase D context protocol 与 Phase D smoke 评估器
- `mind/workspace/answer_benchmark.py`：answer-level `D-5` 评分与 A/B benchmark runner
- `mind/offline/jobs.py` / `mind/offline/service.py` / `mind/offline/worker.py`：Phase E 离线 job contract、maintenance service 与单进程 worker
- `mind/offline/replay.py` / `mind/offline/audit.py` / `mind/offline/assessment.py`：Replay target ranking、evidence audit、`LongHorizonDev v1` 与 Phase E gate
- `mind/governance/service.py` / `mind/governance/gate.py`：Phase H governance control plane 与 formal gate
- `mind/cli.py` / `mind/cli_config.py` / `mind/cli_gate.py`：统一开发/验收 CLI、profile/backend 解析与 Phase J formal gate
- `mind/fixtures/retrieval_benchmark.py`：固定的 RetrievalBenchmark v0 / v1
- `mind/fixtures/episode_answer_bench.py`：固定的 `EpisodeAnswerBench v1`
- `mind/fixtures/long_horizon_dev.py`：固定的 `LongHorizonDev v1`
- `mind/fixtures/mind_cli_scenarios.py`：固定的 `MindCliScenarioSet v1`
- `scripts/run_phase_b_gate.py` / `scripts/run_phase_c_gate.py` / `scripts/run_phase_d_smoke.py` / `scripts/run_phase_e_startup.py` / `scripts/run_phase_e_gate.py` / `scripts/run_phase_f_manifest.py` / `scripts/run_phase_f_baselines.py` / `scripts/run_phase_f_report.py` / `scripts/run_phase_f_comparison.py` / `scripts/run_phase_f_gate.py` / `scripts/run_phase_h_gate.py` / `scripts/run_phase_i_gate.py` / `scripts/run_phase_j_gate.py` / `scripts/run_offline_worker_once.py`：本地 gate / worker 入口
- `tests/test_phase_b_gate.py` / `tests/test_phase_c_gate.py` / `tests/test_phase_d_smoke.py`：阶段 gate 测试

当前存储口径：

- `PostgreSQL` 是 Phase D 起的正式主存储和默认真相源。
- `mind` / `mind-api` / `mind-mcp` / compose 运行时统一只使用 `PostgreSQL`。
- `SQLite` 会继续保留，但角色仅限 reference backend，用于 Phase B / C 基线、CI、测试和 parity 校验。
- 这不是“双主库并存”；`SQLite` 不再属于产品运行时路径。

---

## 文档结构

- [产品文档首页](./docs/index.md)
- [文档索引与作者指南](./docs/docs-authoring.md)
- [产品概览](./docs/product/overview.md)
- [快速开始](./docs/product/quickstart.md)
- [部署指南](./docs/product/deployment.md)
- [CLI 指南](./docs/product/cli.md)
- [REST API 指南](./docs/product/api.md)
- [MCP 指南](./docs/product/mcp.md)
- [系统总览](./docs/architecture/system-overview.md)
- [Frontend Experience](./docs/architecture/frontend-experience.md)
- [历史资料与证据](./docs/history-and-evidence.md)
- [产品化方案与验收蓝图](./docs/design/productization_program.md)
- [产品化审计报告](./docs/reports/productization_audit_report.md)

本地预览产品文档：

```bash
./scripts/dev.sh
```

开发环境会同时启动带热更新的文档服务，默认地址是 `http://127.0.0.1:18602`。
产品前端页面则挂载在 API 下：`http://127.0.0.1:18600/frontend/`。

如果只想单独预览文档站：

```bash
uv sync --extra docs
uv run mkdocs serve --livereload -a 0.0.0.0:18603
```

本地构建/发布静态文档站：

```bash
./scripts/docs-release.sh build
./scripts/docs-release.sh publish-local
```

`publish-local` 默认发布到 `http://127.0.0.1:18604`，避免与开发/生产环境冲突。

默认已使用清华 TUNA PyPI 镜像。如果你需要覆盖，可在 `.env.dev.local` / `.env.prod.local` 中设置：
`MIND_PIP_INDEX_URL`、`MIND_PIP_EXTRA_INDEX_URL`、`MIND_PIP_TRUSTED_HOST`。

GitHub Pages 自动发布：

- workflow: `.github/workflows/docs-pages.yml`
- push 到 `main`、tag `v*` / `docs-v*` 或手动触发后会构建并发布

## 运行方式

推荐从 Phase C 起统一使用 `pyproject.toml` + `uv`：

```bash
uv sync --extra dev
uv run mindtest -h
uv run mindtest primitive -h
# 以下 SQLite 示例仅用于测试/验收 CLI (`mindtest`)，不适用于产品运行时 `mind`
uv run mindtest primitive write-raw --sqlite-path artifacts/dev/mind.sqlite3 --record-kind user_message --episode-id episode-demo --timestamp-order 1 --content "remember this"
uv run mindtest primitive read --sqlite-path artifacts/dev/mind.sqlite3 --object-id raw-episode-demo-...
uv run mindtest access -h
uv run mindtest access run --sqlite-path artifacts/dev/mind.sqlite3 --seed-bench-fixtures --mode flash --task-id task-001 --episode-id episode-001 --query "For episode-001, reply with only success or failure."
uv run mindtest access benchmark
uv run mindtest governance -h
uv run mindtest governance plan-conceal --sqlite-path artifacts/dev/mind.sqlite3 --episode-id episode-demo --reason "conceal demo episode"
uv run mindtest demo -h
uv run mindtest demo ingest-read
uv run mindtest demo access-run
uv run mindtest gate -h
uv run mindtest gate phase-i --output artifacts/phase_i/gate_report.json
uv run mindtest gate phase-j --dsn postgresql+psycopg://postgres:postgres@127.0.0.1:55432/postgres --output artifacts/phase_j/gate_report.json
uv run mindtest report -h
uv run mindtest report acceptance --phase h
uv run mindtest offline -h
uv run mindtest offline worker --dsn postgresql+psycopg://postgres:postgres@127.0.0.1:18605/postgres --max-jobs 5
uv run mindtest config show
uv run mindtest config doctor --backend postgresql
uv run pytest -q
uv run mindtest-phase-b-gate
uv run mindtest-phase-c-gate
uv run mindtest-phase-d-smoke
uv run mindtest-phase-e-startup
uv run mindtest-phase-e-gate
uv run mindtest-phase-f-manifest
uv run mindtest-phase-f-baselines
uv run mindtest-phase-f-report --repeat-count 3 --output artifacts/phase_f/baseline_report.json
uv run mindtest-phase-f-comparison --repeat-count 3 --output artifacts/phase_f/comparison_report.json
uv run mindtest-phase-f-gate --repeat-count 3 --output artifacts/phase_f/gate_report.json
uv run mindtest-phase-g-cost-report --repeat-count 3 --output artifacts/phase_g/cost_report.json
uv run mindtest-phase-g-strategy-dev --run-id 1
uv run mindtest-phase-g-gate --repeat-count 3 --output artifacts/phase_g/gate_report.json
uv run mindtest-phase-j-gate --dsn postgresql+psycopg://postgres:postgres@127.0.0.1:55432/postgres --output artifacts/phase_j/gate_report.json
uv run mindtest-postgres-regression --dsn postgresql+psycopg://postgres:postgres@127.0.0.1:18605/postgres
uv run mindtest-offline-worker-once --dsn postgresql+psycopg://postgres:postgres@127.0.0.1:18605/postgres --max-jobs 5
uv run ruff check mind tests scripts
uv run mypy
```

如果本地还没有 `uv`，当前仓库仍兼容项目虚拟环境下的脚本执行方式：

```bash
.venv/bin/python -m pytest -q
.venv/bin/python scripts/run_phase_b_gate.py
.venv/bin/python scripts/run_phase_c_gate.py
.venv/bin/python scripts/run_phase_d_smoke.py
.venv/bin/python scripts/run_phase_e_startup.py
.venv/bin/python scripts/run_phase_e_gate.py
.venv/bin/python scripts/run_phase_f_manifest.py
.venv/bin/python scripts/run_phase_f_baselines.py
.venv/bin/python scripts/run_phase_f_report.py --repeat-count 3 --output /tmp/phase_f_report.json
.venv/bin/python scripts/run_phase_f_comparison.py --repeat-count 3 --output /tmp/phase_f_comparison.json
.venv/bin/python scripts/run_phase_f_gate.py --repeat-count 3 --output /tmp/phase_f_gate.json
.venv/bin/python scripts/run_phase_g_cost_report.py --repeat-count 3 --output /tmp/phase_g_cost_report.json
.venv/bin/python scripts/run_phase_g_strategy_dev.py --run-id 1
.venv/bin/python scripts/run_phase_g_gate.py --repeat-count 3 --output /tmp/phase_g_gate.json
.venv/bin/python scripts/run_phase_j_gate.py --dsn postgresql+psycopg://postgres:postgres@127.0.0.1:55432/postgres --output /tmp/phase_j_gate.json
.venv/bin/python scripts/run_postgres_regression.py --dsn postgresql+psycopg://postgres:postgres@127.0.0.1:18605/postgres
.venv/bin/python scripts/run_offline_worker_once.py --dsn postgresql+psycopg://postgres:postgres@127.0.0.1:18605/postgres --max-jobs 5
```

当前本地 gate 基线输出应满足：

- Phase B：`phase_b_gate=PASS`
- Phase C：`phase_c_gate=PASS`
- Phase D smoke：`phase_d_smoke=PASS`
- Phase E startup：`phase_e_startup=PASS`
- Phase E gate：`phase_e_gate=PASS`
- Phase F gate：`phase_f_gate=PASS`
- Phase G gate：`phase_g_gate=PASS`
- Phase J gate：`phase_j_gate=PASS`

当前阶段状态说明：

- 当前工作树已通过 `Phase J acceptance gate`。
- `D-5` 现在使用 `EpisodeAnswerBench v1` 的 answer-level A/B benchmark，而不是 `task_success_proxy`。
- `Phase D smoke report` 保留为启动期 / pre-acceptance 基线记录；最新正式口径见 [Phase D 验收报告](./docs/reports/phase_d_acceptance_report.md)。
- Phase E 已完成本地 gate 与独立审计；正式口径见 [Phase E 验收报告](./docs/reports/phase_e_acceptance_report.md) 和 [Phase E 独立审计报告](./docs/reports/phase_e_independent_audit.md)。
- Phase F 已完成本地验收与独立审计；正式口径见 [Phase F 验收报告](./docs/reports/phase_f_acceptance_report.md) 和 [Phase F 独立审计报告](./docs/reports/phase_f_independent_audit.md)。
- Phase G 已完成本地验收与独立审计；正式口径见 [Phase G 验收报告](./docs/reports/phase_g_acceptance_report.md) 和 [Phase G 独立审计报告](./docs/reports/phase_g_independent_audit.md)。
- Phase H 已完成本地 gate 与 PostgreSQL 集成验证；正式口径见 [Phase H 验收报告](./docs/reports/phase_h_acceptance_report.md)。
- Phase I 已完成本地 gate 与 runtime access benchmark；正式口径见 [Phase I 验收报告](./docs/reports/phase_i_acceptance_report.md)。
- Phase J 已完成统一 CLI formal gate；正式口径见 [Phase J 验收报告](./docs/reports/phase_j_acceptance_report.md)。
- [Phase E 启动清单](./docs/design/phase_e_startup_checklist.md) 继续保留启动与收敛轨迹，不再代表当前通过口径。
- [Phase F 启动清单](./docs/design/phase_f_startup_checklist.md) 继续保留启动与收敛轨迹，不再代表当前通过口径。
- [Phase G 启动清单](./docs/design/phase_g_startup_checklist.md) 继续保留启动与收敛轨迹，不再代表当前通过口径。

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
