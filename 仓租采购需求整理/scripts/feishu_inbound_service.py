#!/usr/bin/env python3
import argparse
import json
import os
import shlex
import subprocess
import sys
import tempfile
import threading
import time
import traceback
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


DEFAULT_WORKSPACE = "/Users/bukeyitoukano/Documents/skill-codex"
DEFAULT_WORKBOOK_DIR = "/Users/bukeyitoukano/Desktop/工作标准"
DEFAULT_WORKBOOK_PATH = "/Users/bukeyitoukano/Desktop/工作标准/仓库临租需求_已填.xlsx"
WAREHOUSE_DEMAND_SKILL_PATH = "/Users/bukeyitoukano/.claude/skills/仓租采购需求整理"
WAREHOUSE_EMAIL_SKILL_PATH = "/Users/bukeyitoukano/.claude/skills/仓租采购审批邮件生成"
CONTRACT_REVIEW_SKILL_PATH = "/Users/bukeyitoukano/.claude/skills/合同审核skill"
OPEN_FEISHU_BASE_URL = "https://open.feishu.cn/open-apis"

TOKEN_CACHE = {"token": None, "expire_at": 0}
TOKEN_LOCK = threading.Lock()
WORKFLOW_LOCK = threading.Lock()
SEEN_EVENT_IDS = set()
SEEN_EVENT_LOCK = threading.Lock()
PENDING_ATTACHMENTS = {}
PENDING_ATTACHMENTS_LOCK = threading.Lock()
PENDING_ATTACHMENTS_TTL_SECONDS = 1800


def debug_dir():
    path = Path(os.environ.get("FEISHU_DEBUG_DIR", "/tmp/feishu_warehouse_rent_debug"))
    path.mkdir(parents=True, exist_ok=True)
    return path


def write_debug_payload(payload, prefix="payload"):
    if os.environ.get("FEISHU_DEBUG", "1") in ("0", "false", "False"):
        return
    timestamp = time.strftime("%Y%m%d-%H%M%S")
    suffix = str(int(time.time() * 1000))[-4:]
    name = f"{timestamp}-{suffix}-{prefix}.json"
    try:
        (debug_dir() / name).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"[debug] saved {name}", file=sys.stderr)
    except Exception as exc:
        print(f"[debug] save failed: {exc}", file=sys.stderr)


def env_required(name):
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"缺少环境变量 {name}")
    return value


