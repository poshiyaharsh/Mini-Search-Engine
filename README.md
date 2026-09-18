# Mini Search Engine + Web Crawler

A from-scratch implementation of the core ideas behind modern search engines:
**breadth-first web crawling (respecting robots.txt) → tokenization → inverted index → Okapi BM25 ranking (with term saturation, document length normalization, and phrase boosting) → vector space cosine TF-IDF → Prefix Trie autocomplete → multi-source filters**, served through a hardened Flask API with a modern glassmorphism frontend.

No external search library (like Lucene, Elasticsearch, or Whoosh) is used anywhere. Every algorithm and data structure is implemented directly in plain Python.

---

## Project Structure

```
mini-search-engine/
├── app.py                  # Flask app: auth routes, search, suggest, saved searches, and crawler APIs
├── search_engine.py        # Core IR: Prefix Trie, BM25 ranking, cosine similarity, filters
├── crawler.py              # Web crawler: BFS queue, robots.txt compliance, HTML parser, SSRF defense
├── models.py               # SQLite database models: User and SavedSearch via Flask-SQLAlchemy
├── forms.py                # WTForms: LoginForm & SignupForm with CSRF and validation
├── requirements.txt        # Flask, Flask-SQLAlchemy, Flask-Login, Flask-WTF, beautifulsoup4, etc.
├── instance/               # Local SQLite database (instance/app.db - ignored by git)
├── documents/               # Local corpus: 10 sample notes/articles (.txt)
│   ├── ai_basics.txt
│   ├── python_programming.txt
│   └── ... (8 more)
├── crawled_pages/          # Persisted crawled web pages (saved as JSON)
├── templates/
│   ├── index.html          # Glassmorphic search UI with user menu, filter bar, and saved searches
│   ├── login.html          # Glassmorphic sign-in page with CSRF protection
│   └── signup.html         # Glassmorphic registration page with password confirmation
└── static/
    ├── style.css           # Glass tokens, ambient mesh, user dropdown, auth forms, drawer styles
    └── script.js           # Search client, debounced autocomplete, saved searches manager
```

---

## How It Works

### 1. Web Crawler (`crawler.py`)
Rather than relying on third-party search APIs, the engine crawls live web pages itself:
- **Breadth-First Traversal (BFS):** Uses a FIFO queue (`collections.deque`) seeded with starting URLs, traversing out to a configurable `max_depth` and `max_pages`.
- **`robots.txt` Compliance:** Before making a request to any domain, the crawler verifies `urllib.robotparser.RobotFileParser` to confirm `MiniSearchEngineBot` is allowed to fetch the URL.
- **Politeness & Rate Limiting:** Enforces a mandatory 1.0–2.0 second delay between consecutive requests to the same domain.
- **SSRF & Security Defense:** Pre-screens seed URLs and DNS resolutions against private IPv4/IPv6 ranges (e.g. `127.0.0.1`, `10.0.0.0/8`, `192.168.0.0/16`, AWS metadata `169.254.169.254`).
- **Content Cleaning & Persistence:** Strips boilerplate elements (`<script>`, `<style>`, `<nav>`, etc.), extracts page text, and persists crawled documents as JSON files in `crawled_pages/`.

### 2. Multi-Source Ingestion & Inverted Index (`search_engine.py`)
- Documents are ingested from local files (`documents/`) and crawled web pages (`crawled_pages/`), tagging each with a unified `source` (`local` vs `web`).
- The engine tokenizes, strips punctuation, removes stopwords, and builds an in-memory inverted index:
  $$\text{word} \to \{\text{doc\_id}: \text{term\_frequency}\}$$

---

## Ranking Algorithms: BM25 vs. Cosine TF-IDF

The engine defaults to **Okapi BM25** while retaining **Vector Space Cosine TF-IDF** as a selectable comparative algorithm.

### Okapi BM25 (Default)
BM25 refines classic TF-IDF by introducing **term saturation** and **document length normalization**:

