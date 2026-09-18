"""
Mini Search Engine - Hardened Breadth-First Web Crawler
======================================================
A polite, lightweight web crawler that respects robots.txt, extracts clean text
from web pages, and stores them in a crawled_pages/ directory to be indexed by
the TF-IDF search engine.

Security Hardening:
  - Strict SSRF (Server-Side Request Forgery) protection blocking loopback, private,
    link-local (cloud metadata), multicast, and reserved IP address spaces.
  - Safe redirect validation verifying every hop against SSRF rules.
  - Strict HTTP/HTTPS scheme enforcement.
  - Safe filename hashing (MD5) to prevent path traversal.
  - Response size capping to mitigate zip bombs / memory exhaustion.
  - Strict timeouts to prevent denial-of-service via slowloris endpoints.
"""

import os
import re
import json
import time
import socket
import hashlib
import ipaddress
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

# Prohibited local hostname patterns
BLOCKED_HOSTNAMES = {
    "localhost",
    "localhost.localdomain",
    "0.0.0.0",
    "127.0.0.1",
    "::1",
    "metadata.google.internal",
    "instance-data",
}


def is_safe_url(url: str) -> tuple[bool, str]:
    """
    Validates that a URL uses http/https and does NOT resolve to private,
    loopback, link-local (e.g. AWS 169.254.169.254), or reserved IP ranges.
    """
    try:
        parsed = urlparse(url)
        scheme = parsed.scheme.lower() if parsed.scheme else ""
        if scheme not in ("http", "https"):
            return False, f"Unsupported scheme '{scheme}'. Only HTTP and HTTPS are permitted."

        hostname = parsed.hostname
        if not hostname:
            return False, "Missing hostname in URL."

        clean_host = hostname.lower().strip("[]")
        if clean_host in BLOCKED_HOSTNAMES or clean_host.endswith(".local"):
            return False, f"Access to local target '{hostname}' is prohibited."

        # Attempt to parse as raw IP address first
        try:
            raw_ip = ipaddress.ip_address(clean_host)
            if (
                raw_ip.is_loopback
                or raw_ip.is_private
                or raw_ip.is_link_local
                or raw_ip.is_multicast
                or raw_ip.is_reserved
                or raw_ip.is_unspecified
                or str(raw_ip) == "169.254.169.254"
            ):
                return False, f"Direct access to private/reserved IP '{raw_ip}' is prohibited."
        except ValueError:
            # Not a raw IP literal, proceed to DNS resolution
            pass

        # Resolve hostname to all candidate IP addresses
        port = parsed.port or (443 if scheme == "https" else 80)
        try:
            addr_info = socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
        except socket.gaierror as e:
            return False, f"DNS resolution failed for '{hostname}': {e}"

        if not addr_info:
            return False, f"No DNS records found for '{hostname}'."

        for entry in addr_info:
            ip_str = entry[4][0]
            ip = ipaddress.ip_address(ip_str)
            if (
                ip.is_loopback
                or ip.is_private
                or ip.is_link_local
                or ip.is_multicast
                or ip.is_reserved
                or ip.is_unspecified
                or ip_str == "169.254.169.254"
            ):
                return False, f"Hostname '{hostname}' resolves to private/prohibited IP '{ip_str}'."

        return True, ""
    except Exception as e:
        return False, f"URL security check failed: {e}"


