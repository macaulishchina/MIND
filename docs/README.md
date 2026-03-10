# 文档索引

`docs/` 目录按“冻结规范 / 设计拆解 / 研究笔记 / 验收报告”分层组织，避免所有文档继续堆在同一级目录。

## 目录结构

- `foundation/`
  - [spec.md](./foundation/spec.md)：当前冻结的核心系统规范，包含 runtime access policy、provenance control plane、support unit 与 governance / reshape loop
  - [phase_gates.md](./foundation/phase_gates.md)：阶段 gate、共享指标与验收规则，以及 Phase G 之后的 H ~ K 扩展路线
  - [implementation_stack.md](./foundation/implementation_stack.md)：分阶段实现技术栈与基础设施冻结方案
- `design/`
  - [design_breakdown.md](./design/design_breakdown.md)：设计拆解、阶段推进方式与实现重点
  - [phase_c_startup_checklist.md](./design/phase_c_startup_checklist.md)：Phase C 启动清单与优先级排序
  - [phase_e_startup_checklist.md](./design/phase_e_startup_checklist.md)：Phase E 启动清单与离线维护基础层现状
  - [phase_f_startup_checklist.md](./design/phase_f_startup_checklist.md)：Phase F 启动清单、任务拆分与评测前置工件
  - [phase_g_startup_checklist.md](./design/phase_g_startup_checklist.md)：Phase G 启动清单、任务拆分与策略优化前置工件
  - [phase_h_startup_checklist.md](./design/phase_h_startup_checklist.md)：Phase H 启动清单、provenance foundation 范围控制与任务拆分
  - [phase_i_startup_checklist.md](./design/phase_i_startup_checklist.md)：Phase I 启动清单、runtime access modes 范围控制与任务拆分
  - [phase_j_startup_checklist.md](./design/phase_j_startup_checklist.md)：Phase J 启动清单、governance reshape 范围控制与任务拆分
  - [phase_k_startup_checklist.md](./design/phase_k_startup_checklist.md)：Phase K 启动清单、persona projection 范围控制与任务拆分
- `research/`
  - [research_notes.md](./research/research_notes.md)：早期研究思路、开放问题与探索性笔记
- `reports/`
  - [phase_a_acceptance_report.md](./reports/phase_a_acceptance_report.md)：Phase A 正式验收记录
  - [phase_b_acceptance_report.md](./reports/phase_b_acceptance_report.md)：Phase B 正式验收记录
  - [phase_b_independent_audit.md](./reports/phase_b_independent_audit.md)：Phase B 独立审计与纠偏记录
  - [phase_c_independent_audit.md](./reports/phase_c_independent_audit.md)：Phase C 独立审计与问题收敛记录
  - [phase_c_acceptance_report.md](./reports/phase_c_acceptance_report.md)：Phase C 正式验收记录
  - [phase_c_golden_calls_audit.md](./reports/phase_c_golden_calls_audit.md)：PrimitiveGoldenCalls v1 与 Phase C smoke gate 独立审计
  - [postgres_store_audit.md](./reports/postgres_store_audit.md)：PostgreSQL store、Alembic 与 Phase B/C Postgres 回归审核报告
  - [phase_d_smoke_report.md](./reports/phase_d_smoke_report.md)：Phase D 当前状态、Phase D smoke 与 D-5 raw-top20 benchmark 报告
  - [phase_d_independent_audit.md](./reports/phase_d_independent_audit.md)：Phase D 独立审计与深度复审记录
  - [phase_d_acceptance_report.md](./reports/phase_d_acceptance_report.md)：Phase D 正式验收记录
  - [phase_e_acceptance_report.md](./reports/phase_e_acceptance_report.md)：Phase E 正式验收记录
  - [phase_e_independent_audit.md](./reports/phase_e_independent_audit.md)：Phase E 独立审计报告
  - [phase_f_acceptance_report.md](./reports/phase_f_acceptance_report.md)：Phase F 正式验收记录
  - [phase_f_independent_audit.md](./reports/phase_f_independent_audit.md)：Phase F 独立审核报告
  - [phase_g_acceptance_report.md](./reports/phase_g_acceptance_report.md)：Phase G 正式验收记录
  - [phase_g_independent_audit.md](./reports/phase_g_independent_audit.md)：Phase G 独立审计报告

## 查询入口

