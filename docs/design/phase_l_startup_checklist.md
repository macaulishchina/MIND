# Phase L 启动清单

时点说明：这份文档记录的是 Phase K 通过后，MIND 进入 `Phase L / Development Telemetry` 前的启动约束、任务拆分和范围控制。正式通过口径以后续 Phase L 验收报告为准；这里先冻结开发态观测机制的边界，避免把 telemetry、前端可视化和性能治理搅在一起。

## 目标

Phase L 只做开发模式下的完备内部观测，不做前端展示。

本阶段的目标是：

1. 设计统一 telemetry event schema
2. 在不改变现有功能逻辑的前提下侵入内部实现采集关键数据
3. 覆盖内部结构变化、状态变化和关键决策过程
4. 提供显式开发模式开关
5. 冻结 `InternalTelemetryBench v1`

## 非目标

Phase L 明确不做：

1. 面向终端用户的图形界面
2. 性能优化或采样压缩
3. 正式生产态成本治理
4. 把 telemetry 变成新的业务真相源
5. 为了采集方便而改写现有核心语义

## 任务拆分

1. `L1`：冻结 telemetry event schema 与 `InternalTelemetryBench v1`
2. `L2`：接入 `primitive / retrieval / workspace / access / offline / governance`
3. `L3`：补 before / after / delta 与 correlation id 机制
4. `L4`：实现开发模式开关和持久化策略
5. `L5`：补 Phase L gate、完备度审计和回放报告

## 推荐推进顺序

### `L1` 事件模型冻结

- 把 [../foundation/phase_gates.md](../foundation/phase_gates.md) 中的 `L-1 ~ L-6` 作为唯一 formal gate
- 至少覆盖：
  - 入口事件
  - 内部决策事件
  - 对象状态变化
  - 上下文构建结果
  - 离线动作结果
  - 治理动作结果

### `L2` 采集接入

- 先接：
  - primitive
  - retrieval
  - workspace
  - access
  - offline
  - governance
- 再补：
  - object delta
  - budget / trace 关键字段

### `L3` 关联与回放

- 保证事件可用这些 id 串起来：
  - `run_id`
  - `operation_id`
  - `job_id`
  - `workspace_id`
  - `object_version`
- 目标是后续能重建完整内部时间线

### `L4` 开关与隔离

- 必须显式提供 dev-mode 开关
- 开关关闭时：
  - 不写持久 telemetry
  - 不改变现有能力语义

### `L5` Gate 与报告

- 产出：
  - telemetry coverage audit
  - state delta completeness report
  - replayable timeline audit
  - Phase L gate report

## 当前关键设计约束

1. telemetry 是开发态观测层，不是业务层
2. 完备性优先于性能
3. 观测结果必须足以支撑后续可视化
4. 关闭开关时不得影响普通行为
5. 关键内部字段不能只采结果，不采过程

## 依赖关系

- 依赖 Phase J 的统一入口
- 依赖 Phase K 的统一 capability / provider trace
- 依赖现有模块边界已经基本稳定

## 风险提醒

1. 最大风险是事件采集不全，后续前端可视化只能看到残缺信息
2. 第二个风险是缺少 correlation id，后续无法还原执行链
3. 第三个风险是 telemetry 开关关闭时仍然残留副作用
4. 第四个风险是内部字段命名混乱，后续 debug 成本继续上升

## 完成标志

当以下条件同时满足时，Phase L 可以进入正式验收：

- `L-1 ~ L-6` 都有可运行验证路径
- `InternalTelemetryBench v1`、coverage audit 和 timeline report 都可生成
- telemetry event schema、delta schema 和 dev-mode 语义已经冻结
- 文档、实现和测试对 Phase L 的范围表述一致
