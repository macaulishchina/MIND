# Phase J 启动清单

时点说明：这份文档记录的是 Phase I 通过后，MIND 进入 `Phase J / Governance / Reshape` 前的启动约束、任务拆分和范围控制。正式通过口径以后续 Phase J 验收报告为准；这里先冻结启动顺序，避免把治理执行、persona 和更大范围的产品合规流程揉成一个失控阶段。

## 目标

Phase J 做治理执行层，不做 persona。

本阶段的目标是：

1. 打通 `plan / preview / approve / execute` 的完整治理链
2. 落地 `support unit` 级 mixed-source rewrite
3. 落地默认 `erase_scope=memory_world_plus_artifacts`
4. 建立 artifact cleanup、泄露回归和中断恢复能力
5. 冻结 `ProvenanceGovernanceBench v1`

## 非目标

Phase J 明确不做：

1. persona / projection 实现
2. 完整产品级工单、审批后台或多租户合规系统
3. 绕开 preview / audit 的快捷治理接口
4. 把 governance 扩展成普通 offline maintenance 的替代品
5. 通过人工规则先验写死所有 mixed-source rewrite 结果

## 任务拆分

1. `J1`：冻结 `ProvenanceGovernanceBench v1` 与 preview gold fixture
2. `J2`：实现 preview / plan 准确性与 `support unit` 投影
3. `J3`：实现 mixed-source rewrite 与版本更新
4. `J4`：实现 `erase_scope`、artifact cleanup 与中断恢复
5. `J5`：补 Phase J gate、验收报告和故障注入审计

## 推荐推进顺序

### `J1` 治理 fixture 冻结

- 把 [../foundation/phase_gates.md](../foundation/phase_gates.md) 中的 `J-1 ~ J-8` 作为唯一 formal gate
- 冻结 `ProvenanceGovernanceBench v1`：
  - `conceal`
  - `erase(memory_world)`
  - `erase(memory_world_plus_artifacts)`
  - `erase(full)`
  - mixed-source rewrite
- 为每个样例补充 gold preview、gold rewrite 和 expected cleanup scope

### `J2` Preview 与投影

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

### `J3` Rewrite 与版本更新

- mixed-source 派生对象按 `support unit` 执行：
  - `retained`
  - `rewritten`
  - `dropped`
- 保证：
  - 新版本可追溯
  - dangling support refs `= 0`
  - provenance footprint 已更新

### `J4` Scope 清理与恢复

- 默认实现：
  - `memory_world_plus_artifacts`
- 高风险扩展：
  - `full`
- 补：
  - artifact cleanup
  - fault injection
  - interrupted resume
  - idempotent retry

### `J5` Gate 与报告

- 产出：
  - governance preview audit
  - rewrite correctness report
  - erase scope cleanup report
  - Phase J gate report

## 当前关键设计约束

1. governance 是独立主动阶段，不是 runtime 热路径
2. mixed-source 对象不允许只删依赖不改内容
3. `full` scope 一定属于高风险治理路径
4. `conceal` 和 `erase` 的结果都不能在普通路径旁路漏出
5. Phase J 必须把失败恢复和审计链一起做完，而不是只做 happy path

## 依赖关系

- 依赖 Phase H 的 provenance foundation 与 capability 边界
- 依赖 Phase I 已经稳定的 runtime access policy，但不把 access mode 混进治理执行语义
- 依赖现有对象 schema、version chain 与 artifact 目录结构

## 风险提醒

1. 最大风险是 preview 不准，后续 rewrite 只能在错误范围上执行
2. 第二个风险是 `erase_scope` 漏掉缓存、日志、报表或外部副本
3. 第三个风险是 mixed-source rewrite 造成过删、漏删或 dangling refs
4. 第四个风险是治理执行失败后留下半完成状态，且无法恢复

## 完成标志

当以下条件同时满足时，Phase J 可以进入正式验收：

- `J-1 ~ J-8` 都有可运行验证路径
- `ProvenanceGovernanceBench v1`、preview audit、rewrite audit 和 cleanup report 都可生成
- `support unit` 投影、重写语义、scope 边界与恢复策略已经冻结
- 文档、实现和测试对 Phase J 的范围表述一致
