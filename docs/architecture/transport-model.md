# 传输模型

MIND 当前有 3 个正式产品 transport：

- CLI
- REST
- MCP

以及 1 个开发 transport：

- `mindtest`

## 一致性原则

三种产品 transport 都必须：

- 进入同一套 app services
- 共享同一 error envelope
- 共享 principal/session/policy 语义
- 尽可能保持结果语义一致

## 各自职责

### CLI

- 本地快速操作
- 支持 local 和 remote

### REST

- 服务化接入
- 健康检查、分页、API key auth

### MCP

- tool catalog
- session metadata 映射

## 为什么文档要按 transport 分层

如果把 CLI/REST/MCP 混写在一起，文档会很快失去读者边界。产品文档应该先按使用方式分层，再通过 reference 保持事实统一。
