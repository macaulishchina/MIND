# 快速开始

这个快速开始默认你在仓库根目录，并且希望直接走 PostgreSQL-backed 产品路径。SQLite 只保留给测试和 `mindtest` 验收流。

## 1. 安装依赖

```bash
uv sync --extra dev --extra api --extra mcp --extra docs
```

## 2. 启动开发环境

```bash
./scripts/dev.sh
```

开发环境会拉起 PostgreSQL、API、worker 和文档站。

## 3. 配置本地产品 CLI 使用的 PostgreSQL DSN

```bash
export MIND_POSTGRES_DSN='postgresql+psycopg://postgres:postgres@127.0.0.1:18605/mind'
export MIND_API_KEY='dev-key'
```

## 4. 看产品 CLI

```bash
mind -h
```

你应该能看到 7 组命令：

- `remember`
- `recall`
- `ask`
- `history`
- `session`
- `status`
- `config`

## 5. 写入一条记忆

```bash
mind remember "hello from quickstart" --episode-id quickstart-001
```

## 6. 回忆这条记忆

```bash
mind recall hello
```

## 7. 打开一个会话

```bash
mind session open --principal-id quickstart-user --session-id quickstart-session
```

## 8. 查看系统状态

```bash
mind status
mind config
```

## 9. 调 API

```bash
curl \
  -H 'X-API-Key: dev-key' \
  http://127.0.0.1:18600/v1/system/health
```

## 10. 用远程模式走 CLI

```bash
mind --remote http://127.0.0.1:18600 --api-key dev-key status
```

## 下一步

- 继续本地联调：看 [CLI 指南](./cli.md)
- 继续部署：看 [部署指南](./deployment.md)
- 继续集成：看 [REST API 指南](./api.md) 或 [MCP 指南](./mcp.md)
