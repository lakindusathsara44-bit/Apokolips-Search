"""Bounded asynchronous crawler with robots, rate, size, and SSRF safeguards."""
from __future__ import annotations
import asyncio
import time
from dataclasses import dataclass, field
from urllib.parse import urljoin, urlsplit
from urllib.robotparser import RobotFileParser
import aiohttp
from .config import CrawlConfig
from .parsing import ExtractedDocument, extract_html, extract_sitemap_urls, parse_robots
from .resolver import PublicOnlyResolver
from .safety import UnsafeTargetError, normalize_url

HTML_CONTENT_TYPES = {"text/html", "application/xhtml+xml"}
XML_CONTENT_TYPES = {"application/xml", "text/xml"}
REDIRECT_STATUSES = {301, 302, 303, 307, 308}

@dataclass(frozen=True, slots=True)
class CrawlIssue:
    url: str
    code: str
    message: str

@dataclass(frozen=True, slots=True)
class CrawlReport:
    pages: tuple[ExtractedDocument, ...]
    issues: tuple[CrawlIssue, ...]
    processed_urls: int
    discovered_urls: int
    elapsed_seconds: float

@dataclass(slots=True)
class _RobotsPolicy:
    available: bool
    parser: RobotFileParser | None = None
    sitemap_urls: list[str] = field(default_factory=list)

@dataclass(slots=True)
class _FetchResult:
    status: int
    final_url: str
    content_type: str
    body: bytes

@dataclass(slots=True)
class _ProcessResult:
    page: ExtractedDocument | None = None
    discovered: list[str] = field(default_factory=list)
    issues: list[CrawlIssue] = field(default_factory=list)

class _ResponseTooLarge(Exception):
    pass

