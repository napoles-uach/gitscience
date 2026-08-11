#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
TARGET="${1:-/tmp/gitscience-product-validation}"
OUTPUT="${2:-$TARGET/report.json}"

if [[ -e "$TARGET" ]]; then
  printf 'error: target already exists: %s\n' "$TARGET" >&2
  printf 'choose a new path as the first argument\n' >&2
  exit 1
fi

mkdir -p "$TARGET"
"$REPO_DIR/examples/twisted-ribbon/run-formal-demo.sh" "$TARGET/twisted-ribbon"
"$REPO_DIR/examples/quantum-fmm/run-demo.sh" "$TARGET/quantum-fmm"

python "$SCRIPT_DIR/validate_case_studies.py" \
  --twisted-repo "$TARGET/twisted-ribbon" \
  --fmm-repo "$TARGET/quantum-fmm" \
  --output "$OUTPUT"

printf '\nValidation report: %s\n' "$OUTPUT"
