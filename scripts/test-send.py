#!/usr/bin/env python3
"""Test: 2 người test nhận card của TẤT CẢ member (quyền xem giống Minh Quân).

Dùng dữ liệu thật từ daily-tasks.json / members.json / responses.json, nhưng
mọi tin nhắn chỉ gửi tới 2 người test, không gửi cho member hay PM thật.

  python scripts/test-send.py                      # xem trước, không gửi
  python scripts/test-send.py --send --type form   # card form-link của từng member
  python scripts/test-send.py --send --type reminder --reminder-index 2
  python scripts/test-send.py --send --type report # card báo cáo của từng response
Cần LARK_APP_ID, LARK_APP_SECRET khi --send.
"""

import argparse
import importlib.util
import json
import os
from datetime import datetime

ROOT_SPEC = importlib.util.spec_from_file_location(
    "reminders", os.path.join(os.path.dirname(__file__), "send-reminders.py")
)
rem = importlib.util.module_from_spec(ROOT_SPEC)
ROOT_SPEC.loader.exec_module(rem)
ROOT = rem.ROOT

TEST_RECEIVERS = [
    {"name": "lptrang.neu", "userId": "ou_c953d63832eddba640d56be2c2df3ef6"},
    {"name": "tranmaianh100505", "userId": "ou_4c47a96f203274778fdfbf5d6cfcc283"},
]
FORM_BASE_URL = os.environ.get(
    "FORM_BASE_URL",
    "https://minhwuan1234.github.io/daily-update-task-process-pm/index.html",
)


def form_card(name: str, tasks: list, form_url: str, label: str) -> dict:
    """Card giống send-form-links.yml, gắn tên member để biết là form của ai."""
    els = []
    for i, t in enumerate(tasks[:2], 1):
        due = f" · due **{t.get('dueDate')}**" if t.get("dueDate") else ""
        els += [{"tag": "div", "text": {"tag": "lark_md", "content": f"{i}. {t.get('task', '')}{due}"}},
                {"tag": "hr"}]
    return {
        "config": {"wide_screen_mode": True},
        "header": {"title": {"tag": "plain_text", "content": f"🧪 TEST · {name} — {label}"},
                   "template": "green"},
        "elements": [
            {"tag": "div", "text": {"tag": "lark_md",
                                    "content": f"Form của **{name}** — **{len(tasks[:2])} task**:"}},
            {"tag": "hr"}, *els,
            {"tag": "action", "actions": [{"tag": "button",
                                           "text": {"tag": "plain_text", "content": "✍️ Mở form của " + name},
                                           "type": "primary", "url": form_url}]},
        ],
    }


def report_card(name: str, resp: dict, submitted: int, total: int, label: str) -> dict:
    """Card báo cáo giống collect-response.yml."""
    els = []
    tasks = resp.get("tasks", [])
    for i, t in enumerate(tasks):
        spent = t.get("timeSpent", "")
        line = f"\n  ⏱️ Thời gian: {spent}" if spent and spent != "—" else ""
        els.append({"tag": "div", "text": {"tag": "lark_md",
                    "content": f"**{t.get('title', '')}**\n  📈 Progress: {t.get('progress', '—')}{line}"}})
        if i < len(tasks) - 1:
            els.append({"tag": "hr"})
    msg = (resp.get("message") or "").strip()
    if msg not in ("", "."):
        els += [{"tag": "hr"}, {"tag": "div", "text": {"tag": "lark_md",
                "content": f"🆕 Task khác hoặc Task phát sinh nếu có: _{msg}_"}}]
    return {
        "config": {"wide_screen_mode": True},
        "header": {"title": {"tag": "plain_text", "content": f"🧪 TEST · Update tình hình — {label}"},
                   "template": "green"},
        "elements": [
            {"tag": "div", "text": {"tag": "lark_md",
                                    "content": f"👤 **{name}** đã submit\n📅 {resp.get('submittedAt', '')}"}},
            {"tag": "hr"}, *els, {"tag": "hr"},
            {"tag": "div", "text": {"tag": "lark_md",
                                    "content": f"✅ Đã submit: **{submitted}/{total}** thành viên"}},
        ],
    }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--send", action="store_true", help="Gửi thật (mặc định chỉ in ra)")
    p.add_argument("--type", choices=("form", "reminder", "report"), default="form")
    p.add_argument("--reminder-index", type=int, choices=(1, 2, 3), default=1)
    args = p.parse_args()

    now = datetime.now(rem.VN_TZ)
    label = now.strftime("%d/%m/%Y")
    daily = rem.read_json(ROOT / "daily-tasks.json", {})
    members = rem.read_json(ROOT / "members.json", {})
    responses = rem.read_json(ROOT / "responses.json", {})
    id_to_name = {v: k for k, v in members.items()}
    print(f"Data: tasks date={daily.get('date')} ({daily.get('generatedAt')}), "
          f"responses date={responses.get('date')}")

    # (tên member, card) — mỗi card gửi cho cả 2 người test
    jobs = []
    assigned = [e for e in daily.get("members", []) if e.get("tasks") and members.get(e.get("member"))]
    if args.type == "form":
        for e in assigned:
            url = rem.build_form_url(FORM_BASE_URL, members[e["member"]], now)
            jobs.append((e["member"], form_card(e["member"], e["tasks"], url, label)))
    elif args.type == "reminder":
        done = {r.get("userId") for r in responses.get("responses", [])}
        msg = rem.REMINDER_MESSAGES[args.reminder_index]
        for e in assigned:
            uid = members[e["member"]]
            if uid in done:
                continue
            card = rem.build_card(f"**{e['member']}**: {msg}",
                                  rem.build_form_url(FORM_BASE_URL, uid, now), args.reminder_index)
            jobs.append((e["member"], card))
    else:
        rs = responses.get("responses", [])
        for r in rs:
            name = id_to_name.get(r.get("userId"), r.get("userId", "?"))
            jobs.append((name, report_card(name, r, len(rs), len(assigned), label)))

    print(f"{args.type}: {len(jobs)} card × {len(TEST_RECEIVERS)} người test")
    token = None
    if args.send and jobs:
        token = rem.get_bot_token(os.environ["LARK_APP_ID"], os.environ["LARK_APP_SECRET"])
    for name, card in jobs:
        for rc in TEST_RECEIVERS:
            if not args.send:
                print(f"DRY RUN: [{name}] → {rc['name']}")
                continue
            try:
                rem.send_lark_card(token, rc["userId"], card)
                print(f"Sent [{name}] → {rc['name']}")
            except Exception as e:
                print(f"ERROR [{name}] → {rc['name']}: {e}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
