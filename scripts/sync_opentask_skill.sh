#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC_DIR="${1:-$ROOT_DIR/skills/opentask}"
DEST_DIR="${OPENTASK_SHARED_SKILL_DIR:-$HOME/clawd/skills/.opentask-skill}"
LINK_PATH="${OPENTASK_SHARED_SKILL_LINK:-$HOME/clawd/skills/opentask}"

if [[ ! -d "$SRC_DIR" ]]; then
  echo "source skill directory not found: $SRC_DIR" >&2
  exit 1
fi

mkdir -p "$DEST_DIR"
rsync -a --delete --exclude '.DS_Store' "$SRC_DIR"/ "$DEST_DIR"/

mkdir -p "$(dirname "$LINK_PATH")"
ln -sfn "$DEST_DIR" "$LINK_PATH"

echo "synced opentask skill:"
echo "  src : $SRC_DIR"
echo "  dest: $DEST_DIR"
echo "  link: $LINK_PATH -> $(readlink "$LINK_PATH")"
