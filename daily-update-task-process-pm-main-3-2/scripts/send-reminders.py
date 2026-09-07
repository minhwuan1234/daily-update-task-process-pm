#!/usr/bin/env python3
"""Send one Daily Standup reminder to members who have not submitted yet."""

import argparse
import json
import os
import urllib.error
import urllib.request
from datetime import datetime, time, timezone
from pathlib import Path
from zoneinfo import ZoneInfo


VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")
ROOT = Path(__file__).resolve().parents[1]
REMINDER_MESSAGES = {
    1: "Đừng quên fill task hôm nay nhé!",
    2: "Suýt quên! Fill task thôi",
    3: "Mãi làm quá đúng ko? Đừng quên fill task nhé",
}


def read_json(path: Path, fallback):
    try:
        with path.open(encoding="utf-8") as file:
            return json.load(file)
    except (FileNotFoundError, json.JSONDecodeError) as error:
        print(f"WARNING: Cannot read {path.name}: {error}")
        return fallback


def parse_now(value: str | None) -> datetime:
    if not value:
        return datetime.now(VN_TZ)
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=VN_TZ)
    return parsed.astimezone(VN_TZ)


def tasks_are_for_today(daily: dict, today) -> bool:
    generated_at = daily.get("generatedAt")
    if generated_at:
        try:
            generated = datetime.fromisoformat(
                generated_at.replace("Z", "+00:00")
            ).astimezone(VN_TZ)
            return generated.date() == today
        except ValueError:
            print("WARNING: daily-tasks.json has an invalid generatedAt value.")
            return False

    # Backward-compatible fallback for payloads that only contain `date: 6-Sep`.
    date_label = str(daily.get("date", "")).strip()
    expected = f"{today.day}-{today.strftime('%b')}"
    return date_label.casefold() == expected.casefold()


def submitted_user_ids(responses: dict, today_iso: str) -> set[str]:
    if responses.get("date") != today_iso:
        return set()
    return {
        item.get("userId")
        for item in responses.get("responses", [])
        if isinstance(item, dict) and item.get("userId")
    }


def members_with_tasks(daily: dict, members: dict) -> list[dict]:
    result = []
    for entry in daily.get("members", []):
        if not isinstance(entry, dict) or not entry.get("tasks"):
            continue
        name = str(entry.get("member", "")).strip()
        user_id = members.get(name)
        if not user_id:
            print(f"WARNING: No Lark open_id found for {name!r}; skipping.")
            continue
        result.append({"name": name, "userId": user_id})
    return result


def get_bot_token(app_id: str, app_secret: str) -> str:
    body = json.dumps({"app_id": app_id, "app_secret": app_secret}).encode()
    request = urllib.request.Request(
        "https://open.larksuite.com/open-apis/auth/v3/tenant_access_token/internal",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        data = json.loads(response.read())
    if data.get("code") != 0 or not data.get("tenant_access_token"):
        raise RuntimeError(f"Could not get Lark bot token: {data.get('msg', data)}")
    return data["tenant_access_token"]


def build_form_url(base_url: str, user_id: str, now: datetime) -> str:
    end_of_day_vn = datetime.combine(now.date(), time(23, 59, 59), VN_TZ)
    expires = end_of_day_vn.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    separator = "&" if "?" in base_url else "?"
    return f"{base_url}{separator}userId={user_id}&expires={expires}"


def build_card(message: str, form_url: str, reminder_index: int) -> dict:
    return {
        "config": {"wide_screen_mode": True},
        "header": {
            "title": {"tag": "plain_text", "content": "⏰ Daily Standup Reminder"},
            "template": "orange",
        },
        "elements": [
            {
                "tag": "div",
                "text": {"tag": "lark_md", "content": message},
            },
            {
                "tag": "action",
                "actions": [
                    {
                        "tag": "button",
                        "text": {"tag": "plain_text", "content": "✍️ Fill task ngay"},
                        "type": "primary",
                        "url": form_url,
                    }
                ],
            },
            {
                "tag": "note",
                "elements": [
                    {
                        "tag": "plain_text",
                        "content": f"Nhắc lần {reminder_index}/3 · Bạn sẽ không nhận thêm sau khi submit.",
                    }
                ],
            },
        ],
    }


def send_lark_card(token: str, user_id: str, card: dict) -> None:
    body = json.dumps(
        {
            "receive_id": user_id,
            "msg_type": "interactive",
            "content": json.dumps(card, ensure_ascii=False),
        },
        ensure_ascii=False,
    ).encode("utf-8")
    request = urllib.request.Request(
        "https://open.larksuite.com/open-apis/im/v1/messages?receive_id_type=open_id",
        data=body,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json; charset=utf-8",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            data = json.loads(response.read())
    except urllib.error.HTTPError as error:
        details = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Lark HTTP {error.code}: {details}") from error
    if data.get("code") != 0:
        raise RuntimeError(f"Lark API error: {data.get('msg', data)}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reminder-index", type=int, choices=(1, 2, 3), required=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--now", help="ISO datetime override for testing")
    args = parser.parse_args()

    now = parse_now(args.now)
    today = now.date()
    today_iso = today.isoformat()
    daily = read_json(ROOT / "daily-tasks.json", {})
    members = read_json(ROOT / "members.json", {})
    responses = read_json(ROOT / "responses.json", {})

    if not tasks_are_for_today(daily, today):
        print(f"No task payload generated for {today_iso}; no reminder sent.")
        return 0

    assigned = members_with_tasks(daily, members)
    submitted = submitted_user_ids(responses, today_iso)
    missing = [member for member in assigned if member["userId"] not in submitted]

    print(
        f"Reminder {args.reminder_index}/3: "
        f"assigned={len(assigned)}, submitted={len(submitted)}, missing={len(missing)}"
    )
    if not missing:
        print("Everyone has submitted; no reminder sent.")
        return 0

    message = REMINDER_MESSAGES[args.reminder_index]
    form_base_url = os.environ.get(
        "FORM_BASE_URL",
        "https://minhwuan1234.github.io/daily-update-task-process-pm/index.html",
    )

    if args.dry_run:
        for member in missing:
            print(f"DRY RUN: would send to {member['name']}: {message}")
        return 0

    app_id = os.environ.get("LARK_APP_ID", "")
    app_secret = os.environ.get("LARK_APP_SECRET", "")
    if not app_id or not app_secret:
        raise RuntimeError("LARK_APP_ID and LARK_APP_SECRET are required.")

    token = get_bot_token(app_id, app_secret)
    failures = []
    for member in missing:
        form_url = build_form_url(form_base_url, member["userId"], now)
        card = build_card(message, form_url, args.reminder_index)
        try:
            send_lark_card(token, member["userId"], card)
            print(f"Sent reminder to {member['name']}")
        except Exception as error:
            failures.append(member["name"])
            print(f"ERROR: Could not remind {member['name']}: {error}")

    if failures:
        raise RuntimeError(f"Failed recipients: {', '.join(failures)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
