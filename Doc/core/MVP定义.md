# MIND MVP 定义

## 1. 目标

打通一个当前代码库已经实现、并且可以稳定验收的最小闭环：

- 能写入记忆
- 能按 owner 召回 active memories
- 能手动更新和逻辑删除
- 能查看变更历史

MVP 的重点不是“覆盖所有未来能力”，而是把当前主链收口成一个可靠、
可验证、可继续迭代的基线。

## 2. MVP 边界

### In Scope

- 单 owner 空间下的跨会话记忆
- 公共 API：`add / search / get / get_all / update / delete / history`
- STL-native `add()` 主链
- owner-centered memory 投影
- 写入时记录 `confidence`、`source_context`
- add-path 更新时记录 `version_of`
- 逻辑删除与操作历史追踪
- 基于 TOML 的运行时配置

### Out of Scope

- Web UI / SDK 发布包装
- 多 agent 协作
- 遗忘机制、时间衰减、记忆合并（v1.5）
- 查询分解、多路召回、复杂状态机（v2）
- 图记忆、关系压缩（v3）

## 3. 当前 MVP 架构

### 写入（add）

```
用户对话
  → 单次 LLM 调用输出 STL
  → 解析 STL refs / statements / notes
  → 持久化 STL 关系数据
  → 将当前 chunk 的最终 statement 投影成 owner-centered memory
  → 记录 confidence / source_context / version_of / history
```

### 检索（search）

```
查询
  → Embedding 编码
  → 向量搜索 active owner memories
  → 返回 owner-centered MemoryItem
```

### 手动管理（update / delete / history）

```
update(memory_id, content)
  → 更新内容与向量
  → 记录 UPDATE 历史

delete(memory_id)
  → status=deleted
  → active 检索面不再返回该记忆
  → 记录 DELETE 历史
```

## 4. MVP 推荐运行组合

默认推荐沿用仓库模板：

- 配置入口：`mind.toml.example -> mind.toml`
- 向量存储：Postgres + pgvector
- 历史与 STL store：Postgres
- 在线 STL 抽取：`leihuo:gpt-5.4-mini`
- 提示词模式：基础 prompt，`stl_extraction_supplement = false`

测试和本地验证仍可使用 fake LLM / fake embedding / 本地临时库。

## 5. MVP 成功标准

### 必须通过

1. 用户写入一个稳定偏好后，`search()` 能召回它
2. add-path 改口能形成最终有效记忆，并保留 `version_of` 关系
3. 手动 `update()` 后能通过 `history()` 看到变更记录
4. 被 `delete()` 的记忆不会再出现在 active `search()` / `get_all()` 结果里
5. 写入后的记忆保留 `confidence` 和 `source_context`

### 非阻塞质量观测

- owner-add eval 的代表用例通过情况
- STL 提取质量与模型可靠性
- 重复写入率和误判率

## 6. 已知限制

- 当前默认只正式化了 STL 抽取阶段的在线策略，decision 阶段仍跟随全局 `llm`
- 公共 `search()` 当前只返回 owner-centered memories，不直接暴露底层 STL statement
- 没有 UI、发布包或部署自动化
- 后续质量增强能力属于 v1.5/v2，不在 MVP 闭环里
