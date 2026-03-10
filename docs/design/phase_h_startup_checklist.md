# Phase H 启动清单

时点说明：这份文档记录的是 Phase G 完成后，MIND 进入 `Phase H / Provenance Foundation` 前的启动约束、任务拆分和范围控制。正式通过口径以后续 Phase H 验收报告为准；这里先冻结启动顺序，避免把 provenance、runtime access、governance reshape 和 persona 一次性混成一个超大阶段。

## 目标

Phase H 只做 provenance foundation，不做完整治理重塑。

本阶段的目标是：

1. 建立 `provenance_ledger` 与 `governance_audit` 的最小 control-plane 底座
2. 让 `RawRecord / ImportedRawRecord` 稳定绑定 authoritative direct provenance
3. 建立最小 capability 边界，区分普通读取与 provenance 读取
4. 打通 `plan / preview / conceal / execute-audit` 的最小治理链
5. 验证 provenance 不会泄露进 retrieval / ranking / weighting

## 非目标

Phase H 明确不做：

1. mixed-source 派生对象的 claim / rule / facet / slot 级重写
2. `erase(scope=full)` 的全外部副本处理
3. runtime `Flash / Recall / Reconstruct / Reflective` access mode 实现
4. persona / projection / value schema 的对象化实现
5. 完整产品级权限系统

## 任务拆分

1. `H1`：冻结 Phase H gate 与 fixture / audit 口径
2. `H2`：设计 control-plane 数据模型与最小 capability contract
3. `H3`：接入 ingest provenance 绑定与高权限读取摘要
4. `H4`：落地 `conceal` 最小执行链与 online / offline 可见性隔离
5. `H5`：补 provenance 泄露回归、治理审计和正式 gate

## 推荐推进顺序

### `H1` Gate 与工件冻结

- 把 [../foundation/phase_gates.md](../foundation/phase_gates.md) 中的 `H-1 ~ H-8` 作为本阶段唯一 formal gate
- 明确 Phase H 使用的 fixture：
  - 现有 `GoldenEpisodeSet v1`
  - 现有 `PrimitiveGoldenCalls v1`
  - 补充最小 provenance / conceal regression fixture
- 明确本阶段输出工件：
  - provenance audit report
  - conceal regression report
  - Phase H gate report
- 当前本地入口：
  - `scripts/run_phase_h_gate.py`
  - `artifacts/phase_h/gate_report.json`

### `H2` Control Plane 建模

- 设计 `provenance_ledger` 最小字段集
- 设计 `governance_audit` 最小字段集
  - 至少冻结 `audit_id / operation_id / action / stage / actor / capability / timestamp / outcome / scope / selection / summary`
  - 冻结 `plan / preview / approve / execute` 与 capability 的最小对应关系
- 冻结 capability 边界：
  - `memory_read`
  - `memory_read_with_provenance`
  - `governance_plan`
  - `governance_execute`
  - `governance_approve_full_erase`
- 明确哪些高敏字段只允许出现在 control plane

### `H3` Ingest 与 Read 接入

- `write_raw` 或等价 ingest 路径必须绑定 direct provenance
- 外部导入原始对象也必须绑定 direct provenance
- 普通 `read` 不返回 provenance 摘要
- 高权限读取路径允许返回 provenance 摘要，但不返回超范围高敏字段

### `H4` `conceal` 最小执行链

- 最小流程：
  - `plan`
  - `preview`
  - `execute(conceal)`
  - `audit`
- `conceal` 的最小数据面应表现为 control-plane 可见性标记，而不是新增 data-plane `status`
- `conceal` 后的默认要求：
  - 普通 retrieval 不可见
  - 普通 read 不可见
  - workspace 构建不应纳入
  - offline maintenance 默认不应再消费这些对象
- governance preview 仍应可看见受影响范围

### `H5` 回归与 Gate

- provenance 绑定完整率回归
- capability 隔离回归
- conceal visibility regression
- retrieval / ranking isolation regression
- 形成 Phase H gate report
- 当前 formal gate 已落地为 `scripts/run_phase_h_gate.py`

## 当前关键设计约束

1. provenance 是 control plane，不是 `source_refs`
2. provenance 不得进入 retrieval / ranking / weighting
3. `conceal` 是逻辑不可见，不等同于物理删除
4. Phase H 必须先证明“隔离和审计成立”，再进入后续重写和 erase 扩展
5. 如果某对象类型还没有稳定 governance projection，就不要在 H 阶段声称支持细粒度 rewrite

## 依赖关系

- 依赖 Phase G 已完成的 baseline、评测框架和项目文档整理
- 依赖现有 Phase B / C 的对象、trace、validator 和 primitive contract
- 依赖现有 Phase D / E 的 retrieval、workspace 和 offline maintenance 路径，以便验证 conceal 的隔离效果

## 风险提醒

1. 最大风险不是建表，而是把 provenance 偷渡进现有优化路径
2. 第二个风险是 `conceal` 只在一个读取接口生效，其他路径仍然漏出
3. 第三个风险是过早做 mixed-source rewrite，导致阶段范围失控
4. 第四个风险是把 capability 扩展成完整权限系统，偏离本阶段目标

## 完成标志

当以下条件同时满足时，Phase H 可以进入正式验收：

- `H-1 ~ H-8` 都有可运行验证路径
- provenance audit、conceal regression、gate report 都可生成
- control-plane 最小数据模型、最小 capability 边界与执行链已经冻结
- 文档、实现和测试对 Phase H 的范围表述一致
