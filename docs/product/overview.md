# 产品概览

MIND 是一套面向长期记忆工作流的产品化系统。当前基线已经把研究原型外侧补齐成统一的产品边界：

- `mind/app`：唯一业务边界
- `mind-api`：HTTP/REST 入口
- `mind-mcp`：MCP 工具入口
- `mind`：产品 CLI
- `compose.yaml`：本地联调与部署资产

## 适用场景

- 需要为 agent 保存原始记忆、回忆候选和访问结果
- 需要区分产品调用面与研发/验收调用面
- 需要通过 CLI、HTTP、MCP 共享一套业务语义
- 需要把用户、会话、命名空间和执行策略纳入正式模型

## 当前公开能力

### Memory

- `remember`
- `recall`
- `history`
- `search`
- `get_memory`

### Runtime Access

- `ask`
- `run_access`
- `explain_access`

### Governance

- `plan_conceal`
- `preview_conceal`
- `execute_conceal`

### User State

- principal 读取与偏好更新
- session open/list/show
- runtime defaults 解析

### Operations

- background offline jobs
- health / readiness / config summary
- compose + migration entrypoint
- PostgreSQL-only 产品运行时

## 入口选择

| 入口 | 用途 | 典型用户 |
|---|---|---|
| `mind` | 本地或远程产品操作 | 用户、集成工程师 |
| `mind-api` | 服务化集成 | 平台、后端 |
| `mind-mcp` | agent tool 接入 | agent runtime |
| `mindtest` | 开发、gate、回归 | 内部工程团队 |

所有产品入口统一以 PostgreSQL 作为运行时存储；SQLite 不属于产品 surface，只保留给 `mindtest`、测试和基线校验。

## 不在本轮范围内

本轮产品化完成到 `WP-6`。以下能力仍属于后续阶段：

- provider capability layer 的正式产品接入
- telemetry / frontend-ready 体系
- 更重的 reshape / persona projection

这些设计仍保留在历史和架构文档中，但不应当被误读为当前产品承诺。
