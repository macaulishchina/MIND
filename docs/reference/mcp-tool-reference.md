# MCP Tool Reference

当前 MCP catalog 暴露 11 个工具。

| Tool | 说明 | 最小输入 |
|---|---|---|
| `remember` | 写入一条记忆 | `content`, `episode_id` |
| `recall` | 按 query 回忆 | `query` |
| `ask_memory` | 对记忆提问 | `query` |
| `get_memory` | 取单个对象 | `object_id` |
| `list_memories` | 列最近对象 | 无 |
| `search_memories` | 检索候选 | `query` |
| `plan_conceal` | 规划 conceal | `reason` |
| `preview_conceal` | 预览 conceal | `operation_id` |
| `execute_conceal` | 执行 conceal | `operation_id` |
| `submit_offline_job` | 提交后台任务 | `job_kind`, `payload` |
| `get_job_status` | 查询 job | `job_id` |

## 公共 envelope 字段

MCP 调用也可以显式传：

- `request_id`
- `idempotency_key`
- `namespace`
- `policy`
- `session`
- `input`

如果没有提供，server wrapper 会根据 MCP session metadata 自动构建 `PrincipalContext` 和 `SessionContext`。

## 语义一致性

MCP 和 REST/CLI 共享相同的 app services，因此：

- 结果结构保持一致
- error envelope 保持一致
- session 映射遵循同一产品上下文模型