$$\text{score}(D, Q) = \sum_{t \in Q} \text{IDF}_{\text{BM25}}(t) \cdot \frac{tf(t, D) \cdot (k_1 + 1)}{tf(t, D) + k_1 \cdot \left(1 - b + b \cdot \frac{|D|}{\text{avgdl}}\right)}$$

- **Term Saturation ($k_1 = 1.5$):** Limits the benefit of repeated terms. As $tf$ grows, the term weight asymptotically approaches $(k_1 + 1)$, preventing keyword-stuffed documents from dominating.
- **Document Length Normalization ($b = 0.75$):** Normalizes the document length $|D|$ against the average corpus document length $\text{avgdl}$. Short documents with relevant term occurrences are not penalized in favor of lengthy documents that happen to contain the word purely due to verbosity.
- **Robertson-Spärck Jones IDF:** Smooth corpus discrimination guaranteeing positive values:
  $$\text{IDF}_{\text{BM25}}(t) = \ln\left(\frac{N - \text{df}(t) + 0.5}{\text{df}(t) + 0.5} + 1.0\right)$$
- **Exact Phrase Match Boosting:** If a multi-word query (e.g. `"machine learning"`) appears as an exact contiguous phrase inside the document, its final relevance score is multiplied by **$1.3\times$ (+30% boost)**.

### Cosine TF-IDF (Comparative)
- Uses sublinear term frequency ($1 + \ln(tf)$) and smoothed corpus IDF ($\ln((1 + N)/(1 + df)) + 1$).
- Calculates the cosine of the angle between query and document vectors:
  $$\text{similarity}(\vec{q}, \vec{d}) = \frac{\vec{q} \cdot \vec{d}}{\|\vec{q}\| \|\vec{d}\|}$$
- Always normalized between $0.0$ and $1.0$.

---

## Autocomplete & Query Suggestions

As the user types into the search bar, the frontend debounces input by 250ms and queries `/api/suggest?prefix=<term>`:
- **Prefix Trie Structure:** Built during corpus indexing in $O(V \cdot L)$ time.
- **Prefix Search:** Traverses the trie to the prefix node in $O(L)$ time, then gathers matching completions via depth-first traversal.
- **Ranking by Document Frequency:** Completions are ordered descending by how many documents in the index contain the word (`df`), so widely used terms appear first.
- **Keyboard Navigation:** Users can navigate suggestions with `ArrowDown` / `ArrowUp`, select with `Enter`, and dismiss with `Escape` or clicking outside.

---

## Multi-Dimensional Filters

Users can narrow and compare search results dynamically without reloading the page:
1. **Algorithm Switch:** Toggle between **BM25** and **Cosine TF-IDF**.
2. **Source Filter:**
   - `All`: Search across both local `.txt` documents and crawled web pages.
   - `Local Docs`: Restrict search exclusively to notes in `documents/`.
   - `Crawled Web`: Restrict search exclusively to crawled web documents.
3. **Minimum Score Cutoff:** Filter out low-relevance noise (`Any`, `> 0.05`, `> 0.10`, `> 0.25`, `> 0.50`).

---

## Score Comparison: BM25 vs. Cosine TF-IDF

Below is an actual benchmark comparison of top documents across 3 sample queries:

| Query | Document | Algorithm | Score | Phrase Match? | Key Behavior |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **`machine learning`** | *Machine Learning* | **BM25** | **5.2708** | Yes (+30%) | High saturation reward + phrase match |
| | *Machine Learning* | **Cosine** | **0.3688** | Yes (+30%) | Normalized angular similarity |
| | *Ai Basics* | **BM25** | **3.4231** | Yes (+30%) | High relevance, normalized for doc length |
| | *Ai Basics* | **Cosine** | **0.1955** | Yes (+30%) | Angular match |
| **`climate change`** | *Climate Change* | **BM25** | **7.9665** | Yes (+30%) | Focused document strongly rewarded |
| | *Climate Change* | **Cosine** | **0.3970** | Yes (+30%) | Normalized angle |
| | *Financial Markets* | **BM25** | **1.4867** | No | Incidental mention dampened by BM25 |
| | *Financial Markets* | **Cosine** | **0.0551** | No | Low angle match |
| **`space exploration`** | *Space Exploration* | **BM25** | **8.7311** | Yes (+30%) | Strong exact match with length penalty control |
| | *Space Exploration* | **Cosine** | **0.3882** | Yes (+30%) | Clean angle separation |

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

