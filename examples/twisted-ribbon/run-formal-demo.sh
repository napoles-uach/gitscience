#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET="${1:-/tmp/gitscience-twisted-ribbon-demo}"

if [[ -e "$TARGET" ]]; then
  printf 'error: target already exists: %s\n' "$TARGET" >&2
  printf 'choose a new path as the first argument\n' >&2
  exit 1
fi

gitscience init "$TARGET" --name twisted-ribbon-formal-demo
git -C "$TARGET" config user.name "GitScience Demo"
git -C "$TARGET" config user.email "demo@gitscience.local"

gitscience -C "$TARGET" topic create \
  "Quantum transport in twisted ribbons" --code QT
gitscience -C "$TARGET" model create helicoidal-ribbon-v1 \
  --from "$SCRIPT_DIR/model.yaml"

messages=(
  "Define transport model"
  "Declare covariance assumption"
  "State conditional transport lemma"
  "Derive model corollary"
  "Propose numerical reference point"
)

index=0
for source in "$SCRIPT_DIR"/formal-graph/*.yaml; do
  gitscience -C "$TARGET" claim create --from "$source"
  gitscience -C "$TARGET" commit -m "${messages[$index]}"
  index=$((index + 1))
done

gitscience -C "$TARGET" verify GS-QT-0003
gitscience -C "$TARGET" verify GS-QT-0005
gitscience -C "$TARGET" claim graph
gitscience -C "$TARGET" claim obligations
gitscience -C "$TARGET" audit

printf '\nDemo repository: %s\n' "$TARGET"
