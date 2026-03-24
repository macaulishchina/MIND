# 规格与变更工件

这份文档解释 `.ai/` 里不同类型工件各自承担什么职责。

## 1. Living Specs

位置：`.ai/specs/`

用途：

- 这里存放当前已经批准、正在生效的规格事实
- 一项 capability 对应一个子目录，文件名保持为 `spec.md`
- 这里不放草稿、提案、任务列表或临时讨论

## 2. Active Changes

位置：`.ai/changes/<change-id>/`

用途：

- 每个 change 文件夹只处理一个业务目标
- 它是 proposal、spec delta、tasks、design、verification report 的工作区

命名要求：

- 使用简短的 kebab-case，例如 `add-profile-filters`

## 3. 一个 change 中的必需工件

- `proposal.md`
  任何非小改动都必须先有 proposal
- `tasks.md`
  只有在 proposal 获批后才最终化
- `verification-report.md`
  在 archive 前必须完成

## 4. 条件性工件

- `design.md`
  当技术决策需要长期说明时才创建
- `specs/<capability>/spec.md`
  当 change 影响行为、接口、校验或验收标准时必须存在

## 5. Archive

位置：`.ai/archive/`

用途：

- 保存已经完成的 change 历史
- 只有实现完成、验证完成、living specs 已更新后，change 才能 archive

## 6. Source Of Truth 与 Spec Delta 的区别

- `.ai/specs/<capability>/spec.md`
  写的是当前已经成立的事实
- `.ai/changes/<change-id>/specs/<capability>/spec.md`
  写的是这次 change 想引入的规格变化

不要在草拟阶段直接修改 `.ai/specs/`，否则会把“提议”伪装成“现状”。
