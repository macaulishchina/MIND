# MCP 指南

MCP 入口是 `mind-mcp`，它和 REST 一样复用 `mind/app`，区别只在 transport。

## 依赖

MCP Python SDK 不是基础依赖，使用前需要安装：

```bash
uv sync --extra mcp
```

## 启动

```bash
uv run mind-mcp
```

如果没有安装官方 `mcp` 包，当前实现会明确报错并提示安装 `mind[mcp]`。

## 工具面

当前公开 11 个工具：

- `remember`
- `recall`
- `ask_memory`
- `get_memory`
- `list_memories`
- `search_memories`
- `plan_conceal`
- `preview_conceal`
- `execute_conceal`
- `submit_offline_job`
- `get_job_status`

## Session 映射

MCP client metadata 会先映射成：

- `PrincipalContext`
- `SessionContext`

然后再进入 `AppRequest`。这保证 MCP 与 REST/CLI 的业务语义是一致的。

## 适用场景

- agent runtime 以工具调用方式接入记忆面
- 需要把会话上下文显式传入工具层
- 需要和 REST API 保持统一结果语义

如果你的集成更偏后端服务对服务调用，优先使用 REST；如果更偏 agent tool catalog，优先使用 MCP。
