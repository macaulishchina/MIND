# 文档索引与作者指南

`docs/` 现在分成两条主线：

- 产品文档：面向用户、集成方、运维和内部协作
- 历史文档：保留 foundation / design / reports / research 作为规范与证据

如果你是第一次进入仓库，优先看 [首页](./index.md)。

## 本地预览

```bash
./scripts/dev.sh
```

这会同时启动 API、worker 和带热更新的文档站，默认文档地址为 `http://127.0.0.1:8002`。

如果只需要独立文档预览：

```bash
uv sync --extra docs
uv run mkdocs serve --livereload -a 0.0.0.0:8003
```

发布前建议做一次严格构建：

```bash
uv run mkdocs build --strict
```

如果要做可交付的静态站构建或本地发布，使用：

```bash
./scripts/docs-release.sh build
./scripts/docs-release.sh publish-local
```

`publish-local` 默认使用 `http://127.0.0.1:8004`，用于模拟生产态静态站。

## 产品文档分层

- `product/`
  - [overview.md](./product/overview.md)：产品面、入口和边界
  - [quickstart.md](./product/quickstart.md)：最短上手路径
  - [deployment.md](./product/deployment.md)：产品部署说明
  - [cli.md](./product/cli.md)：产品 CLI 使用
  - [api.md](./product/api.md)：REST API 使用
  - [mcp.md](./product/mcp.md)：MCP 使用
  - [sessions-and-users.md](./product/sessions-and-users.md)：用户/会话模型
- `reference/`
  - [cli-reference.md](./reference/cli-reference.md)
  - [api-reference.md](./reference/api-reference.md)
  - [mcp-tool-reference.md](./reference/mcp-tool-reference.md)
  - [config-reference.md](./reference/config-reference.md)
  - [error-reference.md](./reference/error-reference.md)
- `ops/`
  - [runbook-deploy.md](./ops/runbook-deploy.md)
  - [runbook-docs-release.md](./ops/runbook-docs-release.md)
  - [runbook-upgrade.md](./ops/runbook-upgrade.md)
  - [runbook-troubleshooting.md](./ops/runbook-troubleshooting.md)
  - [security.md](./ops/security.md)
- `architecture/`
  - [system-overview.md](./architecture/system-overview.md)
  - [app-layer.md](./architecture/app-layer.md)
  - [storage-model.md](./architecture/storage-model.md)
  - [transport-model.md](./architecture/transport-model.md)
  - [documentation-system.md](./architecture/documentation-system.md)

## 历史文档与证据

历史资料仍然留在仓库里，但默认不纳入 MkDocs 站点构建，以避免旧阶段文档里的相对代码链接破坏严格构建。

主要位置：

- `docs/foundation/`
- `docs/design/`
- `docs/reports/`
- `docs/research/`

## 维护约定

- 改 CLI 命令面时，同步更新 `product/cli.md` 和 `reference/cli-reference.md`
- 改 REST 路由时，同步更新 `product/api.md` 和 `reference/api-reference.md`
- 改 MCP tool catalog 时，同步更新 `product/mcp.md` 和 `reference/mcp-tool-reference.md`
- 改 env/config 时，同步更新 `product/deployment.md` 和 `reference/config-reference.md`
- 改边界或职责时，同步更新 `architecture/`

## 为什么保留历史文档

MIND 的 foundation / design / reports 文档记录了 Phase B ~ J 和产品化过程中的冻结语义、审计结论与验收口径。产品文档不应该覆盖它们，而应该站在这些证据之上提供更稳定的使用面。
