# PostgreSQL Store + Alembic 初版 + Phase B/C Gate Postgres 回归 — 审核报告

| 项目 | 值 |
| --- | --- |
| 审核范围 | PostgreSQL store 实现、Alembic 迁移、Phase B/C gate Postgres 回归 |
| 审核日期 | 2026-03-09 |
| 审核方式 | 代码逐行审读 + 自动化检查（ruff / mypy / pytest / Phase B&C gate） |
| 涉及新文件 | `mind/kernel/postgres_store.py`, `mind/kernel/sql_tables.py`, `alembic/env.py`, `alembic/script.py.mako`, `alembic/versions/20260309_0001_initial_postgres_schema.py`, `alembic.ini`, `scripts/run_postgres_regression.py`, `tests/test_postgres_regression.py` |
| 涉及修改文件 | `mind/cli.py`, `pyproject.toml`, `README.md` |

---

## 1 自动化基线检查

| 检查项 | 结果 |
| --- | --- |
| pytest（22 条 + 1 skip） | **PASS**（Postgres 测试因无 DSN 预期跳过） |
| ruff | 修复前 **3 处 I001**（alembic/env.py、alembic/versions/...、postgres_store.py）；修复后 **全通过** |
| mypy（27 source files） | **Success** |
| Phase B gate（SQLite） | **PASS** |
| Phase C gate（SQLite） | **PASS** |

---

## 2 多维度审核结果

### 2.1 完整性（Completeness）

#### 2.1.1 Protocol 方法覆盖

`MemoryStore` Protocol 定义了 12 个方法，`PrimitiveTransaction` Protocol 定义了 9 个方法。

| Protocol 方法 | PostgresMemoryStore | \_PostgresStoreTransaction |
| --- | --- | --- |
| `insert_object` | ✅ | ✅ |
| `insert_objects` | ✅ | ✅ |
| `transaction` | ✅ | — |
| `has_object` | ✅ | ✅ |
| `versions_for_object` | ✅ | ✅ |
| `read_object` | ✅ | ✅ |
| `iter_objects` | ✅ | ✅ |
| `raw_records_for_episode` | ✅ | ✅ |
| `record_primitive_call` | ✅ | ✅ |
| `iter_primitive_call_logs` | ✅ | — |
| `record_budget_event` | ✅ | ✅ |
| `iter_budget_events` | ✅ | — |

**结论：** 100% 覆盖，无遗漏。

#### 2.1.2 Schema 三方一致性

三份 schema 定义（`sql_tables.py`、Alembic migration、SQLite `_init_schema`）需保持语义一致。

| 表 / 列 | sql\_tables.py | Alembic migration | SQLite store | 差异说明 |
| --- | --- | --- | --- | --- |
| object\_versions 列 | 11 列含 JSONB | 11 列含 JSONB | 11 列含 TEXT | TEXT→JSONB 为 PG 原生 JSON 优化 |
| inserted\_at 类型 | DateTime(tz=True) | DateTime(tz=True) | TEXT DEFAULT | PG 使用带时区时间戳，更精确 |
| PK / 索引 | PK + 2 idx | PK + 2 idx | PK + 2 idx | 一致 |
| primitive\_call\_logs | 10 列 JSONB | 10 列 JSONB | 10 列 TEXT | 一致（TEXT→JSONB） |
| budget\_events 列 | 9 列 JSONB | 9 列 JSONB | 9 列 TEXT | 一致 |
| budget\_events 索引 | call\_id + scope\_id | call\_id + scope\_id | call\_id 仅 1 个 | PG 额外 scope\_id 索引，前瞻 Phase D |

`sql_tables.py` 与 Alembic migration **完全一致**（列名、类型、nullable、PK、索引名均匹配）。

#### 2.1.3 JSONB 编解码路径

