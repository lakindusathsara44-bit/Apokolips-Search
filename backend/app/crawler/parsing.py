"""Robots, HTML, and XML sitemap parsing with bounded output."""
from __future__ import annotations

import hashlib
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from urllib.parse import urljoin
from urllib.robotparser import RobotFileParser

from bs4 import BeautifulSoup

from .safety import UnsafeTargetError, normalize_url

MAX_PAGE_TEXT_CHARS = 60_000
MAX_LINKS_PER_PAGE = 300
MAX_SITEMAP_URLS = 1_000

@dataclass(frozen=True, slots=True)
class ExtractedDocument:
    url: str
    canonical_url: str
    title: str
    description: str
    language: str
    headings: tuple[str, ...]
    text: str
    content_hash: str
    links: tuple[str, ...]

def parse_robots(robots_url: str, body: str) -> tuple[RobotFileParser, list[str]]:
    """Parse robots.txt and return its parser plus valid Sitemap directives."""
    parser = RobotFileParser()
    parser.set_url(robots_url)
    parser.parse(body.splitlines())
    sitemap_urls: list[str] = []
    for line in body.splitlines():
        key, separator, value = line.partition(":")
        if separator and key.strip().lower() == "sitemap":
            candidate = value.strip()
            if not candidate:
                continue
            try:
                normalized = normalize_url(urljoin(robots_url, candidate))
            except UnsafeTargetError:
                continue
            if normalized not in sitemap_urls:
                sitemap_urls.append(normalized)
            if len(sitemap_urls) >= 20:
                break
    return parser, sitemap_urls

def extract_html(html: bytes, page_url: str) -> ExtractedDocument:
    """Extract useful page text and safe outgoing links from HTML bytes."""
    soup = BeautifulSoup(html, "html.parser")
    for node in soup(["script", "style", "noscript", "template", "svg", "canvas"]):
        node.decompose()
    for node in soup.find_all(["nav", "footer", "header", "aside", "form"]):
        node.decompose()

    title_node = soup.find("title")
    title = title_node.get_text(" ", strip=True)[:500] if title_node else ""
    description = ""
    description_node = soup.find("meta", attrs={"name": re.compile(r"^description$", re.IGNORECASE)})
    if description_node and description_node.get("content"):
        description = str(description_node["content"]).strip()[:1000]

    canonical_url = page_url
    canonical_node = soup.find("link", rel=lambda value: value and "canonical" in value)
    if canonical_node and canonical_node.get("href"):
        try:
            canonical_url = normalize_url(urljoin(page_url, str(canonical_node["href"])))
        except UnsafeTargetError:
            canonical_url = page_url

    html_node = soup.find("html")
    language = str(html_node.get("lang", "")).strip()[:35] if html_node else ""
    headings: list[str] = []
    for heading in soup.find_all(re.compile(r"^h[1-6]$")):
        value = heading.get_text(" ", strip=True)
        if value and value not in headings:
            headings.append(value[:240])
        if len(headings) >= 20:
            break

    text = re.sub(r"\s+", " ", soup.get_text(" ", strip=True)).strip()
    text = text[:MAX_PAGE_TEXT_CHARS]
    content_hash = hashlib.sha256(
        (title + "\n" + description + "\n" + text).encode("utf-8")
    ).hexdigest()

    links: list[str] = []
    for anchor in soup.find_all("a", href=True):
        try:
            candidate = normalize_url(urljoin(page_url, str(anchor["href"])))
        except (UnsafeTargetError, ValueError):
            continue
        if candidate not in links:
            links.append(candidate)
        if len(links) >= MAX_LINKS_PER_PAGE:
            break

    return ExtractedDocument(
        url=page_url, canonical_url=canonical_url, title=title,
        description=description, language=language, headings=tuple(headings),
        text=text, content_hash=content_hash, links=tuple(links),
    )

def extract_sitemap_urls(xml_body: bytes) -> list[str]:
    """Extract bounded <loc> entries from an XML sitemap or sitemap index."""
    if re.search(rb"<!\s*(DOCTYPE|ENTITY)\b", xml_body, flags=re.IGNORECASE):
        raise ValueError("XML document types and entities are not accepted")
    try:
        root = ET.fromstring(xml_body)
    except ET.ParseError as exc:
        raise ValueError("Sitemap XML is malformed") from exc

    urls: list[str] = []
    for element in root.iter():
        if element.tag.rsplit("}", 1)[-1].lower() != "loc" or not element.text:
            continue
        try:
            candidate = normalize_url(element.text.strip())
        except UnsafeTargetError:
            continue
        if candidate not in urls:
            urls.append(candidate)
        if len(urls) >= MAX_SITEMAP_URLS:
            break
    return urls
