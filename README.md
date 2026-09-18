# Mini Search Engine

A small, from-scratch implementation of the ideas behind Google-style search:
tokenization → inverted index → TF-IDF weighting → cosine similarity ranking,
served through a Flask API with a simple HTML/JS frontend.

No search library is used anywhere. Every step is plain Python so you can
read `search_engine.py` top to bottom and see exactly how a query turns into
a ranked list of documents.

## Project structure

```
mini-search-engine/
├── app.py                  # Flask app: serves the frontend + JSON API
├── search_engine.py        # Core logic: tokenizer, inverted index, TF-IDF, ranking
├── requirements.txt
├── documents/               # The corpus - 10 short sample notes/articles
│   ├── ai_basics.txt
│   ├── python_programming.txt
│   └── ... (8 more)
├── templates/
│   └── index.html           # Search page markup
└── static/
    ├── style.css             # Frontend styling
    └── script.js             # Calls /api/search, renders results
```

## How it works

**1. Tokenization** (`tokenize()` in `search_engine.py`)
Lowercases text, strips punctuation, splits into words, and removes a small
stopword list (`the`, `is`, `and`, ...) so common filler words don't dominate
scoring.

**2. Inverted index** (`_build_inverted_index`)
Instead of storing "document → words", we store the reverse: `word →
{document: how many times it appears}`. This is the data structure that lets
a query only touch the handful of documents that actually contain a query
word, instead of scanning the whole corpus.

**3. TF-IDF weighting** (`_compute_tfidf`)
Each word in each document gets a weight:

- `tf` (term frequency, log-dampened) — how often the word appears in *this*
  document. Dampened with `1 + log(tf)` so a word appearing 50 times isn't
  50x more important than one appearing once.
- `idf` (inverse document frequency) — `log((1 + N) / (1 + df)) + 1`. Words
  that appear in almost every document (low signal) get a low weight; rare,
  distinctive words get a high weight.
- `weight = tf * idf`

Every document ends up as a vector of `{word: weight}` over the whole
vocabulary.

**4. Ranking with cosine similarity** (`search()`)
The query is tokenized and turned into a TF-IDF vector the same way a
document is. Each candidate document's relevance score is the **cosine
similarity** between the query vector and the document vector — effectively,
how closely the "direction" of the query matches the "direction" of the
document, regardless of document length. Highest similarity is returned
first.

**5. Frontend**
`static/script.js` calls `/api/search?q=...`, gets back ranked JSON results
with scores and snippets, and renders them. A "how the index works" panel
calls `/api/stats` to show corpus size and vocabulary size.

## Running it

```bash
cd mini-search-engine
pip install -r requirements.txt
python app.py
```

Then open **http://127.0.0.1:5000** and search. Try queries like:
- `machine learning ranking`
- `climate change energy`
- `cricket world cup`

You can also run the ranking logic directly from the command line, without
the web server:

```bash
python search_engine.py "space exploration mars"
```

## Using your own documents

Drop any `.txt` files into `documents/` and restart the server — the index
is rebuilt automatically from whatever is in that folder. There's nothing
domain-specific in the code, so this works just as well for your own notes,
blog posts, or article archive.

## Debug endpoints

- `GET /api/stats` — document count, vocabulary size, list of indexed files
- `GET /api/term/<word>` — inspect the raw posting list and IDF for a
  single word, e.g. `/api/term/machine`

## Ideas for extending this

- Swap the stopword list / add stemming (e.g. Porter stemmer) for better
  matching across word forms (`run`, `running`, `ran`).
- Support phrase queries (`"machine learning"`) using positional indexes.
- Add pagination and highlight all matches in a snippet, not just the first.
- Persist the index to disk (JSON or SQLite) instead of rebuilding on every
  server start, for larger corpora.
- Swap cosine similarity for BM25, the ranking function real search engines
  use as a refinement over plain TF-IDF.

## Why this is a good portfolio project

It touches four things that come up constantly in software/data engineering
interviews and real systems: text preprocessing, building and querying an
index, a weighting scheme (TF-IDF) that appears all over information
retrieval and NLP, and a small full-stack API + frontend wiring it together.
It's also fully self-contained — no external API keys, no database, easy to
demo in two minutes.
