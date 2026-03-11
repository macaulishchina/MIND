# CLI Reference

产品 CLI 入口：`mind`

开发/验收 CLI 入口：`mindtest`

## 全局参数

| 参数 | 说明 |
|---|---|
| `--local` | 进程内直连 app services |
| `--remote` | 远程 REST API base URL |
| `--api-key` | 远程模式使用的 API key |
| `--profile` | CLI profile override |
| `--backend` | `sqlite` 或 `postgresql` |
| `--sqlite-path` | SQLite 文件路径 |
| `--postgres-dsn` | PostgreSQL DSN |

## Product Commands

### `remember`

必填：

- `content`
- `--episode-id`

可选：

- `--timestamp-order`
- `--principal-id`
- `--session-id`
- `--conversation-id`

### `recall`

必填：

- `query`

可选：

- `--query-mode`
- `--max-candidates`
- `--principal-id`
- `--session-id`

### `ask`

必填：

- `query`

可选：

- `--mode`
- `--task-id`
- `--episode-id`
- `--principal-id`
- `--session-id`

### `history`

可选：

- `--limit`
- `--offset`
- `--episode-id`
- `--principal-id`

### `session`

子命令：

- `open`
- `list`
- `show`

### `status`

无业务参数，返回 health + readiness 聚合结果。

### `config`

返回 backend/profile 等脱敏配置摘要。

## Dev Commands

`mindtest` 保留 8 组一级命令族：

- `primitive`
- `access`
- `offline`
- `governance`
- `gate`
- `report`
- `demo`
- `config`

它们不属于正式产品 surface。
