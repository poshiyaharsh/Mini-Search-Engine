# Mini Search Engine + Web Crawler

A from-scratch implementation of the core ideas behind Google-style search engines:
**breadth-first web crawling (respecting robots.txt) → tokenization → inverted index → TF-IDF weighting → cosine similarity ranking**, served through a Flask API with a modern glassmorphism frontend.

No external search library (like Lucene, Elasticsearch, or Whoosh) is used anywhere. Every step is written in plain Python so you can inspect how queries turn into a ranked list of documents and web pages.

---

## Project Structure

```
mini-search-engine/
├── app.py                  # Flask app: frontend routes, search API & crawl endpoint
├── search_engine.py        # Core IR: multi-source ingestion, inverted index, TF-IDF, cosine ranking
├── crawler.py              # Web crawler: BFS queue, robots.txt compliance, HTML parser
├── requirements.txt        # Flask, requests, beautifulsoup4, lxml
├── documents/               # Local corpus: 10 sample notes/articles (.txt)
│   ├── ai_basics.txt
│   ├── python_programming.txt
│   └── ... (8 more)
├── crawled_pages/          # Persisted crawled web pages (saved as JSON)
├── templates/
│   └── index.html          # Modern glassmorphism search & crawler UI
└── static/
    ├── style.css           # Glassmorphic surfaces, animated mesh background, typography
    └── script.js           # Search API client, crawler triggers, interactive stats
```

---

## How It Works

### 1. Web Crawler (`crawler.py`)
Rather than relying on third-party search APIs, the engine crawls live web pages itself:
- **Breadth-First Traversal (BFS):** Uses a FIFO queue (`collections.deque`) seeded with starting URLs, traversing out to a configurable `max_depth` and `max_pages`.
- **`robots.txt` Compliance:** Before making a request to any domain, the crawler checks `urllib.robotparser.RobotFileParser` to verify whether `MiniSearchEngineBot` is allowed to fetch the URL. If disallowed, the page is skipped.
- **Politeness & Rate Limiting:** Implements a mandatory 1.0–2.0 second delay between consecutive requests to the same domain, with a descriptive `User-Agent` header.
- **Domain Scoping:** Automatically restricts crawling to the seed domains by default, preventing the crawler from wandering uncontrollably across external sites.
- **Content Cleaning:** Strips boilerplates (`<script>`, `<style>`, `<nav>`, `<footer>`, `<header>`, `<aside>`, `<svg>`), extracts clean page titles, visible text, and discovers outbound links (`<a href="...">`).
- **Persistence:** Saves crawled pages to `crawled_pages/{url_hash}.json`, allowing newly indexed sites to persist across server restarts.

### 2. Multi-Source Ingestion & Tokenization (`search_engine.py`)
The `SearchEngine` class ingests documents from multiple sources without duplicating IR math:
- Local `.txt` files in `documents/` (tagged as `Local Doc`).
- Crawled web pages in `crawled_pages/` (tagged as `Web Page` with clickable URLs).
- In-memory document payloads.

Each document is tokenized, lowercased, stripped of punctuation, and filtered through a stopword list (`the`, `is`, `and`, ...) so common filler words do not distort relevance.

### 3. Inverted Index
Instead of storing "document → words", the engine maintains an inverted index:
`word → {doc_id: term_frequency}`.
When a query arrives, only candidate documents containing at least one query term are inspected, avoiding exhaustive corpus scans.

### 4. TF-IDF Weighting
Each word in each document is assigned a weight:
- **Term Frequency ($TF$):** Sub-linear log-dampened: `1 + ln(count)` so a term appearing 50 times does not overpower a term appearing once.
- **Inverse Document Frequency ($IDF$):** Smooth corpus discrimination: `ln((1 + N) / (1 + df)) + 1`. Rare terms across the corpus receive higher discriminative weight.
- **Weight:** $w = TF \times IDF$.

### 5. Cosine Similarity Ranking
The search query is tokenized and transformed into a TF-IDF vector in the same vocabulary space as the corpus. The relevance score is the **cosine similarity** between the query vector and candidate document vectors:
$$\text{similarity}(\vec{q}, \vec{d}) = \frac{\vec{q} \cdot \vec{d}}{\|\vec{q}\| \|\vec{d}\|}$$
Documents with the smallest angular distance (highest cosine score) rank first.

---

## Running the Application

### 1. Installation

```bash
cd mini-search-engine
pip install -r requirements.txt
```

### 2. Start the Server

```bash
python app.py
```

Then open **http://127.0.0.1:5000** in your browser.

### 3. Search & Crawl from the UI
- **Search:** Enter search queries in the search bar (e.g. `machine learning ranking`, `climate change energy`, `space exploration`).
- **Crawl & Index:** Click **"Open Crawler"**, paste in seed URLs (e.g. `https://en.wikipedia.org/wiki/Information_retrieval` or `https://docs.python.org/3/tutorial/`), select max pages, and click **"Crawl & Index"**.
- Results will display with dynamic source tags (`[Local Doc]` vs `[Web Page]`) and clickable links for web pages.

---

## Command-Line Usage

You can also run search and crawling directly from your terminal:

```bash
# Test the search ranking logic on local + crawled corpus:
python search_engine.py "space exploration mars"

# Run a standalone crawl test:
python crawler.py "https://en.wikipedia.org/wiki/Search_engine"
```

---

## API Endpoints

- `GET /api/search?q=<query>` — Returns ranked JSON results with TF-IDF similarity scores, source metadata, URLs, and snippets.
- `POST /api/crawl` — Accepts `{"seed_urls": ["..."], "max_pages": 10, "max_depth": 2}`, runs a polite crawl, saves to `crawled_pages/`, and rebuilds the index.
- `GET /api/stats` — Returns index stats: total documents, local document count, crawled web page count, vocabulary size, and document lists.
- `GET /api/term/<word>` — Inspects the raw posting list and IDF for a specific term (e.g. `/api/term/vector`).

---

## Crawler Scope & Ethical Guidelines

> [!IMPORTANT]
> - **Educational Scope:** This crawler is designed as a lightweight educational component for demonstrating information retrieval fundamentals. It is single-threaded and intended for small, controlled crawls (1–25 pages), not web-scale indexing.
> - **Respect `robots.txt`:** The crawler strictly obeys domain `robots.txt` disallow rules via Python's standard `urllib.robotparser`.
> - **Polite Rate Limiting:** An intentional 1.0–2.0 second delay is enforced between requests to the same domain.
> - **Permitted Targets:** Only crawl websites that explicitly allow web scrapers/crawlers or sites you own (e.g., Wikipedia, documentation hubs, personal blogs). Do not attempt to crawl search engine result pages or sites that prohibit automated crawling in their Terms of Service.
