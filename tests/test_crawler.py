"""
Unit and integration tests for crawler.py
Covers:
  - SSRF defense checks (is_safe_url) against private IPs, loopback, and cloud metadata
  - robots.txt compliance using mocked HTTP responses (responses library)
  - Breadth-first crawl traversal and depth/page limits
  - Content extraction, tag cleaning, and malformed HTML handling
  - URL normalization and domain scoping
"""

import os
import json
import pytest
import responses
from crawler import is_safe_url, WebCrawler


class TestSSRFDefense:
    """Tests for SSRF URL validation."""

    def test_blocks_localhost_and_loopback(self):
        blocked = [
            "http://localhost:5000",
            "http://127.0.0.1:8080",
            "http://127.0.0.2",
            "http://[::1]/secret",
        ]
        for url in blocked:
            safe, reason = is_safe_url(url)
            assert safe is False, f"Expected {url} to be blocked, but was marked safe."
            assert len(reason) > 0

    def test_blocks_cloud_metadata(self):
        metadata_urls = [
            "http://169.254.169.254/latest/meta-data/",
            "http://metadata.google.internal/computeMetadata/v1/",
            "http://instance-data/latest/meta-data/",
        ]
        for url in metadata_urls:
            safe, reason = is_safe_url(url)
            assert safe is False, f"Expected {url} to be blocked."

    def test_blocks_private_ip_subnets(self):
        private_ips = [
            "http://10.0.0.1/admin",
            "http://192.168.1.100/router",
            "http://172.16.0.1/dashboard",
        ]
        for url in private_ips:
            safe, _ = is_safe_url(url)
            assert safe is False

    def test_blocks_unsupported_schemes(self):
        invalid_schemes = [
            "file:///etc/passwd",
            "ftp://ftp.example.com/file.txt",
            "gopher://gopher.floodgap.com",
            "javascript:alert(1)",
        ]
        for url in invalid_schemes:
            safe, _ = is_safe_url(url)
            assert safe is False

    def test_allows_public_https_domains(self):
        # Public domains with valid public DNS
        safe, _ = is_safe_url("https://en.wikipedia.org/wiki/Search_engine")
        assert safe is True


class TestRobotsAndPoliteness:
    """Tests for robots.txt parsing and fetch compliance using mocked HTTP."""

    @responses.activate
    def test_robots_txt_disallow_rule_respected(self, tmp_path):
        crawled_dir = str(tmp_path / "crawled")
        crawler = WebCrawler(crawled_dir=crawled_dir, delay_seconds=0.0)

        # Mock robots.txt with disallow rule
        responses.add(
            responses.GET,
            "https://testsite.org/robots.txt",
            body="User-agent: *\nDisallow: /admin/\nDisallow: /private/\nAllow: /public/\n",
            status=200,
            content_type="text/plain",
        )

        assert crawler.can_fetch("https://testsite.org/public/article") is True
        assert crawler.can_fetch("https://testsite.org/admin/dashboard") is False
        assert crawler.can_fetch("https://testsite.org/private/secret") is False

    @responses.activate
    def test_robots_txt_404_defaults_to_permissive(self, tmp_path):
        crawled_dir = str(tmp_path / "crawled")
        crawler = WebCrawler(crawled_dir=crawled_dir, delay_seconds=0.0)

        responses.add(
            responses.GET,
            "https://open-site.org/robots.txt",
            status=404,
        )

        assert crawler.can_fetch("https://open-site.org/any/page") is True


