# 历史资料与证据

产品文档站默认只构建当前稳定使用面，不直接把全部历史阶段材料纳入导航。

## 为什么

原因很简单：

- 旧阶段文档大量引用仓库源码、测试、脚本和产物路径
- 这些链接对仓库阅读有价值，但不适合作为站点内可解析链接
- 如果直接纳入 `mkdocs build --strict`，会把历史材料中的仓库链接都当成 broken links

## 资料仍然保留在哪里

历史资料没有删除，仍然在仓库里：

- `docs/foundation/`
- `docs/design/`
- `docs/reports/`
- `docs/research/`

重点文件包括：

- `docs/design/productization_program.md`
- `docs/foundation/spec.md`
- `docs/foundation/phase_gates.md`
- `docs/reports/productization_audit_report.md`

## 使用建议

- 要用产品：优先看 Product / Reference / Operations / Architecture
- 要追设计来源：回到仓库里的 foundation / design
- 要看审计和验收证据：回到仓库里的 reports

这样处理可以同时保证两件事：

1. 站点能严格构建
2. 历史资料继续保留为工程证据
