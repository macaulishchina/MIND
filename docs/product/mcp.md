# MCP 指南

MCP 入口是 `mind-mcp`，它和 REST 一样复用 `mind/app`，区别只在 transport。

## 依赖

MCP Python SDK 不是基础依赖，使用前需要安装：

```bash
uv sync --extra mcp
```

## 启动

```bash
export MIND_POSTGRES_DSN='postgresql+psycopg://postgres:postgres@127.0.0.1:18605/mind'
uv run mind-mcp
```

`mind-mcp` 和 REST 一样只支持 PostgreSQL 运行时；SQLite 仅保留给测试和 `mindtest`。

如果没有安装官方 `mcp` 包，当前实现会明确报错并提示安装 `mind[mcp]`。

## 工具面

当前公开 11 个工具：

| 工具 | 描述 | 必填参数 |
|---|---|---|
| `remember` | Store a new memory | `content`, `episode_id` |
| `recall` | Recall memories by query | `query` |
| `ask_memory` | Ask a question against stored memories | `query` |
| `get_memory` | Get a single memory object by ID | `object_id` |
| `list_memories` | List recent memory objects | — |
| `search_memories` | Full-text search across memories | `query` |
| `plan_conceal` | Plan a concealment operation | `reason` |
| `preview_conceal` | Preview planned concealment | `operation_id` |
| `execute_conceal` | Execute a planned concealment | `operation_id` |
| `submit_offline_job` | Submit a background job | `job_kind`, `payload` |
| `get_job_status` | Check status of a background job | `job_id` |

## Session 映射

MCP client metadata 会先映射成：

- `PrincipalContext`
- `SessionContext`

然后再进入 `AppRequest`。这保证 MCP 与 REST/CLI 的业务语义是一致的。

如果 tool 参数里带了顶层 `provider_selection`，server 也会把它映射到
`AppRequest`，语义与 REST 一致（详见 [REST API 指南](api.md#请求与响应) 中的 `provider_selection` 说明）。
对 `submit_offline_job`，该字段会被持久化到 job record，worker 执行时继续传递。

## 适用场景

- agent runtime 以工具调用方式接入记忆面
- 需要把会话上下文显式传入工具层
- 需要和 REST API 保持统一结果语义

如果你的集成更偏后端服务对服务调用，优先使用 REST；如果更偏 agent tool catalog，优先使用 MCP。
