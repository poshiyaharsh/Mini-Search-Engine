"""
Mini Search Engine - Flask Backend with Web Crawler
====================================================
Serves the HTML/JS frontend, exposes the TF-IDF search API, and provides a
crawling endpoint to index live web pages.
"""

import os
from flask import Flask, request, jsonify, render_template

from search_engine import SearchEngine
from crawler import WebCrawler

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DOC_DIR = os.path.join(BASE_DIR, "documents")
CRAWLED_DIR = os.path.join(BASE_DIR, "crawled_pages")

os.makedirs(DOC_DIR, exist_ok=True)
os.makedirs(CRAWLED_DIR, exist_ok=True)

app = Flask(__name__)

# Initialize search engine (indexes both local documents and any existing crawled pages)
engine = SearchEngine(doc_dir=DOC_DIR, crawled_dir=CRAWLED_DIR)
crawler = WebCrawler(crawled_dir=CRAWLED_DIR, delay_seconds=1.0)


@app.route("/")
def home():
    return render_template("index.html", doc_count=engine.N)


@app.route("/api/search")
def api_search():
    query = request.args.get("q", "").strip()
    if not query:
        return jsonify({"query": "", "count": 0, "results": [], "total_indexed": engine.N})
    results = engine.search(query, top_k=15)
    return jsonify({
        "query": query,
        "count": len(results),
        "results": results,
        "total_indexed": engine.N,
    })


@app.route("/api/stats")
def api_stats():
    return jsonify(engine.stats())


@app.route("/api/term/<term>")
def api_term(term):
    """Debug endpoint: inspect the inverted index / IDF for a single word."""
    return jsonify(engine.posting_list(term))


@app.route("/api/crawl", methods=["POST"])
def api_crawl():
    """
    Crawls web pages starting from seed URLs, saves them, and refreshes the search index.
    Expects JSON body: {"seed_urls": [...], "max_pages": 10, "max_depth": 2}
    """
    data = request.get_json(silent=True) or {}
    raw_seeds = data.get("seed_urls", [])
    if isinstance(raw_seeds, str):
        # Support either newline or comma-separated string
        raw_seeds = [s.strip() for s in raw_seeds.replace(",", "\n").splitlines() if s.strip()]

    seed_urls = [s.strip() for s in raw_seeds if s.strip()]
    if not seed_urls:
        return jsonify({
            "success": False,
            "error": "No seed URLs provided. Please provide at least one valid URL.",
            "pages_crawled": 0,
            "pages_skipped": 0,
            "errors": ["No seed URLs provided."],
            "total_documents": engine.N,
        }), 400

    try:
        max_pages = max(1, min(int(data.get("max_pages", 10)), 30))
    except (ValueError, TypeError):
        max_pages = 10

    try:
        max_depth = max(0, min(int(data.get("max_depth", 2)), 4))
    except (ValueError, TypeError):
        max_depth = 2

    # Execute breadth-first crawl
    report = crawler.crawl(
        seed_urls=seed_urls,
        max_pages=max_pages,
        max_depth=max_depth,
    )

    # Rebuild search engine index to incorporate the newly crawled pages
    engine.reindex()

    return jsonify({
        "success": True,
        "pages_crawled": report["pages_crawled"],
        "pages_skipped": report["pages_skipped"],
        "errors": report["errors"],
        "crawled_pages": [
            {"url": p["url"], "title": p["title"], "domain": p["domain"]}
            for p in report["pages"]
        ],
        "total_documents": engine.N,
    })


if __name__ == "__main__":
    app.run(debug=True, host="127.0.0.1", port=5000)