class TestCrawlExecutionAndLimits:
    """Tests for BFS crawl queue, link discovery, and page limits."""

    @responses.activate
    def test_crawl_discovers_links_and_terminates_at_max_pages(self, tmp_path, monkeypatch):
        # Mock is_safe_url so tests don't rely on live DNS lookups for mock domains
        monkeypatch.setattr("crawler.is_safe_url", lambda url: (True, "Safe"))

        crawled_dir = str(tmp_path / "crawled")
        crawler = WebCrawler(crawled_dir=crawled_dir, delay_seconds=0.0)

        # Mock robots.txt
        responses.add(
            responses.GET,
            "https://mockednews.org/robots.txt",
            body="User-agent: *\nDisallow: /secret/\n",
            status=200,
        )

        # Mock seed page with links
        page1_html = """
        <!DOCTYPE html>
        <html>
        <head><title>Mocked News Home</title></head>
        <body>
          <h1>Welcome to Mocked News</h1>
          <p>Today in computer science and machine learning research.</p>
          <a href="/tech">Tech News</a>
          <a href="/secret/hidden">Hidden Private Area</a>
          <a href="https://otherdomain.com/outside">External Site</a>
        </body>
        </html>
        """
        responses.add(
            responses.GET,
            "https://mockednews.org/home",
            body=page1_html,
            status=200,
            content_type="text/html",
        )

        # Mock page 2
        page2_html = """
        <!DOCTYPE html>
        <html>
        <head><title>Tech News</title></head>
        <body>
          <h1>Technology Updates</h1>
          <p>Artificial intelligence and neural network systems update.</p>
          <a href="/science">Science News</a>
        </body>
        </html>
        """
        responses.add(
            responses.GET,
            "https://mockednews.org/tech",
            body=page2_html,
            status=200,
            content_type="text/html",
        )

        # Run crawl with max_pages=2
        report = crawler.crawl(
            seed_urls=["https://mockednews.org/home"],
            max_pages=2,
            max_depth=2,
        )

        assert report["pages_crawled"] == 2
        crawled_urls = [p["url"] for p in report["pages"]]
        assert "https://mockednews.org/home" in crawled_urls
        assert "https://mockednews.org/tech" in crawled_urls
        # Disallowed URL should never be crawled
        assert "https://mockednews.org/secret/hidden" not in crawled_urls

        # Confirm 2 JSON files saved to crawled_dir
        saved_files = [f for f in os.listdir(crawled_dir) if f.endswith(".json")]
        assert len(saved_files) == 2

        with open(os.path.join(crawled_dir, saved_files[0]), "r", encoding="utf-8") as f:
            saved_doc = json.load(f)
            assert "url" in saved_doc
            assert "text" in saved_doc
            assert "title" in saved_doc


class TestTextCleaningAndURLNormalization:
    """Tests for HTML parsing, boilerplate stripping, and URL normalization."""

    def test_extract_clean_text_strips_boilerplate(self, tmp_path):
        crawler = WebCrawler(crawled_dir=str(tmp_path), delay_seconds=0.0)
        html = """
        <html>
          <head>
            <title>Test Page Title</title>
            <script>var x = 10; function hide() {}</script>
            <style>body { background: red; }</style>
          </head>
          <body>
            <header><nav>Home | About | Contact</nav></header>
            <main>
              <h1>Real Article Heading</h1>
              <p>This is the important core content of the article.</p>
            </main>
            <footer>Copyright 2026. All rights reserved.</footer>
          </body>
        </html>
        """
        data = crawler.extract_page_data(html, "https://example.com")
        assert data["title"] == "Test Page Title"
        assert "Real Article Heading" in data["text"]
        assert "important core content" in data["text"]
        # Boilerplate tags stripped
        assert "var x = 10" not in data["text"]
        assert "background: red" not in data["text"]

    def test_extract_clean_text_handles_malformed_html(self, tmp_path):
        crawler = WebCrawler(crawled_dir=str(tmp_path), delay_seconds=0.0)
        bad_html = "<div><p>Unclosed paragraph <b>bold text without end"
        data = crawler.extract_page_data(bad_html, "https://example.com/page")
        assert "Unclosed paragraph" in data["text"]
        assert "bold text" in data["text"]

    def test_url_normalization(self):
        assert WebCrawler.normalize_url("HTTPS://Example.COM/Path/") == "https://example.com/Path"
        assert WebCrawler.normalize_url("http://example.com/page#section1") == "http://example.com/page"
        assert WebCrawler.normalize_url("https://example.com/search?q=test") == "https://example.com/search?q=test"
