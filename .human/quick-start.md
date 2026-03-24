# 快速开始

这份文档面向第一次接手这个仓库的开发者。
目标不是讲全，而是让你在几分钟内知道应该从哪里开始、先做什么、哪些事情不能做错。

## 先记住这 4 件事

1. 真正的工作区在 `.ai/`，不是 `.human/`
2. 只有小改动才能跳过完整 change workflow
3. proposal 获批前，不要把 `tasks.md` 当成最终实现计划
4. 如果方向本身可疑、冲突或不可行，先质疑，不要急着实现

## 第一次进入仓库时的最短路径

1. 先读 `.human/context.md`
   了解边界、小改动判断和术语
2. 再读 `.human/workflow.md`
   理解 change 从 proposal、reality check 到 archive 的完整路径
3. 如果你马上要开始动手，再看 `.human/artifacts.md`
   知道 proposal、spec delta、tasks、verification-report 各自放在哪
4. 如果你不确定这次要怎么验，读 `.human/verification.md`
5. 如果你准备真正创建文档，再读 `.human/templates.md`

## 真正开始做一个非小改动时

你最终还是要回到 `.ai/` 里操作，最常见的起点是：

- `.ai/project.md`
  用来判断这是不是小改动
- `.ai/changes/<change-id>/proposal.md`
  非小改动的第一份工件
- `.ai/verification/policy.md`
  选择 verification profile

## 一个最小可行的 change 路径

1. 判断不是小改动
2. 建立 `.ai/changes/<change-id>/`
3. 写 `proposal.md`
4. 先做 reality check，看方向是不是错的、冲突的、或难以实现
5. 如果行为或验收标准变了，补 spec delta
6. 选择 verification profile
7. 等 proposal 获批
8. 最终化 `tasks.md`
9. 实现并写 `verification-report.md`
10. 把接受后的规格并回 `.ai/specs/`
11. 必要时同步 `.human/`
12. 再 archive

## 最容易犯错的地方

- 把 `.human/` 当成真实工件目录
- proposal 还没批准就直接按 tasks 开干
- 明明方向已经显示出冲突或不可行，还硬着头皮继续实现
- 还在讨论中的 spec 直接写进 `.ai/specs/`
- 完成 `.ai/` 改动后忘了看 `.human/` 是否也要更新
- 没有 verification report 就想 archive

## 不确定时怎么保守处理

- 不确定是不是小改动：按非小改动处理
- 不确定方向是不是对的：先做 reality check，再决定要不要继续
- 不确定用哪个 verification profile：选更强的
- 不确定某条 `.ai/` 变化要不要同步到 `.human/`：先同步，再视情况收敛
- 不确定某个 spec 是 current truth 还是 proposal：放进 change folder，不要直接改 living specs
