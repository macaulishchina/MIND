#!/bin/sh
# ============================================================
# scripts/dev.sh — 一键搭建开发环境
# ============================================================
# 用法:
#   ./scripts/dev.sh              后台启动开发环境
#   ./scripts/dev.sh --attach     前台启动开发环境
#   ./scripts/dev.sh --rebuild    强制重建镜像并后台启动
#   ./scripts/dev.sh --down       关闭开发环境
#   ./scripts/dev.sh --logs       查看日志 (跟踪模式)
#   ./scripts/dev.sh --help       显示帮助
set -eu

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
PROJECT_NAME="mind-dev"
OVERLAY_FILE="compose.dev.yaml"
ENV_TEMPLATE=".env.dev"
LOCAL_ENV_FILE=".env.dev.local"
ENV_FILE=""

# ---- 颜色输出 ----
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

info()  { printf "${GREEN}[DEV]${NC} %s\n" "$1"; }
warn()  { printf "${YELLOW}[DEV]${NC} %s\n" "$1"; }
error() { printf "${RED}[DEV]${NC} %s\n" "$1" >&2; }

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

show_help() {
    cat <<EOF
MIND 开发环境管理脚本

用法: ./scripts/dev.sh [选项]

选项:
  (无参数)      后台启动开发环境 (增量构建)
  --attach      前台启动开发环境 (attach 模式)
  --rebuild     强制重建镜像并后台启动
  --down        关闭开发环境并清理容器
  --logs        跟踪查看所有服务日志
  --status      显示服务状态
  --help        显示此帮助信息

运行时环境文件:
  模板: ${ENV_TEMPLATE}
  本地: ${LOCAL_ENV_FILE}

特性:
  - 独立 compose project: ${PROJECT_NAME}
  - 源码热更新: 本地修改 mind/ 目录即时生效
  - 文档热更新: MkDocs dev server 随开发环境一起启动
  - DEBUG 日志级别
  - 远程调试端口: 5678 (debugpy)
  - Worker 轮询间隔: 3s

开发环境地址:
  API:      http://127.0.0.1:8000
  API 文档: http://127.0.0.1:8000/docs
  健康:     http://127.0.0.1:8000/v1/system/health
  就绪:     http://127.0.0.1:8000/v1/system/readiness
  项目文档: http://127.0.0.1:8002/

可选的独立文档预览:
  uv sync --extra docs
  uv run mkdocs serve --livereload -a 0.0.0.0:8003
  打开: http://127.0.0.1:8003
EOF
}

check_deps() {
    if ! command -v docker >/dev/null 2>&1; then
        error "未找到 docker，请先安装"
        exit 1
    fi
    if ! docker compose version >/dev/null 2>&1; then
        error "未找到 docker compose 插件，请安装 Docker Compose V2"
        exit 1
    fi
}

resolve_env_file() {
    if [ -f "$PROJECT_ROOT/$LOCAL_ENV_FILE" ]; then
        printf '%s\n' "$LOCAL_ENV_FILE"
    else
        printf '%s\n' "$ENV_TEMPLATE"
    fi
}

read_env_value() {
    key="$1"
    file="$2"
    sed -n "s/^${key}=//p" "$file" | tail -n 1
}

dsn_password() {
    dsn="$1"
    printf '%s\n' "$dsn" | sed -n 's#^[^:]*://[^:]*:\([^@]*\)@.*#\1#p'
}

api_url() {
    api_bind="$(read_env_value "MIND_API_BIND" "$PROJECT_ROOT/$ENV_FILE")"
    printf 'http://127.0.0.1:%s\n' "$(bind_port "$api_bind" 8000)"
}

api_docs_url() {
    printf '%s/docs\n' "$(api_url)"
}

api_health_url() {
    printf '%s/v1/system/health\n' "$(api_url)"
}

api_readiness_url() {
    printf '%s/v1/system/readiness\n' "$(api_url)"
}

docs_url() {
    docs_bind="$(read_env_value "MIND_DOCS_BIND" "$PROJECT_ROOT/$ENV_FILE")"
    printf 'http://127.0.0.1:%s/\n' "$(bind_port "$docs_bind" 8002)"
}

