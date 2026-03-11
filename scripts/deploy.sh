#!/bin/sh
# ============================================================
# scripts/deploy.sh — 一键生产部署
# ============================================================
# 用法:
#   ./scripts/deploy.sh            交互式后台部署 (需确认)
#   ./scripts/deploy.sh --attach   交互式前台部署 (需确认)
#   ./scripts/deploy.sh -y         跳过确认直接后台部署
#   ./scripts/deploy.sh --down     关闭生产环境
#   ./scripts/deploy.sh --status   查看服务状态
#   ./scripts/deploy.sh --help     显示帮助
set -eu

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
PROJECT_NAME="mind-prod"
OVERLAY_FILE="compose.prod.yaml"
DOCS_FILE="compose.docs.yaml"
ENV_TEMPLATE=".env.prod"
LOCAL_ENV_FILE=".env.prod.local"
ENV_FILE=""

# ---- 颜色输出 ----
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color
IS_TTY_STDOUT=0

if [ -t 1 ]; then
    IS_TTY_STDOUT=1
fi

info()  { printf "${GREEN}[DEPLOY]${NC} %s\n" "$1"; }
warn()  { printf "${YELLOW}[DEPLOY]${NC} %s\n" "$1"; }
error() { printf "${RED}[DEPLOY]${NC} %s\n" "$1" >&2; }

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

supports_hyperlinks() {
    if [ "${MIND_PLAIN_URLS:-0}" = "1" ] || [ "$IS_TTY_STDOUT" != "1" ] || [ "${TERM:-}" = "dumb" ]; then
        return 1
    fi

    if [ -n "${FORCE_HYPERLINKS:-}" ] \
        || [ -n "${WT_SESSION:-}" ] \
        || [ -n "${WEZTERM_PANE:-}" ] \
        || [ -n "${KITTY_WINDOW_ID:-}" ] \
        || [ -n "${VTE_VERSION:-}" ]; then
        return 0
    fi

    case "${TERM_PROGRAM:-}" in
        iTerm.app|WezTerm|vscode|ghostty|Hyper)
            return 0
            ;;
    esac

    return 1
}

format_link() {
    url="$1"
    if supports_hyperlinks; then
        printf '\033]8;;%s\007%s\033]8;;\007' "$url" "$url"
    else
        printf '%s' "$url"
    fi
}

show_help() {
    cat <<EOF
MIND 生产部署脚本

用法: ./scripts/deploy.sh [选项]

选项:
  (无参数)      交互式后台部署 (需确认)
  --attach      交互式前台部署 (attach 模式)
  -y            跳过确认直接后台部署
  --down        关闭生产环境
  --status      显示服务状态
  --logs        查看最近 100 行日志
  --help        显示此帮助信息

运行时环境文件:
  模板: ${ENV_TEMPLATE}
  本地: ${LOCAL_ENV_FILE}

配置:
  compose project: ${PROJECT_NAME}
  日志级别: WARNING
  MIND 1860x 端口族: API 18600 / 文档 18601 / DB 18605
  项目页面: 默认 $(format_link "http://127.0.0.1:18600/frontend/")
  静态文档: 默认 $(format_link "http://127.0.0.1:18601")
  资源限制: 已配置 (CPU/内存)
  后台运行: 是 (detached mode)
EOF
}

check_deps() {
    for cmd in docker curl; do
        if ! command -v "$cmd" >/dev/null 2>&1; then
            error "未找到 $cmd，请先安装"
            exit 1
        fi
    done
    if ! docker compose version >/dev/null 2>&1; then
        error "未找到 docker compose 插件，请安装 Docker Compose V2"
        exit 1
    fi
}

