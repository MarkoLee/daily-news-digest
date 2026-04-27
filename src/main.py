from __future__ import annotations

import argparse
import json
import os
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from deliver import send_feishu
from fetch import fetch_all, load_sources
from rank import rank_items, load_settings
from render import build_digest_id, render_html, render_text


ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT / "config"
DATA_DIR = ROOT / "data"
PUBLIC_DIR = ROOT / "public"
STATE_PATH = DATA_DIR / "state.json"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    settings = load_settings(CONFIG_DIR / "settings.json")
    sources = load_sources(CONFIG_DIR / "sources.json")
    state = load_state()

    now = datetime.now(ZoneInfo(settings["timezone"]))
    date_str = now.strftime("%Y-%m-%d")

    items = fetch_all(sources)
    main_items, backup_items = rank_items(items, settings)

    digest_id = build_digest_id(date_str, [item.fingerprint for item in main_items + backup_items])
    previous_key = state.get("last_send_idempotency_key")
    current_key = f"{date_str}|feishu|morning-1|{digest_id}"

    public_url = publish_summary_page(date_str, main_items, backup_items, settings)
    message = render_text(date_str, main_items, backup_items, settings, public_url)

    if previous_key == current_key and not args.force:
        print("Digest unchanged. Skip resend.")
        return

    if args.dry_run:
        print(message)
        persist_state(state, current_key, digest_id, public_url, main_items, backup_items, dry_run=True)
        return

    webhook = os.environ.get("FEISHU_WEBHOOK_URL", "").strip()
    if not webhook:
        raise RuntimeError("Missing FEISHU_WEBHOOK_URL")
    if public_url.startswith("file://"):
        raise RuntimeError("Missing PUBLIC_BASE_URL for public summary page")

    send_feishu(webhook, message)
    persist_state(state, current_key, digest_id, public_url, main_items, backup_items, dry_run=False)
    print("Sent digest to Feishu.")


def publish_summary_page(date_str, main_items, backup_items, settings):
    html = render_html(date_str, main_items, backup_items, settings)
    summary_dir = ROOT / settings["public_summary_subdir"]
    summary_dir.mkdir(parents=True, exist_ok=True)
    file_path = summary_dir / f"{date_str}.html"
    file_path.write_text(html)
    ensure_public_index(date_str)
    base_url = (
        os.environ.get("PUBLIC_BASE_URL", "").rstrip("/")
        or os.environ.get("GITHUB_PAGES_BASE_URL", "").rstrip("/")
    )
    if base_url:
        return f"{base_url}/daily-news/{date_str}.html"
    return file_path.as_uri()


def load_state() -> dict:
    if not STATE_PATH.exists():
        return {}
    return json.loads(STATE_PATH.read_text())


def persist_state(state, current_key, digest_id, public_url, main_items, backup_items, dry_run):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    next_state = {
        **state,
        "last_send_idempotency_key": current_key,
        "last_digest_id": digest_id,
        "last_public_url": public_url,
        "last_dry_run": dry_run,
        "updated_at": datetime.utcnow().isoformat() + "Z",
        "main_fingerprints": [item.fingerprint for item in main_items],
        "backup_fingerprints": [item.fingerprint for item in backup_items],
    }
    STATE_PATH.write_text(json.dumps(next_state, indent=2, ensure_ascii=False))


def ensure_public_index(date_str: str) -> None:
    index_path = PUBLIC_DIR / "index.html"
    index_path.parent.mkdir(parents=True, exist_ok=True)
    index_html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Daily News Digest</title>
</head>
<body>
  <h1>Daily News Digest</h1>
  <p>Latest digest:</p>
  <ul>
    <li><a href="./daily-news/{date_str}.html">{date_str}</a></li>
  </ul>
</body>
</html>
"""
    index_path.write_text(index_html)


if __name__ == "__main__":
    main()