def request_json(method, url, payload=None, headers=None, timeout=20):
    data = None
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req_headers = {"Content-Type": "application/json; charset=utf-8"}
    if headers:
        req_headers.update(headers)
    req = urllib.request.Request(url, data=data, headers=req_headers, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8")
    return json.loads(raw) if raw else {}


def get_tenant_access_token():
    now = time.time()
    with TOKEN_LOCK:
        if TOKEN_CACHE["token"] and TOKEN_CACHE["expire_at"] > now + 60:
            return TOKEN_CACHE["token"]

        app_id = env_required("FEISHU_APP_ID")
        app_secret = env_required("FEISHU_APP_SECRET")
        result = request_json(
            "POST",
            f"{OPEN_FEISHU_BASE_URL}/auth/v3/tenant_access_token/internal",
            {"app_id": app_id, "app_secret": app_secret},
        )
        if result.get("code") not in (None, 0):
            raise RuntimeError(f"获取 tenant_access_token 失败：{result}")
        token = result.get("tenant_access_token")
        if not token:
            raise RuntimeError(f"获取 tenant_access_token 失败：{result}")
        TOKEN_CACHE["token"] = token
        TOKEN_CACHE["expire_at"] = now + int(result.get("expire", 7200))
        return token


def feishu_headers():
    return {"Authorization": f"Bearer {get_tenant_access_token()}"}


def reply_message(message_id, text):
    if not message_id:
        print(f"[feishu] 无 message_id，无法回复：{text}", file=sys.stderr)
        return
    payload = {
        "msg_type": "text",
        "content": json.dumps({"text": text}, ensure_ascii=False),
    }
    try:
        result = request_json(
            "POST",
            f"{OPEN_FEISHU_BASE_URL}/im/v1/messages/{urllib.parse.quote(message_id)}/reply",
            payload,
            headers=feishu_headers(),
        )
        if result.get("code") not in (None, 0):
            print(f"[feishu] 回复失败：{result}", file=sys.stderr)
    except Exception as exc:
        print(f"[feishu] 回复异常：{exc}", file=sys.stderr)


def download_resource(message_id, file_key, resource_type, target_dir, file_name=None):
    target_dir.mkdir(parents=True, exist_ok=True)
    safe_name = file_name or file_key
    safe_name = "".join(ch if ch not in "/\\" else "_" for ch in safe_name)
    target = target_dir / safe_name
    url = (
        f"{OPEN_FEISHU_BASE_URL}/im/v1/messages/"
        f"{urllib.parse.quote(message_id)}/resources/{urllib.parse.quote(file_key)}"
        f"?type={urllib.parse.quote(resource_type)}"
    )
    req = urllib.request.Request(url, headers=feishu_headers(), method="GET")
    with urllib.request.urlopen(req, timeout=60) as resp:
        target.write_bytes(resp.read())
    return target


def parse_content(raw_content):
    if not raw_content:
        return {}
    if isinstance(raw_content, dict):
        return raw_content
    try:
        return json.loads(raw_content)
    except json.JSONDecodeError:
        return {"text": str(raw_content)}


def collect_resource_refs(value):
    refs = []
    if isinstance(value, dict):
        file_key = value.get("file_key")
        image_key = value.get("image_key")
        if file_key:
            refs.append(
                {
                    "key": file_key,
                    "type": "file",
                    "name": value.get("file_name") or value.get("name"),
                }
            )
        if image_key:
            refs.append({"key": image_key, "type": "image", "name": f"{image_key}.jpg"})
        for item in value.values():
            refs.extend(collect_resource_refs(item))
    elif isinstance(value, list):
        for item in value:
            refs.extend(collect_resource_refs(item))
    return refs


def extract_message(event):
    message = event.get("message") or {}
    content = parse_content(message.get("content"))
    text = content.get("text") or content.get("title") or ""
    return {
        "message_id": message.get("message_id"),
        "message_type": message.get("message_type"),
        "chat_id": message.get("chat_id"),
        "content": content,
        "text": text,
        "resources": collect_resource_refs(content),
    }


def pending_key(event, message):
    sender = event.get("sender") or {}
    sender_id = sender.get("sender_id") or {}
    user_id = sender_id.get("open_id") or sender_id.get("user_id") or "unknown-user"
    return f"{message.get('chat_id') or 'unknown-chat'}:{user_id}"


def remember_attachments(key, paths):
    if not paths:
        return
    with PENDING_ATTACHMENTS_LOCK:
        PENDING_ATTACHMENTS[key] = {
            "paths": list(paths),
            "created_at": time.time(),
        }


def pop_recent_attachments(key):
    with PENDING_ATTACHMENTS_LOCK:
        item = PENDING_ATTACHMENTS.get(key)
        if not item:
            return []
        if time.time() - item["created_at"] > PENDING_ATTACHMENTS_TTL_SECONDS:
            PENDING_ATTACHMENTS.pop(key, None)
            return []
        PENDING_ATTACHMENTS.pop(key, None)
        return list(item["paths"])


def has_pending_attachments(key):
    with PENDING_ATTACHMENTS_LOCK:
        item = PENDING_ATTACHMENTS.get(key)
        return bool(item and time.time() - item["created_at"] <= PENDING_ATTACHMENTS_TTL_SECONDS)


ROUTES = [
    {
        "name": "仓租采购需求整理",
        "keywords": [
            "仓租",
            "临租",
            "仓库临租",
            "仓库租赁",
            "租赁需求",
            "填表",
            "需求表",
            "新增仓",
            "总租金",
        ],
        "skill_path": WAREHOUSE_DEMAND_SKILL_PATH,
        "ack": "已收到仓租采购需求，正在整理需求表和审批邮件。",
        "instructions": """你正在处理一条来自飞书机器人的仓租采购需求。请按“仓租采购需求整理”工作流自动执行：
1. 从飞书消息文本和附件中抽取需求字段；若附件是合同/PDF/Word/图片，请从合同内容中检索需求表必要字段。
2. 更新桌面《仓库临租需求.xlsx》。
3. 只基于新增行生成仓租采购审批邮件正文。
4. 如果缺少必要字段或存在冲突，不要写表，输出需要用户补充/确认的问题。
5. 最终答复要适合直接发回飞书，中文、简洁，包含填表状态、行号、审批邮件或需确认事项。""",
    },
    {
        "name": "仓租采购审批邮件生成",
        "keywords": ["审批邮件", "生成邮件", "写邮件", "邮件正文", "商务条件确认"],
        "skill_path": WAREHOUSE_EMAIL_SKILL_PATH,
        "ack": "已收到邮件生成需求，正在生成审批邮件正文。",
        "instructions": """你正在处理一条来自飞书机器人的仓租采购审批邮件生成需求。请按“仓租采购审批邮件生成”工作流执行：
1. 从飞书消息文本、表格、截图、附件或已给出的新增行中抽取邮件所需字段。
2. 只生成审批邮件正文，不更新《仓库临租需求.xlsx》，除非用户明确要求填表。
3. 如缺少关键金额、租期、面积、单价或价格说明，输出需确认项。
4. 最终答复要适合直接发回飞书，中文、简洁。""",
    },
    {
        "name": "合同审核",
        "keywords": ["合同审核", "审合同", "审核合同", "合同风险", "风险分析", "审查合同", "看看合同"],
        "skill_path": CONTRACT_REVIEW_SKILL_PATH,
        "ack": "已收到合同审核需求，正在审查合同风险。",
        "instructions": """你正在处理一条来自飞书机器人的合同审核需求。请按“合同审核skill”工作流执行：
1. 优先读取飞书附件中的合同文件；没有附件时读取消息文本中的合同内容。
2. 提取合同关键信息，识别主要风险点、缺失条款、异常条款和建议修改方向。
3. 不要更新仓租需求表，也不要生成仓租审批邮件，除非用户明确要求。
4. 最终答复要适合直接发回飞书，中文、结构清晰、重点突出。""",
    },
]


def route_help():
    return """我已收到消息，但还没判断出要走哪个流程。

请在消息开头加一个关键词：
1. 仓租：新增天津（二轮）临租，面积...
2. 邮件：根据这些仓租数据生成审批邮件
3. 合同审核：请审核这份合同风险

也可以直接发送合同附件，并在消息里写“合同审核”或“仓租合同填表”。"""


def choose_route(message_text, attachment_paths):
    text = (message_text or "").strip()
    lowered = text.lower()
    for route in ROUTES:
        if any(keyword.lower() in lowered for keyword in route["keywords"]):
            return route

    if attachment_paths and any(word in lowered for word in ["审核", "风险", "审查", "合同"]):
        if any(str(path).lower().endswith((".pdf", ".doc", ".docx")) for path in attachment_paths):
            return ROUTES[2]

    return None


def build_prompt(route, message_text, attachment_paths, raw_event):
    attachments = "\n".join(f"- {path}" for path in attachment_paths) or "无"
    workbook_path = os.environ.get("WAREHOUSE_RENT_WORKBOOK_PATH", DEFAULT_WORKBOOK_PATH)
    return f"""请使用 skill：{route["skill_path"]}

路由类型：{route["name"]}

{route["instructions"]}

重要写入要求：
- 仓租需求表只能写入这个文件：{workbook_path}
- 不要写入 `/Users/bukeyitoukano/Desktop/工作标准/仓库临租需求.xlsx`。
- 如果旧文件不存在，不要因此中断；请直接使用上面的 `_已填` 文件。

飞书消息文本：
{message_text or "无"}

已下载附件路径：
{attachments}

飞书原始事件 JSON：
```json
{json.dumps(raw_event, ensure_ascii=False, indent=2)}
```
"""


def default_codex_command(output_file):
    workspace = os.environ.get("WAREHOUSE_RENT_WORKSPACE", DEFAULT_WORKSPACE)
    workbook_dir = os.environ.get("WAREHOUSE_RENT_WORKBOOK_DIR", DEFAULT_WORKBOOK_DIR)
    workbook_path = os.environ.get("WAREHOUSE_RENT_WORKBOOK_PATH", DEFAULT_WORKBOOK_PATH)
    return [
        "codex",
        "-C",
        workspace,
        "--add-dir",
        workbook_dir,
        "--add-dir",
        str(Path(workbook_path).parent),
        "-a",
        "never",
        "exec",
        "-o",
        str(output_file),
        "-",
    ]


def workflow_command(output_file):
    configured = os.environ.get("FEISHU_WORKFLOW_COMMAND")
    if configured:
        return [part.format(output_file=str(output_file)) for part in shlex.split(configured)]
    return default_codex_command(output_file)


def run_workflow(prompt):
    with tempfile.TemporaryDirectory(prefix="feishu_warehouse_rent_codex_") as tmp:
        output_file = Path(tmp) / "codex-final.txt"
        cmd = workflow_command(output_file)
        with WORKFLOW_LOCK:
            result = subprocess.run(
                cmd,
                input=prompt,
                text=True,
                capture_output=True,
                timeout=int(os.environ.get("FEISHU_WORKFLOW_TIMEOUT_SECONDS", "1800")),
            )
        final_text = output_file.read_text(encoding="utf-8").strip() if output_file.exists() else ""
        if result.returncode != 0:
            detail = result.stderr.strip() or result.stdout.strip()
            raise RuntimeError(f"工作流执行失败，退出码 {result.returncode}：{detail[-1800:]}")
        return final_text or result.stdout.strip()


def process_event(payload):
    header = payload.get("header") or {}
    event_id = header.get("event_id") or payload.get("uuid")
    event_type = header.get("event_type") or payload.get("type")
    print(f"[feishu] received event_type={event_type} event_id={event_id}", file=sys.stderr)
    with SEEN_EVENT_LOCK:
        if event_id and event_id in SEEN_EVENT_IDS:
            print(f"[feishu] skip duplicate event_id={event_id}", file=sys.stderr)
            return
        if event_id:
            SEEN_EVENT_IDS.add(event_id)

    event = payload.get("event") or {}
    if event_type != "im.message.receive_v1":
        if event_type == "im.chat.access_event.bot_p2p_chat_entered_v1":
            print("[feishu] bot p2p chat entered; silent ignore", file=sys.stderr)
        print(f"[feishu] ignore unsupported event_type={event_type}", file=sys.stderr)
        return

    message = extract_message(event)
    message_id = message["message_id"]
    key = pending_key(event, message)
    print(
        f"[feishu] message_id={message_id} type={message['message_type']} text={message['text']!r}",
        file=sys.stderr,
    )

    work_dir = Path(os.environ.get("FEISHU_INBOUND_WORK_DIR", tempfile.gettempdir()))
    event_dir = work_dir / "feishu_warehouse_rent" / (event_id or str(int(time.time())))
    attachment_paths = []
    for ref in message["resources"]:
        try:
            path = download_resource(
                message_id,
                ref["key"],
                ref["type"],
                event_dir,
                ref.get("name"),
            )
            attachment_paths.append(str(path))
        except Exception as exc:
            print(f"[feishu] 附件下载失败：{ref} {exc}", file=sys.stderr)

    if attachment_paths and not message["text"].strip():
        remember_attachments(key, attachment_paths)
        reply_message(
            message_id,
            "已收到附件。请继续发送要处理的关键词，例如：合同审核、仓租合同填表、邮件生成。",
        )
        return

    recent_attachment_paths = pop_recent_attachments(key)
    if recent_attachment_paths:
        attachment_paths = recent_attachment_paths + attachment_paths
        print(f"[feishu] attached recent files={recent_attachment_paths}", file=sys.stderr)

    route = choose_route(message["text"], attachment_paths)
    if not route:
        if has_pending_attachments(key):
            reply_message(
                message_id,
                "我已收到附件，但还没判断出要走哪个流程。请回复：合同审核、仓租合同填表，或邮件生成。",
            )
            return
        reply_message(message_id, route_help())
        return

    reply_message(message_id, route["ack"])
    print(f"[feishu] route={route['name']}", file=sys.stderr)

    prompt = build_prompt(route, message["text"], attachment_paths, payload)
    try:
        final_text = run_workflow(prompt)
    except Exception:
        final_text = "处理失败，请查看服务日志。\n" + traceback.format_exc(limit=3)
    reply_message(message_id, final_text[:4500])


class FeishuHandler(BaseHTTPRequestHandler):
    def _send_json(self, status, data):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length)
        try:
            payload = json.loads(raw.decode("utf-8"))
        except Exception:
            self._send_json(400, {"error": "invalid json"})
            return
        write_debug_payload(payload, "incoming")

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
            self._send_json(
                400,
                {"error": "encrypted events are not supported; disable Encrypt Key or add decryption"},
            )
            return

        threading.Thread(target=process_event, args=(payload,), daemon=True).start()
        self._send_json(200, {"ok": True})

    def log_message(self, fmt, *args):
        print(f"[http] {self.address_string()} - {fmt % args}", file=sys.stderr)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default=os.environ.get("FEISHU_INBOUND_HOST", "0.0.0.0"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("FEISHU_INBOUND_PORT", "8787")))
    args = parser.parse_args()

    if os.environ.get("FEISHU_ENCRYPT_KEY"):
        print("提示：当前脚本尚未实现事件加密解密，请在飞书后台关闭 Encrypt Key 或补充解密逻辑。")

    server = ThreadingHTTPServer((args.host, args.port), FeishuHandler)
    print(f"Feishu inbound service listening on http://{args.host}:{args.port}/")
    server.serve_forever()


if __name__ == "__main__":
    main()
