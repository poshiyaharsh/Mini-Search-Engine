"""
Mini Search Engine - Breadth-First Web Crawler
==============================================
A polite, lightweight web crawler that respects robots.txt, extracts clean text
from web pages, and stores them in a crawled_pages/ directory to be indexed by
the TF-IDF search engine.
"""

import os
import re
import json
import time
import hashlib
from datetime import datetime, timezone
from collections import deque
from urllib.parse import urlparse, urljoin
import urllib.robotparser

import requests
from bs4 import BeautifulSoup

DEFAULT_USER_AGENT = (
    "MiniSearchEngineBot/1.0 (+https://github.com/poshiyaharsh/Mini-Search-Engine; "
    "educational research crawler)"
)


class WebCrawler:
    def __init__(
        self,
        crawled_dir: str = "crawled_pages",
        user_agent: str = DEFAULT_USER_AGENT,
        delay_seconds: float = 1.0,
        timeout: int = 5,
    ):
        self.crawled_dir = crawled_dir
        self.user_agent = user_agent
        self.delay_seconds = delay_seconds
        self.timeout = timeout
        self.robot_parsers: dict[str, urllib.robotparser.RobotFileParser] = {}
        self.last_request_time: dict[str, float] = {}

        os.makedirs(self.crawled_dir, exist_ok=True)

    # ------------------------------------------------------------------
    # robots.txt politeness & rate limiting
    # ------------------------------------------------------------------
    def _get_robot_parser(self, scheme: str, netloc: str) -> urllib.robotparser.RobotFileParser:
        """Fetch and cache robots.txt parser for a domain."""
        domain_key = f"{scheme}://{netloc}"
        if domain_key in self.robot_parsers:
            return self.robot_parsers[domain_key]

        rp = urllib.robotparser.RobotFileParser()
        robots_url = f"{domain_key}/robots.txt"
        rp.set_url(robots_url)

        try:
            headers = {"User-Agent": self.user_agent}
            resp = requests.get(robots_url, headers=headers, timeout=self.timeout)
            if resp.status_code == 200:
                rp.parse(resp.text.splitlines())
            elif resp.status_code in (401, 403):
                # Disallow all if forbidden
                rp.disallow_all = True
            else:
                # 404 or other status: assume allowed
                rp.allow_all = True
        except Exception:
            # If robots.txt cannot be reached, default to permissive for educational crawl
            rp.allow_all = True

        self.robot_parsers[domain_key] = rp
        return rp

    def can_fetch(self, url: str) -> bool:
        """Check if robots.txt permits crawling this URL."""
        parsed = urlparse(url)
        if not parsed.netloc:
            return False
        rp = self._get_robot_parser(parsed.scheme or "https", parsed.netloc)
        try:
            return rp.can_fetch(self.user_agent, url)
        except Exception:
            return True

    def _wait_for_domain(self, netloc: str):
        """Add a polite delay between requests to the same domain."""
        now = time.time()
        last_time = self.last_request_time.get(netloc, 0.0)
        elapsed = now - last_time
        if elapsed < self.delay_seconds:
            time.sleep(self.delay_seconds - elapsed)
        self.last_request_time[netloc] = time.time()

    # ------------------------------------------------------------------
    # URL normalization & domain scoping
    # ------------------------------------------------------------------
    @staticmethod
    def normalize_url(url: str) -> str:
        """Strip fragment (#...), lowercase scheme/host, remove trailing slash."""
        parsed = urlparse(url)
        # Drop fragment and parameters
        clean_path = parsed.path or "/"
        if clean_path.endswith("/") and len(clean_path) > 1:
            clean_path = clean_path.rstrip("/")
        normalized = f"{parsed.scheme.lower()}://{parsed.netloc.lower()}{clean_path}"
        if parsed.query:
            normalized += f"?{parsed.query}"
        return normalized

    @staticmethod
    def is_same_or_subdomain(netloc: str, allowed_domains: set[str]) -> bool:
        netloc = netloc.lower()
        for allowed in allowed_domains:
            allowed = allowed.lower()
            if netloc == allowed or netloc.endswith("." + allowed):
                return True
        return False

    # ------------------------------------------------------------------
    # HTML Parsing & Content Extraction
    # ------------------------------------------------------------------
    def extract_page_data(self, html: str, base_url: str):
        """Extract clean page title, visible text, and outbound links."""
        soup = BeautifulSoup(html, "html.parser")

        # 1. Extract title
        title = ""
        if soup.title and soup.title.string:
            title = soup.title.string.strip()
        if not title:
            h1 = soup.find("h1")
            if h1:
                title = h1.get_text(strip=True)
        if not title:
            parsed = urlparse(base_url)
            title = parsed.path.strip("/") or parsed.netloc

        # 2. Extract outbound links before removing navigational tags
        outbound_links = []
        for a_tag in soup.find_all("a", href=True):
            href = a_tag["href"].strip()
            if not href or href.startswith(("javascript:", "mailto:", "tel:", "#")):
                continue
            resolved = urljoin(base_url, href)
            parsed_res = urlparse(resolved)
            if parsed_res.scheme in ("http", "https") and parsed_res.netloc:
                outbound_links.append(self.normalize_url(resolved))

        # 3. Strip non-content and layout elements
        for tag in soup([
            "script", "style", "nav", "footer", "header",
            "noscript", "svg", "aside", "form", "button", "iframe"
        ]):
            tag.decompose()

        # 4. Extract visible body text
        text = soup.get_text(separator=" ", strip=True)
        # Collapse multiple whitespace characters
        text = re.sub(r"\s+", " ", text).strip()

        return {
            "title": title,
            "text": text,
            "outbound_links": outbound_links,
        }

    # ------------------------------------------------------------------
    # Main Breadth-First Crawl Loop
    # ------------------------------------------------------------------
    def crawl(
        self,
        seed_urls: list[str],
        max_pages: int = 10,
        max_depth: int = 2,
        allowed_domains: list[str] | None = None,
    ) -> dict:
        """
        Executes a breadth-first crawl starting from seed_urls.
        Returns a summary report and list of crawled page objects.
        """
        if not seed_urls:
            return {
                "pages_crawled": 0,
                "pages_skipped": 0,
                "errors": ["No seed URLs provided."],
                "pages": [],
            }

        # Normalize seeds and determine allowed domains
        queue = deque()
        visited = set()
        domains_filter = set(allowed_domains) if allowed_domains else set()

        for raw_seed in seed_urls:
            raw_seed = raw_seed.strip()
            if not raw_seed:
                continue
            if not re.match(r"^https?://", raw_seed, re.I):
                raw_seed = "https://" + raw_seed
            norm_seed = self.normalize_url(raw_seed)
            parsed = urlparse(norm_seed)
            if parsed.netloc:
                queue.append((norm_seed, 0))
                visited.add(norm_seed)
                if not allowed_domains:
                    domains_filter.add(parsed.netloc.lower())

        crawled_pages = []
        skipped_count = 0
        errors = []

        headers = {
            "User-Agent": self.user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }

        while queue and len(crawled_pages) < max_pages:
            current_url, depth = queue.popleft()
            parsed_current = urlparse(current_url)

            # Check robots.txt
            if not self.can_fetch(current_url):
                skipped_count += 1
                continue

            # Respect per-domain delay
            self._wait_for_domain(parsed_current.netloc)

            try:
                # Stream first to inspect headers before downloading large content
                with requests.get(
                    current_url,
                    headers=headers,
                    timeout=self.timeout,
                    stream=True,
                    allow_redirects=True,
                ) as resp:
                    if resp.status_code != 200:
                        skipped_count += 1
                        continue

                    content_type = resp.headers.get("content-type", "").lower()
                    if "text/html" not in content_type:
                        skipped_count += 1
                        continue

                    # Limit read size to 1.5MB to protect memory
                    html = resp.raw.read(1_500_000).decode(resp.encoding or "utf-8", errors="replace")

            except requests.RequestException as e:
                errors.append(f"{current_url}: {type(e).__name__} - {str(e)[:80]}")
                skipped_count += 1
                continue
            except Exception as e:
                errors.append(f"{current_url}: Unexpected error - {str(e)[:80]}")
                skipped_count += 1
                continue

            # Parse HTML
            page_data = self.extract_page_data(html, current_url)

            # Skip pages with virtually no text
            if len(page_data["text"].split()) < 5:
                skipped_count += 1
                continue

            page_record = {
                "url": current_url,
                "title": page_data["title"] or current_url,
                "text": page_data["text"],
                "domain": parsed_current.netloc,
                "depth": depth,
                "crawled_at": datetime.now(timezone.utc).isoformat(),
            }

            # Save page record to disk
            url_hash = hashlib.md5(current_url.encode("utf-8")).hexdigest()
            file_path = os.path.join(self.crawled_dir, f"{url_hash}.json")
            try:
                with open(file_path, "w", encoding="utf-8") as f:
                    json.dump(page_record, f, ensure_ascii=False, indent=2)
            except IOError as e:
                errors.append(f"Failed to save {current_url} to disk: {e}")

            crawled_pages.append(page_record)

            # If depth limit not reached, queue outbound links within domain scope
            if depth < max_depth:
                for link in page_data["outbound_links"]:
                    if link not in visited and len(visited) < max_pages * 5:
                        visited.add(link)
                        link_netloc = urlparse(link).netloc
                        if self.is_same_or_subdomain(link_netloc, domains_filter):
                            queue.append((link, depth + 1))

        return {
            "pages_crawled": len(crawled_pages),
            "pages_skipped": skipped_count,
            "errors": errors,
            "pages": crawled_pages,
        }

    # ------------------------------------------------------------------
    # Load all previously crawled pages from disk
    # ------------------------------------------------------------------
    def load_saved_pages(self) -> list[dict]:
        """Loads all JSON page records stored in crawled_dir."""
        if not os.path.isdir(self.crawled_dir):
            return []
        pages = []
        for fname in sorted(os.listdir(self.crawled_dir)):
            if fname.endswith(".json"):
                fpath = os.path.join(self.crawled_dir, fname)
                try:
                    with open(fpath, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    if "url" in data and "text" in data:
                        pages.append(data)
                except Exception:
                    continue
        return pages


if __name__ == "__main__":
    # Test crawler CLI
    import sys
    test_seed = sys.argv[1] if len(sys.argv) > 1 else "https://en.wikipedia.org/wiki/Search_engine"
    print(f"Testing crawler with seed: {test_seed}")
    crawler = WebCrawler(crawled_dir="crawled_pages", delay_seconds=1.0)
    report = crawler.crawl([test_seed], max_pages=3, max_depth=1)
    print(f"Crawled: {report['pages_crawled']} pages, Skipped: {report['pages_skipped']}, Errors: {len(report['errors'])}")
    for p in report["pages"]:
        print(f" - {p['title']} ({p['url']}) [len={len(p['text'])} chars]")
