# Frontend Experience

`Phase M / Frontend Experience` 现在已经形成一层独立边界，但它仍然是“轻量 frontend shell + 冻结 transport contract”的工程实现，不是一个脱离现有产品边界的第二套语义层。

## 目标

这层只做三件事：

- 给最终用户和集成人员提供统一的体验入口
- 给 operator 提供显式、可恢复的配置入口
- 给开发态提供隔离的 debug 可视化入口

它不负责重新定义记忆语义，也不直接跨过 `mind/app` 去操作内部对象。

## 运行形态

当前 frontend 采用最轻量的可维护形态：

- 顶层 `frontend/`：静态 `HTML + CSS + ES modules`
- `mind/api/app.py`：以 `/frontend` 静态挂载壳层
- `mind/api/routers/frontend.py`：暴露 frontend-facing JSON transport

明确约束：

- 不使用 Python 渲染页面
- 不引入重量级构建链
- 不让浏览器直接消费 raw telemetry JSONL

## 冻结的前端面

当前冻结了 3 类 surface。

### 功能体验

- `POST /v1/frontend/ingest`
- `POST /v1/frontend/retrieve`
- `POST /v1/frontend/access`
- `POST /v1/frontend/offline`
- `GET /v1/frontend/gate-demo`

这些入口对应 `mind/frontend/experience.py` 中的 contract 和 projection helper。

### 配置入口

- `GET /v1/frontend/settings`
- `POST /v1/frontend/settings:preview`
- `POST /v1/frontend/settings:apply`
- `POST /v1/frontend/settings:restore`

配置入口的边界是“显式配置意图”，不是热修改运行时语义。当前 `apply / restore` 会把快照写到 principal preferences，并保留上一个显式快照用于恢复。

### Debug 可视化

- `POST /v1/frontend/debug:timeline`

debug timeline 返回的不是 raw telemetry，而是 `mind/frontend/debug.py` 投影后的稳定视图：

- timeline events
- object deltas
- context views
- evidence views

## Dev-Mode 边界

Frontend debug surface 只在 `dev_mode=true` 时可用。

这个边界有两层：

- transport / app service 层拒绝非 dev-mode 的 debug 查询
- 静态壳层明确把 debug 描述为 server-side dev-mode capability，而不是常规功能页

普通体验流和配置流不会因为 debug surface 的存在而获得额外内部信息。

## 报告与 Gate

Phase M 当前有 3 个正式产物：

- `mind/frontend/audit.py`
  - responsive audit
- `mind/frontend/reporting.py`
  - frontend flow report
- `mind/frontend/gate.py`
  - `M-1 ~ M-6` formal gate

它们分别覆盖：

- frozen flow coverage
- config / debug / transport surface 完整度
- desktop / mobile 响应式基线
- dev-mode 隔离

## 当前状态

截至 `2026-03-11`，Phase M 的实现基线已包含：

- `FrontendExperienceBench v1`
- 轻量静态 frontend shell
- frontend-facing app services 与 REST routes
- settings `preview / apply / restore`
- debug `timeline / object delta / context / evidence`
- responsive audit
- frontend flow report
- Phase M formal gate

当前这层还没有做的事：

- 更重的浏览器端构建体系
- 原生移动端
- 与后续 Phase N / O 的治理重塑或 persona UI 混合
