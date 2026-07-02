#!/usr/bin/env bash
set -euo pipefail

if [[ "${ALLOW_DATA_GIT_BACKUP:-}" != "1" ]]; then
  echo "Refusing to commit data/ by default."
  echo "Run with ALLOW_DATA_GIT_BACKUP=1 only if the remote is private and you accept the privacy risk."
  exit 2
fi

cd "$(dirname "$0")/.."

git add -f data/
git reset -- data/*.db-wal data/*.db-shm 2>/dev/null || true

if git diff --cached --quiet -- data/; then
  echo "No changes in data/ to back up."
  exit 0
fi

echo "Files staged for data backup:"
git diff --cached --name-only -- data/

git commit -m "backup: data snapshot $(date -u +%Y-%m-%dT%H:%M:%SZ)"
git push origin HEAD
echo "Backup pushed."
