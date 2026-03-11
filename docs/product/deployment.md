# 部署指南

当前最小部署拓扑由 3 个组件组成：

- `postgres`
- `api`
- `worker`

对应资产：

- `compose.yaml`
- `Dockerfile.api`
- `Dockerfile.worker`
- `scripts/entrypoint-api.sh`
- `.env.example`

## 环境变量

至少设置：

- `MIND_POSTGRES_DSN`
- `MIND_API_KEY`

可选：

- `MIND_PROVIDER`
- `MIND_MODEL`
- `MIND_LOG_LEVEL`
- `MIND_DEV_MODE`
- `MIND_API_BIND`

## 本地 compose

```bash
cp .env.example .env
docker compose up --build
```

启动后：

- API 暴露在 `8000`
- health endpoint 为 `GET /v1/system/health`
- API 健康检查使用 `X-API-Key`
- worker 会循环执行 `mindtest-offline-worker-once`

## 直接启动 API

如果不走 compose，也可以直接启动：

```bash
export MIND_POSTGRES_DSN='postgresql+psycopg://postgres:postgres@127.0.0.1:5432/mind'
export MIND_API_KEY='change-me'
uv run mind-api
```

`scripts/entrypoint-api.sh` 的职责是：

1. `alembic upgrade head`
2. 启动 `uvicorn`

## 部署验收

部署后最少检查：

```bash
curl -H 'X-API-Key: change-me' http://127.0.0.1:8000/v1/system/health
curl -H 'X-API-Key: change-me' http://127.0.0.1:8000/v1/system/readiness
```

另外建议保留：

- `pytest tests/test_wp5_deployment.py -q`
- `pytest tests/test_wp3_rest_api.py -q`

## 当前限制

- 认证仍然是 API key 最小实现
- provider 仍是 deterministic stub 基线
- compose 主要用于本地联调和早期部署，不是完整生产平台编排方案