- 想看“系统到底怎么定义”：先看 [foundation/spec.md](./foundation/spec.md)
- 想看“`source_refs` 和 provenance 到底有什么区别、治理重塑怎么定义”：先看 [foundation/spec.md](./foundation/spec.md)
- 想看“Flash / Recall / Reconstruct / Reflective 和 `auto` 档怎么定义”：先看 [foundation/spec.md](./foundation/spec.md)
- 想看“某阶段何时算完成”：先看 [foundation/phase_gates.md](./foundation/phase_gates.md)
- 想看“新增治理能力会不会推翻 A ~ G 既有通过记录”：先看 [foundation/phase_gates.md](./foundation/phase_gates.md)
- 想看“运行时记忆深度后续应该怎么评测”：先看 [foundation/phase_gates.md](./foundation/phase_gates.md)
- 想看“实现到底该用什么技术栈”：先看 [foundation/implementation_stack.md](./foundation/implementation_stack.md)
- 想看“为什么现在同时保留 SQLite 和 PostgreSQL，以及两者各自角色”：先看 [foundation/implementation_stack.md](./foundation/implementation_stack.md)
- 想看“为什么这样设计、怎么推进实现”：先看 [design/design_breakdown.md](./design/design_breakdown.md)
- 想看“为什么要把 provenance / governance 单独做成第三条循环”：先看 [design/design_breakdown.md](./design/design_breakdown.md)
- 想看“组织好的记忆如何长成人格层”：先看 [design/design_breakdown.md](./design/design_breakdown.md)，再看 [research/research_notes.md](./research/research_notes.md)
- 想看“Phase C 启动项后来到底怎么收敛”：先看 [design/phase_c_startup_checklist.md](./design/phase_c_startup_checklist.md)
- 想看“Phase E 启动期是怎么收敛到正式 gate 的”：先看 [design/phase_e_startup_checklist.md](./design/phase_e_startup_checklist.md)
- 想看“Phase F 启动期是怎么收敛到本地验收的”：先看 [design/phase_f_startup_checklist.md](./design/phase_f_startup_checklist.md)
- 想看“Phase G 会按什么顺序推进”：先看 [design/phase_g_startup_checklist.md](./design/phase_g_startup_checklist.md)
- 想看“Phase H 应该先做什么、不该做什么”：先看 [design/phase_h_startup_checklist.md](./design/phase_h_startup_checklist.md)
- 想看“Phase I 应该怎么把固定档位和 `auto` 做成正式能力”：先看 [design/phase_i_startup_checklist.md](./design/phase_i_startup_checklist.md)
- 想看“Phase J 应该怎么做 mixed-source rewrite 和 `erase_scope`”：先看 [design/phase_j_startup_checklist.md](./design/phase_j_startup_checklist.md)
- 想看“Phase K 应该怎么把人格层限制在可追溯 projection”：先看 [design/phase_k_startup_checklist.md](./design/phase_k_startup_checklist.md)
- 想看“还在探索中的想法和背景笔记”：先看 [research/research_notes.md](./research/research_notes.md)
- 想看“Phase D 启动期是怎么收敛的、D-5 最初如何建立”：先看 [reports/phase_d_smoke_report.md](./reports/phase_d_smoke_report.md)
- 想看“最新的正式结果”：先看 [reports/phase_g_acceptance_report.md](./reports/phase_g_acceptance_report.md)，再看 [reports/phase_f_acceptance_report.md](./reports/phase_f_acceptance_report.md)、[reports/phase_e_acceptance_report.md](./reports/phase_e_acceptance_report.md)、[reports/phase_d_acceptance_report.md](./reports/phase_d_acceptance_report.md) 和 [reports/phase_c_acceptance_report.md](./reports/phase_c_acceptance_report.md)
- 想看"最新的独立审计 / 审核"：先看 [reports/phase_g_independent_audit.md](./reports/phase_g_independent_audit.md)，再看 [reports/phase_f_independent_audit.md](./reports/phase_f_independent_audit.md)、[reports/phase_e_independent_audit.md](./reports/phase_e_independent_audit.md)、[reports/phase_d_independent_audit.md](./reports/phase_d_independent_audit.md)、[reports/postgres_store_audit.md](./reports/postgres_store_audit.md)、[reports/phase_c_golden_calls_audit.md](./reports/phase_c_golden_calls_audit.md) 和 [reports/phase_c_independent_audit.md](./reports/phase_c_independent_audit.md)
- 想看“Phase A / B 的历史验收记录”：再看 [reports/phase_a_acceptance_report.md](./reports/phase_a_acceptance_report.md)、[reports/phase_b_acceptance_report.md](./reports/phase_b_acceptance_report.md) 和 [reports/phase_b_independent_audit.md](./reports/phase_b_independent_audit.md)

## 扩展约定

- 冻结语义、接口、指标、gate 的文档放入 `foundation/`
- 对现有方案的实现拆解、工程计划、路线设计放入 `design/`
- 尚未冻结、允许被推翻的探索性内容放入 `research/`
- 具名阶段验收、审计、评审结论放入 `reports/`

`reports/` 下的文档按日期记录时点结论；如果同一阶段同时存在审计和验收，默认以后者作为“当前是否通过”的最新口径。

如果后续文档数量继续增长，优先在这些目录下继续细分，而不是重新回到扁平结构。