class ApokolipsSpider:
    """Crawl a small set of public websites while respecting publisher policies."""
    def __init__(self, config: CrawlConfig | None = None) -> None:
        self.config = config or CrawlConfig()
        self._robots_cache: dict[str, _RobotsPolicy] = {}
        self._robots_locks: dict[str, asyncio.Lock] = {}
        self._host_semaphores: dict[str, asyncio.Semaphore] = {}
        self._last_request_at: dict[str, float] = {}

    async def crawl(self, seeds: list[str]) -> CrawlReport:
        started = time.monotonic()
        issues: list[CrawlIssue] = []
        seen: set[str] = set()
        frontier: list[str] = []
        for seed in seeds[:10]:
            try:
                normalized = normalize_url(seed)
            except UnsafeTargetError as exc:
                issues.append(CrawlIssue(str(seed)[:300], "unsafe_seed", str(exc)))
                continue
            if normalized not in seen:
                seen.add(normalized)
                frontier.append(normalized)

        pages: list[ExtractedDocument] = []
        canonical_seen: set[str] = set()
        content_seen: set[str] = set()
        processed = 0
        if not frontier:
            return CrawlReport((), tuple(issues), 0, 0, round(time.monotonic() - started, 3))

        timeout = aiohttp.ClientTimeout(total=self.config.request_timeout_seconds)
        connector = aiohttp.TCPConnector(
            resolver=PublicOnlyResolver(), use_dns_cache=False,
            limit=self.config.max_concurrency, enable_cleanup_closed=True,
        )
        async with aiohttp.ClientSession(
            timeout=timeout, connector=connector,
            headers={
                "User-Agent": self.config.user_agent,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.1",
            },
            auto_decompress=True, trust_env=False,
        ) as session:
            for depth in range(self.config.max_depth + 1):
                if not frontier or processed >= self.config.max_pages:
                    break
                remaining = self.config.max_pages - processed
                wave = frontier[:remaining]
                frontier = []
                results = await asyncio.gather(
                    *(self._process_url(session, url) for url in wave),
                    return_exceptions=True,
                )
                processed += len(wave)
                for requested_url, result in zip(wave, results, strict=True):
                    if isinstance(result, BaseException):
                        issues.append(CrawlIssue(
                            requested_url, "worker_error", "The URL could not be processed"
                        ))
                        continue
                    issues.extend(result.issues)
                    page = result.page
                    if page is not None:
                        if page.canonical_url in canonical_seen:
                            issues.append(CrawlIssue(
                                page.url, "duplicate_canonical", "A canonical copy was already crawled"
                            ))
                        elif page.content_hash in content_seen:
                            issues.append(CrawlIssue(
                                page.url, "duplicate_content", "Identical page content was already crawled"
                            ))
                        else:
                            canonical_seen.add(page.canonical_url)
                            content_seen.add(page.content_hash)
                            pages.append(page)
                    if depth < self.config.max_depth:
                        for candidate in result.discovered:
                            if candidate not in seen:
                                seen.add(candidate)
                                frontier.append(candidate)

        return CrawlReport(
            tuple(pages), tuple(issues), processed, len(seen),
            round(time.monotonic() - started, 3),
        )

    async def _process_url(
        self, session: aiohttp.ClientSession, url: str
    ) -> _ProcessResult:
        result = _ProcessResult()
        policy = await self._get_robots(session, self._origin(url))
        if not policy.available or policy.parser is None:
            result.issues.append(CrawlIssue(
                url, "robots_unavailable", "robots.txt could not be checked; this host was skipped"
            ))
            return result
        result.discovered.extend(policy.sitemap_urls)
        if not policy.parser.can_fetch(self.config.user_agent, url):
            result.issues.append(CrawlIssue(
                url, "robots_disallowed", "robots.txt does not permit this URL"
            ))
            return result

        path = urlsplit(url).path.lower()
        sitemap_hint = path.endswith(".xml") or "sitemap" in path
        try:
            response = await self._download(
                session, url,
                self.config.max_sitemap_bytes if sitemap_hint else self.config.max_response_bytes,
            )
        except _ResponseTooLarge:
            result.issues.append(CrawlIssue(
                url, "response_too_large", "Response exceeded the configured byte limit"
            ))
            return result
        except (aiohttp.ClientError, asyncio.TimeoutError, OSError, UnsafeTargetError):
            result.issues.append(CrawlIssue(
                url, "request_failed", "Request failed or the destination was rejected"
            ))
            return result

        if response.status != 200:
            result.issues.append(CrawlIssue(
                url, "http_status", f"Server returned HTTP {response.status}"
            ))
            return result
        if response.content_type in XML_CONTENT_TYPES or sitemap_hint:
            try:
                result.discovered.extend(extract_sitemap_urls(response.body))
            except ValueError:
                result.issues.append(CrawlIssue(
                    url, "invalid_sitemap", "The XML sitemap could not be parsed"
                ))
            return result
        if response.content_type not in HTML_CONTENT_TYPES:
            result.issues.append(CrawlIssue(
                url, "unsupported_content_type", "Only HTML pages and XML sitemaps are crawled"
            ))
            return result
        try:
            page = extract_html(response.body, response.final_url)
        except Exception:
            result.issues.append(CrawlIssue(
                url, "html_parse_failed", "The HTML page could not be parsed"
            ))
            return result
        result.page = page
        result.discovered.extend(page.links)
        return result

    async def _get_robots(
        self, session: aiohttp.ClientSession, origin: str
    ) -> _RobotsPolicy:
        if origin in self._robots_cache:
            return self._robots_cache[origin]
        lock = self._robots_locks.setdefault(origin, asyncio.Lock())
        async with lock:
            if origin in self._robots_cache:
                return self._robots_cache[origin]
            robots_url = origin + "/robots.txt"
            try:
                response = await self._download(
                    session, robots_url, self.config.max_robots_bytes
                )
            except (
                aiohttp.ClientError, asyncio.TimeoutError, OSError,
                UnsafeTargetError, _ResponseTooLarge,
            ):
                policy = _RobotsPolicy(available=False)
            else:
                if response.status in {404, 410}:
                    parser, sitemaps = parse_robots(robots_url, "")
                    policy = _RobotsPolicy(True, parser, sitemaps)
                elif 200 <= response.status < 300:
                    body = response.body.decode("utf-8", errors="replace")
                    parser, sitemaps = parse_robots(robots_url, body)
                    policy = _RobotsPolicy(True, parser, sitemaps)
                else:
                    policy = _RobotsPolicy(available=False)
            self._robots_cache[origin] = policy
            return policy

    async def _download(
        self, session: aiohttp.ClientSession, url: str, max_bytes: int
    ) -> _FetchResult:
        current_url = normalize_url(url)
        for redirect_count in range(self.config.max_redirects + 1):
            host = urlsplit(current_url).netloc.lower()
            semaphore = self._host_semaphores.setdefault(host, asyncio.Semaphore(1))
            async with semaphore:
                previous = self._last_request_at.get(host)
                if previous is not None:
                    delay = self.config.min_host_delay_seconds - (time.monotonic() - previous)
                    if delay > 0:
                        await asyncio.sleep(delay)
                self._last_request_at[host] = time.monotonic()
                async with session.get(current_url, allow_redirects=False) as response:
                    if response.status in REDIRECT_STATUSES:
                        location = response.headers.get("Location")
                        if not location:
                            return _FetchResult(
                                response.status, current_url, response.content_type, b""
                            )
                        if redirect_count >= self.config.max_redirects:
                            raise aiohttp.TooManyRedirects(
                                response.request_info, response.history,
                                message="Crawler redirect limit exceeded",
                            )
                        current_url = normalize_url(urljoin(current_url, location))
                        continue
                    if response.status != 200:
                        return _FetchResult(
                            response.status, current_url, response.content_type, b""
                        )
                    content_length = response.headers.get("Content-Length")
                    if content_length:
                        try:
                            if int(content_length) > max_bytes:
                                raise _ResponseTooLarge
                        except ValueError:
                            pass
                    chunks: list[bytes] = []
                    total = 0
                    async for chunk in response.content.iter_chunked(64 * 1024):
                        total += len(chunk)
                        if total > max_bytes:
                            raise _ResponseTooLarge
                        chunks.append(chunk)
                    return _FetchResult(
                        response.status, current_url, response.content_type.lower(),
                        b"".join(chunks),
                    )
        raise aiohttp.TooManyRedirects(None, (), message="Crawler redirect limit exceeded")

    @staticmethod
    def _origin(url: str) -> str:
        parts = urlsplit(url)
        return f"{parts.scheme}://{parts.netloc}"