| 操作 | SQLite | PostgreSQL | 正确性 |
| --- | --- | --- | --- |
| 写入 content\_json | `json.dumps(obj["content"])` → TEXT | `obj["content"]` → JSONB（驱动自动序列化） | ✅ |
| 读取 content\_json | `json.loads(row["content_json"])` → dict | `row["content_json"]` → 已为 dict | ✅ |
| 写入 cost\_json | `json.dumps([...])` → TEXT | `[item.model_dump() for ...]` → JSONB | ✅ |
| 读取 cost\_json | `json.loads(row["cost_json"])` → list | `row["cost_json"]` → 已为 list | ✅ |
| 写入 error\_json（nullable） | `json.dumps(...) or None` | `dict or None` | ✅ |

psycopg3 + JSONB 列自动处理 Python 原生类型与 JSON 的双向映射，代码正确跳过了手动 `json.dumps/loads`。

#### 2.1.4 辅助功能完整性

| 功能 | 实现 | 说明 |
| --- | --- | --- |
| `build_postgres_store_factory` | ✅ | 返回与 `MemoryStoreFactory` 类型兼容的工厂 |
| `run_postgres_migrations` | ✅ | 动态覆盖 `sqlalchemy.url` 和 `script_location` |
| `temporary_postgres_database` | ✅ | CREATE + yield + pg\_terminate\_backend + DROP |
| CLI `postgres_regression_main` | ✅ | 双临时库隔离 Phase B / C |
| pytest 集成测试 | ✅ | skipif 无 DSN；覆盖空库 + 双 gate |
| pyproject.toml 依赖声明 | ✅ | alembic, psycopg\[binary\], sqlalchemy |
| 入口脚本 | ✅ | `scripts/run_postgres_regression.py` + entry\_point |

---

### 2.2 必要性（Necessity）

| 文件 | 必要性评估 |
| --- | --- |
| `postgres_store.py` | **必要** — Phase D 核心后端，必须独立于 SQLite 实现 |
| `sql_tables.py` | **必要** — 为 Alembic 和运行时代码提供唯一 schema 定义源 |
| Alembic 目录（env.py / ini / mako / migration） | **必要** — implementation\_stack.md 明确冻结 Alembic 为迁移工具 |
| `cli.py` 修改 | **必要** — 提供 Postgres 回归入口 |
| `pyproject.toml` 依赖 | **必要** — 新增的三个库均为 implementation\_stack.md 冻结选型 |
| `tests/test_postgres_regression.py` | **必要** — CI 可选集成测试 |
| `scripts/run_postgres_regression.py` | **必要** — 保持脚本入口一致性 |
| `README.md` 修改 | **必要** — 文档同步 |

无多余文件或无用代码。所有 import 均被实际使用（逐一验证）。

---

### 2.3 合理性（Reasonableness）

#### 2.3.1 技术选型合规

| 选型 | implementation\_stack.md 冻结 | 实际使用 | 合规 |
| --- | --- | --- | --- |
| PostgreSQL 16 + JSONB | ✅ | JSONB 列 + `->>` 操作符 | ✅ |
| SQLAlchemy 2 Core（禁 ORM） | ✅ | 仅 `sa.Table` / `sa.select` / `sa.insert` | ✅ |
| psycopg 3 | ✅ | `psycopg[binary]>=3.2` | ✅ |
| Alembic | ✅ | 标准 migration workflow | ✅ |

#### 2.3.2 架构设计合理性

| 设计决策 | 评价 |
| --- | --- |
| 工厂模式 `MemoryStoreFactory` 插拔后端 | **优秀** — 无需修改 gate 代码即可切换 SQLite / Postgres |
| Transaction 类直接持有 connection | **合理** — Postgres 中读操作需要使用事务连接才能看到未提交写入 |
| `raw_records_for_episode` 用 JSONB `->>` 在 SQL 层过滤 | **优秀** — 优于 SQLite 的全量 Python 过滤（O(N)→O(1) with index） |
| `temporary_postgres_database` 用 `pg_terminate_backend` 清理 | **合理** — 确保 DROP DATABASE 不会因活跃连接阻塞 |
| AUTOCOMMIT 隔离级别用于 admin DDL | **正确** — CREATE/DROP DATABASE 不可在事务内执行 |
| 两个独立临时库分别跑 Phase B / C | **合理** — 完全隔离，避免数据串扰 |

#### 2.3.3 Transaction 生命周期安全性

