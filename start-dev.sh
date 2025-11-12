#!/bin/bash
set -euo pipefail

echo "🚀 TTS 開発サーバを起動します..."

PROJECT_ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$PROJECT_ROOT"

# 環境の読み込み（存在すれば）
if [ -f .env ]; then
  set -a; source .env; set +a
fi

# pyenv 仮想環境があれば有効化、なければ .venv を使用
if command -v pyenv >/dev/null 2>&1; then
  if pyenv versions --bare | grep -qx "tts-3.12.10"; then
    eval "$(pyenv init -)" >/dev/null 2>&1 || true
    pyenv activate tts-3.12.10 >/dev/null 2>&1 || true
  fi
fi
if [ -z "${VIRTUAL_ENV:-}" ] && [ -d .venv ]; then
  . .venv/bin/activate
fi

# 出力ディレクトリの作成（LOCAL保存向け）
mkdir -p "${AUDIO_OUTPUT_DIR:-./outputs}"

PORT="${PORT:-8000}"
FRONTEND_PORT="${FRONTEND_PORT:-3000}"

# 既存プロセスのチェックと終了関数
cleanup_port() {
  local port=$1
  local service_name=$2
  
  # ポートを使用しているプロセスを検出（複数の方法で確実に検出）
  local pids=""
  
  # 方法1: lsofを使用（最も確実）
  if command -v lsof >/dev/null 2>&1; then
    pids=$(lsof -ti ":$port" 2>/dev/null || true)
  fi
  
  # 方法2: ssを使用（lsofが使えない場合）
  if [ -z "$pids" ] && command -v ss >/dev/null 2>&1; then
    local ss_output=$(ss -ltnp 2>/dev/null | grep -E ":$port[[:space:]]" || true)
    if [ -n "$ss_output" ]; then
      # ss の出力例: LISTEN 0 128 0.0.0.0:3000 0.0.0.0:* users:(("node",pid=12345,fd=20))
      pids=$(echo "$ss_output" | grep -oE 'pid=[0-9]+' | cut -d= -f2 | sort -u || true)
    fi
  fi
  
  # 方法3: netstatを使用（最後の手段）
  if [ -z "$pids" ] && command -v netstat >/dev/null 2>&1; then
    local netstat_output=$(netstat -ltnp 2>/dev/null | grep -E ":$port[[:space:]]" || true)
    if [ -n "$netstat_output" ]; then
      # netstat の出力例: tcp 0 0 0.0.0.0:3000 0.0.0.0:* LISTEN 12345/node
      pids=$(echo "$netstat_output" | awk '{print $7}' | grep -oE '^[0-9]+' | sort -u || true)
    fi
  fi
  
  # 方法4: fuserを使用（追加の検出方法）
  if [ -z "$pids" ] && command -v fuser >/dev/null 2>&1; then
    pids=$(fuser "$port/tcp" 2>/dev/null | tr -d ' ' || true)
  fi
  
  if [ -n "$pids" ]; then
    echo "⚠️  ポート ${port} は既に使用されています。既存の${service_name}プロセスを終了します..."
    for pid in $pids; do
      # PIDが数字であることを確認
      if [[ "$pid" =~ ^[0-9]+$ ]] && ps -p "$pid" >/dev/null 2>&1; then
        echo "   終了中: PID ${pid}"
        kill "$pid" 2>/dev/null || true
      fi
    done
    # プロセスの終了を待つ（最大5秒）
    local count=0
    while [ $count -lt 5 ]; do
      sleep 1
      local remaining=""
      if command -v lsof >/dev/null 2>&1; then
        remaining=$(lsof -ti ":$port" 2>/dev/null || true)
      elif command -v ss >/dev/null 2>&1; then
        local ss_check=$(ss -ltnp 2>/dev/null | grep -E ":$port[[:space:]]" || true)
        if [ -n "$ss_check" ]; then
          remaining=$(echo "$ss_check" | grep -oE 'pid=[0-9]+' | cut -d= -f2 | sort -u || true)
        fi
      fi
      if [ -z "$remaining" ]; then
        break
      fi
      count=$((count + 1))
    done
    # まだ残っている場合は強制終了
    local remaining_pids=""
    if command -v lsof >/dev/null 2>&1; then
      remaining_pids=$(lsof -ti ":$port" 2>/dev/null || true)
    elif command -v ss >/dev/null 2>&1; then
      local ss_remaining=$(ss -ltnp 2>/dev/null | grep -E ":$port[[:space:]]" || true)
      if [ -n "$ss_remaining" ]; then
        remaining_pids=$(echo "$ss_remaining" | grep -oE 'pid=[0-9]+' | cut -d= -f2 | sort -u || true)
      fi
    fi
    if [ -n "$remaining_pids" ]; then
      echo "   強制終了中..."
      for pid in $remaining_pids; do
        if [[ "$pid" =~ ^[0-9]+$ ]]; then
          kill -9 "$pid" 2>/dev/null || true
        fi
      done
      sleep 1
    fi
    echo "✅ ${service_name}の既存プロセスを終了しました"
  fi
}

