# Capability Layer

`Phase K / LLM Capability Layer` 已经在代码里形成一层独立边界，但它当前仍以内部工程与开发/验收入口为主，不应被误读成“产品面已经完全开放模型配置”。

## 目标

这一层只做一件事：把已有处理能力收敛成统一 capability 调用面。

当前冻结的 capability catalog：

- `summarize`
- `reflect`
- `answer`
- `offline_reconstruct`

对应 contract、adapter protocol、fallback 语义、trace 字段和基准夹具都已经固定在 `mind/capabilities/`。

## 边界

这层的输入输出是业务 capability，而不是 provider 私有 API 原语。

上层调用方：

- `mind/primitives/service.py`
- `mind/workspace/answer_benchmark.py`
- `mind/access/benchmark.py`
- `mind/offline/service.py`

不需要知道底层是 `responses`、`messages` 还是 `generateContent`。

这层当前明确保证：

- provider / model / endpoint / auth / timeout / retry 走统一配置模型
- `openai / claude / gemini` 有真实 adapter
- 不配置外部模型时保留 deterministic baseline
- provider 不可用时只允许 deterministic fallback 或 structured failure
- `provider / model / endpoint / version / timing` 必进 trace

## 运行形态

默认情况下，`CapabilityService` 使用 deterministic baseline。

如果配置了外部 provider，对应 adapter 会通过统一 service 装配：

- `OpenAI Responses API`
- `Anthropic Messages API`
- `Gemini generateContent API`

这层不把 provider 私有特性抬升为系统主语义；adapter 负责把 provider 差异压回统一 request / response contract。

## 配置

统一配置入口在 `mind/capabilities/config.py`。

关键环境变量：

- `MIND_PROVIDER`
- `MIND_MODEL`
- `MIND_PROVIDER_ENDPOINT`
- `MIND_PROVIDER_TIMEOUT_MS`
- `MIND_PROVIDER_RETRY_POLICY`
- `MIND_PROVIDER_API_KEY`
- `OPENAI_API_KEY`
- `ANTHROPIC_API_KEY`
- `GOOGLE_API_KEY`

通用规则：

- `MIND_PROVIDER_API_KEY` 是跨 provider 的统一覆盖位
- 没有统一 key 时，分别回落到 provider 自己的环境变量
- 不配置外部认证时，系统仍可走 deterministic baseline

## 开发与验收入口

Phase K 现在有两条正式开发入口：

```bash
mindtest gate phase-k
mindtest report phase-k-compatibility
```

也保留了直接脚本入口：

```bash
mindtest-phase-k-gate
mindtest-phase-k-compatibility-report
```

如果只想跑 deterministic baseline，直接执行即可。

如果要显式跑 live provider adapter，需要声明 provider：

```bash
mindtest gate phase-k --live-provider openai
mindtest report phase-k-compatibility --live-provider openai --live-provider claude
```

显式请求 live provider 但缺少认证时，CLI 会直接失败，而不是静默降级。

## 产物

当前 Phase K 会产出 4 类结构化结果：

- `CapabilityAdapterBench v1`
- `failure audit`
- `provider compatibility report`
- `Phase K gate report`

默认 JSON 输出路径：

- `artifacts/phase_k/gate_report.json`
- `artifacts/phase_k/provider_compatibility.json`

## 当前状态

截至 `2026-03-11`，Phase K 的实现基线已包含：

- capability contract 与 adapter protocol
- provider config 模型
- deterministic / openai / claude / gemini adapter
- summarize / reflect / answer / offline_reconstruct 接入统一层
- failure audit、trace audit、compatibility report、formal gate
- `mindtest` gate/report 入口

当前仍未完成的部分：

- Phase K 正式 acceptance report
- 更完整的产品面配置暴露与 operator 文档
- 下一阶段 `Phase L / Development Telemetry` 的前置收口
