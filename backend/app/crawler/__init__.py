"""Responsible, bounded web crawling for Apokolips Search."""
from .config import CrawlConfig
from .spider import ApokolipsSpider

__all__ = ["ApokolipsSpider", "CrawlConfig"]
