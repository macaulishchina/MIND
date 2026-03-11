# CLI 指南

产品 CLI 入口是 `mind`。它和 `mindtest` 分工明确：

- `mind`：产品使用面
- `mindtest`：开发/验收使用面

## 运行模式

### Local

默认模式，CLI 直接在进程内构建 `AppServiceRegistry`。

常用参数：

- `--profile`
- `--backend`
- `--sqlite-path`
- `--postgres-dsn`

### Remote

CLI 通过 HTTP 调用 REST API。

常用参数：

- `--remote`
- `--api-key`

## 命令面

### remember

写入一条记忆：

```bash
uv run mind remember "remember me" --episode-id ep-001
```

### recall

按 query 回忆：

```bash
uv run mind recall remember
```

### ask

触发 memory access：

```bash
uv run mind ask remember --mode auto
```

### history

列最近记忆：

```bash
uv run mind history --limit 10
```

### session

```bash
uv run mind session open --principal-id demo-user --session-id demo-session
uv run mind session list --principal-id demo-user
uv run mind session show demo-session
```

### status

```bash
uv run mind status
```

### config

```bash
uv run mind config
```

## 输出约定

所有产品 CLI 子命令都输出 JSON，退出码规则为：

- `0`：顶层 `status == "ok"`
- `1`：其他状态

## 何时使用 `mindtest`

出现以下需求时，应该转到 `mindtest`：

- 跑阶段 gate
- 跑 primitive/access/governance/offline 开发面
- 做回归或基准测试
- 排查实现级问题，而不是产品集成问题
