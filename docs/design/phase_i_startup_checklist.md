# Phase I 启动清单

时点说明：这份文档记录的是 Phase H 通过后，MIND 进入 `Phase I / Runtime Access Modes` 前的启动约束、任务拆分和范围控制。正式通过口径以后续 Phase I 验收报告为准；这里先冻结启动顺序，避免把 access depth、治理执行和 persona 一次性混成同一个阶段。

## 目标

Phase I 只做 runtime access modes，不做治理重写。

本阶段的目标是：

1. 落地 `Flash / Recall / Reconstruct / Reflective` 四个固定访问档
2. 落地 `auto` 调度器及其 trace / 原因码
3. 冻结 `AccessDepthBench v1`
4. 建立固定档位与 `auto` 的质量 / 性能 frontier 比较
5. 验证显式用户锁定档位不会被 `auto` 覆盖

## 非目标

Phase I 明确不做：

1. mixed-source rewrite 或 `erase_scope` 扩展
2. persona / projection 实现
3. 新增一套独立于现有 primitives 的访问深度 primitives
4. 以 provenance 信号参与 retrieval / ranking / weighting
5. 通过访问深度改写对象真值或治理语义

## 任务拆分

1. `I1`：冻结 `AccessDepthBench v1` 与四档 / `auto` 合约
2. `I2`：实现四个固定档位与 mode trace
3. `I3`：实现 `auto` 调度器、原因码与锁档遵从
4. `I4`：建立 quality / cost frontier benchmark 与回归
5. `I5`：补 Phase I gate、验收报告和调度审计

## 推荐推进顺序

### `I1` 基准与语义冻结

- 把 [../foundation/phase_gates.md](../foundation/phase_gates.md) 中的 `I-1 ~ I-8` 作为唯一 formal gate
- 冻结 `AccessDepthBench v1`：
  - `speed-sensitive`
  - `balanced`
  - `high-correctness`
- 为每个任务样例补充：
  - 推荐固定档位
  - 时间预算
  - hard constraints
  - gold facts / gold memory refs

### `I2` 固定档位落地

- `Flash`：最小 read / workspace 成本路径
- `Recall`：默认平衡档
- `Reconstruct`：允许跨片段、跨 episode 重建
- `Reflective`：在 `Reconstruct` 基础上增加证据与一致性检查
- 所有固定档位都必须输出：
  - 起始 mode
  - 关键 read / expand / verification trace
  - 最终回答前的 mode summary

### `I3` `auto` 调度器

- 支持：
  - `upgrade`
  - `downgrade`
  - `jump`
- 每次切换必须有：
  - reason code
  - 切换前后 mode
  - 触发条件摘要
- 如果用户显式锁定固定档位，`auto` 只能执行，不得覆盖

### `I4` benchmark 与回归

- 固定档位 benchmark
- `auto` 对“先满足场景下限、再按 `CostEfficiencyScore` 选出的 family-best fixed mode”的 frontier comparison
- 切换稳定性与震荡回归
- 锁档遵从回归

### `I5` Gate 与报告

- 产出：
  - access benchmark report
  - `auto` decision audit
  - Phase I gate report

## 当前关键设计约束

1. access mode 是 runtime policy，不是新 primitive
2. `Reflective` 不等同于 primitive `reflect`
3. `auto` 不能偷偷覆盖用户显式锁定的固定档位
4. 访问深度调节的是 retrieval / read / workspace / verification 强度，而不是对象真值
5. Phase I 必须同时回答质量、性能和可解释性，不能只保留一个总分

## 依赖关系

- 依赖 Phase H 已经建立稳定的 provenance / visibility / audit 边界
- 依赖现有 Phase D / F / G 的 retrieval、workspace、benchmark 与策略 trace 框架
- 依赖现有 `EpisodeAnswerBench v1` 与新增 `AccessDepthBench v1`

## 风险提醒

1. 最大风险是四个档位只有名字不同，行为上却没有实质差异
2. 第二个风险是 `auto` 退化成“永远选最深档”
3. 第三个风险是只做质量比较，不做真实成本和时延比较
4. 第四个风险是固定档位和 `auto` 没有统一 trace，导致后续无法优化

## 完成标志

当以下条件同时满足时，Phase I 可以进入正式验收：

- `I-1 ~ I-8` 都有可运行验证路径
- 四个固定档位和 `auto` 都有稳定 trace
- `AccessDepthBench v1`、frontier comparison 和调度审计都可重复运行
- 文档、实现和测试对 Phase I 的范围表述一致
