"""
Mini Search Engine - Core Logic
=================================
Implements:
  1. Text preprocessing (tokenization, stopword removal)
  2. Multi-source document ingestion (local .txt files + crawled web pages JSON/dicts)
  3. An inverted index (word -> which documents contain it, and how often)
  4. TF-IDF weighting (how important a word is to a document, relative to the corpus)
  5. Cosine similarity ranking (compares the query vector to each document vector)

This is deliberately written without any external NLP/search libraries so every
step of "how Google-style search actually works" is visible and hackable.
"""

import os
import re
import math
import json
from collections import defaultdict, Counter

# A small, hand-picked stopword list. Stopwords are common words ("the", "is",
# "and") that carry little meaning for search relevance, so we drop them.
STOPWORDS = set("""
a an and are as at be by for from has have he in is it its of on that the to
was were will with this these those i you your our their can could should
would may might not no do does did but or if then so than too very just
about into over over under again further once here there when where why how
all any both each few more most other some such nor own same so up down out
""".split())

TOKEN_PATTERN = re.compile(r"[a-zA-Z0-9']+")


def tokenize(text: str):
    """Lowercase, strip punctuation, split into words, drop stopwords/short tokens."""
    if not text:
        return []
    text = text.lower()
    tokens = TOKEN_PATTERN.findall(text)
    return [t for t in tokens if t not in STOPWORDS and len(t) > 1]