# PIDファイルから古いプロセスをクリーンアップ
cleanup_pid_file() {
  local pid_file=$1
  if [ -f "$pid_file" ]; then
    local old_pid=$(cat "$pid_file" 2>/dev/null || echo "")
    if [ -n "$old_pid" ] && ps -p "$old_pid" >/dev/null 2>&1; then
      echo "⚠️  PIDファイルに残っているプロセス（${old_pid}）を終了します..."
      kill "$old_pid" 2>/dev/null || true
      sleep 1
    fi
    rm -f "$pid_file"
  fi
}

# 起動前のクリーンアップ
cleanup_port "$PORT" "バックエンド"
cleanup_port "$FRONTEND_PORT" "フロントエンド"
cleanup_pid_file "${PROJECT_ROOT}/backend.pid"
cleanup_pid_file "${PROJECT_ROOT}/frontend.pid"

# クリーンアップ関数（スクリプト終了時）
cleanup_on_exit() {
  echo ""
  echo "🛑 サーバを停止します..."
  if [ -f "${PROJECT_ROOT}/backend.pid" ]; then
    local pid=$(cat "${PROJECT_ROOT}/backend.pid" 2>/dev/null || echo "")
    if [ -n "$pid" ] && ps -p "$pid" >/dev/null 2>&1; then
      kill "$pid" 2>/dev/null || true
    fi
    rm -f "${PROJECT_ROOT}/backend.pid"
  fi
  if [ -f "${PROJECT_ROOT}/frontend.pid" ]; then
    local pid=$(cat "${PROJECT_ROOT}/frontend.pid" 2>/dev/null || echo "")
    if [ -n "$pid" ] && ps -p "$pid" >/dev/null 2>&1; then
      kill "$pid" 2>/dev/null || true
    fi
    rm -f "${PROJECT_ROOT}/frontend.pid"
  fi
  exit 0
}

# シグナルハンドラを設定
trap cleanup_on_exit INT TERM

echo "📦 Backend: uvicorn backend.main:app (http://localhost:${PORT}) を起動..."

# --env-file は .env がある場合のみ指定
ENV_FILE_ARGS=()
if [ -f .env ]; then
  ENV_FILE_ARGS=(--env-file .env)
fi

python -m uvicorn backend.main:app --reload --host 0.0.0.0 --port "$PORT" "${ENV_FILE_ARGS[@]}" &
BACKEND_PID=$!
echo "$BACKEND_PID" > "${PROJECT_ROOT}/backend.pid"

# フロントエンド（任意）: frontend ディレクトリに package.json があれば起動
FRONTEND_PID=""
if [ -f frontend/package.json ]; then
  # フロントエンド起動前にポートが空いていることを再確認
  cleanup_port "$FRONTEND_PORT" "フロントエンド"
  
  echo "🎨 Frontend: Next.js dev server を起動します (http://localhost:${FRONTEND_PORT:-3000})..."
  # プロキシ経由に統一するため、フロントからは相対パスでNext APIを叩く。
  # バックエンドURLはNextのAPI Routeが参照する環境変数で渡す。
  unset NEXT_PUBLIC_API_BASE_URL
  export BACKEND_BASE_URL="${API_BASE_URL:-http://localhost:${PORT}}"
  (
    cd frontend
    # パッケージマネージャ自動判定
    if command -v pnpm >/dev/null 2>&1 && [ -f pnpm-lock.yaml ]; then
      pnpm install --silent || true
      pnpm dev &
    elif command -v yarn >/dev/null 2>&1 && [ -f yarn.lock ]; then
      yarn install --silent || true
      yarn dev &
    else
      npm install --silent || true
      npm run dev &
    fi
    FRONTEND_CHILD_PID=$!
    echo "$FRONTEND_CHILD_PID" > ../frontend.pid
    wait
  ) &
  FRONTEND_PID=$!
else
  echo "ℹ️ frontend/package.json が見つかりませんでした。フロント起動はスキップします。"
fi

echo "✅ 起動コマンド送出済み。バックエンドPID=${BACKEND_PID} フロントPID=${FRONTEND_PID:-N/A}"
echo "📊 Backend:   http://localhost:${PORT}"
echo "🎨 Frontend:  http://localhost:${FRONTEND_PORT:-3000} (存在する場合)"

# どちらかが終了するまで待機
wait ${BACKEND_PID}
