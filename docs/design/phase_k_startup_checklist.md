# Phase K 启动清单

时点说明：这份文档记录的是 Phase J 通过后，MIND 进入 `Phase K / LLM Capability Layer` 前的启动约束、任务拆分和范围控制。正式通过口径以后续 Phase K 验收报告为准；这里先冻结统一能力调用层，避免把 provider 适配、前端配置和内部观测一起揉成一个超大阶段。

## 当前实现状态

截至 `2026-03-11`，Phase K 已经不是纯设计占位，而是进入实现基线。

当前已经落地：

- capability catalog、typed contract 与 adapter protocol
- provider config 模型与 deterministic baseline
- `openai / claude / gemini` 真实 adapter
- `summarize / reflect / answer / offline_reconstruct` 接入统一 capability 层
- `CapabilityAdapterBench v1`、failure audit、trace audit、provider compatibility report、Phase K formal gate
- `mindtest gate phase-k` 与 `mindtest report phase-k-compatibility` 开发入口

当前仍待收口：

- Phase K 正式 acceptance report
- 面向 operator / 产品面的进一步说明
- 进入 Phase L 前的 telemetry 前置约束梳理

## 目标

Phase K 只做统一模型能力层，不做前端和内部可视化。

本阶段的目标是：

1. 盘点现有处理能力并定义统一 capability 接口
2. 让 `summarize / reflect / answer / offline_reconstruct` 可通过同一层调用
3. 支持通过配置切换不同模型和接口地址
4. 兼容主流 `openai / claude / gemini` 风格接口
5. 保留现有 deterministic baseline 作为 fallback

## 非目标

Phase K 明确不做：

1. 前端配置页面
2. 把系统强制绑定到外部模型
3. provider 私有特性直接上升为系统主语义
4. 细化到每个能力都各自发明一套模型接入方式
5. 让“不配置模型”变成不可运行

## 任务拆分

1. `K1`：冻结 capability catalog、adapter contract 与 `CapabilityAdapterBench v1`
2. `K2`：实现 provider / model / endpoint / auth 配置模型
3. `K3`：把摘要 / 反思 / 回答 / 离线重构平滑接入统一能力层
4. `K4`：实现 fallback、错误收敛和调用 trace
5. `K5`：补 Phase K gate、provider 兼容回归和文档

## 推荐推进顺序

### `K1` 能力目录冻结

- 把 [../foundation/phase_gates.md](../foundation/phase_gates.md) 中的 `K-1 ~ K-7` 作为唯一 formal gate
- 冻结 capability：
  - `summarize`
  - `reflect`
  - `answer`
  - `offline_reconstruct`
- 为每个 capability 补齐：
  - 输入 contract
  - 输出 contract
  - 可选 fallback 语义
  - trace 字段

### `K2` 配置与 adapter

- 支持：
  - provider 名称
  - model 名称
  - API endpoint
  - 认证信息
  - timeout / retry 基础策略
- provider 兼容目标：
  - `openai`
  - `claude`
  - `gemini`

### `K3` 现有能力接入

- 把已有能力盘点并挂到统一层：
  - primitive summarize
  - primitive reflect
  - runtime answer path
  - offline reconstruct / promotion path
- 要求：
  - 调用方不因 provider 变化而重写业务代码
  - 不配置模型时仍能回到当前 baseline

### `K4` fallback 与 trace

- provider 不可用时只能：
  - fallback
  - structured failure
- 禁止 silent drift
- 模型调用必须记录：
  - provider
  - model
  - endpoint
  - version
  - timing

### `K5` Gate 与报告

- 产出：
  - capability contract audit
  - provider compatibility report
  - fallback / failure audit
  - Phase K gate report

## 当前关键设计约束

1. 能力层是统一适配层，不是新的记忆真相源
2. 不同 provider 的差异不能直接泄露到上层业务调用
3. fallback 语义必须显式，不允许 silent drift
4. 现有 deterministic baseline 必须保留
5. trace 和 provenance / capability 边界不能冲突

## 依赖关系

- 依赖 Phase J 的统一 CLI 和配置入口雏形
- 依赖现有 primitive / access / offline 能力已经稳定可调用
- 依赖 Phase H 的 capability / provenance 边界不被新模型层破坏

## 风险提醒

1. 最大风险是“统一接口”最后只停留在命名统一，没有真实平滑切换能力
2. 第二个风险是 provider 差异泄露到业务层，导致上层代码继续分叉
3. 第三个风险是 fallback 失控，出现 silent drift
4. 第四个风险是外部模型接入后把当前本地闭环打断

## 完成标志

当以下条件同时满足时，Phase K 可以进入正式验收：

- `K-1 ~ K-7` 都有可运行验证路径
- `CapabilityAdapterBench v1`、provider compatibility report 和 fallback audit 都可生成
- capability contract、adapter contract 和配置模型已经冻结
- 文档、实现和测试对 Phase K 的范围表述一致
