# Phase J 验收报告

验收日期：`2026-03-10`

验收对象版本：

- `git HEAD = d898dc2`
- 本报告对应对象为 `d898dc2` 之后、尚未提交的本地工作树（包含本轮 Phase J unified CLI、config、demo、gate 与验收文档改动）

数据 / fixture 版本：

- `MindCliScenarioSet v1`
- `AccessDepthBench v1` canonical seed fixtures
- 本地 PostgreSQL demo DSN：`postgresql+psycopg://postgres:postgres@127.0.0.1:55432/postgres`

验收对象：

- [phase_gates.md](../foundation/phase_gates.md)
- [phase_j_startup_checklist.md](../design/phase_j_startup_checklist.md)
- [pyproject.toml](../../pyproject.toml)
- [cli.py](../../mind/cli.py)
- [cli_config.py](../../mind/cli_config.py)
- [phase_j.py](../../mind/phase_j.py)
- [mind_cli_scenarios.py](../../mind/fixtures/mind_cli_scenarios.py)
- [run_phase_j_gate.py](../../scripts/run_phase_j_gate.py)
- [test_cli_config.py](../../tests/test_cli_config.py)
- [test_phase_j_cli_preparation.py](../../tests/test_phase_j_cli_preparation.py)
- [test_phase_j_gate.py](../../tests/test_phase_j_gate.py)

相关文档：

- Phase J 启动与范围控制见 [../design/phase_j_startup_checklist.md](../design/phase_j_startup_checklist.md)
- Phase J gate 与阶段定义见 [../foundation/phase_gates.md](../foundation/phase_gates.md)

验收范围：

- `J-1` CLI help 完整度
- `J-2` 命令族覆盖
- `J-3` 体验流覆盖
- `J-4` profile / backend 切换正确性
- `J-5` 输出与退出码稳定性
- `J-6` 旧能力包装无回归

验收方法：

- 按 [phase_gates.md](../foundation/phase_gates.md) 的 `J-1 ~ J-6` 逐条核对
- 运行 `.venv/bin/pytest -q`
- 运行 `.venv/bin/ruff check mind tests scripts`
- 运行 `.venv/bin/mypy`
- 运行 `python3 scripts/run_phase_j_gate.py --dsn postgresql+psycopg://postgres:postgres@127.0.0.1:55432/postgres --output artifacts/phase_j/gate_report.json`

## 1. 结论

Phase J 本次验收结论：`PASS`

判定依据：

- `J-1 ~ J-6` 六项 MUST-PASS 指标全部通过
- `mind` 顶层 CLI 已收敛为统一体验入口，`primitive / access / offline / governance / gate / report / demo / config` 八个一级命令族全部可达
- `MindCliScenarioSet v1`、config audit、输出/退出码 contract 与 Phase J formal gate 已形成统一闭环
- 本地全量静态检查、测试和统一 CLI 包装回归通过，未发现对已完成 Phase B/C/H/I/G 的回归

## 2. Gate 结果

| Gate | 阈值 | 结果 | 结论 |
| --- | --- | --- | --- |
| `J-1` | `mind -h` 与全部一级命令 help coverage `= 100%` | `9 / 9` | `PASS` |
| `J-2` | `primitive / access / offline / governance / gate / report / demo / config = 8 / 8` 全部可达；`MindCliScenarioSet v1 >= 25` | `8 / 8`，`26` scenarios，`9` families | `PASS` |
| `J-3` | `ingest-read / retrieve / access-run / offline-job / gate-report = 5 / 5` 主流程通过 | `5 / 5`，PostgreSQL demo configured | `PASS` |
| `J-4` | `SQLite / PostgreSQL` profile 切换、配置优先级与参数解析样例 `20 / 20` 通过 | `20 / 20` | `PASS` |
| `J-5` | `text / json` 输出 schema 校验通过率 `= 100%`；非法输入的非零退出码覆盖率 `= 100%` | output `8 / 8`，invalid exit `5 / 5` | `PASS` |
| `J-6` | 现有阶段 gate 与关键能力通过统一 CLI 包装后成功率 `= 100%` | `5 / 5` | `PASS` |

补充验证：

| 验证项 | 结果 |
| --- | --- |
| `.venv/bin/pytest -q` | `252 passed, 11 skipped` |
| `.venv/bin/ruff check mind tests scripts` | `All checks passed!` |
| `.venv/bin/mypy` | `Success: no issues found in 116 source files` |
| `python3 scripts/run_phase_j_gate.py --dsn ...` | `phase_j_gate=PASS` |

备注：

