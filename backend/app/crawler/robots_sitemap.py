import xml.etree.ElementTree as ET
from urllib.robotparser import RobotFileParser

from app.crawler.fetch import FetchError, safe_fetch
from app.crawler.security import CrawlSecurityPolicy

SITEMAP_NS = "{http://www.sitemaps.org/schemas/sitemap/0.9}"
MAX_SITEMAP_RECURSION = 3


async def fetch_robots(base_url: str, policy: CrawlSecurityPolicy) -> tuple[RobotFileParser, list[str]]:
    robots_url = base_url.rstrip("/") + "/robots.txt"
    parser = RobotFileParser()
    sitemap_urls: list[str] = []
    try:
        result = await safe_fetch(robots_url, policy)
    except FetchError:
        parser.parse([])  # no reachable robots.txt — default to allow-all
        return parser, sitemap_urls

    lines = result.text.splitlines()
    parser.parse(lines)
    sitemap_urls = [line.split(":", 1)[1].strip() for line in lines if line.lower().startswith("sitemap:")]
    return parser, sitemap_urls


async def fetch_sitemap_urls(sitemap_url: str, policy: CrawlSecurityPolicy, _depth: int = 0) -> list[str]:
    if _depth > MAX_SITEMAP_RECURSION:
        return []
    try:
        result = await safe_fetch(sitemap_url, policy)
    except FetchError:
        return []

    try:
        root = ET.fromstring(result.text)
    except ET.ParseError:
        return []

    urls: list[str] = []
    if root.tag.endswith("sitemapindex"):
        for sitemap in root.findall(f"{SITEMAP_NS}sitemap"):
            loc = sitemap.find(f"{SITEMAP_NS}loc")
            if loc is not None and loc.text:
                urls.extend(await fetch_sitemap_urls(loc.text.strip(), policy, _depth + 1))
    else:
        for url_el in root.findall(f"{SITEMAP_NS}url"):
            loc = url_el.find(f"{SITEMAP_NS}loc")
            if loc is not None and loc.text:
                urls.append(loc.text.strip())
    return urls
