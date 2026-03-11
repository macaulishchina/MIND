# 系统总览

当前产品化基线可以概括成 5 层：

1. Core domain
2. Application service layer
3. Transport layer
4. Store / persistence
5. Deployment / operations

## 核心原则

- transport 不直接碰 domain service
- domain 不知道 REST/MCP/CLI
- `mind/app` 是统一业务边界
- PostgreSQL 是正式真相源，SQLite 是 reference backend

## 主要模块

### Core Domain

- `mind/primitives`
- `mind/access`
- `mind/governance`
- `mind/offline`

### Product Layer

- `mind/app`
- `mind/api`
- `mind/mcp`
- `mind/product_cli.py`

### Persistence

- `mind/kernel/store.py`
- `mind/kernel/postgres_store.py`
- `alembic/`

## 为什么要这样分

这样做的好处是：

- CLI/REST/MCP 的行为可以共用一套测试和业务 contract
- 用户态上下文可以统一进入 `AppRequest`
- 产品文档可以围绕稳定 surface 组织，而不是跟随内部实现细节漂移