Open **http://127.0.0.1:5000** in your browser.

---

## User Accounts & Saved Searches

The search engine features full user authentication and personal query bookmarking while maintaining **100% public access** for anonymous visitors to search and crawl.

### 1. Authentication Architecture
- **Flask-Login Session Management:** Tracks authenticated sessions securely using signed session cookies (`HttpOnly=True`, `SameSite=Lax`, and `Secure` dynamically enabled in production).
- **Werkzeug Password Hashing:** Passwords are cryptographically hashed using `scrypt` or `pbkdf2:sha256` before being stored. Plaintext passwords are never saved.
- **Flask-WTF CSRF Protection:** All forms (login, registration, logout) and mutating API endpoints require valid CSRF tokens submitted via form fields or `X-CSRFToken` headers.
- **Brute-Force Rate Limiting:** Enforces an in-memory limit of **5 login attempts per minute** per client IP, returning HTTP 429 when exceeded.
- **SQLite Database (`instance/app.db`):** Backed by Flask-SQLAlchemy with `User` and `SavedSearch` models, automatically created on startup.

### 2. Saved Searches & Privacy Isolation
- **1-Click Save:** Authenticated users can click **"Save Search"** directly from search results to save their query string, selected algorithm (`bm25` vs `cosine`), and active filter settings (`source`, `min_score`).
- **Strict Authorization Isolation:** Users can only view and delete their own saved searches. Attempting to access or delete another user's saved search returns `403 Forbidden`.
- **1-Click Re-run:** Re-running a saved query restores the exact search query and all filter criteria instantly.

---

## API Endpoints

### Public Endpoints
- `GET /`
  - Glassmorphic search interface, live stats, filter controls, and crawler modal.
- `GET /api/search?q=<query>&algo=<bm25|cosine>&source=<all|local|web>&min_score=<float>`
  - Returns ranked JSON results with scores, snippet highlights, phrase match flags, and applied filter metadata.
- `GET /api/suggest?prefix=<term>&limit=8`
  - Returns top vocabulary completions ranked by document frequency.
- `POST /api/crawl`
  - Accepts `{"seed_urls": ["..."], "max_pages": 5, "max_depth": 1}`, crawls matching domains safely, persists to `crawled_pages/`, and rebuilds the index.
- `GET /api/stats`
  - Returns total documents, local documents, crawled web pages, unique terms, and average document length (`avgdl`).
- `GET /api/term/<word>`
  - Inspects the raw posting list and IDF for a specific vocabulary word.

### Authentication & Saved Searches Endpoints
- `GET /signup` / `POST /signup`
  - Account creation with email validation and password confirmation.
- `GET /login` / `POST /login`
  - User sign-in with rate-limiting and session creation.
- `POST /logout`
  - Secure session termination (requires CSRF token).
- `GET /api/searches` *(Requires Auth)*
  - Returns the logged-in user's saved searches in reverse-chronological order.
- `POST /api/searches` *(Requires Auth & CSRF)*
  - Saves a search query, algorithm, and filter options for the authenticated user.
- `DELETE /api/searches/<id>` *(Requires Auth & CSRF)*
  - Deletes a saved search with strict ownership verification.

---

## Command-Line Usage

```bash
# Test BM25 search ranking:
python search_engine.py "machine learning" bm25

# Test Cosine similarity search ranking:
python search_engine.py "machine learning" cosine

# Run a standalone crawl test:
python crawler.py "https://en.wikipedia.org/wiki/Search_engine"
```
