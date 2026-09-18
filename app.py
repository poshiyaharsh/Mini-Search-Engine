"""
Mini Search Engine - Flask Backend
====================================
Serves the HTML/JS frontend and exposes a small JSON API on top of the
SearchEngine class in search_engine.py.

Run with:
    python app.py
Then open http://127.0.0.1:5000 in your browser.
"""

import os
from flask import Flask, request, jsonify, render_template

from search_engine import SearchEngine

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DOC_DIR = os.path.join(BASE_DIR, "documents")

app = Flask(__name__)

# Build the index once, when the server starts.
engine = SearchEngine(DOC_DIR)


@app.route("/")
def home():
    return render_template("index.html", doc_count=engine.N)


@app.route("/api/search")
def api_search():
    query = request.args.get("q", "").strip()
    if not query:
        return jsonify({"query": "", "count": 0, "results": []})
    results = engine.search(query, top_k=10)
    return jsonify({"query": query, "count": len(results), "results": results})


@app.route("/api/stats")
def api_stats():
    return jsonify(engine.stats())


@app.route("/api/term/<term>")
def api_term(term):
    """Debug endpoint: inspect the inverted index / IDF for a single word."""
    return jsonify(engine.posting_list(term))


if __name__ == "__main__":
    app.run(debug=True, host="127.0.0.1", port=5000)
