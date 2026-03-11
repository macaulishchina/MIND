# 存储模型

## 存储角色

### PostgreSQL

- 正式真相源
- compose 默认 backend
- 支撑 worker 和多 transport 集成

### SQLite

- reference backend
- 测试与 CI
- 低成本本地原型

## 新增产品态表

- `principals`
- `sessions`
- `namespaces`

它们通过 Alembic migration 纳入 schema 管理。

## Offline Jobs

后台任务也已经抽成稳定 contract，并在 SQLite/PostgreSQL 两端都有实现，包括：

- enqueue
- claim
- complete
- fail
- cancel

## 文档策略

面向最终用户的文档只暴露“如何选择 backend、如何配置 DSN、如何恢复/升级”；更底层的 schema 演化和历史设计继续放在 foundation/design/reports。
