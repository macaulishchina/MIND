# 安全与密钥

## 当前认证边界

当前正式 transport 的最小认证是 API key：

- Header: `X-API-Key`
- Source: `MIND_API_KEY`

这适合最小产品基线，但不等同于完整生产身份体系。

## 密钥管理建议

- 不要把 `.env` 提交进仓库
- 不要把真实 DSN 写进文档示例
- 使用部署系统的 secret store 注入 `MIND_API_KEY`
- 轮换 API key 时同步更新依赖方

## 日志与脱敏

- CLI config 输出会脱敏 DSN
- `config_summary()` 不返回明文 DSN
- 文档示例只使用占位值或本地演示值

## Dev Mode

`MIND_DEV_MODE` 只应该用于开发/调试，不应当被当成生产开关依赖。
