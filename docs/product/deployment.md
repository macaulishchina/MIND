# 部署指南

本指南用于将 MIND 部署到生产环境。如果你是在搭建开发环境，请参考 [开发环境指南](../ops/dev-environment.md)。

## 架构

生产部署由 4 个组件组成：

```
┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐
│ postgres │◄───│   api    │    │  worker  │    │   docs   │
│ (pg16)   │◄───│ (uvicorn)│    │ (轮询任务)│    │ (static) │
└──────────┘    └──────────┘    └──────────┘    └──────────┘
```

对应资产：

| 文件 | 说明 |
|------|------|
| `compose.yaml` | 公共基础配置 |
| `compose.dev.yaml` | 开发环境覆盖层（含文档热更新服务） |
| `compose.prod.yaml` | 生产环境覆盖层 |
| `compose.docs.yaml` | 静态文档站服务 |
| `Dockerfile.api` | API 镜像 |
| `Dockerfile.worker` | Worker 镜像 |
| `Dockerfile.docs` | 文档静态站镜像 |
| `Dockerfile.docs.dev` | 开发环境文档热更新镜像 |
| `.env.prod` | 生产环境变量模板 |
| `.env.prod.local` | 生产环境实际运行时配置（首次部署自动生成，不提交） |
| `scripts/deploy.sh` | 一键部署脚本 |
| `scripts/docs-release.sh` | 本地文档站构建/发布脚本 |
| `scripts/entrypoint-api.sh` | API 入口脚本 |

## 一键部署

```bash
./scripts/deploy.sh
```

默认会在确认后以后台模式部署，并在 smoke check 通过后打印完整访问 URL。

首次运行时：

1. 从 `.env.prod` 复制到 `.env.prod.local`
2. **提示你编辑 `.env.prod.local` 中的必填项**（数据库密码、DSN、API Key）
3. 编辑完成后，重新运行即可

### 部署命令

```bash
./scripts/deploy.sh            # 交互式后台部署 (需确认)
./scripts/deploy.sh --attach   # 交互式前台部署 (需确认)
./scripts/deploy.sh -y         # 跳过确认直接后台部署
./scripts/deploy.sh --down     # 关闭生产环境
./scripts/deploy.sh --status   # 查看服务状态
./scripts/deploy.sh --logs     # 查看最近日志
```

脚本会固定使用独立的 compose project `mind-prod`，避免与开发环境共用容器、网络和数据库卷。
后台部署完成后，脚本会打印以下完整 URL：

- API：`http://127.0.0.1:18600`
- 项目页面：`http://127.0.0.1:18600/frontend/`
- API 文档：`http://127.0.0.1:18600/docs`
- 健康：`http://127.0.0.1:18600/v1/system/health`
- 就绪：`http://127.0.0.1:18600/v1/system/readiness`
- 项目文档：`http://127.0.0.1:18601/`

开发环境的热更新文档站则由 `./scripts/dev.sh` 提供，默认使用 `http://127.0.0.1:18602`。

### 手动部署

如果不使用一键脚本：

```bash
cp .env.prod .env.prod.local
# 编辑 .env.prod.local，至少修改:
#   - MIND_POSTGRES_PASSWORD
#   - MIND_POSTGRES_DSN
#   - MIND_API_KEY
MIND_ENV_FILE=.env.prod.local docker compose \
  --project-name mind-prod \
  --env-file .env.prod.local \
  -f compose.yaml \
  -f compose.prod.yaml \
  -f compose.docs.yaml \
  up --build -d
```

## 环境变量

### 必填

| 变量 | 说明 |
|------|------|
| `MIND_POSTGRES_PASSWORD` | PostgreSQL 容器初始化密码 |
| `MIND_POSTGRES_DSN` | PostgreSQL 连接字符串 |
| `MIND_API_KEY` | API 认证密钥 |