class WebCrawler:
    def __init__(
        self,
        crawled_dir: str = "crawled_pages",
        user_agent: str = DEFAULT_USER_AGENT,
        delay_seconds: float = 1.0,
        connect_timeout: float = 3.0,
        read_timeout: float = 5.0,
        max_redirects: int = 4,
        max_page_bytes: int = 1_500_000,
    ):
        self.crawled_dir = crawled_dir
        self.user_agent = user_agent
        self.delay_seconds = max(0.5, delay_seconds)
        self.timeout = (connect_timeout, read_timeout)
        self.max_redirects = max_redirects
        self.max_page_bytes = max_page_bytes

        self.robot_parsers: dict[str, urllib.robotparser.RobotFileParser] = {}
        self.last_request_time: dict[str, float] = {}

        os.makedirs(self.crawled_dir, exist_ok=True)

    # ------------------------------------------------------------------
    # SSRF-Safe HTTP Fetcher with Redirect Validation
    # ------------------------------------------------------------------
    def safe_fetch(self, url: str, headers: dict) -> requests.Response:
        """
        Executes an HTTP GET request while strictly validating every redirect
        hop against SSRF rules to prevent SSRF bypass via 30x redirects.
        """
        current_url = url
        for _ in range(self.max_redirects + 1):
            safe, reason = is_safe_url(current_url)
            if not safe:
                raise ValueError(f"SSRF blocked '{current_url}': {reason}")

            resp = requests.get(
                current_url,
                headers=headers,
                timeout=self.timeout,
                stream=True,
                allow_redirects=False,
            )

            # Follow redirects manually with SSRF checks on each hop
            if resp.is_redirect or resp.status_code in (301, 302, 303, 307, 308):
                location = resp.headers.get("Location")
                if not location:
                    break
                current_url = urljoin(current_url, location)
                continue

            return resp

        raise requests.TooManyRedirects(f"Exceeded {self.max_redirects} redirects.")

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

        # Validate robots.txt URL against SSRF before requesting
        safe, reason = is_safe_url(robots_url)
        if not safe:
            rp.disallow_all = True
            self.robot_parsers[domain_key] = rp
            return rp

        try:
            headers = {"User-Agent": self.user_agent}
            resp = self.safe_fetch(robots_url, headers=headers)
            if resp.status_code == 200:
                text = resp.text
                rp.parse(text.splitlines())
            elif resp.status_code in (401, 403):
                rp.disallow_all = True
            else:
                rp.allow_all = True
        except Exception:
            # If robots.txt unreachable, default to permissive for public sites
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

        # Sanitize title length
        title = re.sub(r"\s+", " ", title).strip()[:200]

        # 2. Extract outbound links before removing navigational tags
        outbound_links = []
        for a_tag in soup.find_all("a", href=True):
            href = a_tag["href"].strip()
            if not href or href.startswith(("javascript:", "mailto:", "tel:", "#", "data:")):
                continue
            resolved = urljoin(base_url, href)
            parsed_res = urlparse(resolved)
            if parsed_res.scheme in ("http", "https") and parsed_res.netloc:
                outbound_links.append(self.normalize_url(resolved))

        # 3. Strip non-content and layout elements
        for tag in soup([
            "script", "style", "nav", "footer", "header",
            "noscript", "svg", "aside", "form", "button", "iframe", "meta", "link"
        ]):
            tag.decompose()

        # 4. Extract visible body text
        text = soup.get_text(separator=" ", strip=True)
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

        # Normalize seeds, validate SSRF upfront, and determine allowed domains
        queue = deque()
        visited = set()
        domains_filter = set(allowed_domains) if allowed_domains else set()
        errors = []
        skipped_count = 0

        for raw_seed in seed_urls:
            raw_seed = raw_seed.strip()
            if not raw_seed:
                continue
            if not re.match(r"^https?://", raw_seed, re.I):
                raw_seed = "https://" + raw_seed

            norm_seed = self.normalize_url(raw_seed)
            safe, reason = is_safe_url(norm_seed)
            if not safe:
                errors.append(f"Skipped unsafe seed URL '{raw_seed}': {reason}")
                skipped_count += 1
                continue

            parsed = urlparse(norm_seed)
            if parsed.netloc and norm_seed not in visited:
                queue.append((norm_seed, 0))
                visited.add(norm_seed)
                if not allowed_domains:
                    domains_filter.add(parsed.netloc.lower())

        crawled_pages = []

        headers = {
            "User-Agent": self.user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }

        while queue and len(crawled_pages) < max_pages:
            current_url, depth = queue.popleft()
            parsed_current = urlparse(current_url)

            # SSRF re-check on dequeue
            safe, reason = is_safe_url(current_url)
            if not safe:
                errors.append(f"SSRF violation '{current_url}': {reason}")
                skipped_count += 1
                continue

            # Check robots.txt
            if not self.can_fetch(current_url):
                skipped_count += 1
                continue

            # Respect per-domain delay
            self._wait_for_domain(parsed_current.netloc)

            try:
                resp = self.safe_fetch(current_url, headers=headers)
                if resp.status_code != 200:
                    skipped_count += 1
                    continue

                content_type = resp.headers.get("content-type", "").lower()
                if "text/html" not in content_type:
                    skipped_count += 1
                    continue

                # Read up to max_page_bytes with automatic gzip/deflate decompression
                chunks = []
                total_bytes = 0
                for chunk in resp.iter_content(chunk_size=8192):
                    chunks.append(chunk)
                    total_bytes += len(chunk)
                    if total_bytes >= self.max_page_bytes:
                        break
                raw_bytes = b"".join(chunks)
                html = raw_bytes.decode(resp.encoding or "utf-8", errors="replace")

            except requests.RequestException as e:
                errors.append(f"{current_url}: {type(e).__name__} - {str(e)[:80]}")
                skipped_count += 1
                continue
            except ValueError as e:
                errors.append(f"{current_url}: Blocked - {str(e)[:80]}")
                skipped_count += 1
                continue
            except Exception as e:
                errors.append(f"{current_url}: Unexpected error - {str(e)[:80]}")
                skipped_count += 1
                continue

            # Parse HTML
            page_data = self.extract_page_data(html, current_url)

            # Skip pages with insufficient text
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

            # Safe filename: hex MD5 hash prevents path traversal
            url_hash = hashlib.md5(current_url.encode("utf-8")).hexdigest()
            file_path = os.path.join(self.crawled_dir, f"{url_hash}.json")
            try:
                with open(file_path, "w", encoding="utf-8") as f:
                    json.dump(page_record, f, ensure_ascii=False, indent=2)
            except IOError as e:
                errors.append(f"Failed to save {current_url} to disk: {e}")

            crawled_pages.append(page_record)

            # Queue outbound links within domain scope
            if depth < max_depth:
                for link in page_data["outbound_links"]:
                    if link not in visited and len(visited) < max_pages * 5:
                        visited.add(link)
                        link_netloc = urlparse(link).netloc
                        if self.is_same_or_subdomain(link_netloc, domains_filter):
                            # Pre-check SSRF before queuing
                            safe_link, _ = is_safe_url(link)
                            if safe_link:
                                queue.append((link, depth + 1))

        return {
            "pages_crawled": len(crawled_pages),
            "pages_skipped": skipped_count,
            "errors": errors,
            "pages": crawled_pages,
        }

    # ------------------------------------------------------------------
    # Load all previously crawled pages from disk safely
    # ------------------------------------------------------------------
    def load_saved_pages(self) -> list[dict]:
        """Loads all valid JSON page records stored in crawled_dir."""
        if not os.path.isdir(self.crawled_dir):
            return []
        pages = []
        canonical_base = os.path.abspath(self.crawled_dir)

        for fname in sorted(os.listdir(self.crawled_dir)):
            if fname.endswith(".json") and re.match(r"^[a-f0-9]{32}\.json$", fname):
                fpath = os.path.join(self.crawled_dir, fname)
                # Verify path traversal safety
                if not os.path.abspath(fpath).startswith(canonical_base):
                    continue
                try:
                    with open(fpath, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    if isinstance(data, dict) and "url" in data and "text" in data:
                        pages.append(data)
                except Exception:
                    continue
        return pages
