#!/usr/bin/env python3
"""Feishu todo reminder worker.

Polls a Feishu Bitable table and sends reminders for due or overdue rows.
"""

from __future__ import annotations

import argparse
import base64
import datetime as dt
import hashlib
import hmac
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request


OPEN_FEISHU_BASE_URL = "https://open.feishu.cn/open-apis"


def env_required(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be an integer, got {raw!r}") from exc


def now_local() -> dt.datetime:
    tz_name = os.environ.get("TODO_TIMEZONE", "Asia/Shanghai")
    try:
        from zoneinfo import ZoneInfo

        return dt.datetime.now(ZoneInfo(tz_name))
    except Exception:
        return dt.datetime.now().astimezone()


def http_json(method: str, url: str, *, headers=None, payload=None, timeout=30):
    body = None
    request_headers = {"Content-Type": "application/json; charset=utf-8"}
    if headers:
        request_headers.update(headers)
    if payload is not None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")

    request = urllib.request.Request(url, data=body, headers=request_headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            data = response.read().decode("utf-8")
            return json.loads(data) if data else {}
    except urllib.error.HTTPError as exc:
        data = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code} {method} {url}: {data}") from exc


def tenant_access_token() -> str:
    result = http_json(
        "POST",
        f"{OPEN_FEISHU_BASE_URL}/auth/v3/tenant_access_token/internal",
        payload={
            "app_id": env_required("FEISHU_APP_ID"),
            "app_secret": env_required("FEISHU_APP_SECRET"),
        },
    )
    if result.get("code") != 0:
        raise RuntimeError(f"Failed to get tenant_access_token: {result}")
    return result["tenant_access_token"]


def feishu_headers(token: str):
    return {"Authorization": f"Bearer {token}"}


def list_records(token: str, app_token: str, table_id: str):
    records = []
    page_token = None
    while True:
        query = {"page_size": "100"}
        if page_token:
            query["page_token"] = page_token
        url = (
            f"{OPEN_FEISHU_BASE_URL}/bitable/v1/apps/"
            f"{urllib.parse.quote(app_token)}/tables/{urllib.parse.quote(table_id)}/records?"
            f"{urllib.parse.urlencode(query)}"
        )
        result = http_json("GET", url, headers=feishu_headers(token))
        if result.get("code") != 0:
            raise RuntimeError(f"Failed to list records: {result}")
        data = result.get("data") or {}
        records.extend(data.get("items") or [])
        if not data.get("has_more"):
            return records
        page_token = data.get("page_token")


def patch_record(token: str, app_token: str, table_id: str, record_id: str, fields: dict):
    url = (
        f"{OPEN_FEISHU_BASE_URL}/bitable/v1/apps/"
        f"{urllib.parse.quote(app_token)}/tables/{urllib.parse.quote(table_id)}"
        f"/records/{urllib.parse.quote(record_id)}"
    )
    result = http_json("PUT", url, headers=feishu_headers(token), payload={"fields": fields})
    if result.get("code") != 0:
        raise RuntimeError(f"Failed to update record {record_id}: {result}")
    return result


def send_webhook(text: str):
    webhook = env_required("TODO_FEISHU_WEBHOOK_URL")
    payload = {"msg_type": "text", "content": {"text": text}}
    secret = os.environ.get("TODO_FEISHU_WEBHOOK_SECRET")
    if secret:
        timestamp = str(int(time.time()))
        string_to_sign = f"{timestamp}\n{secret}".encode("utf-8")
        payload["timestamp"] = timestamp
        payload["sign"] = base64.b64encode(
            hmac.new(string_to_sign, b"", digestmod=hashlib.sha256).digest()
        ).decode("utf-8")
    result = http_json("POST", webhook, payload=payload)
    if result.get("code") not in (None, 0) or result.get("StatusCode") not in (None, 0):
        raise RuntimeError(f"Failed to send webhook message: {result}")
    return result


def text_value(value):
    if value is None:
        return ""
    if isinstance(value, list):
        parts = []
        for item in value:
            if isinstance(item, dict):
                parts.append(str(item.get("text") or item.get("name") or item.get("value") or ""))
            else:
                parts.append(str(item))
        return "".join(parts).strip()
    if isinstance(value, dict):
        return str(value.get("text") or value.get("name") or value.get("value") or "").strip()
    return str(value).strip()


def option_value(value):
    return text_value(value)


def parse_datetime_value(value):
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        timestamp = value / 1000 if value > 10_000_000_000 else value
        return dt.datetime.fromtimestamp(timestamp, tz=now_local().tzinfo)
    raw = text_value(value)
    if not raw:
        return None
    normalized = raw.replace("/", "-").strip()
    formats = [
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d",
        "%Y.%m.%d %H:%M",
        "%Y.%m.%d",
    ]
    for fmt in formats:
        try:
            parsed = dt.datetime.strptime(normalized, fmt)
            if fmt == "%Y-%m-%d":
                parsed = parsed.replace(hour=0, minute=0)
            return parsed.replace(tzinfo=now_local().tzinfo)
        except ValueError:
            pass
    return None


def same_local_date(value, current: dt.datetime) -> bool:
    parsed = parse_datetime_value(value)
    return bool(parsed and parsed.date() == current.date())


def is_enabled(value) -> bool:
    return option_value(value) in {"开启", "开", "ON", "On", "on", "true", "True", "1", "是"}


def is_done(value) -> bool:
    return option_value(value) in {"已完成", "完成", "done", "Done", "DONE"}


def build_message(fields: dict, current: dt.datetime) -> str:
    task_id = text_value(fields.get(os.environ.get("TODO_FIELD_TASK_ID", "任务ID")))
    item = text_value(fields.get(os.environ.get("TODO_FIELD_TITLE", "待办事项")))
    due = text_value(fields.get(os.environ.get("TODO_FIELD_DUE_DATE", "截止日期")))
    priority = option_value(fields.get(os.environ.get("TODO_FIELD_PRIORITY", "优先级")))
    task_type = option_value(fields.get(os.environ.get("TODO_FIELD_TYPE", "待办类型")))

    lines = ["待办提醒"]
    if item:
        lines.append(f"事项：{item}")
    if task_id:
        lines.append(f"任务ID：{task_id}")
    if due:
        lines.append(f"截止日期：{due}")
    extras = " / ".join(part for part in [priority, task_type] if part)
    if extras:
        lines.append(f"分类：{extras}")
    lines.append(f"提醒时间：{current.strftime('%Y-%m-%d %H:%M')}")
    return "\n".join(lines)


def due_records(records, current: dt.datetime):
    field_status = os.environ.get("TODO_FIELD_STATUS", "完成情况")
    field_switch = os.environ.get("TODO_FIELD_REMINDER_SWITCH", "提醒开关")
    field_next = os.environ.get("TODO_FIELD_NEXT_REMINDER", "下次提醒时间")
    field_last = os.environ.get("TODO_FIELD_LAST_FOLLOW", "最后跟进日期")

    for record in records:
        fields = record.get("fields") or {}
        reminder_time = parse_datetime_value(fields.get(field_next))
        if not reminder_time:
            continue
        if not is_enabled(fields.get(field_switch)):
            continue
        if is_done(fields.get(field_status)):
            continue
        if reminder_time > current:
            continue
        if same_local_date(fields.get(field_last), current):
            continue
        yield record, reminder_time


def run_once() -> int:
    current = now_local()
    app_token = env_required("TODO_BITABLE_APP_TOKEN")
    table_id = env_required("TODO_BITABLE_TABLE_ID")
    field_last = os.environ.get("TODO_FIELD_LAST_FOLLOW", "最后跟进日期")
    field_ai_status = os.environ.get("TODO_FIELD_AI_STATUS", "AI处理状态")
    update_ai_status = os.environ.get("TODO_UPDATE_AI_STATUS", "1") not in {"0", "false", "False"}

    token = tenant_access_token()
    records = list_records(token, app_token, table_id)
    count = 0
    for record, reminder_time in due_records(records, current):
        fields = record.get("fields") or {}
        message = build_message(fields, current)
        send_webhook(message)
        updates = {field_last: int(current.timestamp() * 1000)}
        if update_ai_status and field_ai_status in fields:
            updates[field_ai_status] = "已提醒"
        patch_record(token, app_token, table_id, record["record_id"], updates)
        count += 1
        print(
            f"sent reminder record_id={record['record_id']} "
            f"reminder_time={reminder_time.isoformat()}",
            flush=True,
        )
    print(f"checked {len(records)} records, sent {count} reminders", flush=True)
    return count


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true", help="Run one polling pass and exit.")
    args = parser.parse_args()

    interval = env_int("TODO_POLL_INTERVAL_SECONDS", 300)
    if interval < 30:
        raise RuntimeError("TODO_POLL_INTERVAL_SECONDS must be at least 30")

    while True:
        try:
            run_once()
        except Exception as exc:
            print(f"[error] {exc}", file=sys.stderr, flush=True)
            if args.once:
                return 1
        if args.once:
            return 0
        time.sleep(interval)


if __name__ == "__main__":
    sys.exit(main())
