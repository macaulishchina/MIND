# Config Reference

## 环境变量

### Required

| 变量 | 说明 |
|---|---|
| `MIND_POSTGRES_USER` | PostgreSQL 用户名（compose 部署默认 `postgres`） |
| `MIND_POSTGRES_PASSWORD` | PostgreSQL 容器初始化密码（compose 部署必填） |
| `MIND_POSTGRES_DB` | PostgreSQL 数据库名（compose 部署默认 `mind`） |
| `MIND_POSTGRES_DSN` | PostgreSQL DSN |
| `MIND_API_KEY` | REST API key |

### Provider

| 变量 | 说明 |
|---|---|
| `MIND_PROVIDER` | 当前 provider 标识，默认 `stub` |
| `MIND_MODEL` | 当前 model 标识，默认 `deterministic` |

### Optional

| 变量 | 说明 |
|---|---|
| `MIND_API_BIND` | API bind 地址；compose 脚本当前固定为 `0.0.0.0:8000` |
| `MIND_DOCS_BIND` | 文档站 bind 地址；dev 默认 `0.0.0.0:8002`，prod 默认 `0.0.0.0:8001` |
| `MIND_LOG_LEVEL` | 日志级别 |
| `MIND_DEV_MODE` | 开发模式开关 |
| `MIND_PIP_INDEX_URL` | Docker 构建时的主 PyPI 镜像源，默认 `https://pypi.tuna.tsinghua.edu.cn/simple` |
| `MIND_PIP_EXTRA_INDEX_URL` | Docker 构建时的附加 PyPI 镜像源 |
| `MIND_PIP_TRUSTED_HOST` | Docker 构建时的可信镜像域名，默认 `pypi.tuna.tsinghua.edu.cn` |
| `MIND_SQLITE_PATH` | SQLite 路径覆盖 |
| `MIND_CLI_PROFILE` | CLI profile 覆盖（`auto` / `sqlite_local` / `postgres_main` / `postgres_test`） |
| `MIND_TEST_POSTGRES_DSN` | Postgres test profile DSN |

## CLI Profiles

| Profile | 默认 backend | 用途 |
|---|---|---|
| `auto` | 自动解析 | 有 `MIND_POSTGRES_DSN` 就走 PostgreSQL，否则回退 SQLite |
| `sqlite_local` | `sqlite` | 本地开发和轻量回归 |
| `postgres_main` | `postgresql` | 正式 backend / worker |
| `postgres_test` | `postgresql` | 回归和临时测试 |

## CLI Backends

| Backend | 说明 |
|---|---|
| `sqlite` | reference backend |
| `postgresql` | 正式真相源 |

## 脱敏规则

`config_summary()` 和 CLI config 输出会自动脱敏 `postgres_dsn` 中的密码部分。