- Phase J 的 representative flow audit 使用本地临时 `pgvector` 环境覆盖了 `demo offline-job` 路径，因此 `J-3` 不是纯 SQLite 口径
- 全量 `pytest` 仍包含 `11` 个可选跳过项；这不影响本次 Phase J gate 通过，因为 formal gate 已用显式 `--dsn` 覆盖了 PostgreSQL demo 流程

## 3. 逐条核对

### `J-1` CLI help 完整度

核对结果：

- [cli.py](../../mind/cli.py) 已冻结 `mind -h` 与八个一级命令族的统一帮助入口
- [phase_j.py](../../mind/phase_j.py) 当前会对 `mind -h` 与 `primitive / access / offline / governance / gate / report / demo / config` 八个一级命令逐一做 help audit
- 当前 `help_coverage_count = 9 / 9`

判定：

- `J-1 = PASS`

### `J-2` 命令族覆盖

核对结果：

- [cli.py](../../mind/cli.py) 已把 `primitive / access / offline / governance / gate / report / demo / config` 八个一级命令族全部接入统一入口
- [mind_cli_scenarios.py](../../mind/fixtures/mind_cli_scenarios.py) 已冻结 `MindCliScenarioSet v1`
- 当前 gate 中：
  - `family_reachability_count = 8 / 8`
  - `scenario_count = 26`
  - `scenario_family_count = 9`

判定：

- `J-2 = PASS`

### `J-3` 体验流覆盖

核对结果：

- [phase_j.py](../../mind/phase_j.py) 当前会执行五条代表性 CLI 主流程：
  - `demo ingest-read`
  - `primitive retrieve`
  - `demo access-run`
  - `demo offline-job`
  - `report acceptance --phase h`
- `demo offline-job` 已通过显式 PostgreSQL admin DSN 接上真实临时库与迁移链
- 当前 `representative_flow_pass_count = 5 / 5`

判定：

- `J-3 = PASS`

### `J-4` profile / backend 切换正确性

核对结果：

- [cli_config.py](../../mind/cli_config.py) 已冻结 `profile / backend / dsn / sqlite-path` 的解析优先级
- 当前支持：
  - `auto`
  - `sqlite_local`
  - `postgres_main`
  - `postgres_test`
- [phase_j.py](../../mind/phase_j.py) 当前对 `20` 条显式 config case 做解析审计
- 当前 `config_audit_pass_count = 20 / 20`

判定：

- `J-4 = PASS`

### `J-5` 输出与退出码稳定性

核对结果：

- [cli.py](../../mind/cli.py) 当前已把 Phase J 统一 CLI 的主要返回收敛成稳定 text/json output
- [phase_j.py](../../mind/phase_j.py) 会分别审计：
  - `8` 条输出 contract
  - `5` 条非法输入非零退出码覆盖
- 当前结果：
  - `output_contract_pass_count = 8 / 8`
  - `invalid_exit_coverage_count = 5 / 5`

判定：

- `J-5 = PASS`

### `J-6` 旧能力包装无回归

核对结果：

- [cli.py](../../mind/cli.py) 已把旧阶段关键入口统一包装到 `mind gate` 与 `mind report`
- [phase_j.py](../../mind/phase_j.py) 当前对以下包裹路径做回归审计：
  - `mind gate phase-b`
  - `mind gate phase-c`
  - `mind gate phase-h`
  - `mind gate phase-i`
  - `mind report acceptance --phase h`
- 当前 `wrapped_regression_pass_count = 5 / 5`

判定：

- `J-6 = PASS`

## 4. 阻断项与剩余风险

阻断项：

- 未发现阻断 Phase J 通过的硬性问题

主要发现：

- `mind` 现在已经不是脚本入口集合，而是统一帮助、统一配置、统一 demo、统一 gate 与统一 report 的正式体验层
- Phase J 没有改写 primitive / access / offline / governance 的内部语义，而是把现有能力收敛进单一入口，符合阶段边界

非阻断风险：

- Phase J gate 的 `offline-job` representative flow 依赖可用 PostgreSQL admin DSN；后续更稳妥的做法仍然是在 CI 中固定这条 demo 回归链
- 当前 CLI 的 output contract 已可测试，但前端可直接依赖的统一 API/telemetry 协议仍是后续 `Phase K / L / M` 的工作

## 5. 最终结论

本次验收判定：

`Phase J = PASS`

当前状态：

- Phase J unified CLI experience 已具备本地 formal gate
- 当前 gate 工件默认输出为 [artifacts/phase_j/gate_report.json](../../artifacts/phase_j/gate_report.json)
- 下一阶段可进入 `Phase K: LLM Capability Layer`
