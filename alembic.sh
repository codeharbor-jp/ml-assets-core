#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="/home/dev/projects/tts"
DATABASE_URL=postgresql://postgres:postgres@192.168.0.100:5432/video_tts
cd "$ROOT_DIR"

if [[ -z "${DATABASE_URL:-}" ]]; then
  echo "DATABASE_URL is not set. please export it before running this script." >&2
  exit 1
fi

alembic upgrade head