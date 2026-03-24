# 开发者手册

`.human/` 是给开发者阅读的中文手册。
它基于 `.ai/` 的 workflow 规则整理而成，但不会按 `.ai/` 的目录逐个镜像。

## 这份手册的定位

- `.ai/` 是工作流源规则和实际工件所在位置
- `.human/` 是更适合人类理解的中文说明层
- 两者必须语义一致，但不要求文件结构一一对应

## 推荐阅读顺序

1. [项目与边界](./context.md)
2. [开发流程](./workflow.md)
3. [规格与变更工件](./artifacts.md)
4. [验证体系](./verification.md)
5. [模板使用说明](./templates.md)

## 与 `.ai/` 的关系

- 当 `.ai/` 的开发者规则发生变化时，需要同步更新这份手册
- 如果 `.ai/` 和 `.human/` 出现冲突，应先修正文档，不要默认接受漂移
- `.human/` 的目的是帮助开发者快速理解，不替代 `.ai/` 中真实存在的工件位置

## 内容映射

- `.ai/README.md` + `.ai/project.md` -> `context.md` 与 `workflow.md`
- `.ai/specs/` + `.ai/changes/` + `.ai/archive/` -> `artifacts.md`
- `.ai/templates/` -> `templates.md`
- `.ai/verification/` -> `verification.md`
