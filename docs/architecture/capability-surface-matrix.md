# 能力暴露矩阵

这份文档的作用很具体：

- 固定 MIND 最初记忆模型设计的完整能力面
- 对照当前各层实现与暴露情况
- 明确哪些属于后续应补齐的正式缺口

时点说明：本文档基于 `2026-03-11` 的仓库状态整理，作为后续实现、产品化裁剪和 transport 扩展的对照基线。

## 判定规则

表格中的状态含义如下：

- `已`：该层已实现，且可以直接作为该层的正式能力使用
- `部`：该层只暴露了部分能力，或只通过间接方式可用
- `待`：从最初设计看，这层应当具备，但当前仍未正式实现
- `否`：该层当前不作为正式暴露面，不默认视为缺陷

补充说明：

- `否` 不自动进入 backlog；只有在“需要实现/补齐”列中被标记，才视为后续应收口项
- `mind` 是产品 CLI，不等于“全量记忆模型 CLI”
- `mindtest` 是开发、验收和内核能力调试入口，覆盖面显著大于 `mind`

## 能力范围基线

本文以以下材料作为“最初能力面”的真相源：

- 当前站点内的 [产品概览](../product/overview.md) 与 [系统总览](./system-overview.md)
- 仓库内的历史规格与蓝图：`docs/foundation/spec.md`、`docs/design/productization_program.md`

## 核心记忆能力矩阵

| 能力 | Kernel | App | REST | MCP | `mind` | `mindtest` | Worker | 需要实现/补齐 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 8 类核心对象 | 已 | 部 | 部 | 部 | 部 | 已 | 部 | 若要产品级对象浏览/治理，补 type-aware browse/manage surface |
| 7 个 primitive | 已 | 部 | 部 | 部 | 否 | 已 | 部 | 不是硬缺口；是否产品化直出属于产品面裁剪决策 |
| Memory ingest/query | 已 | 已 | 已 | 已 | 部 | 已 | 否 | `mind` 还缺 `search / get-memory` |
| `WorkspaceView` | 已 | 部 | 部 | 部 | 部 | 已 | 否 | 若要更强可观测性，补 standalone workspace inspect |
| Access modes `flash / recall / reconstruct / reflective / auto` | 已 | 已 | 已 | 部 | 部 | 已 | 否 | MCP 缺 `run_access / explain_access`；`mind` 缺 explain 面 |
| Offline replay ranking | 已 | 否 | 否 | 否 | 否 | 已 | 否 | 若要运维或平台侧可用，补 app/REST/MCP 入口 |
| Offline reflect | 已 | 已 | 已 | 已 | 否 | 已 | 已 | 核心链路已齐 |
| Offline summarize | 部 | 待 | 待 | 待 | 否 | 部 | 待 | 需要新增 offline job kind，而不只是 primitive `summarize` |
| Offline schema promotion / reconstruct | 已 | 已 | 已 | 已 | 否 | 已 | 已 | 核心链路已齐，缺更好的 explain/ops 视图 |
| Offline archive / deprecate / reprioritize | 部 | 待 | 待 | 待 | 否 | 部 | 待 | 需要新增 maintenance job kinds / policy / batch 入口 |
| Governance `conceal` | 已 | 已 | 已 | 已 | 否 | 已 | 否 | 核心链路已齐 |
| Governance `erase / approve / reshape rewrite` | 待 | 待 | 待 | 待 | 否 | 待 | 否 | 相对原始规格最明确的硬缺口 |

## 产品化辅助能力矩阵

| 能力 | Kernel | App | REST | MCP | `mind` | `mindtest` | Worker | 需要实现/补齐 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Capability layer `summarize / reflect / answer / offline_reconstruct` | 已 | 部 | 部 | 部 | 部 | 部 | 已 | 已统一到内部；若要对外可观测，需补 transport/admin surface |
| Provider status / provider config observability | 否 | 已 | 待 | 否 | 待 | 部 | 否 | 补正式 REST / CLI 入口 |
| User / principal state | 否 | 已 | 已 | 否 | 否 | 否 | 否 | 若 agent 侧需要，可补 MCP user tools |
| Session lifecycle | 否 | 已 | 已 | 否 | 已 | 否 | 否 | 若 MCP 集成需要会话操作，可补 session tools |
| Jobs queue lifecycle | 已 | 已 | 已 | 部 | 否 | 已 | 已 | MCP 还缺 `list / cancel`，`mind` 也没有 jobs 面 |
| System health / readiness / config | 否 | 已 | 已 | 否 | 已 | 部 | 否 | 若 agent 运维要用，可补 MCP system tools |

## 当前必须补齐的实现项

### P0

- Offline summarize job
- Offline archive / deprecate / reprioritize 的 job 化与批处理入口
- Governance `erase / approve / reshape rewrite`

### P1

- MCP 补 `run_access / explain_access / list_jobs / cancel_job`
- `mind` 补 `search / get-memory`
- REST / CLI 补 provider status 正式入口

### P2

- Workspace 独立 inspect / explain 入口
- Product-facing object browse / type-aware manage surface
- Offline replay ranking 的产品化或平台化入口

## 使用约束

后续实现、文档和验收讨论应遵循以下规则：

1. 讨论“是否已实现”时，以本矩阵和对应源码为准，不以单一 transport 的功能感知为准。
2. 讨论“是否要补”时，先区分它是 `待` 还是 `否`。
3. 新增 transport 时，优先复用 `mind/app`，避免绕过应用服务层直接暴露内核。
4. 若某项能力进入产品面，应同步更新本文档，而不是只更新命令帮助或接口文档。
