# Mini Search Engine

A full-text search engine built from scratch in Python and Flask. It indexes local text documents and crawled web pages using an inverted index, ranking results with Okapi BM25 and TF-IDF with Cosine Similarity. The project demonstrates core Information Retrieval (IR) principles, replacing basic substring matching with statistical term weighting, document length normalization, and phrase match boosting. User accounts, search history, and query bookmarking are persisted locally with SQLite and SQLAlchemy.

---

## Features

- **Information Retrieval & Ranking:**
  - **Okapi BM25:** Probabilistic ranking model with term frequency saturation ($k_1 = 1.5$), document length normalization ($b = 0.75$), and Robertson-Spärck Jones Inverse Document Frequency (IDF).
  - **TF-IDF with Cosine Similarity:** Vector Space Model with sublinear term frequency scaling ($1 + \log(\text{tf})$) and L2 vector normalization.
  - **Exact Phrase Match Boosting:** Applies a configurable score boost (+30%) when query terms appear as consecutive phrases in document text.
- **Inverted Index:**
  - In-memory dictionary mapping terms to postings lists containing document IDs and term frequencies for fast lookup without scanning raw document files.
- **Prefix Trie Autocomplete:**
  - In-memory prefix tree providing keystroke-by-keystroke query suggestions ranked by corpus document frequency.
- **Search Filters:**
  - **Source Filtering:** Scope queries to local documents, crawled web pages, or all indexed content.
  - **Relevance Cutoff:** Filter out low-confidence results below a minimum score threshold.
- **Polite Web Crawler:**
  - Breadth-First Search (BFS) crawling with configurable maximum pages and traversal depth limits.
  - `robots.txt` compliance parsing and polite per-host request delays.
  - Server-Side Request Forgery (SSRF) validation blocking private subnets, loopback addresses, cloud metadata endpoints, and non-HTTP protocols.
  - HTML text extraction stripping scripts, styles, navigation, and boilerplate markup.
- **User Accounts & Saved Searches:**
  - User registration, login, and session persistence using Flask-Login and salted password hashing (`werkzeug.security`).
  - Cross-Site Request Forgery (CSRF) protection on all form submissions via Flask-WTF.
  - Per-user query history and bookmarking with strict user-level access isolation.
- **Automated Test Suite:**
  - 58 unit and integration tests covering the tokenizer, trie, inverted index, ranking models, crawler security, API endpoints, and authentication routes.
  - 88% test coverage verified with `pytest` and `pytest-cov`.

---

## Project Structure

```
mini-search-engine/
├── app.py                  # Flask application, REST API endpoints, and authentication routes
├── search_engine.py        # Tokenizer, PrefixTrie, inverted index, BM25, and Cosine ranking engine
├── crawler.py              # Polite web crawler with robots.txt compliance and SSRF validation
├── models.py               # SQLAlchemy database models for User and SavedSearch
├── forms.py                # Flask-WTF forms for user registration and login with CSRF protection
├── requirements.txt        # Runtime application dependencies
├── requirements-dev.txt    # Testing dependencies (pytest, pytest-cov, responses)
├── pytest.ini              # Pytest configuration and test runner settings
├── LICENSE                 # MIT License file
├── .gitignore              # Files and patterns excluded from version control
├── documents/              # Local text files making up the default search corpus
├── crawled_pages/          # JSON files containing web pages crawled and indexed by the crawler
├── templates/
│   ├── index.html          # Main search engine interface and saved searches drawer
│   ├── login.html          # User authentication sign-in page
│   └── signup.html         # User registration page
├── static/
│   ├── style.css           # CSS styling, layout, theme tokens, and animations
│   └── script.js           # Client-side search requests, autocomplete, and UI interactions
└── tests/
    ├── conftest.py         # Pytest fixtures for isolated corpus, test database, and Flask client
    ├── test_api.py         # Integration tests for search endpoints, auth, and saved searches
    ├── test_crawler.py     # Unit tests for SSRF defense, robots.txt, and HTML extraction
    └── test_search_engine.py # Unit tests for tokenization, trie, index, and ranking formulas
```

---

## How It Works

The search engine processes text through a four-stage pipeline:

```
Raw Text / Query ──► Tokenization ──► Inverted Index Lookup ──► BM25 / Cosine Scoring ──► Ranked Results
```

### 1. Tokenization and Preprocessing
Raw text from documents and incoming search queries is converted into normalized tokens:
- Converted to lowercase.
- Punctuation and non-alphanumeric characters stripped (preserving alphanumeric terms and apostrophes).
- Common English stopwords (such as "the", "is", "at") are removed using a curated stopword set.
- Single-character noise tokens are discarded.

### 2. Inverted Index Construction
During startup, the engine reads all local `.txt` documents and crawled JSON files once. It compiles an inverted index—a dictionary where every unique word maps to a postings list:

```
"algorithm" ──► [ {doc_id: 1, tf: 3}, {doc_id: 4, tf: 1} ]
"index"     ──► [ {doc_id: 1, tf: 5}, {doc_id: 2, tf: 2} ]
```

This structure eliminates full-text file scans during queries, reducing candidate document discovery to instant dictionary lookups.

### 3. Relevance Scoring (BM25 & Cosine Similarity)
When a search query is submitted:
1. The query terms are preprocessed and looked up in the inverted index to retrieve matching candidate documents.
2. The selected algorithm computes a numerical relevance score for each candidate:
   - **BM25:** Evaluates term rarity across the corpus (Inverse Document Frequency), rewards documents containing matching terms while applying term saturation so excessive repetition does not skew results, and normalizes scores against document length compared to average corpus length.
   - **Cosine Similarity:** Treats the query and documents as vectors of TF-IDF weights in multidimensional term space, measuring the cosine of the angle between them.
3. If the query consists of multiple terms that appear adjacent in the original document text in the exact order queried, an exact phrase match bonus (+30%) is applied.

### 4. Ranked Results Delivery
Candidate documents are sorted in descending order by final score, filtered against any active source or score thresholds, paired with generated contextual text snippets highlighting matched terms, and returned as JSON to the interface.

---

## Setup & Running Locally

### 1. Prerequisites
- Python 3.11 or 3.12
- Git

### 2. Installation
```bash
# Clone repository
git clone https://github.com/poshiyaharsh/Mini-Search-Engine.git
cd Mini-Search-Engine

# Create and activate virtual environment
python -m venv venv

# Windows:
venv\Scripts\activate

# Linux/macOS:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 3. Run the Application
```bash
python app.py
```

Open **`http://127.0.0.1:5000`** in your browser.

> The SQLite database (`instance/app.db`) and necessary corpus directories are initialized automatically on startup.

---

## Running Tests

Install test dependencies:
```bash
pip install -r requirements-dev.txt
```

Run all 58 automated tests:
```bash
pytest -v
```

Run tests with test coverage breakdown:
```bash
pytest --cov=. --cov-report=term-missing
```

---

## License

MIT License — see LICENSE file
