from __future__ import annotations

import json
import urllib.request


def send_feishu(webhook_url: str, message: str) -> None:
    payload = {"msg_type": "text", "content": {"text": message}}
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        webhook_url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        response.read()
