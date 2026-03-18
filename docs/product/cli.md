# CLI 指南

产品 CLI 入口是 `mind`。它和 `mindtest` 分工明确：

- `mind`：产品使用面
- `mindtest`：开发/验收使用面

## 运行模式

### Local

默认模式，CLI 直接在进程内构建 `AppServiceRegistry`，并且只支持 PostgreSQL 运行时。

常用参数：

- `--profile`
- `--backend`
- `--postgres-dsn`

启动前需要通过环境变量或参数提供 PostgreSQL DSN：

```bash
export MIND_POSTGRES_DSN='postgresql+psycopg://postgres:postgres@127.0.0.1:18605/mind'
mind status
```

`mind` 不再支持 SQLite 本地运行；SQLite 仅保留给测试和 `mindtest`。

直接输入 `mind` 会先尝试按当前环境变量或 `--postgres-dsn` 建立连接。连接成功后进入交互式 shell，此时可以连续输入 `remember`、`recall`、`status` 等二级命令；输入 `exit` / `quit` 或 `Ctrl-D` 退出。

### Remote

CLI 通过 HTTP 调用 REST API。

常用参数：

- `--json`
- `--color`
- `--remote`
- `--api-key`

## 命令面

### remember

写入一条记忆：

```bash
mind remember "remember me" --episode-id ep-001
# 或先进入 shell
mind
mind> remember "remember me"
```

`--episode-id` 现在可选；如果省略，CLI 会自动生成
`<username>-<hostname>-<window-instance-id>`。

### recall

按 query 回忆：

```bash
mind recall remember
```

当前产品 CLI 不额外限制 object type；默认会在所有最新、非 `invalid` 状态的对象里检索。
终端输出会显示 candidate 的 `object type`，如果有可用的文本内容预览也会一并显示。

### ask

触发 memory access：

```bash
mind ask remember --mode auto
```

`mind ask` 现在会显示 capability layer 生成的最终 answer，以及本次 access 的
上下文/候选/选中对象摘要。

### history

列最近记忆：

```bash
mind history --limit 10
```

### session

```bash
mind session open --principal-id demo-user --session-id demo-session
mind session list --principal-id demo-user
mind session show demo-session
```

### status

```bash
mind status
```

### config

```bash
mind config
mind config --provider openai --model gpt-4.1-mini
```

`mind config` 现在会同时显示 runtime 配置和 provider 状态。
如果传 `--provider / --model / --endpoint / --timeout-ms / --retry-policy`，
CLI 会走一次请求级 provider resolution 预览，不需要先修改环境变量。

`--provider` 合法值：`stub`、`openai`、`claude`、`gemini`。

## 各命令参数一览

| 命令 | 参数 | 说明 |
|---|---|---|
| `remember` | `content`（必填）、`--episode-id`、`--timestamp-order`、`--principal-id`、`--session-id`、`--conversation-id` | 写入一条记忆 |
| `recall` | `query`（必填）、`--query-mode`、`--max-candidates`、`--principal-id`、`--session-id` | 按 query 检索候选 |
| `ask` | `query`（必填）、`--mode`、`--task-id`、`--episode-id`、`--principal-id`、`--session-id` | 向记忆提问，返回 answer |
| `history` | `--limit`、`--offset`、`--episode-id`、`--principal-id` | 最近记忆列表 |
| `session open` | `--principal-id`（必填）、`--session-id`（必填）、`--conversation-id`、`--channel`、`--client-id`、`--device-id` | 打开/更新会话 |
| `session list` | `--principal-id` | 列出会话 |
| `session show` | `session_id`（必填） | 查看单个会话 |
| `config` | `--provider`、`--model`、`--endpoint`、`--timeout-ms` | 配置与 provider 预览 |

## 输出约定

产品 CLI 默认输出适合终端阅读的文本结果，会按命令类型对关键字段做摘要、分组和列表化展示。
在交互式终端里会自动启用颜色、高亮状态和表格对齐；如需关闭可传 `--color never`。

如果你需要脚本化消费原始响应结构，显式传 `--json`：

```bash
mind --json status
mind --json recall remember
```

如果你想强制开启颜色：

```bash
mind --color always status
```

退出码规则为：

- `0`：顶层 `status == "ok"`
- `1`：其他状态

## 何时使用 `mindtest`

出现以下需求时，应该转到 `mindtest`：

- 跑阶段 gate
- 跑 primitive/access/governance/offline 开发面
- 做回归或基准测试
- 排查实现级问题，而不是产品集成问题

### `mindtest report public-dataset`

公开数据集验证走开发/验收 CLI：

```bash
uv run mindtest report public-dataset hotpotqa \
	--source tests/data/public_datasets/hotpotqa_local_slice.json \
	--provider openai \
	--model gpt-4.1-mini \
	--strategy public-dataset \
	--output artifacts/dev/public_datasets/hotpotqa_openai_report.json
```

常用参数：

- `--source`：指定本地编译好的 slice JSON。
- `--provider` / `--model` / `--endpoint` / `--timeout-ms` / `--retry-policy`：显式指定 answer capability 的 provider 配置。
- `--strategy`：长时程复用策略，可选 `fixed`、`optimized`、`public-dataset`。
- `--output`：持久化 JSON 报告。

报告输出会额外打印 `answer_provider_configured`。如果你选择了 `openai` / `claude` / `gemini` 但这里是 `false`，说明当前环境没有可用凭据，answer 路径可能按默认策略回退到 deterministic provider。
