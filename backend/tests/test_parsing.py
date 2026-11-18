import pytest
from app.crawler.parsing import extract_html, extract_sitemap_urls, parse_robots

def test_extract_html_metadata_text_and_links() -> None:
    html = b"""
    <html lang="en">
      <head><title>Example Page</title>
        <meta name="description" content="A useful page">
        <link rel="canonical" href="/canonical">
        <script>secretScriptText()</script>
      </head>
      <body><nav>Navigation text</nav>
        <main><h1>Welcome</h1><p>Search engine project.</p>
          <a href="/about">About</a><a href="mailto:hello@example.com">Email</a>
        </main><footer>Footer text</footer>
      </body>
    </html>
    """
    page = extract_html(html, "https://example.com/start")
    assert page.title == "Example Page"
    assert page.description == "A useful page"
    assert page.canonical_url == "https://example.com/canonical"
    assert page.language == "en"
    assert page.headings == ("Welcome",)
    assert "Search engine project." in page.text
    assert "Navigation text" not in page.text
    assert "Footer text" not in page.text
    assert "secretScriptText" not in page.text
    assert page.links == ("https://example.com/about",)
    assert len(page.content_hash) == 64

def test_html_canonical_rejects_unsafe_target() -> None:
    page = extract_html(
        b'<html><head><link rel="canonical" href="http://127.0.0.1/private"></head><body>Hello</body></html>',
        "https://example.com/",
    )
    assert page.canonical_url == "https://example.com/"

def test_parse_sitemap_and_filter_non_public_urls() -> None:
    xml = b"""<?xml version="1.0"?>
    <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
      <url><loc>https://example.com/a</loc></url>
      <url><loc>https://example.com/b</loc></url>
      <url><loc>http://127.0.0.1/admin</loc></url>
    </urlset>"""
    assert extract_sitemap_urls(xml) == [
        "https://example.com/a", "https://example.com/b"
    ]

def test_sitemap_rejects_doctype_and_entities() -> None:
    with pytest.raises(ValueError, match="entities"):
        extract_sitemap_urls(b'<!DOCTYPE foo [<!ENTITY x "boom">]><urlset/>')
    with pytest.raises(ValueError, match="malformed"):
        extract_sitemap_urls(b"<urlset>")

def test_parse_robots_rules_and_sitemaps() -> None:
    robots = """
User-agent: *
Disallow: /private
Allow: /private/public
Sitemap: https://example.com/sitemap.xml
"""
    parser, sitemaps = parse_robots("https://example.com/robots.txt", robots)
    assert parser.can_fetch("ApokolipsSpider/0.2", "https://example.com/public")
    assert not parser.can_fetch("ApokolipsSpider/0.2", "https://example.com/private")
    assert parser.can_fetch("ApokolipsSpider/0.2", "https://example.com/private/public")
    assert sitemaps == ["https://example.com/sitemap.xml"]
