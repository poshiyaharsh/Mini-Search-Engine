"""
Mini Search Engine - Hardened Flask Backend
===========================================
Serves the HTML/JS frontend, exposes the TF-IDF search API, and provides a
crawling endpoint to index live web pages.

Security Hardening:
  - Strict input validation and query size capping
  - SSRF pre-screening on crawl seed URLs
  - Concurrency locks preventing crawl/reindex race conditions
  - In-memory rate limiting per client IP
  - Security headers (CSP, X-Frame-Options, X-Content-Type-Options)
  - Safe error handling preventing traceback leakage
  - Production-safe debug configuration
"""

import os
import re
import time
import logging
import threading
from collections import defaultdict
from flask import Flask, request, jsonify, render_template

from search_engine import SearchEngine
from crawler import WebCrawler, is_safe_url

# Configure structured logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("MiniSearchEngine")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DOC_DIR = os.path.join(BASE_DIR, "documents")
CRAWLED_DIR = os.path.join(BASE_DIR, "crawled_pages")

os.makedirs(DOC_DIR, exist_ok=True)
os.makedirs(CRAWLED_DIR, exist_ok=True)

app = Flask(__name__)

# Enforce 1MB maximum payload size
app.config["MAX_CONTENT_LENGTH"] = 1 * 1024 * 1024

# Concurrency lock for web crawling & reindexing
crawl_lock = threading.Lock()

# Initialize core services
engine = SearchEngine(doc_dir=DOC_DIR, crawled_dir=CRAWLED_DIR)
crawler = WebCrawler(crawled_dir=CRAWLED_DIR, delay_seconds=1.0)

# ------------------------------------------------------------------
# Lightweight In-Memory Rate Limiter
# ------------------------------------------------------------------
rate_limit_lock = threading.Lock()
request_history: dict[str, list[float]] = defaultdict(list)


def check_rate_limit(client_ip: str, max_requests: int, window_seconds: int) -> bool:
    """Returns True if within rate limit, False if limit exceeded."""
    now = time.time()
    with rate_limit_lock:
        timestamps = request_history[client_ip]
        # Prune timestamps outside window
        request_history[client_ip] = [t for t in timestamps if now - t < window_seconds]
        if len(request_history[client_ip]) >= max_requests:
            return False
        request_history[client_ip].append(now)
        return True


# ------------------------------------------------------------------
# Security Headers & Global Error Handlers
# ------------------------------------------------------------------
@app.after_request
def set_security_headers(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "font-src 'self' https://fonts.gstatic.com; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "img-src 'self' data: https:; "
        "connect-src 'self'; "
        "frame-ancestors 'none';"
    )
    return response


@app.errorhandler(400)
def handle_bad_request(e):
    return jsonify({"error": str(getattr(e, "description", "Bad request."))}), 400


@app.errorhandler(404)
def handle_not_found(e):
    return jsonify({"error": "Resource not found."}), 404


@app.errorhandler(405)
def handle_method_not_allowed(e):
    return jsonify({"error": "Method not allowed."}), 405


@app.errorhandler(413)
def handle_payload_too_large(e):
    return jsonify({"error": "Payload too large. Maximum size is 1MB."}), 413


@app.errorhandler(429)
def handle_too_many_requests(e):
    return jsonify({"error": "Too many requests. Please slow down."}), 429


@app.errorhandler(500)
def handle_internal_error(e):
    logger.error("Internal Server Error: %s", e, exc_info=True)
    return jsonify({"error": "An internal server error occurred."}), 500


# ------------------------------------------------------------------
# Routes
# ------------------------------------------------------------------
@app.route("/")
def home():
    return render_template("index.html", doc_count=engine.N)


