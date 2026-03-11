# 部署 Runbook

## 目标

把 `postgres + api + worker` 启起来，并验证健康状态。

## 标准流程

1. 准备 `.env`
2. 执行 `docker compose up --build`
3. 等待 `postgres` healthy
4. 等待 `api` healthy
5. 等待 `worker` heartbeat 正常
6. 验证 `health` 和 `readiness`

## 最小检查

```bash
curl -H 'X-API-Key: change-me' http://127.0.0.1:8000/v1/system/health
curl -H 'X-API-Key: change-me' http://127.0.0.1:8000/v1/system/readiness
```

## 失败时先看

- `MIND_POSTGRES_DSN` 是否与 compose 网络内地址一致
- `MIND_API_KEY` 是否已配置
- Alembic migration 是否在 API 启动前执行
- worker 是否在循环调用 `mindtest-offline-worker-once`