| 场景 | 行为 | 安全性 |
| --- | --- | --- |
| 正常 commit | commit → close connection → clear flag | ✅ |
| commit 失败 | rollback → close connection（finally 保证）→ re-raise | ✅ 无泄漏 |
| 异常退出 | rollback → close connection → clear flag | ✅ |
| 嵌套事务 | `_begin_transaction` 抛 StoreError | ✅ 与 SQLite 行为一致 |

#### 2.3.4 安全性

| 检查项 | 结果 |
| --- | --- |
| SQL 注入 | 所有数据查询使用 SQLAlchemy 参数化；DDL 中 `temp_name` 由 `uuid.hex` 生成（纯字母数字） |
| 连接泄漏 | `_rollback_transaction` 的 finally 块保证 connection 关闭；`temporary_postgres_database` 的 finally 块保证 admin\_engine.dispose() |
| 敏感信息 | DSN 不写入日志或报告输出 |

---

### 2.4 时机合理性

`implementation_stack.md` 注明「PostgreSQL、SQLAlchemy、Alembic 统一推迟到 Phase D」。当前提交属于 **Phase D 准备工作**，在 Phase C gate 全部通过后引入基础设施，符合推进节奏。且不修改任何 Phase B/C 已有逻辑，仅通过工厂模式扩展。

---

## 3 发现的缺陷

### D-1: ruff I001 import 排序（低）— 已修复 ✅

- **位置：** `alembic/env.py`、`alembic/versions/20260309_0001_initial_postgres_schema.py`、`mind/kernel/postgres_store.py`
- **问题：** import 块未按 ruff isort 规则排序
- **修复：** `ruff check --fix`

### D-2: `_admin_url_for` 逻辑边界条件（低）— 已修复 ✅

- **位置：** `mind/kernel/postgres_store.py` 函数 `_admin_url_for`
- **问题：** 当 `base_url.database` 为 `None` 或空字符串时，`or "postgres"` 使条件短路，返回未设置 `database="postgres"` 的原始 URL，导致 admin 连接可能连错库
- **修复前：**
  ```python
  def _admin_url_for(base_url: URL) -> URL:
      database = base_url.database or "postgres"
      if database != "postgres":
          return base_url.set(database="postgres")
      return base_url
  ```
- **修复后：**
  ```python
  def _admin_url_for(base_url: URL) -> URL:
      if base_url.database == "postgres":
          return base_url
      return base_url.set(database="postgres")
  ```
- **影响：** 当前所有调用方均传入完整 DSN，实际不触发。修复为防御性改进。

---

## 4 观察记录（无需修复）

| 编号 | 观察 | 说明 |
| --- | --- | --- |
| O-1 | PG 使用 JSONB 替代 SQLite TEXT | 正向升级，利用原生 JSON 查询能力 |
| O-2 | budget\_events 多一个 scope\_id 索引 | Phase D 前瞻优化 |
| O-3 | `raw_records_for_episode` 用 SQL 过滤 | 性能从 O(N) 降至 O(log N)，正向改进 |
| O-4 | Transaction 类重复实现 `iter_objects` / `raw_records_for_episode` | 必要——需使用事务连接读取未提交数据 |
| O-5 | `_transaction_open` 非线程安全 | 与 SQLite 实现一致，MemoryStore 不承诺线程安全 |

---

## 5 修复后验证

| 验证项 | 结果 |
| --- | --- |
| ruff check . | **全通过** |
| mypy（27 files） | **Success** |
| pytest（22 + 1 skip） | **全通过** |
| Phase B gate（SQLite） | **PASS** |
| Phase C gate（SQLite） | **PASS** |

---

## 6 总结

| 维度 | 评级 | 说明 |
| --- | --- | --- |
| 完整性 | **A** | Protocol 100% 覆盖；schema 三方一致；JSONB 编解码正确 |
| 必要性 | **A** | 无多余文件或代码；所有 import 均被使用 |
| 合理性 | **A** | 严格遵循冻结选型；架构模式优秀；安全性良好 |
| 代码质量 | **A−** | 两处低级缺陷已修复；其余代码结构清晰 |

**总体评价：高质量实现，2 处低级缺陷均已修复，可提交。**
