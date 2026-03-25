# MIND MVP 定义

## 1. 目标

打通一个最小闭环：能记住、能召回、能更新、能删除。

在此基础上，比 mem0 多做一件事：**写入时记录置信度和来源**，为后续质量增强积累数据。

## 2. MVP 边界

### In Scope

- 单用户场景
- 跨会话记忆
- 四个核心操作：add / search / update / delete
- LLM 两步决策流程（提取事实 + 判断操作）
- 写入时标注 confidence 和 source_context
- 更新时记录 version_of
- 操作历史追踪

### Out of Scope

- 多用户 / 多 Agent
- 图记忆
- 遗忘机制（v1.5）
- 查询分解和多路径检索（v2）
- 复杂状态机（v2）
- 后台巩固任务
- Web UI

## 3. 核心流程

### 写入（add）

```
用户对话
  → LLM 提取事实（同时输出 confidence）
  → 对每条事实：
      → Embedding 编码
      → 向量搜索 Top-5 相似旧记忆
      → LLM 判断 ADD / UPDATE / DELETE / NONE
      → ADD: 新建记忆，记录 source_context 和 confidence
      → UPDATE: 新建记忆 + 记录 version_of + 旧记忆保留
      → DELETE: 标记旧记忆为 deleted
      → NONE: 不操作
```

### 检索（search）

```
查询
  → Embedding 编码
  → 向量搜索（过滤 status=active）
  → 按相似度排序返回 Top-K
```

### 更新（update）

```
手动更新
  → 重新 Embedding
  → 更新向量存储
  → 记录操作历史
```

### 删除（delete）

```
删除
  → 标记 status=deleted（逻辑删除）
  → 记录操作历史
```

## 4. 与 mem0 基线的差异

MVP 阶段只做三个差异化增强，每个都是低成本高收益：

| 增强点 | 实现成本 | 说明 |
|--------|---------|------|
| confidence 标注 | 修改提取 prompt，多返回一个字段 | 为 v1.5 的置信度降权积累数据 |
| source_context | 写入时多存一个字段 | 为后续记忆验证和审计保留依据 |
| version_of | UPDATE 时多存一个字段 | 为版本追踪和回滚保留能力 |

这三个增强的共同特点：**v1 只写入不使用**，不影响核心流程的简洁性，但为后续增强预埋了数据基础。

## 5. 技术实现

| 组件 | 选择 |
|------|------|
| 语言 | Python |
| LLM | OpenAI（开发用 gpt-4o-mini） |
| Embedding | OpenAI text-embedding-3-small |
| 向量存储 | Qdrant in-memory（开发）/ Qdrant server（生产） |
| 历史记录 | SQLite |

## 6. 成功标准

### 必须通过

1. 用户说"我喜欢黑咖啡"，新会话问饮品推荐时能正确召回
2. 用户改口"我现在只喝美式"，系统更新记忆且能记录 version_of 关系
3. 被删除的记忆不再出现在检索结果中
4. 每条记忆都有 confidence 和 source_context 记录

### 质量观测（不作为通过标准，但需要记录）

- LLM 事实提取的准确率（人工抽检）
- 重复记忆的产生率
- UPDATE/DELETE 判断的准确率

## 7. 实施顺序

### 第一步：数据模型 + 存储层

- 定义 MemoryItem 核心层 + 增强层
- 实现向量存储接口（Qdrant）
- 实现 SQLite 历史记录

### 第二步：写入流程

- 实现事实提取 prompt（参考 mem0，增加 confidence 输出）
- 实现更新决策 prompt（参考 mem0 的 ADD/UPDATE/DELETE/NONE）
- 实现 add() 方法

### 第三步：检索流程

- 实现 search() 方法
- 实现基础过滤（status=active）

### 第四步：管理操作

- 实现 get / get_all / update / delete / history
- 端到端测试

## 8. 不做的事

- 不做 Web UI，用 Python API 或 CLI 验证
- 不做多后端适配，v1 只接 Qdrant
- 不做遗忘机制，v1.5 再加
- 不做查询分解，v2 再加
- 不做图记忆，v3 再加