validate_env() {
    bind="$(read_env_value "MIND_API_BIND" "$PROJECT_ROOT/$ENV_FILE")"
    postgres_password="$(read_env_value "MIND_POSTGRES_PASSWORD" "$PROJECT_ROOT/$ENV_FILE")"
    postgres_dsn="$(read_env_value "MIND_POSTGRES_DSN" "$PROJECT_ROOT/$ENV_FILE")"
    dsn_password_value="$(dsn_password "$postgres_dsn")"

    if [ -n "$bind" ] && [ "$bind" != "0.0.0.0:8000" ]; then
        error "compose 开发环境当前仅支持 MIND_API_BIND=0.0.0.0:8000 (当前: $bind)"
        exit 1
    fi
    if [ -n "$postgres_password" ] && [ -n "$dsn_password_value" ] && [ "$postgres_password" != "$dsn_password_value" ]; then
        error "MIND_POSTGRES_PASSWORD 必须与 MIND_POSTGRES_DSN 中的密码保持一致"
        exit 1
    fi
}

ensure_env() {
    if [ ! -f "$PROJECT_ROOT/$LOCAL_ENV_FILE" ]; then
        info "未找到 ${LOCAL_ENV_FILE}，从 ${ENV_TEMPLATE} 复制..."
        cp "$PROJECT_ROOT/$ENV_TEMPLATE" "$PROJECT_ROOT/$LOCAL_ENV_FILE"
        info "${LOCAL_ENV_FILE} 已创建，使用开发默认配置"
    fi
    ENV_FILE="$LOCAL_ENV_FILE"
}

compose() {
    MIND_ENV_FILE="$ENV_FILE" docker compose \
        --project-name "$PROJECT_NAME" \
        --env-file "$ENV_FILE" \
        -f compose.yaml \
        -f "$OVERLAY_FILE" \
        "$@"
}

show_detached_summary() {
    echo ""
    info "========================================="
    info "  开发环境已在后台启动"
    info "  API:      $(api_url)"
    info "  API 文档: $(api_docs_url)"
    info "  健康:     $(api_health_url)"
    info "  就绪:     $(api_readiness_url)"
    info "  项目文档: $(docs_url)"
    info "  日志:     ./scripts/dev.sh --logs"
    info "  状态:     ./scripts/dev.sh --status"
    info "========================================="
}

ACTION="up"
ATTACH_MODE=false
REBUILD_MODE=false

while [ "$#" -gt 0 ]; do
    case "$1" in
        --help|-h)
            show_help
            exit 0
            ;;
        --down|--logs|--status)
            if [ "$ACTION" != "up" ] || [ "$ATTACH_MODE" = true ] || [ "$REBUILD_MODE" = true ]; then
                error "选项组合无效: $1"
                exit 1
            fi
            ACTION="$1"
            ;;
        --attach)
            if [ "$ACTION" != "up" ]; then
                error "--attach 只能和启动模式一起使用"
                exit 1
            fi
            ATTACH_MODE=true
            ;;
        --rebuild)
            if [ "$ACTION" != "up" ]; then
                error "--rebuild 只能和启动模式一起使用"
                exit 1
            fi
            REBUILD_MODE=true
            ;;
        *)
            error "未知选项: $1"
            show_help
            exit 1
            ;;
    esac
    shift
done

cd "$PROJECT_ROOT"
check_deps

case "$ACTION" in
    --down)
        ENV_FILE="$(resolve_env_file)"
        info "关闭开发环境..."
        compose down
        info "开发环境已关闭"
        exit 0
        ;;
    --logs)
        ENV_FILE="$(resolve_env_file)"
        compose logs -f
        exit 0
        ;;
    --status)
        ENV_FILE="$(resolve_env_file)"
        compose ps
        exit 0
        ;;
    up)
        ensure_env
        validate_env
        if [ "$REBUILD_MODE" = true ]; then
            if [ "$ATTACH_MODE" = true ]; then
                info "强制重建镜像并以前台模式启动开发环境..."
                compose up --build --force-recreate
            else
                info "强制重建镜像并在后台启动开发环境..."
                compose up --build --force-recreate -d
                show_detached_summary
            fi
        else
            if [ "$ATTACH_MODE" = true ]; then
                info "以前台模式启动开发环境 (增量构建)..."
                compose up --build
            else
                info "在后台启动开发环境 (增量构建)..."
                compose up --build -d
                show_detached_summary
            fi
        fi
        ;;
esac
