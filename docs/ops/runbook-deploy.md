# 部署 Runbook

## 目标

把 `postgres + api + worker + docs` 在生产环境启起来，并验证健康状态。

## 推荐流程

### 使用一键脚本

```bash
./scripts/deploy.sh
```

脚本会默认在后台完成部署，并在最后执行 smoke check。它固定使用独立的 compose project `mind-prod`，并同时启动静态文档站。完成后会打印完整访问 URL。
smoke check 除了验证 `health / readiness / docs`，还会执行 `mindtest gate product-readiness`，并把 gate 工件落在 `artifacts/product/product_readiness_gate.json` 与 `artifacts/product/product_readiness_gate.md`。

如果你需要前台 attach 模式：

```bash
./scripts/deploy.sh --attach
```

### 手动流程

1. 准备 `.env.prod.local`

    ```bash
    cp .env.prod .env.prod.local
    # 编辑 .env.prod.local，设置:
    #   - MIND_POSTGRES_PASSWORD
    #   - MIND_POSTGRES_DSN
    #   - MIND_API_KEY
    ```

2. 构建并启动

    ```bash
    MIND_ENV_FILE=.env.prod.local docker compose \
      --project-name mind-prod \
      --env-file .env.prod.local \
      -f compose.yaml \
      -f compose.prod.yaml \
      -f compose.docs.yaml \
      up --build -d
    ```

3. 等待 `postgres` healthy
4. 等待 `api` healthy
5. 等待 `worker` heartbeat 正常
6. 验证 `docs` 静态站可访问
7. 验证 `health` 和 `readiness`
8. 执行 `mindtest gate product-readiness --output artifacts/product/product_readiness_gate.json --markdown-output artifacts/product/product_readiness_gate.md`

## 最小检查

```bash
curl -H 'X-API-Key: YOUR_KEY' http://127.0.0.1:18600/v1/system/health
curl -H 'X-API-Key: YOUR_KEY' http://127.0.0.1:18600/v1/system/readiness
curl -I http://127.0.0.1:18601/
mindtest gate product-readiness --output artifacts/product/product_readiness_gate.json --markdown-output artifacts/product/product_readiness_gate.md
```

## GitHub Actions Gate

仓库提供了 `.github/workflows/product-readiness.yml`，在 pull request 和 push 到 `main` / `v*` / `release-v*` 时执行 readiness gate 并上传 artifact bundle。详见 [部署指南](../product/deployment.md#部署验收)。

## 服务管理

```bash
# 查看状态
./scripts/deploy.sh --status

# 查看日志
./scripts/deploy.sh --logs

# 关闭
./scripts/deploy.sh --down
```

## 失败时先看

- `MIND_POSTGRES_DSN` 是否与 compose 网络内地址一致
- `MIND_POSTGRES_PASSWORD` 是否与 DSN 中密码一致
- `MIND_API_KEY` 是否已配置
- `.env.prod.local` 中是否还有 `CHANGE_ME` 占位符
- 静态文档站是否已在 `http://127.0.0.1:18601` 返回 200
- `artifacts/product/product_readiness_gate.json` 中是否记录了失败组件和 failure ids
- `artifacts/product/product_readiness_gate.md` 是否给出了可读的 gate 摘要表
- Alembic migration 是否在 API 启动前执行
- Worker 是否在循环调用 `mindtest-offline-worker-once`
- 日志级别是否为 `WARNING`（正常生产行为）

## 开发环境

如果是搭建开发环境，请参考 [开发环境指南](./dev-environment.md)。
开发环境内置的热更新文档站默认地址为 `http://127.0.0.1:18602`；它与生产静态文档站 `http://127.0.0.1:18601` 分离。
