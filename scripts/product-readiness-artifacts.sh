#!/bin/sh
set -eu

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
OUTPUT_DIR="$PROJECT_ROOT/artifacts/product"

info() {
    printf '[PRODUCT-ARTIFACTS] %s\n' "$1"
}

error() {
    printf '[PRODUCT-ARTIFACTS] %s\n' "$1" >&2
}

show_help() {
    cat <<EOF
Generate the full product-readiness artifact bundle.

Usage: ./scripts/product-readiness-artifacts.sh [--output-dir DIR]

Artifacts:
  transport_audit_report.json / .md
  deployment_smoke_report.json / .md
  product_readiness_report.json / .md
  product_readiness_gate.json / .md
EOF
}

check_uv() {
    if ! command -v uv >/dev/null 2>&1; then
        error "uv is required to generate product-readiness artifacts"
        exit 1
    fi
}

run_mindtest() {
    if command -v mindtest >/dev/null 2>&1; then
        mindtest "$@"
        return
    fi
    check_uv
    uv run mindtest "$@"
}

while [ "$#" -gt 0 ]; do
    case "$1" in
        --output-dir)
            shift
            if [ "$#" -eq 0 ]; then
                error "--output-dir requires a value"
                exit 1
            fi
            OUTPUT_DIR="$1"
            ;;
        --help|-h)
            show_help
            exit 0
            ;;
        *)
            error "unknown option: $1"
            show_help
            exit 1
            ;;
    esac
    shift
done

mkdir -p "$OUTPUT_DIR"
cd "$PROJECT_ROOT"

info "Generating product transport audit artifacts..."
run_mindtest report product-transport \
    --output "$OUTPUT_DIR/transport_audit_report.json" \
    --markdown-output "$OUTPUT_DIR/transport_audit_report.md"

info "Generating deployment smoke artifacts..."
run_mindtest report deployment-smoke \
    --output "$OUTPUT_DIR/deployment_smoke_report.json" \
    --markdown-output "$OUTPUT_DIR/deployment_smoke_report.md"

info "Generating product readiness report artifacts..."
run_mindtest report product-readiness \
    --output "$OUTPUT_DIR/product_readiness_report.json" \
    --markdown-output "$OUTPUT_DIR/product_readiness_report.md"

info "Generating product readiness gate artifacts..."
run_mindtest gate product-readiness \
    --output "$OUTPUT_DIR/product_readiness_gate.json" \
    --markdown-output "$OUTPUT_DIR/product_readiness_gate.md"

info "Product artifact bundle ready in $OUTPUT_DIR"