class SearchEngine:
    def __init__(
        self,
        doc_dir: str | None = None,
        crawled_dir: str | None = None,
        extra_docs: list[dict] | None = None,
    ):
        self.doc_dir = doc_dir
        self.crawled_dir = crawled_dir

        self.documents = {}        # doc_id -> raw text
        self.doc_meta = {}         # doc_id -> metadata dict (title, filename, url, source, domain)
        self.doc_names = {}        # doc_id -> display label (for backward compatibility)
        self.tokenized_docs = {}   # doc_id -> list of tokens
        self.inverted_index = defaultdict(dict)  # term -> {doc_id: term_frequency}
        self.doc_freq = {}         # term -> number of documents containing it
        self.idf = {}              # term -> inverse document frequency
        self.doc_vectors = {}      # doc_id -> {term: tf_idf_weight}
        self.doc_norms = {}        # doc_id -> vector length (for cosine similarity)
        self.N = 0                 # total number of documents

        self.reindex(extra_docs=extra_docs)

    # ------------------------------------------------------------------
    # STEP 1: Ingest documents from multiple sources & reindex
    # ------------------------------------------------------------------
    def reindex(self, extra_docs: list[dict] | None = None):
        """Clears and rebuilds the inverted index and TF-IDF models from all sources."""
        self.documents.clear()
        self.doc_meta.clear()
        self.doc_names.clear()
        self.tokenized_docs.clear()
        self.inverted_index.clear()
        self.doc_freq.clear()
        self.idf.clear()
        self.doc_vectors.clear()
        self.doc_norms.clear()

        doc_id = 0

        # Source A: Local .txt files
        if self.doc_dir and os.path.isdir(self.doc_dir):
            files = sorted(f for f in os.listdir(self.doc_dir) if f.endswith(".txt"))
            for fname in files:
                path = os.path.join(self.doc_dir, fname)
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        text = f.read()
                    self.documents[doc_id] = text
                    self.doc_names[doc_id] = fname
                    self.doc_meta[doc_id] = {
                        "filename": fname,
                        "title": fname.replace(".txt", "").replace("_", " ").title(),
                        "url": None,
                        "source": "file",
                        "domain": "local",
                    }
                    self.tokenized_docs[doc_id] = tokenize(text)
                    doc_id += 1
                except Exception as e:
                    print(f"Warning: Failed to read local doc {fname}: {e}")

        # Source B: Crawled web pages from crawled_dir
        if self.crawled_dir and os.path.isdir(self.crawled_dir):
            json_files = sorted(f for f in os.listdir(self.crawled_dir) if f.endswith(".json"))
            for jname in json_files:
                jpath = os.path.join(self.crawled_dir, jname)
                try:
                    with open(jpath, "r", encoding="utf-8") as f:
                        page = json.load(f)
                    url = page.get("url", "")
                    title = page.get("title") or url
                    text = page.get("text", "")
                    domain = page.get("domain", "")

                    if text.strip():
                        self.documents[doc_id] = text
                        self.doc_names[doc_id] = title
                        self.doc_meta[doc_id] = {
                            "filename": title,
                            "title": title,
                            "url": url,
                            "source": "web",
                            "domain": domain,
                            "crawled_at": page.get("crawled_at"),
                        }
                        self.tokenized_docs[doc_id] = tokenize(text)
                        doc_id += 1
                except Exception as e:
                    print(f"Warning: Failed to read crawled page {jname}: {e}")

        # Source C: In-memory document dicts
        if extra_docs:
            for doc in extra_docs:
                url = doc.get("url")
                title = doc.get("title") or doc.get("filename") or (url or f"doc_{doc_id}")
                text = doc.get("text", "")
                if text.strip():
                    self.documents[doc_id] = text
                    self.doc_names[doc_id] = title
                    self.doc_meta[doc_id] = {
                        "filename": doc.get("filename") or title,
                        "title": title,
                        "url": url,
                        "source": doc.get("source", "web" if url else "file"),
                        "domain": doc.get("domain", ""),
                    }
                    self.tokenized_docs[doc_id] = tokenize(text)
                    doc_id += 1

        self.N = len(self.documents)
        self._build_inverted_index()
        self._compute_tfidf()

    def add_documents(self, new_docs: list[dict]):
        """Ingests additional documents into the corpus and refreshes the index."""
        if not new_docs:
            return
        self.reindex(extra_docs=new_docs)

    # ------------------------------------------------------------------
    # STEP 2: Build the inverted index
    #   word -> { doc_id: how many times the word appears in that doc }
    # ------------------------------------------------------------------
    def _build_inverted_index(self):
        for doc_id, tokens in self.tokenized_docs.items():
            term_counts = Counter(tokens)
            for term, tf in term_counts.items():
                self.inverted_index[term][doc_id] = tf

        for term, postings in self.inverted_index.items():
            self.doc_freq[term] = len(postings)  # how many docs contain this term

    # ------------------------------------------------------------------
    # STEP 3: Compute TF-IDF weights for every document
    #   tf  = 1 + log(raw term frequency)          -> dampens very frequent words
    #   idf = log((1 + N) / (1 + df)) + 1           -> rare words score higher
    #   weight = tf * idf
    # ------------------------------------------------------------------
    def _compute_tfidf(self):
        if self.N == 0:
            return

        for term, df in self.doc_freq.items():
            self.idf[term] = math.log((1 + self.N) / (1 + df)) + 1

        for doc_id, tokens in self.tokenized_docs.items():
            term_counts = Counter(tokens)
            vector = {}
            for term, tf in term_counts.items():
                weighted_tf = 1 + math.log(tf)
                vector[term] = weighted_tf * self.idf[term]
            self.doc_vectors[doc_id] = vector
            norm = math.sqrt(sum(w * w for w in vector.values())) or 1e-9
            self.doc_norms[doc_id] = norm

    # ------------------------------------------------------------------
    # STEP 4: Rank documents for a query using cosine similarity
    #   Treats the query itself as a tiny "document", builds its TF-IDF
    #   vector using the corpus's IDF values, and measures the angle
    #   between the query vector and each candidate document vector.
    #   A smaller angle (cosine closer to 1) means higher relevance.
    # ------------------------------------------------------------------
    def search(self, query: str, top_k: int = 10):
        q_tokens = tokenize(query)
        if not q_tokens or self.N == 0:
            return []

        q_counts = Counter(q_tokens)
        q_vector = {}
        for term, tf in q_counts.items():
            if term in self.idf:  # ignore words never seen in the corpus
                weighted_tf = 1 + math.log(tf)
                q_vector[term] = weighted_tf * self.idf[term]

        if not q_vector:
            return []

        q_norm = math.sqrt(sum(w * w for w in q_vector.values())) or 1e-9

        # Only score documents that actually contain at least one query term
        candidate_docs = set()
        for term in q_vector:
            candidate_docs.update(self.inverted_index.get(term, {}).keys())

        scored = []
        for doc_id in candidate_docs:
            d_vector = self.doc_vectors[doc_id]
            dot_product = sum(q_vector[t] * d_vector.get(t, 0.0) for t in q_vector)
            similarity = dot_product / (q_norm * self.doc_norms[doc_id])
            if similarity > 0:
                scored.append((doc_id, similarity))

        scored.sort(key=lambda pair: pair[1], reverse=True)

        results = []
        for doc_id, score in scored[:top_k]:
            meta = self.doc_meta.get(doc_id, {})
            results.append({
                "doc_id": doc_id,
                "filename": self.doc_names[doc_id],
                "title": meta.get("title", self.doc_names[doc_id]),
                "url": meta.get("url"),
                "source": meta.get("source", "file"),
                "domain": meta.get("domain"),
                "score": round(score, 4),
                "snippet": self._make_snippet(doc_id, set(q_tokens)),
            })
        return results

    # ------------------------------------------------------------------
    # Helper: build a short preview around the first matching query word
    # ------------------------------------------------------------------
    def _make_snippet(self, doc_id: int, q_tokens: set, window: int = 14):
        raw = self.documents.get(doc_id, "")
        words = raw.split()
        lowered = [w.lower().strip(".,!?;:\"'()[]{}") for w in words]
        for i, w in enumerate(lowered):
            if w in q_tokens:
                start = max(0, i - window // 2)
                end = min(len(words), i + window // 2)
                prefix = "... " if start > 0 else ""
                suffix = " ..." if end < len(words) else ""
                return prefix + " ".join(words[start:end]) + suffix
        return " ".join(words[:window]) + (" ..." if len(words) > window else "")

    # ------------------------------------------------------------------
    # Introspection helpers, handy for index stats dashboard
    # ------------------------------------------------------------------
    def stats(self):
        local_docs = [m["filename"] for m in self.doc_meta.values() if m.get("source") == "file"]
        web_docs = [m["title"] for m in self.doc_meta.values() if m.get("source") == "web"]

        return {
            "num_documents": self.N,
            "num_local_documents": len(local_docs),
            "num_web_documents": len(web_docs),
            "num_unique_terms": len(self.inverted_index),
            "documents": [self.doc_meta[i]["title"] for i in range(self.N)],
            "local_documents": local_docs,
            "web_documents": web_docs,
        }

    def posting_list(self, term: str):
        term = term.lower()
        postings = self.inverted_index.get(term, {})
        return {
            "term": term,
            "document_frequency": self.doc_freq.get(term, 0),
            "idf": round(self.idf.get(term, 0.0), 4),
            "postings": {self.doc_names[d]: tf for d, tf in postings.items()},
        }


if __name__ == "__main__":
    import sys
    base_dir = os.path.dirname(os.path.abspath(__file__))
    doc_dir = os.path.join(base_dir, "documents")
    crawled_dir = os.path.join(base_dir, "crawled_pages")
    engine = SearchEngine(doc_dir=doc_dir, crawled_dir=crawled_dir)
    query = " ".join(sys.argv[1:]) or "machine learning ranking"
    print(f"\nQuery: {query!r}")
    print(f"Indexed {engine.N} documents, {len(engine.inverted_index)} unique terms\n")
    for rank, r in enumerate(engine.search(query), start=1):
        print(f"{rank}. [{r['source'].upper()}] {r['title']} (score={r['score']})")
        if r.get("url"):
            print(f"    URL: {r['url']}")
        print(f"    ...{r['snippet']}\n")
