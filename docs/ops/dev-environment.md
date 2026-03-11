# 开发环境指南

本指南帮助你快速搭建 MIND 的本地开发环境，支持代码热更新、DEBUG 日志查看和快速迭代。

## 前置条件

| 工具 | 最低版本 | 安装 |
|------|---------|------|
| Docker | 24+ | [docker.com](https://docs.docker.com/get-docker/) |
| Docker Compose V2 | 2.20+ | Docker Desktop 内置 |
| uv | 0.4+ | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |

## 一键启动

```bash
./scripts/dev.sh
```

首次运行会自动从 `.env.dev` 复制到 `.env.dev.local`，然后在后台启动 API、worker、postgres 和带热更新的文档服务。脚本结束后会直接打印可访问的完整 URL，方便快速打开。

默认地址：

- API：`http://127.0.0.1:8000`
- API 文档：`http://127.0.0.1:8000/docs`
- 健康：`http://127.0.0.1:8000/v1/system/health`
- 就绪：`http://127.0.0.1:8000/v1/system/readiness`
- 文档：`http://127.0.0.1:8002`

如果要以前台 attach 模式运行：

```bash
./scripts/dev.sh --attach
```

如果只想单独预览项目文档，另开一个终端执行：

```bash
uv sync --extra docs
uv run mkdocs serve --livereload -a 0.0.0.0:8003
```

然后打开 `http://127.0.0.1:8003`。

### 常用命令

```bash
./scripts/dev.sh              # 后台启动 (增量构建)
./scripts/dev.sh --attach     # 前台启动
./scripts/dev.sh --rebuild    # 强制重建镜像并后台启动
./scripts/dev.sh --rebuild --attach  # 强制重建镜像并前台启动
./scripts/dev.sh --down       # 关闭环境
./scripts/dev.sh --logs       # 跟踪日志
./scripts/dev.sh --status     # 服务状态
```

脚本固定使用独立的 compose project `mind-dev`，避免与生产环境共享容器和数据库卷。

## 开发环境特性

### 热更新

开发环境将本地 `mind/` 目录挂载到容器内，配合 uvicorn `--reload`：

- 修改 `mind/` 下的 Python 文件 → API 自动重启
- 修改 `alembic/` 下的迁移文件 → 重新运行迁移即可生效
- 修改 `docs/`、`mkdocs.yml`、`README.md` → 文档站自动刷新
- **无需重新构建镜像**

### 日志

开发环境默认 `DEBUG` 日志级别：

```bash
# 跟踪所有服务日志
./scripts/dev.sh --logs

# 只看 API 日志
MIND_ENV_FILE=.env.dev.local docker compose --project-name mind-dev --env-file .env.dev.local -f compose.yaml -f compose.dev.yaml logs -f api

# 只看 Worker 日志
MIND_ENV_FILE=.env.dev.local docker compose --project-name mind-dev --env-file .env.dev.local -f compose.yaml -f compose.dev.yaml logs -f worker

# 只看文档站日志
MIND_ENV_FILE=.env.dev.local docker compose --project-name mind-dev --env-file .env.dev.local -f compose.yaml -f compose.dev.yaml logs -f docs
```

### 远程调试

开发环境暴露 debugpy 端口 `5678`。在代码中添加：

```python
import debugpy
debugpy.listen(("0.0.0.0", 5678))
debugpy.wait_for_client()  # 可选：等待调试器连接
```

然后在 IDE 中配置远程调试，连接到 `localhost:5678`。

### Worker 轮询

开发环境 Worker 轮询间隔缩短为 3 秒（生产为 10 秒），便于快速观察离线任务执行。

## 环境变量

开发默认模板定义在 `.env.dev`，本地运行时文件为 `.env.dev.local`：

| 变量 | 开发默认值 | 说明 |
|------|-----------|------|
| `MIND_POSTGRES_PASSWORD` | `postgres` | PostgreSQL 容器密码 |
| `MIND_POSTGRES_DSN` | `...@postgres:5432/mind` | 容器网络内的 PostgreSQL |
| `MIND_API_KEY` | `dev-key` | 开发用 API 密钥 |
| `MIND_LOG_LEVEL` | `DEBUG` | 日志级别 |
| `MIND_DEV_MODE` | `true` | 启用开发特性 |
| `MIND_API_BIND` | `0.0.0.0:8000` | compose 开发环境当前固定为 8000 |
| `MIND_DOCS_BIND` | `0.0.0.0:8002` | compose 开发环境文档热更端口 |
| `MIND_PROVIDER` | `stub` | 使用 stub 无需真实 LLM |
| `MIND_PIP_INDEX_URL` | `https://pypi.tuna.tsinghua.edu.cn/simple` | Docker 构建时的主 PyPI 镜像源 |
| `MIND_PIP_EXTRA_INDEX_URL` | 空 | Docker 构建时的附加 PyPI 镜像源 |
| `MIND_PIP_TRUSTED_HOST` | `pypi.tuna.tsinghua.edu.cn` | Docker 构建时的可信镜像域名 |

开发环境默认已使用清华 TUNA PyPI 镜像。如果你需要覆盖，可在 `.env.dev.local` 中设置例如企业内网或其他镜像源：

```dotenv
MIND_PIP_INDEX_URL=https://your-mirror.example/simple
MIND_PIP_TRUSTED_HOST=your-mirror.example
```

## 不用 Docker 的本地开发

如果希望直接在主机运行（例如调试单个组件）：

```bash
# 1. 安装依赖
uv sync --extra dev --extra api --extra mcp --extra docs

# 2. 启动 PostgreSQL (仍用 Docker)
MIND_ENV_FILE=.env.dev docker compose \
  --project-name mind-dev \
  --env-file .env.dev \
  -f compose.yaml \
  -f compose.dev.yaml \
  up postgres -d

# 3. 配置环境变量 (注意 DSN 用 localhost)
export MIND_POSTGRES_DSN='postgresql+psycopg://postgres:postgres@127.0.0.1:5432/mind'
export MIND_API_KEY='dev-key'
export MIND_DEV_MODE=true

# 4. 运行迁移
uv run alembic upgrade head

# 5. 启动 API (带热更新)
uv run uvicorn mind.api.app:create_app --factory --reload --log-level debug

# 6. 在另一个终端启动 Worker
uv run mindtest-offline-worker-once --dsn "$MIND_POSTGRES_DSN"
```

## 反复部署技巧

开发阶段经常需要重置环境：

```bash
# 重建镜像 + 重新创建容器 (保留数据)
./scripts/dev.sh --rebuild

# 完全清理 (包括数据库数据)
./scripts/dev.sh --down
docker volume rm mind-dev_postgres_data
./scripts/dev.sh

# 只重启 API (不重建)
MIND_ENV_FILE=.env.dev.local docker compose --project-name mind-dev --env-file .env.dev.local -f compose.yaml -f compose.dev.yaml restart api
```

## 下一步

- 部署到生产：看 [部署指南](../product/deployment.md)
- 排障：看 [故障排查](./runbook-troubleshooting.md)
