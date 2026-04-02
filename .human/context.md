# 项目与边界

这份文档解释当前仓库的长期背景、工作边界和术语。

## 当前状态

- 仓库已经不只是 workflow 脚手架，而是包含可运行的 Python 记忆系统实现
- 当前已有稳定事实写入 `.ai/specs/`，覆盖 owner-centered memory、STL 语法与评测、runtime logging 等能力
- 日常回归基线是 `pytest tests/`，更细的阶段级验证和提示词/模型评测位于 `tests/eval/`
- 在线 STL 抽取默认策略已经独立于全局 LLM 默认值维护，不应假设所有阶段天然共用同一模型

## 工作边界

- 每次改动都要围绕明确目标展开
- 不要把功能开发、重构和无关清理混在同一个 change 中
- 能写入仓库的上下文，不要只留在聊天记录里
- 不要把项目规划、需求草稿或临时产品方向直接写进 `.ai/` 或 `.human/`
  的 workflow 文档，除非它们正在被正式固化为 approved spec 或 change 工件
- 发现工作流文档过期时，应尽快修正
- 当一个方向很可能有冲突、不可行、或者本身就不对时，AI 不应该机械执行，
  而应该先提出质疑、指出问题，并给出更好的方向

## 什么算小改动

只有同时满足下面条件，才能跳过完整 change workflow：

- 只影响一个很窄的局部行为或局部文案
- 不需要额外审批
- 不改变公开行为、接口或验收标准
- 可以用一次很短的验证完成确认

只要不满足以上任一条件，就应该进入 `.ai/changes/<change-id>/`
的完整工作流。

## 默认工作原则

- 当前事实只写在 `.ai/specs/`
- 提议中的工作只写在 `.ai/changes/`
- 在 change 被接受之前，不要直接改写 `.ai/specs/`
- 在 proposal 获批前，要先完成现实性检查：看方向是否冲突、是否可行、
  是否有更好的替代方案
- proposal 获批是进入实现前唯一的硬门槛
- `design.md` 只在确实需要稳定技术决策说明时创建
- 每个非小改动都要选择一个 verification profile

## 术语速查

- `capability`：一个相对完整的能力域
- `source of truth`：当前已批准的规格事实
- `change`：一次提议中或进行中的工作单元
- `proposal`：说明“为什么要改、打算怎么改”的文档
- `reality check`：在实现前主动识别方向错误、实现冲突、不可行性和更优路径的检查
- `spec delta`：针对某次 change 的规格修改提议
- `verification profile`：这次 change 需要达到的验证强度
- `verification report`：记录这次验证证据和残余风险的文档
