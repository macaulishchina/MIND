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

### `mindtest report public-dataset`

用途：对一个公开数据集 slice 运行统一 retrieval/workspace/long-horizon 验证。

必填：

- `dataset`

可选：

- `--source`
- `--output`
- `--provider`
- `--model`
- `--endpoint`
- `--timeout-ms`
- `--retry-policy`
- `--strategy`：`fixed` / `optimized` / `public-dataset`

示例：

```bash
uv run mindtest report public-dataset scifact \
	--source tests/data/public_datasets/scifact_local_slice.json \
	--provider claude \
	--model claude-3-7-sonnet \
	--strategy optimized
```

输出摘要中的关键字段：

- `answer_provider`：当前请求选择的 answer provider。
- `answer_model`：当前请求选择的 model。
- `answer_provider_configured`：当前 provider 是否已解析到可用认证信息。
- `long_horizon_strategy`：本次长时程评估使用的策略实现 ID。

注意：`answer_provider_configured=false` 且 provider 不是 `stub` 时，answer capability 可能因为默认 fallback 策略而回退到 deterministic provider。
