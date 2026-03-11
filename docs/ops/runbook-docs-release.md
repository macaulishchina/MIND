# 文档发布 Runbook

## 目标

构建 MIND 的静态文档站，并支持两条发布路径：

- 本地构建与本地容器发布
- GitHub Actions 构建并发布到 GitHub Pages

## 本地构建

```bash
./scripts/docs-release.sh build
```

这会执行 `mkdocs build --strict`，并把静态站生成到 `site/`。

如果需要归档发布物：

```bash
./scripts/docs-release.sh package
```

归档文件会输出到 `artifacts/docs-release/`。

## 本地发布

```bash
./scripts/docs-release.sh publish-local
```

发布后访问：

- 文档首页：`http://127.0.0.1:18604`

常用管理命令：

```bash
./scripts/docs-release.sh --status
./scripts/docs-release.sh --logs
./scripts/docs-release.sh --down
```

## 应用部署中的文档站

生产部署脚本现在会一并构建并启动静态文档服务：

```bash
./scripts/deploy.sh
```

部署完成后：

- API：`http://127.0.0.1:18600`
- 文档：`http://127.0.0.1:18601`

开发环境里的热更新文档站由 `./scripts/dev.sh` 提供，默认地址是 `http://127.0.0.1:18602`，与这里的静态发布地址分离。

## GitHub 构建发布

仓库提供了 GitHub Pages workflow：

- 工作流文件：`.github/workflows/docs-pages.yml`
- 触发条件：
  - push 到 `main`
  - push tag `v*` / `docs-v*`
  - 手动 `workflow_dispatch`
  - pull request 仅构建校验，不执行发布

发布前提：

1. 仓库启用 GitHub Pages
2. Pages source 选择 `GitHub Actions`

工作流会执行：

1. 安装 Python + `uv`
2. `uv sync --extra docs --extra api --extra mcp`
3. `uv run mkdocs build --strict`
4. 上传 `site/` 为 Pages artifact
5. 发布到 GitHub Pages

## 失败时先看

- `uv sync --extra docs --extra api --extra mcp` 是否成功
- `mkdocs build --strict` 是否有 broken links 或 import 问题
- `Dockerfile.docs` 构建时是否能完成 `mkdocs build --strict`
- 仓库 Settings 中 GitHub Pages 是否设置为 `GitHub Actions`
- `./scripts/docs-release.sh publish-local` 后 `docs` 容器是否 healthy
