"""Robots, HTML, and XML sitemap parsing with bounded output."""
from __future__ import annotations

import hashlib
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from urllib.parse import urljoin, urlsplit

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


@dataclass(frozen=True, slots=True)
class RobotsRules:
    """robots.txt matcher using longest-match precedence and Allow tie-breaks."""

    groups: tuple[tuple[tuple[str, ...], tuple[tuple[bool, str], ...]], ...]

    @staticmethod
    def _matches(pattern: str, target: str) -> bool:
        end_anchored = pattern.endswith("$")
        pattern_body = pattern[:-1] if end_anchored else pattern
        expression = "".join(
            ".*" if char == "*" else re.escape(char)
            for char in pattern_body
        )
        expression += "$" if end_anchored else ".*"
        return re.match(expression, target) is not None

    def can_fetch(self, user_agent: str, url: str) -> bool:
        """Return whether the best-matching robots rule permits the URL."""
        product = user_agent.split("/", 1)[0].strip().casefold()
        matching_groups: list[
            tuple[tuple[str, ...], tuple[tuple[bool, str], ...]]
        ] = []
        best_agent_length = -1

        for agents, rules in self.groups:
            matching_agents = [
                agent for agent in agents
                if agent == "*" or (agent and agent in product)
            ]
            if not matching_agents:
                continue
            specificity = max(
                0 if agent == "*" else len(agent)
                for agent in matching_agents
            )
            if specificity > best_agent_length:
                best_agent_length = specificity
                matching_groups = [(agents, rules)]
            elif specificity == best_agent_length:
                matching_groups.append((agents, rules))

        if best_agent_length < 0:
            return True

        parts = urlsplit(url)
        target = parts.path or "/"
        if parts.query:
            target += "?" + parts.query

        matched_rules: list[tuple[int, bool]] = []
        for _agents, rules in matching_groups:
            for allowed, pattern in rules:
                if self._matches(pattern, target):
                    specificity = len(pattern.replace("*", "").removesuffix("$"))
                    matched_rules.append((specificity, allowed))

        if not matched_rules:
            return True

        longest = max(specificity for specificity, _allowed in matched_rules)
        return any(
            allowed
            for specificity, allowed in matched_rules
            if specificity == longest
        )


def parse_robots(robots_url: str, body: str) -> tuple[RobotsRules, list[str]]:
    """Parse robots.txt and return its rule matcher plus valid Sitemap directives."""
    groups: list[tuple[tuple[str, ...], tuple[tuple[bool, str], ...]]] = []
    agents: list[str] = []
    rules: list[tuple[bool, str]] = []
    sitemap_urls: list[str] = []

    for raw_line in body.splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if not line or ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip().casefold()
        value = value.strip()

        if key == "user-agent":
            if rules and agents:
                groups.append((tuple(agents), tuple(rules)))
                agents = []
                rules = []
            if value:
                agents.append(value.casefold())
        elif key in {"allow", "disallow"} and agents:
            # An empty Disallow means that no path is disallowed.
            if value:
                rules.append((key == "allow", value))
        elif key == "sitemap" and value and len(sitemap_urls) < 20:
            try:
                normalized = normalize_url(urljoin(robots_url, value))
            except UnsafeTargetError:
                continue
            if normalized not in sitemap_urls:
                sitemap_urls.append(normalized)

    if agents:
        groups.append((tuple(agents), tuple(rules)))

    return RobotsRules(tuple(groups)), sitemap_urls


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
    description_node = soup.find(
        "meta",
        attrs={"name": re.compile(r"^description$", re.IGNORECASE)},
    )
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
        url=page_url,
        canonical_url=canonical_url,
        title=title,
        description=description,
        language=language,
        headings=tuple(headings),
        text=text,
        content_hash=content_hash,
        links=tuple(links),
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
