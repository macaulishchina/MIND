# 模板使用说明

这份文档帮助开发者理解 `.ai/templates/` 与
`.ai/verification/templates/` 中各模板的用途。

## 1. `proposal.md`

用途：

- 定义这次 change 的目标、边界、影响和验证计划

开发者需要重点写清：

- Change ID、类型、状态
- 是否有 spec impact
- 使用哪个 verification profile
- In Scope / Out Of Scope
- 验收信号
- 还有哪些开放问题

## 2. `spec.md`

这个模板有两种用法：

- 在 `.ai/specs/` 中写 current truth
- 在 `.ai/changes/<change-id>/specs/` 中写 spec delta

写 current truth 时：

- 用 `Requirement` 和 `Scenario` 表达当前规则

写 spec delta 时：

- 用 `ADDED / MODIFIED / REMOVED Requirements`
- 如果是 `MODIFIED`，要写完整的新 requirement，而不是只写差异描述

## 3. `tasks.md`

用途：

- 在 proposal 获批后，把实现工作变成可执行的步骤列表

注意：

- proposal 未批准前，不要把它当成最终实现计划
- tasks 中要包含验证步骤
- 如果 `.ai/` 有开发者规则变更，closeout 要包含 `.human/` 更新

## 4. `design.md`

用途：

- 为复杂技术决策提供稳定说明

适用场景：

- 跨模块方案选择
- 有明显 tradeoff
- 需要记录被放弃方案与风险

## 5. `verification-report.md`

用途：

- 记录本次 change 的验证 profile、各 check 结果、证据和残余风险

开发者至少要写清：

- 这次用的 profile
- 每个关键 check 的结果
- 证据是什么
- 如果有未完成的验证，为什么可以接受
