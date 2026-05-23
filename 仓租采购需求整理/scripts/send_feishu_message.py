#!/usr/bin/env python3
import argparse
import base64
import hashlib
import hmac
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request

KEYCHAIN_ACCOUNT = "warehouse-rent-demand-fill"
KEYCHAIN_WEBHOOK_SERVICE = "codex-feishu-webhook"
KEYCHAIN_SECRET_SERVICE = "codex-feishu-webhook-secret"


def read_keychain_password(service):
    try:
        result = subprocess.run(
            [
                "security",
                "find-generic-password",
                "-a",
                KEYCHAIN_ACCOUNT,
                "-s",
                service,
                "-w",
            ],
            check=False,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        return None
    if result.returncode != 0:
        return None
    value = result.stdout.strip()
    return value or None


def get_secret(env_name, keychain_service):
    return os.environ.get(env_name) or read_keychain_password(keychain_service)


def build_payload(text, secret=None):
    payload = {
        "msg_type": "text",
        "content": {
            "text": text,
        },
    }
    if secret:
        timestamp = str(int(time.time()))
        string_to_sign = f"{timestamp}\n{secret}".encode("utf-8")
        sign = base64.b64encode(
            hmac.new(string_to_sign, b"", digestmod=hashlib.sha256).digest()
        ).decode("utf-8")
        payload["timestamp"] = timestamp
        payload["sign"] = sign
    return payload


def read_text(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read().strip()


def send_message(webhook_url, payload):
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        webhook_url,
        data=data,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        body = response.read().decode("utf-8")
    try:
        parsed = json.loads(body)
    except json.JSONDecodeError:
        parsed = {"raw": body}
    return parsed


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--text", required=True, help="Path to UTF-8 text file to send.")
    args = parser.parse_args()

    webhook_url = get_secret("FEISHU_WEBHOOK_URL", KEYCHAIN_WEBHOOK_SERVICE)
    if not webhook_url:
        print(
            json.dumps(
                {
                    "ok": False,
                    "reason": "缺少 FEISHU_WEBHOOK_URL，且 Keychain 中未找到 codex-feishu-webhook",
                },
                ensure_ascii=False,
            )
        )
        return 2

    text = read_text(args.text)
    if not text:
        print(json.dumps({"ok": False, "reason": "消息内容为空"}, ensure_ascii=False))
        return 2

    payload = build_payload(
        text, get_secret("FEISHU_WEBHOOK_SECRET", KEYCHAIN_SECRET_SERVICE)
    )

    try:
        result = send_message(webhook_url, payload)
    except urllib.error.HTTPError as exc:
        reason = exc.read().decode("utf-8", errors="replace")
        print(json.dumps({"ok": False, "reason": reason}, ensure_ascii=False))
        return 1
    except Exception as exc:
        print(json.dumps({"ok": False, "reason": str(exc)}, ensure_ascii=False))
        return 1

    ok = result.get("StatusCode") in (None, 0) and result.get("code") in (None, 0)
    print(json.dumps({"ok": ok, "response": result}, ensure_ascii=False))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
