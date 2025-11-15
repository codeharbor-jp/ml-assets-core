#!/bin/bash
set -euo pipefail

echo "🚀 ml-assets-core 開発環境（Docker + Analytics Dashboard）を起動します..."

PROJECT_ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$PROJECT_ROOT"

BACKEND_PORT="${ML_CORE_PORT:-${PORT:-8820}}"
FRONTEND_PORT="${FRONTEND_PORT:-3820}"
export ML_CORE_PORT="${BACKEND_PORT}"
export FRONTEND_PORT

if [ -f .env ]; then
  set -a
  source .env
  set +a
fi

if docker compose version >/dev/null 2>&1; then
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
  exit 0
}
trap cleanup INT TERM

echo "📦 ml-assets-core Backend/Frontend を起動します (Docker Compose)"
${COMPOSE_CMD} up -d --build ml-core analytics-dashboard

echo "✅ 起動が完了しました。"
echo "   Backend : http://localhost:${BACKEND_PORT}"
echo "   Frontend: http://localhost:${FRONTEND_PORT}"
echo ""
echo "📜 ログを表示しています。Ctrl+C で停止します（停止時に docker compose down を実行）。"
${COMPOSE_CMD} logs -f ml-core analytics-dashboard
