# Phase J 启动清单

时点说明：这份文档记录的是 Phase I 通过后，MIND 进入 `Phase J / Unified CLI Experience` 前的启动约束、任务拆分和范围控制。正式通过口径以后续 Phase J 验收报告为准；这里先冻结统一命令行入口的边界，避免把 CLI、前端和模型接入一次性揉成一个失控阶段。

产品化 addendum：

- 这份文档描述的是历史上的统一开发/验收 CLI 启动边界
- 若这套入口继续保留，其正式命名应迁移到 `mindtest`
- `mind` 这个命名保留给产品级 CLI
- 完整产品化方案见 [productization_program.md](./productization_program.md)

## 目标

Phase J 只做统一命令行体验层，不做前端和模型接入。

本阶段的目标是：

1. 设计并落地强大、完整的 `mind` 命令行入口
2. 让 `mind -h` 与一级命令帮助完整可用
3. 让所有现有记忆模块都能通过 `mind` 被体验、测试和调试
4. 统一 profile / backend / 输出格式 / demo 场景的命令语义
5. 冻结 `MindCliScenarioSet v1`

## 非目标

Phase J 明确不做：

1. 前端图形界面
2. 真实 LLM provider 适配层
3. 内部结构可视化 debug 页面
4. 改写现有模块内部语义，只允许包装与统一入口
5. 把 CLI 变成临时脚本集合的别名层

## 任务拆分

1. `J1`：冻结 `mind` 顶层命令树、帮助口径和 `MindCliScenarioSet v1`
2. `J2`：统一 `primitive / access / offline / governance / gate / report / demo / config` 一级命令
3. `J3`：打通核心体验流与 profile / backend 切换
4. `J4`：统一输出格式、错误码和退出码
5. `J5`：补 Phase J gate、CLI 场景回归和可用性审计

## 推荐推进顺序

### `J1` 命令树冻结

- 把 [../foundation/phase_gates.md](../foundation/phase_gates.md) 中的 `J-1 ~ J-6` 作为唯一 formal gate
- 冻结一级命令族：
  - `primitive`
  - `access`
  - `offline`
  - `governance`
  - `gate`
  - `report`
  - `demo`
  - `config`
- 为每个命令族补齐：
  - help
  - 最小示例
  - 统一输出模式

### `J2` 入口统一

- 保持现有能力不变，只统一入口
- 重点打通：
  - `write_raw / read / retrieve`
  - access modes
  - offline worker / job
  - governance control plane
  - phase gates / reports

### `J3` profile 与体验流

- 至少支持：
  - `SQLite` 本地 profile
  - `PostgreSQL` profile
- 至少提供：
  - ingest-read demo
  - retrieve demo
  - access run demo
  - offline job demo
  - gate / report demo

### `J4` 输出和错误语义

- 统一：
  - text 输出
  - json 输出
  - 非零退出码
  - 参数错误提示
- 不能让调用方依赖隐式 stderr 文本猜状态

### `J5` Gate 与审计

- 产出：
  - CLI help audit
  - `MindCliScenarioSet v1` report
  - config / backend switching audit
  - Phase J gate report

## 当前关键设计约束

1. CLI 是统一体验层，不是新的业务逻辑层
2. CLI 不得偷偷改变原有 primitive / access / offline / governance 语义
3. 帮助、参数和输出口径必须统一
4. `mind` 必须能成为主要体验入口，而不是只包一部分功能
5. 旧脚本可以保留，但新口径以 `mind` 为主

## 依赖关系

- 依赖 Phase H 的 provenance foundation
- 依赖 Phase I 的 runtime access modes 已稳定
- 依赖现有 CLI / 脚本 / gate 已经可运行，Phase J 只做入口收敛

## 风险提醒

1. 最大风险是 CLI 只是脚本别名层，体验仍然碎片化
2. 第二个风险是 profile / backend 规则不统一，导致命令难用
3. 第三个风险是输出 contract 不稳定，后续前端和自动化都没法依赖
4. 第四个风险是统一入口过程中引入旧能力回归

## 完成标志

当以下条件同时满足时，Phase J 可以进入正式验收：

- `J-1 ~ J-6` 都有可运行验证路径
- `mind -h` 与一级命令 help 已冻结
- `MindCliScenarioSet v1`、config audit 和 Phase J gate report 都可生成
- 文档、实现和测试对 Phase J 的范围表述一致
