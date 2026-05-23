#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${WAREHOUSE_RENT_FEISHU_ENV:-$HOME/.warehouse-rent-feishu.env}"
PORT="${FEISHU_INBOUND_PORT:-8787}"

if [[ -f "$ENV_FILE" ]]; then
  # shellcheck disable=SC1090
  source "$ENV_FILE"
fi

missing=()
[[ -n "${FEISHU_APP_ID:-}" ]] || missing+=("FEISHU_APP_ID")
[[ -n "${FEISHU_APP_SECRET:-}" ]] || missing+=("FEISHU_APP_SECRET")

if (( ${#missing[@]} > 0 )); then
  cat <<EOF
还差飞书应用信息，服务不能启动。

请新建这个文件：
  $ENV_FILE

写入：
  export FEISHU_APP_ID="你的飞书应用 App ID"
  export FEISHU_APP_SECRET="你的飞书应用 App Secret"
  export FEISHU_VERIFICATION_TOKEN="你的飞书事件订阅 Verification Token，可选"

缺少：${missing[*]}
EOF
  exit 1
fi

echo "正在启动仓租采购飞书机器人入口..."
echo "本机地址：http://127.0.0.1:${PORT}/feishu/events"
echo
echo "注意：飞书不能直接访问 127.0.0.1。"
echo "还需要用 cloudflared/ngrok 或服务器域名，把这个本机地址变成公网 HTTPS 地址。"
echo

exec python3 "$SCRIPT_DIR/feishu_inbound_service.py" --host 0.0.0.0 --port "$PORT"
