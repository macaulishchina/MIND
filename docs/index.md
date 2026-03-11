# MIND Documentation.

MIND 现在已经同时提供 4 类正式入口：

- `mind`：产品 CLI，面向最终用户与集成人员
- `mind-api`：FastAPI REST 服务，面向后端/平台集成
- `mind-mcp`：MCP Server v1，面向 agent runtime 与工具编排
- `mindtest`：开发/验收 CLI，保留给工程回归和阶段 gate

这套文档的目标不是重复设计文档，而是把“如何使用、如何部署、如何排障、系统怎么组织”拆成独立且可维护的层次。

## 前置依赖：安装 uv

MIND 项目默认使用 `uv` 管理依赖与环境，如果您本地还未安装 `uv`，可以执行以下命令进行安装（或参考 [uv官方文档](https://github.com/astral-sh/uv)）：

```bash
# macOS / Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# 激活 uv 环境变量
source $HOME/.local/bin/env
```

## 从哪里开始

- 想 10 分钟跑通产品体验：看 [快速开始](./product/quickstart.md)
- 想直接部署 API/worker：看 [部署指南](./product/deployment.md)
- 想对接 HTTP：看 [REST API 指南](./product/api.md) 和 [API Reference](./reference/api-reference.md)
- 想对接 MCP：看 [MCP 指南](./product/mcp.md) 和 [MCP Tool Reference](./reference/mcp-tool-reference.md)
- 想理解 `mind/app`、存储和 transport 边界：看 [系统总览](./architecture/system-overview.md)
- 想追溯历史阶段、验收和研究材料：看 [历史资料与证据](./history-and-evidence.md)

## 文档分层

### Product

讲“怎么把产品用起来”，偏任务导向。

### Reference

讲“接口和配置到底是什么”，偏事实导向。

### Operations

讲“怎么部署、升级、排障、管密钥”，偏运行导向。

### Architecture

讲“系统边界怎么划、为什么这样设计”，偏内部协作与高级集成。

## 版本与来源

- 当前仓库版本：`0.2.0`
- 当前文档覆盖范围：`WP-0 ~ WP-6` 已完成的产品化基线
- 历史 Phase B ~ J 的规范、gate、审计和报告继续保留在 `docs/foundation/`、`docs/design/`、`docs/reports/`

## 本地预览

```bash
uv sync --extra docs
uv run mkdocs serve --livereload -a 0.0.0.0:8001
```

发布前建议至少执行一次严格构建：

```bash
uv run mkdocs build --strict
```
