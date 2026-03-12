# Phase N 启动清单

时点说明：这份文档记录的是 Phase M 通过后，MIND 进入 `Phase N / Governance / Reshape` 前的启动约束、任务拆分和范围控制。正式通过口径以后续 Phase N 验收报告为准；这里先冻结治理执行层边界，避免把后移后的治理、persona 和更大范围的产品合规流程揉成一个失控阶段。

## 目标

Phase N 做治理执行层，不做 persona。

本阶段的目标是：

1. 打通 `plan / preview / approve / execute` 的完整治理链
2. 落地 `support unit` 级 mixed-source rewrite
3. 落地默认 `erase_scope=memory_world_plus_artifacts`
4. 建立 artifact cleanup、泄露回归和中断恢复能力
5. 冻结 `ProvenanceGovernanceBench v1`

## 非目标

Phase N 明确不做：

1. persona / projection 实现
2. 完整产品级工单、审批后台或多租户合规系统
3. 绕开 preview / audit 的快捷治理接口
4. 把 governance 扩展成普通 offline maintenance 的替代品
5. 通过人工规则先验写死所有 mixed-source rewrite 结果

## 任务拆分

1. `N1`：冻结 `ProvenanceGovernanceBench v1` 与 preview gold fixture
2. `N2`：实现 preview / plan 准确性与 `support unit` 投影
3. `N3`：实现 mixed-source rewrite 与版本更新
4. `N4`：实现 `erase_scope`、artifact cleanup 与中断恢复
5. `N5`：补 Phase N gate、验收报告和故障注入审计

## 当前评估（`2026-03-12`）

### 已完成的基础工作

- `Phase H` 已完成最小 governance control plane：`plan / preview / execute(conceal)`、治理审计链、online / offline conceal 隔离、低权限阻断与 provenance foundation 已存在
- governance 已暴露到正式 transport：当前仓库已有 REST、MCP 和统一 CLI 的 `plan_conceal / preview_conceal / execute_conceal`
- `execute_conceal` 已具备最小幂等性：重复执行会进入 `already_concealed_object_ids`，不会因为重复 conceal 直接冲突
- `Phase L / M / WP-8` 的 telemetry、frontend、product readiness 和 artifact bundle 已收口，因此 `Phase N` 当前不再受产品化入口或调试基线阻塞
- 当前仓库全量回归结果为 `pytest -q -> 640 passed, 12 skipped`

### 尚未完成的工作

- 还没有 `ProvenanceGovernanceBench v1`，也没有 preview gold fixture、gold rewrite 或 expected cleanup scope
- 现有治理语义仍然是 `conceal-only`；尚未实现 `erase(memory_world)`、`erase(memory_world_plus_artifacts)`、`erase(full)` 或 `approve(full)`
- 还没有 `support unit` 级治理投影；`claim / facet / rule / slot` 的最小治理粒度尚未进入正式 contract
- 还没有 mixed-source rewrite 执行路径，因此 `retained / rewritten / dropped` 的判定、版本更新和 dangling support refs 审计都未落地
- 还没有 artifact cleanup、fault injection、interrupted resume、面向 `Phase N` 的 idempotent retry 体系
- 还没有 `governance preview audit`、`rewrite correctness report`、`erase scope cleanup report`、`Phase N gate report`

### 需要做的工作

1. 先做 `N1`，冻结 `ProvenanceGovernanceBench v1` 与 preview gold fixture，把 `N-1 ~ N-8` 对应的基准样例先固定住
2. 再做 `N2`，把现有 `conceal` preview 从“原始对象级”推进到“support unit 级”投影，并给出 approval/scope 语义
3. 接着做 `N3`，实现 mixed-source rewrite、版本更新和 `retained / rewritten / dropped` 判定
4. 然后做 `N4`，补 `erase_scope=memory_world_plus_artifacts`、artifact cleanup、恢复与重试；`full` scope 保持高风险路径
5. 最后做 `N5`，把 preview audit、rewrite audit、cleanup audit 和 `Phase N gate` 组装成正式验收闭环

## 推荐推进顺序

### `N1` 治理 fixture 冻结

- 把 [../foundation/phase_gates.md](../foundation/phase_gates.md) 中的 `N-1 ~ N-8` 作为唯一 formal gate
- 冻结 `ProvenanceGovernanceBench v1`：
  - `conceal`
  - `erase(memory_world)`
  - `erase(memory_world_plus_artifacts)`
  - `erase(full)`
  - mixed-source rewrite
- 为每个样例补充 gold preview、gold rewrite 和 expected cleanup scope

### `N2` Preview 与投影

- 把对象稳定投影到最小治理粒度：
  - `claim`
  - `facet`
  - `rule`
  - `slot`
- `plan / preview` 必须输出：
  - 受影响原始对象
  - 受影响 `support unit`
  - 预计 `retained / rewritten / dropped`
  - 需要的 approval 等级

### `N3` Rewrite 与版本更新

- mixed-source 派生对象按 `support unit` 执行：
  - `retained`
  - `rewritten`
  - `dropped`
- 保证：
  - 新版本可追溯
  - dangling support refs `= 0`
  - provenance footprint 已更新

### `N4` Scope 清理与恢复

- 默认实现：
  - `memory_world_plus_artifacts`
- 高风险扩展：
  - `full`
- 补：
  - artifact cleanup
  - fault injection
  - interrupted resume
  - idempotent retry

### `N5` Gate 与报告

- 产出：
  - governance preview audit
  - rewrite correctness report
  - erase scope cleanup report
  - Phase N gate report

## 当前关键设计约束

1. governance 是独立主动阶段，不是 runtime 热路径
2. mixed-source 对象不允许只删依赖不改内容
3. `full` scope 一定属于高风险治理路径
4. `conceal` 和 `erase` 的结果都不能在普通路径旁路漏出
5. Phase N 必须把失败恢复和审计链一起做完，而不是只做 happy path

## 依赖关系

- 依赖 Phase H 的 provenance foundation 与 capability 边界
- 依赖 Phase I 已经稳定的 runtime access policy，但不把 access mode 混进治理执行语义
- 阶段顺序上后移到 Phase M 之后，但治理语义仍以前序 control plane 为基础

## 风险提醒

1. 最大风险是 preview 不准，后续 rewrite 只能在错误范围上执行
2. 第二个风险是 `erase_scope` 漏掉缓存、日志、报表或外部副本
3. 第三个风险是 mixed-source rewrite 造成过删、漏删或 dangling refs
4. 第四个风险是治理执行失败后留下半完成状态，且无法恢复

## 完成标志

当以下条件同时满足时，Phase N 可以进入正式验收：

- `N-1 ~ N-8` 都有可运行验证路径
- `ProvenanceGovernanceBench v1`、preview audit、rewrite audit 和 cleanup report 都可生成
- `support unit` 投影、重写语义、scope 边界与恢复策略已经冻结
- 文档、实现和测试对 Phase N 的范围表述一致
