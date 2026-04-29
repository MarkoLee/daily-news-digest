from __future__ import annotations

import json
import re
import concurrent.futures
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
        self.last_title_by_url: dict[str, str] = {}
        self.last_href = ""
        self.capture_context = False
        self.context_buffer: list[str] = []
        self.seen_context_for_href: set[str] = set()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "a":
            if self.last_href and tag in {"p", "div", "span"}:
                self.capture_context = True
                self.context_buffer = []
            return
        attr_map = dict(attrs)
        href = attr_map.get("href") or ""
        if href.startswith("/news/"):
            self.in_anchor = True
            self.current_href = href
            self.current_text = []
            self.last_href = href

    def handle_data(self, data: str) -> None:
        if self.in_anchor:
            self.current_text.append(data.strip())
        elif self.capture_context:
            self.context_buffer.append(data.strip())

    def handle_endtag(self, tag: str) -> None:
        if tag != "a" or not self.in_anchor:
            if self.capture_context and tag in {"p", "div", "span"} and self.last_href:
                context_text = clean_summary(" ".join(part for part in self.context_buffer if part))
                if context_text and self.last_href not in self.seen_context_for_href:
                    self.seen_context_for_href.add(self.last_href)
                    title = self.last_title_by_url.get(self.last_href, "")
                    self.items.append(
                        {
                            "title": title,
                            "url": f"https://www.anthropic.com{self.last_href}",
                            "summary": context_text,
                        }
                    )
                self.capture_context = False
                self.context_buffer = []
            return
        text = " ".join(part for part in self.current_text if part).strip()
        if text and len(text) > 12:
            cleaned_title = clean_anthropic_title(text)
            self.last_title_by_url[self.current_href] = cleaned_title
            self.items.append(
                {
                    "title": cleaned_title,
                    "url": f"https://www.anthropic.com{self.current_href}",
                    "summary": "",
                }
            )
        self.in_anchor = False
        self.current_href = ""
        self.current_text = []


class _AnthropicArticleParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.capture_p = False
        self.current_p: list[str] = []
        self.paragraphs: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "p":
            self.capture_p = True
            self.current_p = []

    def handle_data(self, data: str) -> None:
        if self.capture_p:
            self.current_p.append(data.strip())

    def handle_endtag(self, tag: str) -> None:
        if tag != "p" or not self.capture_p:
            return
        text = clean_summary(" ".join(part for part in self.current_p if part))
        if len(text) >= 40:
            self.paragraphs.append(text)
        self.capture_p = False
        self.current_p = []


def load_sources(path: str | Path) -> list[dict[str, Any]]:
    return json.loads(Path(path).read_text())


def fetch_all(sources: list[dict[str, Any]]) -> list[NewsItem]:
    items: list[NewsItem] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(len(sources), 6) or 1) as executor:
        futures = [executor.submit(fetch_source_safe, source) for source in sources]
        for future in concurrent.futures.as_completed(futures):
            items.extend(future.result())
    return items


def fetch_source_safe(source: dict[str, Any]) -> list[NewsItem]:
    try:
        source_type = source["type"]
        if source_type == "rss":
            return fetch_rss_source(source["name"], source["url"])
        if source_type == "html":
            return fetch_anthropic_news(source["name"], source["url"])
        return []
    except Exception as exc:
        print(f"Skip source: {source['name']} | {exc}")
        return []


def fetch_url(url: str) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=8) as response:
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
        raw_summary = candidate.get("summary", "") or "Anthropic newsroom update."
        items.append(
            NewsItem(
                title=candidate["title"],
                url=candidate["url"],
                source=source_name,
                published_at=datetime.now(timezone.utc).isoformat(),
                raw_summary=raw_summary,
            )
        )
        if len(items) >= 20:
            break
    return items


def fetch_anthropic_article_summary(url: str) -> str:
    try:
        html = fetch_url(url)
    except Exception:
        return ""
    parser = _AnthropicArticleParser()
    parser.feed(html)
    for paragraph in parser.paragraphs:
        if not looks_like_noise(paragraph):
            return paragraph[:260]
    return ""


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


def looks_like_noise(text: str) -> bool:
    lower = text.lower()
    return any(
        token in lower
        for token in (
            "subscribe",
            "cookie",
            "javascript",
            "privacy policy",
            "terms of service",
        )
    )
