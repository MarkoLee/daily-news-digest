from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request

from rank import RankedItem


TRANSLATE_BASE_URL = "https://translation.googleapis.com/language/translate/v2"
USER_AGENT = "daily-news-digest/0.2"


def localize_ranked_items(items: list[RankedItem]) -> list[RankedItem]:
    if not items:
        return items

    titles = [item.title for item in items]
    summaries = [item.summary for item in items]
    translated_titles = translate_many(titles)
    translated_summaries = translate_many(summaries)

    localized: list[RankedItem] = []
    for item, title_zh, summary_zh in zip(items, translated_titles, translated_summaries):
        if looks_mixed_language(summary_zh):
            summary_zh = translate_many([item.summary])[0]
        item.display_title = title_zh or item.title
        item.display_summary = summary_zh or item.summary
        localized.append(item)
    return localized


def translate_text(text: str, cache: dict[str, str]) -> str:
    source = compact_text(text)
    if not source:
        return ""
    if source in cache:
        return cache[source]

    api_key = os.environ.get("GOOGLE_TRANSLATE_API_KEY", "").strip()
    if not api_key:
        cache[source] = source
        return source

    body = urllib.parse.urlencode(
        {
            "q": source,
            "target": "zh-CN",
            "format": "text",
            "key": api_key,
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        TRANSLATE_BASE_URL,
        data=body,
        headers={
            "User-Agent": USER_AGENT,
            "Content-Type": "application/x-www-form-urlencoded",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=4) as response:
            payload = json.loads(response.read().decode("utf-8", errors="ignore"))
        translated = payload["data"]["translations"][0]["translatedText"]
        translated = compact_text(translated)
    except Exception:
        translated = source

    cache[source] = translated
    return translated


def translate_many(texts: list[str]) -> list[str]:
    cleaned = [compact_text(text) for text in texts]
    if not cleaned:
        return []

    api_key = os.environ.get("GOOGLE_TRANSLATE_API_KEY", "").strip()
    if not api_key:
        return cleaned

    body_items: list[tuple[str, str]] = [("q", text) for text in cleaned]
    body_items.extend(
        [
            ("target", "zh-CN"),
            ("format", "text"),
            ("key", api_key),
        ]
    )
    body = urllib.parse.urlencode(body_items).encode("utf-8")
    request = urllib.request.Request(
        TRANSLATE_BASE_URL,
        data=body,
        headers={
            "User-Agent": USER_AGENT,
            "Content-Type": "application/x-www-form-urlencoded",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=8) as response:
            payload = json.loads(response.read().decode("utf-8", errors="ignore"))
        translations = payload["data"]["translations"]
        if len(translations) != len(cleaned):
            return cleaned
        return [compact_text(item["translatedText"]) for item in translations]
    except Exception:
        return cleaned


def compact_text(text: str) -> str:
    return " ".join(text.replace("\n", " ").split()).strip()


def looks_mixed_language(text: str) -> bool:
    if not text:
        return False
    ascii_letters = sum(1 for ch in text if ("a" <= ch.lower() <= "z"))
    cjk_chars = sum(1 for ch in text if "\u4e00" <= ch <= "\u9fff")
    return ascii_letters >= 20 and cjk_chars >= 4