@app.route("/api/search")
def api_search():
    client_ip = request.remote_addr or "unknown"
    if not check_rate_limit(f"search:{client_ip}", max_requests=80, window_seconds=60):
        return jsonify({"error": "Search rate limit exceeded. Please wait a moment."}), 429

    raw_query = request.args.get("q", "")
    if not isinstance(raw_query, str):
        return jsonify({"error": "Invalid query parameter."}), 400

    query = raw_query.strip()
    if len(query) > 500:
        return jsonify({"error": "Search query too long (max 500 characters)."}), 400

    # Parse algorithm ('bm25' or 'cosine', default 'bm25')
    raw_algo = request.args.get("algo", "bm25").lower().strip()
    algo = "cosine" if raw_algo == "cosine" else "bm25"

    # Parse source filter ('all', 'local', 'web')
    raw_source = request.args.get("source", "all").lower().strip()
    if raw_source in ("file", "local"):
        source_filter = "local"
    elif raw_source == "web":
        source_filter = "web"
    else:
        source_filter = "all"

    # Parse min_score cutoff
    raw_min_score = request.args.get("min_score", "0.0")
    try:
        min_score = max(0.0, min(float(raw_min_score), 100.0))
    except (ValueError, TypeError):
        min_score = 0.0

    if not query:
        return jsonify({
            "query": "",
            "algo": algo,
            "source": source_filter,
            "min_score": min_score,
            "count": 0,
            "results": [],
            "total_indexed": engine.N,
        })

    try:
        results = engine.search(
            query,
            top_k=15,
            algo=algo,
            source_filter=source_filter,
            min_score=min_score,
        )
        return jsonify({
            "query": query,
            "algo": algo,
            "source": source_filter,
            "min_score": min_score,
            "count": len(results),
            "results": results,
            "total_indexed": engine.N,
        })
    except Exception as e:
        logger.error("Search execution error: %s", e, exc_info=True)
        return jsonify({"error": "Search execution failed."}), 500


@app.route("/api/suggest")
def api_suggest():
    """Returns top vocabulary completions for prefix starting characters."""
    client_ip = request.remote_addr or "unknown"
    if not check_rate_limit(f"suggest:{client_ip}", max_requests=150, window_seconds=60):
        return jsonify({"error": "Suggestions rate limit exceeded. Please slow down."}), 429

    raw_prefix = request.args.get("prefix", "")
    if not isinstance(raw_prefix, str):
        return jsonify({"prefix": "", "suggestions": []})

    prefix = raw_prefix.strip()[:60]
    if not prefix:
        return jsonify({"prefix": "", "suggestions": []})

    # Only accept alphanumeric prefix tokens
    if not re.match(r"^[a-zA-Z0-9']+$", prefix):
        return jsonify({"prefix": prefix, "suggestions": []})

    try:
        limit = max(1, min(int(request.args.get("limit", 8)), 20))
    except (ValueError, TypeError):
        limit = 8

    try:
        suggestions = engine.suggest(prefix, limit=limit)
        return jsonify({
            "prefix": prefix,
            "suggestions": suggestions,
        })
    except Exception as e:
        logger.error("Suggest execution error: %s", e, exc_info=True)
        return jsonify({"error": "Failed to generate suggestions."}), 500


@app.route("/api/stats")
def api_stats():
    try:
        return jsonify(engine.stats())
    except Exception as e:
        logger.error("Stats retrieval error: %s", e, exc_info=True)
        return jsonify({"error": "Failed to retrieve stats."}), 500


@app.route("/api/term/<term>")
def api_term(term):
    """Debug endpoint: inspect the inverted index / IDF for a single word."""
    if not term or not isinstance(term, str):
        return jsonify({"error": "Invalid term."}), 400

    clean_term = term.strip()[:60]
    # Path traversal & injection guard: only allow word tokens
    if not re.match(r"^[a-zA-Z0-9']+$", clean_term):
        return jsonify({"error": "Term must be an alphanumeric word token."}), 400

    try:
        return jsonify(engine.posting_list(clean_term))
    except Exception as e:
        logger.error("Term posting list lookup error: %s", e, exc_info=True)
        return jsonify({"error": "Failed to lookup term."}), 500


