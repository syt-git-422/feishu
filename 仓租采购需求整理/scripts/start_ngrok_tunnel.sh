#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
NGROK_BIN="${NGROK_BIN:-$REPO_DIR/bin/ngrok}"
PORT="${FEISHU_INBOUND_PORT:-8787}"
DOMAIN="${NGROK_DOMAIN:-duckling-enquirer-perjurer.ngrok-free.dev}"

if [[ ! -x "$NGROK_BIN" ]]; then
  echo "找不到 ngrok：$NGROK_BIN"
  exit 1
fi

echo "正在启动固定 ngrok 地址..."
echo "飞书事件订阅地址：https://${DOMAIN}/feishu/events"
echo

exec "$NGROK_BIN" http "$PORT" --url="https://${DOMAIN}" --log stdout
