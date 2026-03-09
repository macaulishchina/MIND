# 文档索引

`docs/` 目录按“冻结规范 / 设计拆解 / 研究笔记 / 验收报告”分层组织，避免所有文档继续堆在同一级目录。

## 目录结构

- `foundation/`
  - [spec.md](./foundation/spec.md)：当前冻结的核心系统规范
  - [phase_gates.md](./foundation/phase_gates.md)：阶段 gate、共享指标与验收规则
  - [implementation_stack.md](./foundation/implementation_stack.md)：分阶段实现技术栈与基础设施冻结方案
- `design/`
  - [design_breakdown.md](./design/design_breakdown.md)：设计拆解、阶段推进方式与实现重点
  - [phase_c_startup_checklist.md](./design/phase_c_startup_checklist.md)：Phase C 启动清单与优先级排序
- `research/`
  - [research_notes.md](./research/research_notes.md)：早期研究思路、开放问题与探索性笔记
- `reports/`
  - [phase_a_acceptance_report.md](./reports/phase_a_acceptance_report.md)：Phase A 正式验收记录
  - [phase_b_acceptance_report.md](./reports/phase_b_acceptance_report.md)：Phase B 正式验收记录
  - [phase_b_independent_audit.md](./reports/phase_b_independent_audit.md)：Phase B 独立审计与纠偏记录
  - [phase_c_independent_audit.md](./reports/phase_c_independent_audit.md)：Phase C 独立审计与问题收敛记录
  - [phase_c_acceptance_report.md](./reports/phase_c_acceptance_report.md)：Phase C 正式验收记录
  - [phase_c_golden_calls_audit.md](./reports/phase_c_golden_calls_audit.md)：PrimitiveGoldenCalls v1 与 Phase C smoke gate 独立审计

## 查询入口

- 想看“系统到底怎么定义”：先看 [foundation/spec.md](./foundation/spec.md)
- 想看“某阶段何时算完成”：先看 [foundation/phase_gates.md](./foundation/phase_gates.md)
- 想看“实现到底该用什么技术栈”：先看 [foundation/implementation_stack.md](./foundation/implementation_stack.md)
- 想看“为什么这样设计、怎么推进实现”：先看 [design/design_breakdown.md](./design/design_breakdown.md)
- 想看“Phase C 启动项后来到底怎么收敛”：先看 [design/phase_c_startup_checklist.md](./design/phase_c_startup_checklist.md)
- 想看“还在探索中的想法和背景笔记”：先看 [research/research_notes.md](./research/research_notes.md)
- 想看“最新的正式结果”：先看 [reports/phase_c_acceptance_report.md](./reports/phase_c_acceptance_report.md)
- 想看“最新的独立审计”：先看 [reports/phase_c_golden_calls_audit.md](./reports/phase_c_golden_calls_audit.md)，再看 [reports/phase_c_independent_audit.md](./reports/phase_c_independent_audit.md)
- 想看“Phase A / B 的历史验收记录”：再看 [reports/phase_a_acceptance_report.md](./reports/phase_a_acceptance_report.md)、[reports/phase_b_acceptance_report.md](./reports/phase_b_acceptance_report.md) 和 [reports/phase_b_independent_audit.md](./reports/phase_b_independent_audit.md)

## 扩展约定

- 冻结语义、接口、指标、gate 的文档放入 `foundation/`
- 对现有方案的实现拆解、工程计划、路线设计放入 `design/`
- 尚未冻结、允许被推翻的探索性内容放入 `research/`
- 具名阶段验收、审计、评审结论放入 `reports/`

`reports/` 下的文档按日期记录时点结论；如果同一阶段同时存在审计和验收，默认以后者作为“当前是否通过”的最新口径。

如果后续文档数量继续增长，优先在这些目录下继续细分，而不是重新回到扁平结构。