@app.route("/api/crawl", methods=["POST"])
def api_crawl():
    """
    Crawls web pages starting from seed URLs, saves them, and refreshes the search index.
    Expects JSON body: {"seed_urls": [...], "max_pages": 10, "max_depth": 2}
    """
    client_ip = request.remote_addr or "unknown"
    if not check_rate_limit(f"crawl:{client_ip}", max_requests=6, window_seconds=60):
        return jsonify({"error": "Crawl rate limit exceeded (maximum 6 crawl requests per minute)."}), 429

    if not request.is_json:
        return jsonify({"error": "Request Content-Type must be application/json."}), 400

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "Malformed JSON payload."}), 400

    raw_seeds = data.get("seed_urls", [])
    if isinstance(raw_seeds, str):
        raw_seeds = [s.strip() for s in raw_seeds.replace(",", "\n").splitlines() if s.strip()]
    elif not isinstance(raw_seeds, list):
        return jsonify({"error": "seed_urls must be a list or newline-separated string."}), 400

    seed_urls = [str(s).strip() for s in raw_seeds if str(s).strip()]
    if not seed_urls:
        return jsonify({"error": "No seed URLs provided. Please provide at least one valid URL."}), 400

    if len(seed_urls) > 10:
        return jsonify({"error": "Too many seed URLs provided (maximum 10)."}), 400

    # SSRF Pre-Validation
    valid_seeds = []
    rejected_seeds = []
    for s in seed_urls:
        if not re.match(r"^https?://", s, re.I):
            s = "https://" + s
        safe, reason = is_safe_url(s)
        if safe:
            valid_seeds.append(s)
        else:
            rejected_seeds.append({"url": s, "reason": reason})

    if not valid_seeds:
        return jsonify({
            "success": False,
            "error": "All provided seed URLs were rejected due to security restrictions (SSRF / private target protection).",
            "rejected_seeds": rejected_seeds,
            "pages_crawled": 0,
            "pages_skipped": len(rejected_seeds),
            "errors": [f"{r['url']}: {r['reason']}" for r in rejected_seeds],
            "total_documents": engine.N,
        }), 400

    try:
        max_pages = max(1, min(int(data.get("max_pages", 10)), 25))
    except (ValueError, TypeError):
        max_pages = 10

    try:
        max_depth = max(0, min(int(data.get("max_depth", 2)), 3))
    except (ValueError, TypeError):
        max_depth = 2

    # Prevent concurrent crawls from causing race conditions
    if not crawl_lock.acquire(blocking=False):
        return jsonify({
            "error": "A crawl job is already in progress. Please wait for it to complete.",
            "success": False,
        }), 429

    try:
        logger.info("Starting crawl for %d seed(s), max_pages=%d, max_depth=%d", len(valid_seeds), max_pages, max_depth)
        report = crawler.crawl(
            seed_urls=valid_seeds,
            max_pages=max_pages,
            max_depth=max_depth,
        )

        # Atomically reindex to incorporate newly crawled pages
        engine.reindex()

        all_errors = [f"{r['url']}: {r['reason']}" for r in rejected_seeds] + report["errors"]

        return jsonify({
            "success": True,
            "pages_crawled": report["pages_crawled"],
            "pages_skipped": report["pages_skipped"] + len(rejected_seeds),
            "errors": all_errors,
            "crawled_pages": [
                {"url": p["url"], "title": p["title"], "domain": p["domain"]}
                for p in report["pages"]
            ],
            "total_documents": engine.N,
        })
    except Exception as e:
        logger.error("Crawl process error: %s", e, exc_info=True)
        return jsonify({"error": f"Crawl process encountered an unexpected error: {e}"}), 500
    finally:
        crawl_lock.release()


if __name__ == "__main__":
    # Safe production config: debug mode disabled unless explicitly opted-in via env
    flask_debug = os.environ.get("FLASK_DEBUG", "0").lower() in ("1", "true")
    app.run(debug=flask_debug, host="127.0.0.1", port=5000)
