"""Validated limits for the local-first crawler."""
from dataclasses import dataclass

DEFAULT_USER_AGENT = (
    "ApokolipsSpider/0.2 "
    "(+https://github.com/lakindusathsara44-bit/Apokolips-Search)"
)

@dataclass(frozen=True, slots=True)
class CrawlConfig:
    user_agent: str = DEFAULT_USER_AGENT
    max_pages: int = 10
    max_depth: int = 2
    max_concurrency: int = 4
    min_host_delay_seconds: float = 1.0
    request_timeout_seconds: float = 15.0
    max_response_bytes: int = 2 * 1024 * 1024
    max_robots_bytes: int = 256 * 1024
    max_sitemap_bytes: int = 1024 * 1024
    max_redirects: int = 5

    def __post_init__(self) -> None:
        if not self.user_agent.strip() or len(self.user_agent) > 200:
            raise ValueError("user_agent must contain 1–200 characters")
        if not 1 <= self.max_pages <= 100:
            raise ValueError("max_pages must be between 1 and 100")
        if not 0 <= self.max_depth <= 5:
            raise ValueError("max_depth must be between 0 and 5")
        if not 1 <= self.max_concurrency <= 8:
            raise ValueError("max_concurrency must be between 1 and 8")
        if self.min_host_delay_seconds < 0.5:
            raise ValueError("min_host_delay_seconds must be at least 0.5")
        if not 1 <= self.request_timeout_seconds <= 60:
            raise ValueError("request_timeout_seconds must be between 1 and 60")
        if not 1024 <= self.max_response_bytes <= 10 * 1024 * 1024:
            raise ValueError("max_response_bytes must be between 1 KiB and 10 MiB")
        if not 1024 <= self.max_robots_bytes <= 1024 * 1024:
            raise ValueError("max_robots_bytes must be between 1 KiB and 1 MiB")
        if not 1024 <= self.max_sitemap_bytes <= 5 * 1024 * 1024:
            raise ValueError("max_sitemap_bytes must be between 1 KiB and 5 MiB")
        if not 0 <= self.max_redirects <= 10:
            raise ValueError("max_redirects must be between 0 and 10")
