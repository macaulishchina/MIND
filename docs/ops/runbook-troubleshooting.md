# 故障排查

## API 返回 401

优先检查：

- `MIND_API_KEY` 是否配置
- 请求头是否带了 `X-API-Key`
- CLI remote 模式是否传了 `--api-key`

## Readiness 失败

优先检查：

- store 是否可连通
- PostgreSQL DSN 是否正确
- migration 是否已执行

## Worker 没有消费任务

优先检查：

- compose 中 worker 是否正常循环
- `mindtest-offline-worker-once` 是否可执行
- job 是否真的是 `pending`

## MCP 启动失败

优先检查：

- 是否安装了 `mcp` SDK
- 是否通过 `uv sync --extra mcp` 安装了可选依赖

## CLI local 和 remote 结果不一致

优先检查：

- local/remote 是否指向同一 backend
- remote API 是否使用同一版本
- API key principal 与 local principal 是否影响结果过滤
