#!/usr/bin/env python3
"""Feishu todo inbound service.

Receives Feishu app bot message events and updates the todo sheet.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from feishu_todo_reminder import (
    column_letter,
    env_int,
    get_wiki_node,
    http_json,
    is_done,
    now_local,
    query_sheets,
    read_sheet_values,
    select_sheet_id,
    send_app_bot_message,
    sheet_records,
    tenant_access_token,
    text_value,
    write_sheet_cell,
)


TASK_ID_PATTERN = re.compile(r"T-\d{8}-\d{3}", re.IGNORECASE)


def parse_message_text(message: dict) -> str:
    raw = message.get("content") or ""
    try:
        content = json.loads(raw)
    except json.JSONDecodeError:
        return raw.strip()
    return text_value(content.get("text"))


def sender_open_id(event: dict) -> str:
    sender = event.get("sender") or {}
    sender_id = sender.get("sender_id") or {}
    return sender_id.get("open_id") or sender_id.get("user_id") or ""


def resolve_sheet(token: str):
    wiki_node_token = os.environ.get("TODO_WIKI_NODE_TOKEN")
    if wiki_node_token:
        obj_token, obj_type = get_wiki_node(token, wiki_node_token)
        if obj_type != "sheet":
            raise RuntimeError(f"Todo inbound service currently supports sheet wiki nodes, got {obj_type}")
        spreadsheet_token = obj_token
    else:
        spreadsheet_token = os.environ.get("TODO_SPREADSHEET_TOKEN")
        if not spreadsheet_token:
            raise RuntimeError("Missing TODO_WIKI_NODE_TOKEN or TODO_SPREADSHEET_TOKEN")

    sheets = query_sheets(token, spreadsheet_token)
    sheet_id = select_sheet_id(sheets)
    values = read_sheet_values(token, spreadsheet_token, sheet_id)
    return spreadsheet_token, sheet_id, list(sheet_records(values))


def row_task_id(record: dict) -> str:
    field_task_id = os.environ.get("TODO_FIELD_TASK_ID", "任务ID")
    return text_value((record.get("fields") or {}).get(field_task_id))


def today_reminded_candidate(record: dict) -> bool:
    fields = record.get("fields") or {}
    field_status = os.environ.get("TODO_FIELD_STATUS", "完成情况")
    field_last = os.environ.get("TODO_FIELD_LAST_FOLLOW", "最后跟进日期")
    field_ai_status = os.environ.get("TODO_FIELD_AI_STATUS", "AI处理状态")

    if is_done(fields.get(field_status)):
        return False
    if text_value(fields.get(field_ai_status)) not in {"已提醒", "已发送提醒"}:
        return False
    last_value = text_value(fields.get(field_last))
    today = now_local().strftime("%Y-%m-%d")
    return last_value.startswith(today) or last_value.replace("/", "-").startswith(today)


def find_target_record(records: list[dict], message_text: str):
    match = TASK_ID_PATTERN.search(message_text)
    if match:
        target_id = match.group(0).upper()
        matches = [record for record in records if row_task_id(record).upper() == target_id]
        if not matches:
            return None, f"没找到任务ID：{target_id}"
        return matches[0], None

    candidates = [record for record in records if today_reminded_candidate(record)]
    if len(candidates) == 1:
        return candidates[0], None
    if len(candidates) > 1:
        ids = "、".join(row_task_id(record) for record in candidates if row_task_id(record))
        return None, f"今天有多条已提醒待办，请回复：已完成 任务ID。例如：已完成 {ids.split('、')[0]}"
    return None, "我没找到今天刚提醒且未完成的待办，请回复：已完成 任务ID。"


def mark_completed(token: str, spreadsheet_token: str, sheet_id: str, record: dict):
    field_status = os.environ.get("TODO_FIELD_STATUS", "完成情况")
    field_ai_status = os.environ.get("TODO_FIELD_AI_STATUS", "AI处理状态")
    header_positions = record.get("header_positions") or {}
    row_number = record["row_number"]

    if field_status not in header_positions:
        raise RuntimeError(f"表格缺少字段：{field_status}")

    status_cell = f"{column_letter(header_positions[field_status])}{row_number}"
    write_sheet_cell(token, spreadsheet_token, sheet_id, status_cell, "已完成")

    if field_ai_status in header_positions:
        ai_cell = f"{column_letter(header_positions[field_ai_status])}{row_number}"
        write_sheet_cell(token, spreadsheet_token, sheet_id, ai_cell, "已完成")


def handle_text_event(event: dict):
    message = event.get("message") or {}
    if message.get("message_type") != "text":
        return
    text = parse_message_text(message)
    if "已完成" not in text and "完成" not in text:
        return

    token = tenant_access_token()
    reply_to = sender_open_id(event)
    try:
        spreadsheet_token, sheet_id, records = resolve_sheet(token)
        target, error = find_target_record(records, text)
        if error:
            if reply_to:
                send_app_bot_message(token, error, "open_id", reply_to)
            return
        mark_completed(token, spreadsheet_token, sheet_id, target)
        task_id = row_task_id(target)
        response = f"已更新完成状态：{task_id}" if task_id else "已更新完成状态。"
        if reply_to:
            send_app_bot_message(token, response, "open_id", reply_to)
    except Exception as exc:
        print(f"[todo-inbound] failed: {exc}", file=sys.stderr, flush=True)
        if reply_to:
            try:
                send_app_bot_message(token, f"更新失败：{exc}", "open_id", reply_to)
            except Exception:
                pass


def process_event(payload: dict):
    header = payload.get("header") or {}
    event = payload.get("event") or {}
    event_type = header.get("event_type") or payload.get("event_type")
    if event_type != "im.message.receive_v1":
        print(f"[todo-inbound] ignore event_type={event_type}", flush=True)
        return
    handle_text_event(event)


class FeishuTodoHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self._send_json(200, {"ok": True})

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length).decode("utf-8")
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            self._send_json(400, {"error": "invalid json"})
            return

        expected_token = os.environ.get("FEISHU_VERIFICATION_TOKEN")
        received_token = (
            payload.get("token")
            or (payload.get("header") or {}).get("token")
            or (payload.get("event") or {}).get("token")
        )
        if expected_token and received_token and received_token != expected_token:
            self._send_json(403, {"error": "invalid token"})
            return

        if payload.get("type") == "url_verification" and payload.get("challenge"):
            self._send_json(200, {"challenge": payload["challenge"]})
            return

        if payload.get("encrypt"):
            self._send_json(400, {"error": "encrypted events are not supported"})
            return

        threading.Thread(target=process_event, args=(payload,), daemon=True).start()
        self._send_json(200, {"ok": True})

    def _send_json(self, status: int, data: dict):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        print(f"[http] {self.address_string()} - {fmt % args}", file=sys.stderr)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default=os.environ.get("TODO_INBOUND_HOST", "0.0.0.0"))
    parser.add_argument("--port", type=int, default=env_int("TODO_INBOUND_PORT", 8788))
    args = parser.parse_args()

    server = ThreadingHTTPServer((args.host, args.port), FeishuTodoHandler)
    print(f"Feishu todo inbound service listening on http://{args.host}:{args.port}/")
    server.serve_forever()


if __name__ == "__main__":
    main()