check_uv() {
    if ! command -v uv >/dev/null 2>&1; then
        error "未找到 uv，请先安装"
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

validate_env() {
    env_path="$PROJECT_ROOT/$ENV_FILE"

    if grep -q "CHANGE_ME" "$env_path" 2>/dev/null; then
        error "${ENV_FILE} 中仍有 CHANGE_ME 占位符，请先修改配置"
        exit 1
    fi

    bind="$(read_env_value "MIND_API_BIND" "$env_path")"
    postgres_password="$(read_env_value "MIND_POSTGRES_PASSWORD" "$env_path")"
    postgres_dsn="$(read_env_value "MIND_POSTGRES_DSN" "$env_path")"
    dsn_password_value="$(dsn_password "$postgres_dsn")"
    if [ -n "$bind" ] && [ "$bind" != "0.0.0.0:18600" ]; then
        error "compose 生产环境当前仅支持 MIND_API_BIND=0.0.0.0:18600 (当前: $bind)"
        exit 1
    fi

    if [ -z "$postgres_password" ] || [ -z "$dsn_password_value" ] || [ "$postgres_password" != "$dsn_password_value" ]; then
        error "MIND_POSTGRES_PASSWORD 必须与 MIND_POSTGRES_DSN 中的密码保持一致"
        exit 1
    fi

    dev_mode="$(read_env_value "MIND_DEV_MODE" "$env_path")"
    if [ "$dev_mode" != "false" ]; then
        error "生产环境必须设置 MIND_DEV_MODE=false"
        exit 1
    fi
}

ensure_env() {
    if [ ! -f "$PROJECT_ROOT/$LOCAL_ENV_FILE" ]; then
        warn "未找到 ${LOCAL_ENV_FILE}，从 ${ENV_TEMPLATE} 复制..."
        cp "$PROJECT_ROOT/$ENV_TEMPLATE" "$PROJECT_ROOT/$LOCAL_ENV_FILE"
        warn "⚠️  请编辑 ${LOCAL_ENV_FILE}，修改以下必填项:"
        warn "  - MIND_POSTGRES_PASSWORD"
        warn "  - MIND_POSTGRES_DSN"
        warn "  - MIND_API_KEY"
        error "请编辑 ${LOCAL_ENV_FILE} 后重新运行此脚本"
        exit 1
    fi

    ENV_FILE="$LOCAL_ENV_FILE"
    validate_env
}

compose() {
    MIND_ENV_FILE="$ENV_FILE" docker compose \
        --project-name "$PROJECT_NAME" \
        --env-file "$ENV_FILE" \
        -f compose.yaml \
        -f "$OVERLAY_FILE" \
        -f "$DOCS_FILE" \
        "$@"
}

docs_url() {
    docs_bind="$(read_env_value "MIND_DOCS_BIND" "$PROJECT_ROOT/$ENV_FILE")"
    printf 'http://127.0.0.1:%s/\n' "$(bind_port "$docs_bind" 18601)"
}

api_url() {
    api_bind="$(read_env_value "MIND_API_BIND" "$PROJECT_ROOT/$ENV_FILE")"
    printf 'http://127.0.0.1:%s\n' "$(bind_port "$api_bind" 18600)"
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

frontend_url() {
    printf '%s/frontend/\n' "$(api_url)"
}

build_docs_site() {
    check_uv
    info "构建静态文档站..."
    uv run mkdocs build --strict >/dev/null
    info "静态文档站构建完成"
}

confirm_deploy() {
    if [ "${1:-}" = "-y" ]; then
        return 0
    fi
    printf "${YELLOW}[DEPLOY]${NC} 即将部署到生产环境，确认继续? [y/N] "
    read -r answer
    case "$answer" in
        [yY]|[yY][eE][sS]) return 0 ;;
        *) info "部署取消"; exit 0 ;;
    esac
}

smoke_check() {
    info "执行部署验收检查..."
    api_key="$(read_env_value "MIND_API_KEY" "$PROJECT_ROOT/$ENV_FILE")"
    max_wait=90
    elapsed=0

    while [ "$elapsed" -lt "$max_wait" ]; do
        if curl -sf -H "X-API-Key: $api_key" "$(api_health_url)" >/dev/null 2>&1; then
            if curl -sf "$(docs_url)" >/dev/null 2>&1; then
                info "health 检查通过"
                info "docs 检查通过"

                if curl -sf -H "X-API-Key: $api_key" "$(api_readiness_url)" >/dev/null 2>&1; then
                    info "readiness 检查通过"
                else
                    warn "readiness 检查未通过 (服务可能仍在初始化)"
                fi
                return 0
            fi
        fi
        sleep 3
        elapsed=$((elapsed + 3))
        printf "."
    done
    echo ""
    error "部署验收检查超时，请检查日志: ./scripts/deploy.sh --logs"
    return 1
}

show_detached_summary() {
    echo ""
    info "========================================="
    info "  部署完成"
    info "  API:      $(format_link "$(api_url)")"
    info "  项目页面: $(format_link "$(frontend_url)")"
    info "  API 文档: $(format_link "$(api_docs_url)")"
    info "  健康:     $(format_link "$(api_health_url)")"
    info "  就绪:     $(format_link "$(api_readiness_url)")"
    info "  项目文档: $(format_link "$(docs_url)")"
    info "  日志:     ./scripts/deploy.sh --logs"
    info "  状态:     ./scripts/deploy.sh --status"
    info "========================================="
}

ACTION="up"
ATTACH_MODE=false
AUTO_APPROVE=false

while [ "$#" -gt 0 ]; do
    case "$1" in
        --help|-h)
            show_help
            exit 0
            ;;
        --down|--status|--logs)
            if [ "$ACTION" != "up" ] || [ "$ATTACH_MODE" = true ] || [ "$AUTO_APPROVE" = true ]; then
                error "选项组合无效: $1"
                exit 1
            fi
            ACTION="$1"
            ;;
        --attach)
            if [ "$ACTION" != "up" ]; then
                error "--attach 只能和部署模式一起使用"
                exit 1
            fi
            ATTACH_MODE=true
            ;;
        -y)
            if [ "$ACTION" != "up" ]; then
                error "-y 只能和部署模式一起使用"
                exit 1
            fi
            AUTO_APPROVE=true
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
        info "关闭生产环境..."
        compose down
        info "生产环境已关闭"
        exit 0
        ;;
    --status)
        ENV_FILE="$(resolve_env_file)"
        compose ps
        exit 0
        ;;
    --logs)
        ENV_FILE="$(resolve_env_file)"
        compose logs --tail=100
        exit 0
        ;;
    up)
        ensure_env
        if [ "$AUTO_APPROVE" = true ]; then
            confirm_deploy "-y"
        else
            confirm_deploy ""
        fi
        build_docs_site
        if [ "$ATTACH_MODE" = true ]; then
            info "以前台模式部署生产环境..."
            compose up --build
        else
            info "在后台部署生产环境..."
            compose up --build -d
            info "容器已在后台启动，等待服务就绪..."
            smoke_check
            show_detached_summary
        fi
        ;;
esac
