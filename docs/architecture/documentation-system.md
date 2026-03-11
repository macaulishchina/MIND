# 文档系统

这套文档方案本身也需要被当成产品的一部分维护。

## 目标

同时服务 4 类读者：

- 新用户
- 集成方
- 运维方
- 内部工程团队

## 信息架构

- `docs/product/`：任务导向，回答“怎么用”
- `docs/reference/`：事实导向，回答“接口是什么”
- `docs/ops/`：运行导向，回答“怎么部署和排障”
- `docs/architecture/`：边界导向，回答“为什么这样设计”
- `docs/foundation/`、`docs/design/`、`docs/reports/`：历史规范与证据

## 工具链

- `mkdocs`
- `mkdocs-material`
- `mkdocstrings`
- `mike`

## 维护约定

每次变更如果影响以下任一项，应同步更新文档：

- CLI 命令面
- REST 路由
- MCP tool catalog
- 配置/env
- 部署拓扑
- 产品边界和上下文模型

## 发布建议

- 本地预览：`uv run mkdocs serve`
- 严格构建：`uv run mkdocs build --strict`
- 版本化发布：使用 `mike` 维护 `latest` 和版本分支

## 当前限制

当前文档站已经有结构和发布配置，但 API/CLI reference 仍是手工维护版本；如果后续公开面继续增长，建议把 OpenAPI 和 CLI help 的提取自动化。
