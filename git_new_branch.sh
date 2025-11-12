#!/usr/bin/env bash

set -euo pipefail

if [ "$#" -ne 1 ]; then
  echo "Usage: $0 <branch-name>"
  exit 64
fi

BRANCH="$1"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

git fetch origin

if git rev-parse --verify "$BRANCH" >/dev/null 2>&1; then
  echo "ローカルブランチ '$BRANCH' をチェックアウトします。"
  git checkout "$BRANCH"
elif git ls-remote --exit-code --heads origin "$BRANCH" >/dev/null 2>&1; then
  echo "リモートブランチ 'origin/$BRANCH' に追従するローカルブランチを作成しチェックアウトします。"
  git checkout --track "origin/$BRANCH"
else
  echo "新しいブランチ '$BRANCH' を作成しチェックアウトします。"
  git checkout -b "$BRANCH"
fi

echo "ブランチ '$BRANCH' を 'origin' にプッシュします。"
git push -u origin "$BRANCH"