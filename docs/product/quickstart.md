# 快速开始

这个快速开始默认你在仓库根目录，并且希望先用本地 SQLite 跑通最短链路。

## 1. 安装依赖

```bash
uv sync --extra dev --extra api --extra mcp --extra docs
```

## 2. 看产品 CLI

```bash
uv run mind -h
```

你应该能看到 7 组命令：

- `remember`
- `recall`
- `ask`
- `history`
- `session`
- `status`
- `config`

## 3. 写入一条记忆

```bash
uv run mind remember "hello from quickstart" --episode-id quickstart-001
```

## 4. 回忆这条记忆

```bash
uv run mind recall hello
```

## 5. 打开一个会话

```bash
uv run mind session open --principal-id quickstart-user --session-id quickstart-session
```

## 6. 查看系统状态

```bash
uv run mind status
uv run mind config
```

## 7. 启动 REST API

先准备环境变量：

```bash
export MIND_API_KEY='dev-key'
```

再启动服务：

```bash
uv run mind-api
```

## 8. 调 API

```bash
curl \
  -H 'X-API-Key: dev-key' \
  http://127.0.0.1:8000/v1/system/health
```

## 9. 用远程模式走 CLI

```bash
uv run mind --remote http://127.0.0.1:8000 --api-key dev-key status
```

## 下一步

- 继续本地联调：看 [CLI 指南](./cli.md)
- 继续部署：看 [部署指南](./deployment.md)
- 继续集成：看 [REST API 指南](./api.md) 或 [MCP 指南](./mcp.md)
