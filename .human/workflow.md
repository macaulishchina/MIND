# 开发流程

这份文档描述开发者在这个仓库里应该怎样推进一项非小改动。

## 总原则

- 先澄清 change，再进入实现
- 先做现实性检查，再决定是不是值得推进这个方向
- 先写 proposal，再拆 tasks
- 先在 change 内提出 spec delta，再把批准后的结果并入 living specs
- 完成实现后再归档，而不是把 `.ai/changes/` 当长期历史仓库

## 标准流程

1. 判断这是不是小改动
2. 如果不是，在 `.ai/changes/<change-id>/` 下创建 change 工作区
3. 先写 `proposal.md`
4. 对初始方向做 reality check：识别错误假设、现有冲突、不可行性和更优替代
5. 如果行为、接口、验证标准会变化，补充 change-local spec delta
6. 选择 verification profile
7. 经过澄清与评审后，明确 proposal 已批准
8. 只有在 proposal 获批后，才最终化 `tasks.md`
9. 根据 tasks 实现变更
10. 完成验证并写 `verification-report.md`
11. 把被接受的规格更新并入 `.ai/specs/`
12. 如果 `.ai/` 的开发者规则变了，同步更新 `.human/`
13. 把整个 change 文件夹移入 `.ai/archive/`

## 审批门槛

- `proposal` 获批是唯一硬门槛
- “clarify” 是一个阶段，不强制单独建文件
- 如果 proposal 还没批准，就不应该把 tasks 当成最终实现计划

## 面向开发者的要求

- 不要把 `.human/` 当作真实工件存放位置
- 当 AI 对方向提出反对意见时，优先把它当成需要讨论的信号，
  而不是把它压回去要求继续做半成品
- 真正执行工作时，仍然要在 `.ai/changes/`、`.ai/specs/` 等目录操作
- `.human/` 的职责是帮助你更快理解流程，而不是替代 `.ai/`
