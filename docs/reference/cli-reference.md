# CLI Reference

产品 CLI 入口：`mind`

开发/验收 CLI 入口：`mindtest`

## `mind` 全局参数

| 参数 | 说明 |
|---|---|
| `--local` | 进程内直连 app services |
| `--remote` | 远程 REST API base URL |
| `--api-key` | 远程模式使用的 API key |
| `--json` | 输出原始 JSON envelope，适合脚本或自动化消费 |
| `--color` | `auto` / `always` / `never`，控制终端颜色与高亮 |
| `--profile` | `auto` 或 `postgres_main` |
| `--backend` | 仅支持 `postgresql` |
| `--postgres-dsn` | PostgreSQL DSN |

`mind` 的本地模式只支持 PostgreSQL；`--sqlite-path` 不属于产品 CLI 支持面。

## Product Commands

### `remember`

必填：

- `content`

可选：

- `--episode-id`（默认 `<username>-<hostname>-<window-instance-id>`）
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

默认会在所有最新、非 `invalid` 状态的对象里检索。终端输出会尽量展示 candidate 的 `object type`；如果接口没有返回可用的文本内容预览，则不会显示 preview 列。

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

## `mindtest` 说明

`mindtest` 保留 8 组一级命令族：

- `primitive`
- `access`
- `offline`
- `governance`
- `gate`
- `report`
- `demo`
- `config`

它们不属于正式产品 surface。`mindtest` 仍保留 `sqlite_local` / `--sqlite-path` 等测试与验收参数，用于 gate、回归和 reference backend 校验。
