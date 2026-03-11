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
export MIND_POSTGRES_DSN='postgresql+psycopg://postgres:postgres@127.0.0.1:5432/mind'
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
```

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