### 可选

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `MIND_POSTGRES_USER` | `postgres` | PostgreSQL 用户名 |
| `MIND_POSTGRES_DB` | `mind` | PostgreSQL 数据库名 |
| `MIND_PROVIDER` | `stub` | AI 提供者 |
| `MIND_MODEL` | `deterministic` | 模型名称 |
| `MIND_LOG_LEVEL` | `WARNING` | 日志级别（生产） |
| `MIND_DEV_MODE` | `false` | 开发模式 (生产必须为 false) |
| `MIND_API_BIND` | `0.0.0.0:18600` | API 监听地址（compose 部署当前固定为 18600） |
| `MIND_DOCS_BIND` | `0.0.0.0:18601` | 生产静态文档站监听地址 |
| `MIND_PIP_INDEX_URL` | `https://pypi.tuna.tsinghua.edu.cn/simple` | Docker 构建时的主 PyPI 镜像源 |
| `MIND_PIP_EXTRA_INDEX_URL` | 空 | Docker 构建时的附加 PyPI 镜像源 |
| `MIND_PIP_TRUSTED_HOST` | `pypi.tuna.tsinghua.edu.cn` | Docker 构建时的可信镜像域名 |

## 生产配置特性

`compose.prod.yaml` 覆盖层提供：

- **日志级别**: `WARNING`（减少输出噪音）
- **资源限制**: API 2C/1G、Worker 1C/512M、PostgreSQL 2C/2G
- **后台运行**: 配合 `-d` 参数
- **开发模式关闭**: 无热更新、无调试端口
- **环境隔离**: 使用独立 project `mind-prod`

`compose.docs.yaml` 提供：

- **静态文档站构建**: 基于 `mkdocs build --strict`
- **文档服务发布**: Nginx 提供只读静态站
- **默认访问地址**: `http://127.0.0.1:18601`

开发环境文档站则由 `compose.dev.yaml` 提供：

- **文档热更新**: `mkdocs serve --livereload`
- **默认访问地址**: `http://127.0.0.1:18602`
- **用途**: 本地开发与联调，不用于生产发布

生产配置默认已使用清华 TUNA PyPI 镜像；如果需要覆盖，可在 `.env.prod.local` 中配置 `MIND_PIP_INDEX_URL` /
`MIND_PIP_EXTRA_INDEX_URL` / `MIND_PIP_TRUSTED_HOST`，这些值会自动透传到 `api`、`worker`
和开发态文档镜像构建阶段。

## 部署验收

部署脚本会自动执行 smoke check。当前 smoke check 不只验证 `health / readiness / docs`，还会执行 `mindtest gate product-readiness`，并把结果写到 `artifacts/product/product_readiness_gate.json` 与 `artifacts/product/product_readiness_gate.md`。也可手动验证：

```bash
curl -H 'X-API-Key: YOUR_KEY' http://127.0.0.1:18600/v1/system/health
curl -H 'X-API-Key: YOUR_KEY' http://127.0.0.1:18600/v1/system/readiness
curl -I http://127.0.0.1:18601/
mindtest gate product-readiness --output artifacts/product/product_readiness_gate.json --markdown-output artifacts/product/product_readiness_gate.md
```

更全面的验收测试：

```bash
uv run pytest tests/test_wp5_deployment.py -q
uv run pytest tests/test_wp3_rest_api.py -q
./scripts/product-readiness-artifacts.sh
```

`DeploymentSmokeSuite v1` 除了静态 compose / Docker 资产检查，还会执行 runtime product transport audit，确认 REST / MCP / CLI 一致性在部署基线上没有漂移。
`./scripts/product-readiness-artifacts.sh` 可一键生成 `product-transport`、`deployment-smoke`、`product-readiness` 三类 report / gate 的 JSON 与 Markdown 工件。CI 入口 `.github/workflows/product-readiness.yml` 复用同一脚本并上传完整 artifact bundle。

## 运维

- 部署操作流程：看 [部署 Runbook](../ops/runbook-deploy.md)
- 文档发布：看 [文档发布 Runbook](../ops/runbook-docs-release.md)
- 升级流程：看 [升级 Runbook](../ops/runbook-upgrade.md)
- 排障：看 [故障排查](../ops/runbook-troubleshooting.md)

## 当前限制

- 认证仍是 API key 最小实现
- Provider 仍是 deterministic stub 基线
- Compose 主要用于本地联调和早期部署，不是完整生产平台编排方案
