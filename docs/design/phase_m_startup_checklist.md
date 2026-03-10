# Phase M 启动清单

时点说明：这份文档记录的是 Phase L 通过后，MIND 进入 `Phase M / Frontend Experience` 前的启动约束、任务拆分和范围控制。正式通过口径以后续 Phase M 验收报告为准；这里先冻结前端阶段的功能边界，避免把体验入口、配置入口和后续治理 / persona 一起推成一个失控产品阶段。

## 目标

Phase M 做前端体验层，不提前实现后续治理重塑和人格层能力。

本阶段的目标是：

1. 提供统一功能体验入口
2. 提供 backend / model / dev-mode 配置入口
3. 提供内部操作可视化 debug 入口
4. 保持与 CLI / backend contract 一致
5. 冻结 `FrontendExperienceBench v1`

## 非目标

Phase M 明确不做：

1. 原生移动端应用
2. 完整产品级运营后台
3. 提前实现 mixed-source rewrite 或 persona projection
4. 让前端绕开 CLI / backend contract 直接改写内部语义
5. 关闭 dev-mode 时仍暴露 debug 入口

## 任务拆分

1. `M1`：冻结前端信息架构、页面边界和 `FrontendExperienceBench v1`
2. `M2`：实现功能体验入口
3. `M3`：实现 backend / model / dev-mode 配置入口
4. `M4`：实现内部操作可视化 debug 入口
5. `M5`：补 Phase M gate、E2E 和响应式回归

## 推荐推进顺序

### `M1` IA 与 contract 冻结

- 把 [../foundation/phase_gates.md](../foundation/phase_gates.md) 中的 `M-1 ~ M-6` 作为唯一 formal gate
- 冻结三类入口：
  - 功能体验
  - 配置
  - debug
- 冻结前后端 contract：
  - 功能调用
  - 配置读写
  - telemetry / debug 查询

### `M2` 功能体验入口

- 至少覆盖：
  - ingest
  - retrieve
  - access run
  - offline job
  - gate / demo

### `M3` 配置入口

- 至少支持：
  - backend / profile
  - provider / model
  - dev-mode
- 配置入口不能偷改运行时语义，只能改变显式配置

### `M4` debug 可视化

- 可视化至少包括：
  - 事件时间线
  - 对象变化
  - context / evidence 选择
  - 关键内部决策
- debug 入口必须依赖 dev-mode

### `M5` Gate 与回归

- 产出：
  - frontend flow report
  - config audit
  - debug visualization audit
  - Phase M gate report

## 当前关键设计约束

1. 前端是体验层，不是新的业务语义层
2. 前端必须建立在 CLI / capability / telemetry contract 之上
3. debug 入口和普通体验入口必须边界清楚
4. 配置入口必须显式、可审查、可恢复
5. desktop / mobile 两端都必须能正常工作

## 依赖关系

- 依赖 Phase J 的统一 CLI 入口
- 依赖 Phase K 的模型能力层和配置模型
- 依赖 Phase L 的完备 telemetry 数据底座

## 风险提醒

1. 最大风险是前端把体验入口和 debug 入口混成一个难用界面
2. 第二个风险是前后端 contract 漂移，导致 UI 不稳定
3. 第三个风险是 debug 数据不完整，页面看起来丰富但实际误导
4. 第四个风险是 dev-mode 边界失效，普通模式也暴露内部信息

## 完成标志

当以下条件同时满足时，Phase M 可以进入正式验收：

- `M-1 ~ M-6` 都有可运行验证路径
- `FrontendExperienceBench v1`、config audit、debug UI audit 和 responsive report 都可生成
- 前端 IA、contract 与 dev-mode 边界已经冻结
- 文档、实现和测试对 Phase M 的范围表述一致
