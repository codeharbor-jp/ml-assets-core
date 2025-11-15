#!/bin/bash
set -euo pipefail

echo "🚀 ml-assets-core 開発環境（Docker + Analytics Dashboard）を起動します..."

PROJECT_ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$PROJECT_ROOT"

BACKEND_PORT="${PORT:-8820}"
FRONTEND_PORT="${FRONTEND_PORT:-3820}"
export ML_CORE_PORT="${BACKEND_PORT}"

if [ -f .env ]; then
  set -a
  source .env
  set +a
fi

if command -v "docker compose" >/dev/null 2>&1; then
  COMPOSE_CMD="docker compose"
elif command -v docker-compose >/dev/null 2>&1; then
  COMPOSE_CMD="docker-compose"
else
  echo "❌ docker compose が見つかりません。インストールしてから再実行してください。"
  exit 1
fi

FRONTEND_PID=""
KEEPALIVE_PID=""

cleanup() {
  echo ""
  echo "🛑 サービスを停止します..."
  ${COMPOSE_CMD} down --remove-orphans >/dev/null 2>&1 || true
  if [ -n "${FRONTEND_PID}" ] && ps -p "${FRONTEND_PID}" >/dev/null 2>&1; then
    kill "${FRONTEND_PID}" >/dev/null 2>&1 || true
  fi
  if [ -n "${KEEPALIVE_PID}" ] && ps -p "${KEEPALIVE_PID}" >/dev/null 2>&1; then
    kill "${KEEPALIVE_PID}" >/dev/null 2>&1 || true
  fi
  exit 0
}
trap cleanup INT TERM

echo "📦 Backend (Docker) を起動: http://localhost:${BACKEND_PORT}"
${COMPOSE_CMD} up -d --build ml-core

if [ -f dashboards/analytics/package.json ]; then
  echo "🎨 Frontend (Next.js) を起動: http://localhost:${FRONTEND_PORT}"
  pushd dashboards/analytics >/dev/null
  if command -v pnpm >/dev/null 2>&1 && [ -f pnpm-lock.yaml ]; then
    pnpm install --silent >/dev/null 2>&1 || true
    NEXT_PUBLIC_CORE_API_URL="http://localhost:${BACKEND_PORT}/api/v1" pnpm dev -- --port "${FRONTEND_PORT}" &
  elif command -v yarn >/dev/null 2>&1 && [ -f yarn.lock ]; then
    yarn install --silent >/dev/null 2>&1 || true
    NEXT_PUBLIC_CORE_API_URL="http://localhost:${BACKEND_PORT}/api/v1" yarn dev --port "${FRONTEND_PORT}" &
  else
    npm install --silent >/dev/null 2>&1 || true
    NEXT_PUBLIC_CORE_API_URL="http://localhost:${BACKEND_PORT}/api/v1" npm run dev -- --port "${FRONTEND_PORT}" &
  fi
  FRONTEND_PID=$!
  popd >/dev/null
else
  echo "ℹ️ dashboards/analytics に Next.js プロジェクトが見つからないためフロントは起動しません。"
fi

echo "✅ 起動が完了しました。"
echo "   Backend : http://localhost:${BACKEND_PORT}"
if [ -n "${FRONTEND_PID}" ]; then
  echo "   Frontend: http://localhost:${FRONTEND_PORT}"
  wait "${FRONTEND_PID}"
else
  echo "   Frontend: (未起動)"
  (while true; do sleep 3600; done) &
  KEEPALIVE_PID=$!
  wait "${KEEPALIVE_PID}"
fi
