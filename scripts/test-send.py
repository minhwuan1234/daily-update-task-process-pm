#!/usr/bin/env python3
"""Test: gửi card Lark chỉ cho 2 người test (không đụng members.json / daily-tasks.json).

Chạy thử (không gửi):   python scripts/test-send.py
Gửi thật:               LARK_APP_ID=... LARK_APP_SECRET=... python scripts/test-send.py --send
Test card nhắc lần 2:   python scripts/test-send.py --send --type reminder --reminder-index 2
"""

import argparse
import importlib.util
import json
import os
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Tái sử dụng logic thật của script reminder để test đúng card/URL production.
spec = importlib.util.spec_from_file_location("reminders", ROOT / "scripts" / "send-reminders.py")
rem = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rem)

TEST_USERS = [
    {"name": "lptrang.neu", "userId": "ou_c953d63832eddba640d56be2c2df3ef6"},
    {"name": "tranmaianh100505", "userId": "ou_4c47a96f203274778fdfbf5d6cfcc283"},
]
SAMPLE_TASKS = [
    {"task": "[TEST] Task mẫu 1", "dueDate": "20/11"},
    {"task": "[TEST] Task mẫu 2", "dueDate": "21/11"},
]
FORM_BASE_URL = os.environ.get(
    "FORM_BASE_URL",
    "https://minhwuan1234.github.io/daily-update-task-process-pm/index.html",
)


def build_form_link_card(form_url: str, today_label: str) -> dict:
    """Card giống send-form-links.yml."""
    elements = []
    for i, t in enumerate(SAMPLE_TASKS, 1):
        elements.append({"tag": "div", "text": {"tag": "lark_md",
                         "content": f"{i}. {t['task']} · due **{t['dueDate']}**"}})
        elements.append({"tag": "hr"})
    return {
        "config": {"wide_screen_mode": True},
        "header": {"title": {"tag": "plain_text", "content": f"🧪 TEST · Update tình hình — {today_label}"},
                   "template": "green"},
        "elements": [
            {"tag": "div", "text": {"tag": "lark_md",
                                    "content": f"Xin chào! Hôm nay bạn có **{len(SAMPLE_TASKS)} task** cần update:"}},
            {"tag": "hr"},
            *elements,
            {"tag": "action", "actions": [{"tag": "button",
                                           "text": {"tag": "plain_text", "content": "✍️ Điền Daily Standup"},
                                           "type": "primary", "url": form_url}]},
            {"tag": "note", "elements": [{"tag": "plain_text", "content": "Tin nhắn test, bỏ qua nếu không liên quan."}]},
        ],
    }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--send", action="store_true", help="Gửi thật (mặc định chỉ in ra)")
    p.add_argument("--type", choices=("form", "reminder"), default="form")
    p.add_argument("--reminder-index", type=int, choices=(1, 2, 3), default=1)
    args = p.parse_args()

    now = datetime.now(rem.VN_TZ)
    today_label = now.strftime("%d/%m/%Y")

    token = None
    if args.send:
        token = rem.get_bot_token(os.environ["LARK_APP_ID"], os.environ["LARK_APP_SECRET"])

    for u in TEST_USERS:
        url = rem.build_form_url(FORM_BASE_URL, u["userId"], now)
        if args.type == "form":
            card = build_form_link_card(url, today_label)
        else:
            card = rem.build_card(rem.REMINDER_MESSAGES[args.reminder_index], url, args.reminder_index)

        if not args.send:
            print(f"DRY RUN → {u['name']} ({u['userId']})\n  {url}")
            continue
        try:
            rem.send_lark_card(token, u["userId"], card)
            print(f"Sent {args.type} to {u['name']}")
        except Exception as e:
            print(f"ERROR {u['name']}: {e}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
