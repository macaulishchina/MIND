# 存储模型

## 存储角色

### PostgreSQL

- 正式真相源
- compose 默认 backend
- 支撑 `mind` / REST / MCP / worker / compose 多 transport 集成

### SQLite

- reference backend
- 仅测试、CI、gate 和 parity 校验
- 不属于产品运行时或部署路径

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

面向最终用户的文档只暴露 PostgreSQL 运行时的配置、部署和恢复路径；SQLite 只在测试、foundation 和历史证据文档中出现。
