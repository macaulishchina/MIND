# 验证体系

这份文档解释这套 workflow 如何定义“验证已经足够”。

## 核心思想

验证不是某个脚本名字，而是一套模型：

- `policy`：什么时候需要什么级别的验证
- `profiles`：一组可复用的验证档位
- `checks`：每个档位需要满足的验证目标
- `verification report`：实际记录证据的文档

即使仓库暂时没有自动化脚本，这套验证体系也能运行，因为人工验证也属于有效证据。

## Profile 怎么选

- `quick`
  用于仍需 change workflow、但风险较低且范围较小的改动
- `feature`
  用于新增能力或改变用户可见行为的改动
- `refactor`
  用于目标是“保持行为不变”的内部整理
- `full`
  用于高风险、跨能力或归档前需要强验证的改动

拿不准时，优先选更强的 profile。

## 常用 Checks

- `workflow-integrity`
  检查这次 change 是否按流程推进
- `change-completeness`
  检查 change 工件是否能独立说明这次改动
- `spec-consistency`
  检查 proposal、spec delta、tasks 之间是否一致
- `behavior-parity`
  检查 refactor 是否真的保持行为不变
- `manual-review`
  在没有自动化时的通用兜底检查
- `human-doc-sync`
  当 `.ai/` 改动影响开发者规则时，检查 `.human/` 是否也同步更新

## 证据规则

- 有自动化时，可以用命令结果作为证据
- 没有自动化时，可以用人工 walkthrough、评审记录、对比说明作为证据
- 跳过某个 check 时，必须写明原因和替代证据

## Archive 前的要求

对于任何非小改动，archive 之前都应具备：

- 已选择的 verification profile
- 已完成的 verification report
- 对残余风险的明确说明
- 如果 `.ai/` 有开发者规则更新，对 `.human/` 的同步处理
