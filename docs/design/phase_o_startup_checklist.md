# Phase O 启动清单

时点说明：这份文档记录的是 Phase N 通过后，MIND 进入 `Phase O / Persona / Projection` 前的启动约束、任务拆分和范围控制。正式通过口径以后续 Phase O 验收报告为准；这里先冻结人格层边界，避免把人格工程化过早推成一个脱离记忆证据的黑箱模块。

## 目标

Phase O 做 persona projection，不造黑箱人格对象。

本阶段的目标是：

1. 建立 autobiographical grouping 与 preference / value schema
2. 落地 runtime persona projection
3. 建立 persona 输出的 evidence trace
4. 验证 persona 会随 governance 动作同步更新
5. 冻结 `PersonaProjectionBench v1`

## 非目标

Phase O 明确不做：

1. 独立、权威、不可追溯的 `PersonaObject`
2. 完整情绪模拟系统或“内心状态引擎”
3. 用 persona projection 覆盖 task constraints 或产品规则
4. 通过参数更新而不是记忆对象来固化人格
5. 脱离治理链的 persona 快捷缓存

## 任务拆分

1. `O1`：冻结 `PersonaProjectionBench v1` 与 identity bundle 结构
2. `O2`：实现 autobiographical grouping 与 preference / value schema
3. `O3`：实现 runtime persona projection 与 evidence trace
4. `O4`：实现治理后的 persona 更新与泄露回归
5. `O5`：补 Phase O gate、验收报告和 neutral-task A/B 回归

## 推荐推进顺序

### `O1` 基准与 bundle 冻结

- 把 [../foundation/phase_gates.md](../foundation/phase_gates.md) 中的 `O-1 ~ O-6` 作为唯一 formal gate
- 冻结 `PersonaProjectionBench v1`：
  - autobiographical continuity
  - preference consistency
  - value judgment
  - governance-after-update
- 为每组 identity bundle 补充：
  - 可用 evidence set
  - 不可用 / 已治理 evidence set
  - 中性任务对照样例

### `O2` 记忆组织层

- 建立：
  - autobiographical grouping
  - preference schema
  - value schema
- 保证这些结构：
  - 仍然可追溯
  - 仍然受治理链约束
  - 不把短期状态写死成长期人格真值

### `O3` Runtime Projection

- persona projection 必须输出：
  - 使用到的 memory support
  - persona projection summary
  - 关键 persona 相关 claim 的证据链
- persona projection 只能影响：
  - 风格
  - 自我表述
  - 偏好 / 价值相关判断
- 不能绕开：
  - task constraints
  - safety boundary
  - governance visibility

### `O4` Governance 级联

- 对 autobiographical / preference / value 相关记忆执行治理后：
  - persona projection 要同步变化
  - 已失效 persona 表达不能在普通路径继续漏出
  - persona cache 需要与治理语义对齐

### `O5` Gate 与报告

- 产出：
  - persona grounding audit
  - consistency benchmark report
  - governance-coupled persona regression
  - neutral-task A/B regression
  - Phase O gate report

## 当前关键设计约束

1. persona 是 projection，不是新的权威真相源
2. persona 相关输出必须可追溯到记忆证据或 prompt 已知信息
3. 治理动作必须能级联影响 persona projection
4. 短期情绪或风格状态不能污染长期价值层
5. 引入 persona 后，不得明显破坏非 persona 任务

## 依赖关系

- 依赖 Phase H 的 provenance foundation
- 依赖 Phase N 已经稳定的 governance / reshape 执行能力
- 依赖现有 runtime access、workspace 和 evidence audit 框架

## 风险提醒

1. 最大风险是 persona projection 退化成无依据的风格模仿
2. 第二个风险是 preference / value / autobiographical 三层混在一起
3. 第三个风险是治理后 persona 没有同步更新，保留陈旧自我叙述
4. 第四个风险是 persona 增强了表达，却削弱了中性任务的完成质量

## 完成标志

当以下条件同时满足时，Phase O 可以进入正式验收：

- `O-1 ~ O-6` 都有可运行验证路径
- `PersonaProjectionBench v1`、grounding audit、consistency report 和 neutral-task A/B regression 都可生成
- autobiographical grouping、value schema 与 persona projection 的边界已经冻结
- 文档、实现和测试对 Phase O 的范围表述一致
