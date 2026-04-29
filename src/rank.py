from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from fetch import NewsItem


@dataclass
class RankedItem:
    title: str
    url: str
    source: str
    published_at: str
    raw_summary: str
    summary: str
    score: float
    fingerprint: str
    section: str
    display_title: str = ""
    display_summary: str = ""


def load_settings(path: str | Path) -> dict:
    return json.loads(Path(path).read_text())


def rank_items(items: list[NewsItem], settings: dict) -> tuple[list[RankedItem], list[RankedItem]]:
    deduped: dict[str, RankedItem] = {}
    for item in items:
        fingerprint = build_item_fingerprint(item.title, item.source, item.published_at)
        score = score_item(item, settings)
        if score <= 0:
            continue
        summary = summarize_item(item, settings)
        candidate = RankedItem(
            title=item.title,
            url=item.url,
            source=item.source,
            published_at=item.published_at,
            raw_summary=item.raw_summary,
            summary=summary,
            score=score,
            fingerprint=fingerprint,
            section="main",
            display_title=item.title,
            display_summary=summary,
        )
        existing = deduped.get(fingerprint)
        if existing is None or candidate.score > existing.score:
            deduped[fingerprint] = candidate

    ranked = sorted(deduped.values(), key=lambda item: item.score, reverse=True)
    main_count = settings["main_items"]
    backup_count = settings["backup_items"]
    main = ranked[:main_count]
    backup = ranked[main_count : main_count + backup_count]
    for item in backup:
        item.section = "watch"
    return main, backup


def score_item(item: NewsItem, settings: dict) -> float:
    title = item.title.lower()
    summary = item.raw_summary.lower()
    text = f"{title} {summary}"

    exclude_keywords = settings["exclude_keywords"]
    if any(keyword.lower() in text for keyword in exclude_keywords):
        return -1

    include_hits = sum(1 for keyword in settings["include_keywords"] if keyword.lower() in text)
    source_weight = settings["source_weights"].get(item.source, 1.0)
    freshness = freshness_score(item.published_at)
    return include_hits * 1.2 + source_weight + freshness


def freshness_score(published_at: str) -> float:
    try:
        published = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
    except ValueError:
        return 0.2
    age_hours = max((datetime.now(timezone.utc) - published).total_seconds() / 3600, 0)
    if age_hours <= 6:
        return 1.4
    if age_hours <= 24:
        return 1.0
    if age_hours <= 48:
        return 0.5
    return 0.1


def summarize_item(item: NewsItem, settings: dict) -> str:
    source_hint = infer_source_hint(item)
    base = item.raw_summary or item.title
    base = re.sub(r"\s+", " ", base).strip()
    if len(base) > 90:
        base = base[:87].rstrip() + "..."
    if source_hint and source_hint not in base:
        return f"{source_hint}。{base}"
    return base


def infer_source_hint(item: NewsItem) -> str:
    title = item.title.lower()
    hints = []
    if any(token in title for token in ("launch", "release", "introducing", "introduces")):
        hints.append("产品/发布动态")
    if any(token in title for token in ("funding", "raises", "startup")):
        hints.append("创业/融资动态")
    if any(token in title for token in ("chip", "gpu", "semiconductor")):
        hints.append("芯片/基础设施动态")
    if "ai" in title or "model" in title or "claude" in title or "gpt" in title:
        hints.append("AI 相关")
    return "，".join(dict.fromkeys(hints))


def build_item_fingerprint(title: str, source: str, published_at: str) -> str:
    normalized_title = re.sub(r"[^a-z0-9]+", " ", title.lower()).strip()
    publish_date = published_at[:10]
    raw = f"{normalized_title}|{source.lower()}|{publish_date}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
