# 升级 Runbook

## 升级前

- 记录当前版本和 commit
- 备份 PostgreSQL
- 确认目标版本对应的文档版本
- 预跑关键回归

## 升级步骤

1. 拉取目标版本代码
2. 更新镜像或 Python 环境
3. 执行 `alembic upgrade head`
4. 重启 API
5. 重启 worker
6. 验证 `health` / `readiness`
7. 跑一次最小 smoke

## 建议 smoke

```bash
pytest tests/test_wp3_rest_api.py -q
pytest tests/test_wp5_deployment.py -q
pytest tests/test_wp6_product_cli.py -q
```

## 回滚

当前仓库没有实现完整自动回滚编排；升级前的数据库备份和版本化镜像是主要兜底手段。
