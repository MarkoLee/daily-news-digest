from __future__ import annotations

import hashlib
from datetime import datetime
from html import escape

from rank import RankedItem


def build_digest_id(date_str: str, item_fingerprints: list[str]) -> str:
    joined = "-".join([date_str, *item_fingerprints])
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()[:16]


def render_text(date_str: str, main_items: list[RankedItem], backup_items: list[RankedItem], settings: dict, public_url: str) -> str:
    lines = [
        f"{settings['digest_title']} | {date_str}",
        "",
        settings["top_block_title"],
    ]
    top_line = infer_top_line(main_items)
    lines.append(f"- {top_line}")
    lines.append("")
    lines.append("主列表")
    for index, item in enumerate(main_items, start=1):
        lines.append(f"{index}. {item.display_title or item.title}")
        lines.append(f"   摘要：{item.display_summary or item.summary}")
        lines.append(f"   来源：{item.source}")
        lines.append(f"   摘要页：{public_url}")
    lines.append("")
    lines.append(settings["watch_block_title"])
    for item in backup_items:
        lines.append(f"- {item.display_title or item.title} | {item.source} | {public_url}")
    return "\n".join(lines)


def render_html(date_str: str, main_items: list[RankedItem], backup_items: list[RankedItem], settings: dict) -> str:
    top_line = infer_top_line(main_items)
    generated_at = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    main_html = "\n".join(render_item_html(item, ranked_index=index + 1) for index, item in enumerate(main_items))
    backup_html = "\n".join(render_item_html(item, ranked_index=None) for item in backup_items)
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(settings['digest_title'])} - {escape(date_str)}</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, sans-serif; margin: 40px auto; max-width: 860px; padding: 0 16px; color: #1f2937; background: #f8fafc; }}
    .card {{ background: white; border-radius: 16px; padding: 24px; box-shadow: 0 8px 30px rgba(15, 23, 42, 0.06); }}
    h1, h2 {{ margin: 0 0 12px; }}
    .meta {{ color: #64748b; font-size: 14px; margin-bottom: 24px; }}
    .top {{ background: #eff6ff; border-left: 4px solid #2563eb; padding: 16px; border-radius: 10px; margin-bottom: 24px; }}
    .item {{ border-top: 1px solid #e5e7eb; padding: 16px 0; }}
    .item:first-child {{ border-top: none; padding-top: 0; }}
    .source {{ color: #475569; font-size: 14px; }}
    a {{ color: #2563eb; text-decoration: none; }}
  </style>
</head>
<body>
  <div class="card">
    <h1>{escape(settings['digest_title'])}</h1>
    <div class="meta">{escape(date_str)} | Generated at {escape(generated_at)}</div>
    <div class="top">
      <strong>{escape(settings['top_block_title'])}</strong>
      <div>{escape(top_line)}</div>
    </div>
    <h2>主列表</h2>
    {main_html}
    <h2>{escape(settings['watch_block_title'])}</h2>
    {backup_html}
  </div>
</body>
</html>
"""


def render_item_html(item: RankedItem, ranked_index: int | None) -> str:
    prefix = f"{ranked_index}. " if ranked_index is not None else ""
    return f"""
    <div class="item">
      <div><strong>{escape(prefix + (item.display_title or item.title))}</strong></div>
      <div>{escape(item.display_summary or item.summary)}</div>
      <div class="source">{escape(item.source)} | <a href="{escape(item.url)}" target="_blank" rel="noopener noreferrer">原文</a></div>
    </div>
    """


def infer_top_line(items: list[RankedItem]) -> str:
    if not items:
        return "今天暂无符合规则的高优先级条目。"
    first = items[0]
    return f"今天最值得先看的方向：{first.display_title or first.title}"
