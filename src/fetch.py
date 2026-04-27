from __future__ import annotations

import json
import re
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from html import unescape
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET


USER_AGENT = "daily-news-digest/0.1"


@dataclass
class NewsItem:
    title: str
    url: str
    source: str
    published_at: str
    raw_summary: str
    topic: str = ""


class _AnthropicNewsParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.in_anchor = False
        self.current_href = ""
        self.current_text: list[str] = []
        self.items: list[dict[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "a":
            return
        attr_map = dict(attrs)
        href = attr_map.get("href") or ""
        if href.startswith("/news/"):
            self.in_anchor = True
            self.current_href = href
            self.current_text = []

    def handle_data(self, data: str) -> None:
        if self.in_anchor:
            self.current_text.append(data.strip())

    def handle_endtag(self, tag: str) -> None:
        if tag != "a" or not self.in_anchor:
            return
        text = " ".join(part for part in self.current_text if part).strip()
        if text and len(text) > 12:
            self.items.append(
                {
                    "title": clean_anthropic_title(text),
                    "url": f"https://www.anthropic.com{self.current_href}",
                }
            )
        self.in_anchor = False
        self.current_href = ""
        self.current_text = []


def load_sources(path: str | Path) -> list[dict[str, Any]]:
    return json.loads(Path(path).read_text())


def fetch_all(sources: list[dict[str, Any]]) -> list[NewsItem]:
    items: list[NewsItem] = []
    for source in sources:
        try:
            source_type = source["type"]
            if source_type == "rss":
                items.extend(fetch_rss_source(source["name"], source["url"]))
            elif source_type == "html":
                items.extend(fetch_anthropic_news(source["name"], source["url"]))
        except Exception as exc:
            print(f"Skip source: {source['name']} | {exc}")
    return items


def fetch_url(url: str) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=20) as response:
        return response.read().decode("utf-8", errors="ignore")


def fetch_rss_source(source_name: str, url: str) -> list[NewsItem]:
    xml_text = fetch_url(url)
    root = ET.fromstring(xml_text)

    channel_items = root.findall(".//channel/item")
    if channel_items:
        return [item_from_rss(source_name, node) for node in channel_items[:30]]

    atom_items = root.findall(".//{http://www.w3.org/2005/Atom}entry")
    return [item_from_atom(source_name, node) for node in atom_items[:30]]


def item_from_rss(source_name: str, node: ET.Element) -> NewsItem:
    title = text_or_empty(node.find("title"))
    link = text_or_empty(node.find("link"))
    description = clean_summary(text_or_empty(node.find("description")))
    published_at = normalize_datetime(text_or_empty(node.find("pubDate")))
    return NewsItem(title=title, url=link, source=source_name, published_at=published_at, raw_summary=description)


def item_from_atom(source_name: str, node: ET.Element) -> NewsItem:
    ns = "{http://www.w3.org/2005/Atom}"
    title = text_or_empty(node.find(f"{ns}title"))
    link_node = node.find(f"{ns}link")
    link = ""
    if link_node is not None:
        link = link_node.attrib.get("href", "")
    summary = clean_summary(text_or_empty(node.find(f"{ns}summary")) or text_or_empty(node.find(f"{ns}content")))
    published_raw = text_or_empty(node.find(f"{ns}updated")) or text_or_empty(node.find(f"{ns}published"))
    published_at = normalize_datetime(published_raw)
    return NewsItem(title=title, url=link, source=source_name, published_at=published_at, raw_summary=summary)


def fetch_anthropic_news(source_name: str, url: str) -> list[NewsItem]:
    html = fetch_url(url)
    parser = _AnthropicNewsParser()
    parser.feed(html)
    seen: set[str] = set()
    items: list[NewsItem] = []
    for candidate in parser.items:
        normalized = candidate["url"]
        if normalized in seen:
            continue
        seen.add(normalized)
        items.append(
            NewsItem(
                title=candidate["title"],
                url=candidate["url"],
                source=source_name,
                published_at=datetime.now(timezone.utc).isoformat(),
                raw_summary="Anthropic newsroom update.",
            )
        )
        if len(items) >= 20:
            break
    return items


def text_or_empty(node: ET.Element | None) -> str:
    if node is None or node.text is None:
        return ""
    return node.text.strip()


def clean_summary(value: str) -> str:
    text = re.sub(r"<[^>]+>", " ", value)
    text = unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:260]


def normalize_datetime(value: str) -> str:
    if not value:
        return datetime.now(timezone.utc).isoformat()
    try:
        return parsedate_to_datetime(value).astimezone(timezone.utc).isoformat()
    except (TypeError, ValueError, IndexError):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc).isoformat()
        except ValueError:
            return datetime.now(timezone.utc).isoformat()


def normalize_title(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def clean_anthropic_title(value: str) -> str:
    text = re.sub(r"\b(Product|Announcements|Research)\b", " ", value, flags=re.IGNORECASE)
    text = re.sub(r"\b[A-Z][a-z]{2} \d{1,2}, \d{4}\b", " ", text)
    text = re.sub(r"\s+", " ", text).strip(" -")
    return text
