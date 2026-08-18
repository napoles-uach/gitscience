#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET="${1:-/tmp/gitscience-quantum-fmm-demo}"

if [[ -e "$TARGET" ]]; then
  printf 'error: target already exists: %s\n' "$TARGET" >&2
  printf 'choose a new path as the first argument\n' >&2
  exit 1
fi

gitscience init "$TARGET" --name quantum-fmm-occupancy-study
git -C "$TARGET" config user.name "GitScience Demo"
git -C "$TARGET" config user.email "demo@gitscience.local"

gitscience -C "$TARGET" topic create \
  "Occupancy-controlled quantum fast multipole methods" --code QF
gitscience -C "$TARGET" model create quantum-fmm-occupancy-v1 \
  --from "$SCRIPT_DIR/model.yaml"
gitscience -C "$TARGET" study create quantum-fmm \
  --from "$SCRIPT_DIR/study.yaml"

messages=(
  "Define quantum-FMM occupancy model"
  "Declare restricted FMM error assumption"
  "State abstract error accumulation lemma"
  "State RDM occupancy-tail lemma"
  "Derive conditional FMM error bound"
  "Declare independent occupancy diagnostic"
  "Compare finite occupancy regimes"
  "Record dynamic occupancy conjecture"
  "Record spin-sector scope obligation"
)

index=0
for source in "$SCRIPT_DIR"/formal-graph/*.yaml; do
  gitscience -C "$TARGET" claim create --from "$source"
  gitscience -C "$TARGET" commit -m "${messages[$index]}"
  index=$((index + 1))
done

gitscience -C "$TARGET" formal create GS-QF-0003 \
  --from "$SCRIPT_DIR/formalization-error-accumulation.yaml"
gitscience -C "$TARGET" commit -m "Propose formal accumulation obligation"
gitscience -C "$TARGET" formal approve FM-000001
gitscience -C "$TARGET" commit -m "Approve formal accumulation semantics"
gitscience -C "$TARGET" formal verify FM-000001 --commit-evidence
gitscience -C "$TARGET" verify GS-QF-0007
gitscience -C "$TARGET" claim graph
gitscience -C "$TARGET" claim obligations
gitscience -C "$TARGET" audit

printf '\nDemo repository: %s\n' "$TARGET"
