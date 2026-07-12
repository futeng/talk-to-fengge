#!/bin/bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
PID_DIR="/tmp/talk-to-persona-cloud"
mkdir -p "$PID_DIR"
cd "$PROJECT_DIR"

if [ ! -f .env.local ]; then
    echo "缺少 .env.local。先运行："
    echo "uv run python scripts/bootstrap_cloud_env.py --key-file ~/Documents/key.txt"
    exit 1
fi

set -a
source .env.local
set +a

if ! command -v livekit-server >/dev/null 2>&1; then
    echo "缺少 livekit-server。macOS 请先运行：brew install livekit"
    exit 1
fi

cleanup() {
    for name in agent web; do
        if [ -f "$PID_DIR/$name.pid" ]; then
            kill "$(cat "$PID_DIR/$name.pid")" 2>/dev/null || true
            rm -f "$PID_DIR/$name.pid"
        fi
    done
    if [ -f "$PID_DIR/livekit.pid" ]; then
        kill "$(cat "$PID_DIR/livekit.pid")" 2>/dev/null || true
        rm -f "$PID_DIR/livekit.pid"
    fi
}
trap cleanup EXIT INT TERM

if ! lsof -nP -iTCP:7880 -sTCP:LISTEN >/dev/null 2>&1; then
    livekit-server --dev \
        --node-ip=127.0.0.1 \
        --keys "$LIVEKIT_API_KEY: $LIVEKIT_API_SECRET" \
        --rtc.enable_loopback_candidate \
        >/tmp/livekit-cloud.log 2>&1 &
    echo "$!" > "$PID_DIR/livekit.pid"
    sleep 2
fi

uv run python -u -m worker.main start >/tmp/talk-cloud-agent.log 2>&1 &
echo "$!" > "$PID_DIR/agent.pid"
sleep 3
if ! kill -0 "$(cat "$PID_DIR/agent.pid")" 2>/dev/null; then
    tail -30 /tmp/talk-cloud-agent.log
    exit 1
fi

uv run python -u -m worker.web_server >/tmp/talk-cloud-web.log 2>&1 &
echo "$!" > "$PID_DIR/web.pid"
sleep 2

echo "全云端实时人物对话已启动：http://127.0.0.1:8766"
echo "日志：/tmp/talk-cloud-agent.log"
open http://127.0.0.1:8766 2>/dev/null || true
read -r -p "按回车停止服务..."
