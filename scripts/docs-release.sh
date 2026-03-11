#!/bin/sh
# ============================================================
# scripts/docs-release.sh — 静态文档站构建与发布
# ============================================================
set -eu

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
PROJECT_NAME="mind-docs"
COMPOSE_FILE="compose.docs.yaml"
DOCS_BIND="${DOCS_BIND:-0.0.0.0:8004}"
ARTIFACT_DIR="$PROJECT_ROOT/artifacts/docs-release"

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

info()  { printf "${GREEN}[DOCS]${NC} %s\n" "$1"; }
warn()  { printf "${YELLOW}[DOCS]${NC} %s\n" "$1"; }
error() { printf "${RED}[DOCS]${NC} %s\n" "$1" >&2; }

bind_port() {
    bind="$1"
    default_port="$2"
    port="$(printf '%s\n' "$bind" | sed -n 's#^[^:]*:\([0-9][0-9]*\)$#\1#p')"
    if [ -n "$port" ]; then
        printf '%s\n' "$port"
    else
        printf '%s\n' "$default_port"
    fi
}

docs_url() {
    printf 'http://127.0.0.1:%s\n' "$(bind_port "$DOCS_BIND" 8004)"
}

show_help() {
    cat <<EOF
MIND 静态文档站构建与发布脚本

用法: ./scripts/docs-release.sh <命令>

命令:
  build           本地严格构建静态站到 site/
  package         构建并打包站点到 artifacts/docs-release/
  publish-local   以容器方式发布静态站到本机
  --status        查看本地文档服务状态
  --logs          查看本地文档服务日志
  --down          关闭本地文档服务
  --help          显示此帮助信息

本地文档服务:
  compose project: ${PROJECT_NAME}
  Host bind: ${DOCS_BIND}
  URL: $(docs_url)
EOF
}

check_uv() {
    if ! command -v uv >/dev/null 2>&1; then
        error "未找到 uv，请先安装"
        exit 1
    fi
}

check_docker() {
    if ! command -v docker >/dev/null 2>&1; then
        error "未找到 docker，请先安装"
        exit 1
    fi
    if ! docker compose version >/dev/null 2>&1; then
        error "未找到 docker compose 插件，请安装 Docker Compose V2"
        exit 1
    fi
}

compose() {
    MIND_DOCS_BIND="$DOCS_BIND" docker compose \
        --project-name "$PROJECT_NAME" \
        -f "$COMPOSE_FILE" \
        "$@"
}

build_site() {
    check_uv
    cd "$PROJECT_ROOT"
    info "严格构建静态站..."
    uv run mkdocs build --strict
    info "静态站已生成: site/"
}

package_site() {
    build_site
    mkdir -p "$ARTIFACT_DIR"
    archive="$ARTIFACT_DIR/mind-docs-site-$(date -u +%Y%m%dT%H%M%SZ).tar.gz"
    tar -czf "$archive" -C "$PROJECT_ROOT/site" .
    info "站点归档已生成: $archive"
}

publish_local() {
    build_site
    check_docker
    cd "$PROJECT_ROOT"
    info "构建并发布本地静态文档服务..."
    compose up --build -d
    info "本地文档服务已启动: $(docs_url)"
}

cd "$PROJECT_ROOT"

case "${1:-}" in
    build)
        build_site
        ;;
    package)
        package_site
        ;;
    publish-local)
        publish_local
        ;;
    --status)
        check_docker
        compose ps
        ;;
    --logs)
        check_docker
        compose logs --tail=100
        ;;
    --down)
        check_docker
        info "关闭本地文档服务..."
        compose down
        info "本地文档服务已关闭"
        ;;
    --help|-h|"")
        show_help
        ;;
    *)
        error "未知命令: $1"
        show_help
        exit 1
        ;;
esac
