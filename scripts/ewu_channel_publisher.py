#!/usr/bin/env python3
"""Publish at most one approved EWU vacancy per run without touching the polling bot."""
import datetime as dt
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
QUEUE = ROOT / "vacancies" / "approved.json"
STATE = ROOT / "vacancies" / "published.json"
BOT_LINK = "https://t.me/UkrainianWelders_bot"
ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{4,80}$")


def read_json(path, default):
    if not path.exists():
        return default
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def eligible_posts(queue, state, today):
    """Only explicitly reviewed, non-expired offers; never repeat attempted posts."""
    if not isinstance(queue, list) or not isinstance(state, dict):
        raise ValueError("Invalid vacancy queue or delivery ledger")
    selected = []
    seen = set()
    for item in queue:
        if not isinstance(item, dict):
            raise ValueError("Each vacancy must be an object")
        identifier = item.get("id")
        if not isinstance(identifier, str) or not ID_PATTERN.fullmatch(identifier):
            raise ValueError("Invalid vacancy id")
        if identifier in seen:
            raise ValueError("Duplicate vacancy id in queue")
        seen.add(identifier)
        if identifier in state:
            continue
        if item.get("status") != "approved" or item.get("approved") is not True:
            continue
        if item.get("employer_verified") is not True:
            continue
        if not isinstance(item.get("approved_by"), str) or not item["approved_by"].strip():
            continue
        expires = dt.date.fromisoformat(item["valid_until"])
        if expires < today:
            continue
        if item.get("publish_from") and dt.date.fromisoformat(item["publish_from"]) > today:
            continue
        message = item.get("text")
        if not isinstance(message, str) or not message.strip():
            raise ValueError("Approved vacancy has no text")
        message = message.strip()
        if BOT_LINK not in message:
            message += "\n\n🤖 Откликнуться: " + BOT_LINK
        if len(message) > 4096:
            raise ValueError("Vacancy message exceeds Telegram's text limit")
        selected.append((identifier, message))
    return selected


def record_delivery(state, identifier, data, *, commit):
    state[identifier] = data
    STATE.write_text(json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if not commit:
        return
    subprocess.run(["git", "config", "user.name", "ewu-publisher[bot]"], check=True)
    subprocess.run(["git", "config", "user.email", "41898282+github-actions[bot]@users.noreply.github.com"], check=True)
    subprocess.run(["git", "add", str(STATE.relative_to(ROOT))], cwd=ROOT, check=True)
    subprocess.run(["git", "commit", "-m", "EWU channel delivery: " + identifier], cwd=ROOT, check=True)
    branch = os.environ.get("GITHUB_REF_NAME", "main")
    if not re.fullmatch(r"[A-Za-z0-9._/-]+", branch):
        raise RuntimeError("Invalid GitHub branch")
    subprocess.run(["git", "push", "origin", "HEAD:" + branch], cwd=ROOT, check=True)


def send_message(token, channel, message):
    data = json.dumps({
        "chat_id": channel,
        "text": message,
        "disable_web_page_preview": True
    }, ensure_ascii=False).encode("utf-8")
    request = Request(
        "https://api.telegram.org/bot" + token + "/sendMessage",
        data=data, headers={"Content-Type": "application/json"}, method="POST"
    )
    try:
        with urlopen(request, timeout=20) as response:
            payload = json.load(response)
    except HTTPError as err:
        raise RuntimeError("Telegram rejected publication (HTTP " + str(err.code) + ")") from None
    except (URLError, TimeoutError):
        # Network outcome may be unknown; do not retry an attempted post automatically.
        raise RuntimeError("Telegram delivery uncertain; check the channel before any retry") from None
    if not payload.get("ok"):
        raise RuntimeError("Telegram rejected publication")
    return payload.get("result", {}).get("message_id")


def main():
    queue = read_json(QUEUE, [])
    state = read_json(STATE, {})
    today = dt.datetime.now(dt.timezone.utc).date()
    pending = eligible_posts(queue, state, today)
    if not pending:
        print("No new approved, currently valid vacancies.")
        return 0
    identifier, text = pending[0]
    if "--dry-run" in sys.argv:
        print("DRY RUN: eligible vacancy " + identifier + ", " + str(len(text)) + " characters")
        return 0

    token = os.getenv("EWU_TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        print("Not activated: GitHub Actions secret EWU_TELEGRAM_BOT_TOKEN is missing.")
        return 0
    channel = os.getenv("EWU_CHANNEL_ID", "@EWUpraca")
    if channel != "@EWUpraca":
        raise RuntimeError("Unexpected target channel")

    # Persist a non-retryable attempt BEFORE the network request: at-most-once by default.
    stamp = dt.datetime.now(dt.timezone.utc).isoformat()
    record_delivery(state, identifier, {"status": "attempted", "at": stamp}, commit=True)
    message_id = send_message(token, channel, text)
    record_delivery(state, identifier, {
        "status": "published", "at": stamp, "telegram_message_id": message_id
    }, commit=True)
    print("Published approved vacancy " + identifier + " to @EWUpraca.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (ValueError, KeyError, RuntimeError, subprocess.CalledProcessError) as exc:
        print("Publisher stopped: " + str(exc), file=sys.stderr)
        sys.exit(1)
