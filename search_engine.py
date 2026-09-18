"""
Mini Search Engine - Hardened Core Logic
=========================================
Implements:
  1. Multi-source document ingestion (local .txt files + crawled web pages)
  2. Robust text preprocessing & tokenization
  3. Thread-safe, atomic index rebuilding
  4. Dampened TF-IDF weighting (sublinear TF, smoothed IDF)
  5. Vector space cosine similarity ranking

Hardened for edge cases:
  - Empty corpus (N = 0)
  - Documents with zero tokens / stopwords only
  - Queries with only stopwords
  - Zero-division in norms
  - Duplicate documents & path traversal protection
  - Thread safety during concurrent reindexing & searching
"""

import os
import re
import math
import json
import threading
from collections import defaultdict, Counter

STOPWORDS = frozenset("""
a an and are as at be by for from has have he in is it its of on that the to
was were will with this these those i you your our their can could should
would may might not no do does did but or if then so than too very just
about into over over under again further once here there when where why how
all any both each few more most other some such nor own same so up down out
""".split())

TOKEN_PATTERN = re.compile(r"[a-zA-Z0-9']+")


def tokenize(text: str) -> list[str]:
    """Lowercase, strip punctuation, split into words, drop stopwords/short tokens."""
    if not text or not isinstance(text, str):
        return []
    text = text.lower()
    tokens = TOKEN_PATTERN.findall(text)
    return [t for t in tokens if t not in STOPWORDS and len(t) > 1 and len(t) <= 60]


class SearchEngine:
    def __init__(
        self,
        doc_dir: str | None = None,
        crawled_dir: str | None = None,
        extra_docs: list[dict] | None = None,
    ):
        self.doc_dir = doc_dir
        self.crawled_dir = crawled_dir
        self._lock = threading.RLock()

        self.documents: dict[int, str] = {}
        self.doc_meta: dict[int, dict] = {}
        self.doc_names: dict[int, str] = {}
        self.tokenized_docs: dict[int, list[str]] = {}
        self.inverted_index: dict[str, dict[int, int]] = defaultdict(dict)
        self.doc_freq: dict[str, int] = {}
        self.idf: dict[str, float] = {}
        self.doc_vectors: dict[int, dict[str, float]] = {}
        self.doc_norms: dict[int, float] = {}
        self.N: int = 0

        self.reindex(extra_docs=extra_docs)

    # ------------------------------------------------------------------
    # Atomic Multi-Source Reindexing
    # ------------------------------------------------------------------
    def reindex(self, extra_docs: list[dict] | None = None):
        """
        Atomically rebuilds the inverted index and TF-IDF models from all sources.
        Constructs new state in local variables and swaps references atomically under lock.
        """
        new_documents = {}
        new_doc_meta = {}
        new_doc_names = {}
        new_tokenized_docs = {}
        new_inverted_index = defaultdict(dict)
        new_doc_freq = {}
        new_idf = {}
        new_doc_vectors = {}
        new_doc_norms = {}

        seen_urls = set()
        doc_id = 0

        # Source A: Local .txt files
        if self.doc_dir and os.path.isdir(self.doc_dir):
            canonical_doc_dir = os.path.abspath(self.doc_dir)
            try:
                files = sorted(f for f in os.listdir(self.doc_dir) if f.endswith(".txt"))
            except Exception:
                files = []

            for fname in files:
                # Path traversal guard: verify canonical path
                full_path = os.path.abspath(os.path.join(self.doc_dir, fname))
                if not full_path.startswith(canonical_doc_dir) or not os.path.isfile(full_path):
                    continue

                try:
                    with open(full_path, "r", encoding="utf-8", errors="replace") as f:
                        text = f.read()
                except Exception:
                    continue

                tokens = tokenize(text)
                new_documents[doc_id] = text
                new_doc_names[doc_id] = fname
                new_doc_meta[doc_id] = {
                    "filename": fname,
                    "title": fname.replace(".txt", "").replace("_", " ").title(),
                    "url": None,
                    "source": "file",
                    "domain": "local",
                }
                new_tokenized_docs[doc_id] = tokens
                doc_id += 1

        # Source B: Crawled web pages from crawled_dir
        if self.crawled_dir and os.path.isdir(self.crawled_dir):
            canonical_crawled_dir = os.path.abspath(self.crawled_dir)
            try:
                json_files = sorted(f for f in os.listdir(self.crawled_dir) if f.endswith(".json"))
            except Exception:
                json_files = []

            for jname in json_files:
                # Path traversal guard
                full_path = os.path.abspath(os.path.join(self.crawled_dir, jname))
                if not full_path.startswith(canonical_crawled_dir) or not os.path.isfile(full_path):
                    continue

                try:
                    with open(full_path, "r", encoding="utf-8", errors="replace") as f:
                        page = json.load(f)
                except Exception:
                    continue

                if not isinstance(page, dict):
                    continue

                url = str(page.get("url") or "").strip()
                # Deduplicate pages by normalized URL
                norm_url = url.lower().rstrip("/")
                if norm_url in seen_urls:
                    continue
                seen_urls.add(norm_url)

                title = str(page.get("title") or url or f"Web Page {doc_id}").strip()
                text = str(page.get("text") or "")
                domain = str(page.get("domain") or "")

                tokens = tokenize(text)
                new_documents[doc_id] = text
                new_doc_names[doc_id] = title
                new_doc_meta[doc_id] = {
                    "filename": title,
                    "title": title,
                    "url": url if (url.startswith("http://") or url.startswith("https://")) else None,
                    "source": "web",
                    "domain": domain,
                    "crawled_at": page.get("crawled_at"),
                }
                new_tokenized_docs[doc_id] = tokens
                doc_id += 1

        # Source C: In-memory document dicts
        if extra_docs and isinstance(extra_docs, list):
            for doc in extra_docs:
                if not isinstance(doc, dict):
                    continue
                url = str(doc.get("url") or "").strip()
                title = str(doc.get("title") or doc.get("filename") or url or f"doc_{doc_id}").strip()
                text = str(doc.get("text") or "")
                tokens = tokenize(text)

                new_documents[doc_id] = text
                new_doc_names[doc_id] = title
                new_doc_meta[doc_id] = {
                    "filename": str(doc.get("filename") or title),
                    "title": title,
                    "url": url if (url.startswith("http://") or url.startswith("https://")) else None,
                    "source": doc.get("source", "web" if url else "file"),
                    "domain": str(doc.get("domain") or ""),
                }
                new_tokenized_docs[doc_id] = tokens
                doc_id += 1

        total_n = len(new_documents)

        # Build Inverted Index
        for d_id, tokens in new_tokenized_docs.items():
            term_counts = Counter(tokens)
            for term, tf in term_counts.items():
                new_inverted_index[term][d_id] = tf

        for term, postings in new_inverted_index.items():
            new_doc_freq[term] = len(postings)

        # Compute TF-IDF weights
        if total_n > 0:
            for term, df in new_doc_freq.items():
                # Smoothed IDF: guaranteed >= 1.0 even if df == N
                new_idf[term] = max(1.0, math.log((1 + total_n) / (1 + df)) + 1)

            for d_id, tokens in new_tokenized_docs.items():
                term_counts = Counter(tokens)
                vector = {}
                for term, tf in term_counts.items():
                    if tf > 0:
                        weighted_tf = 1.0 + math.log(tf)
                        vector[term] = weighted_tf * new_idf.get(term, 1.0)
                new_doc_vectors[d_id] = vector
                norm = math.sqrt(sum(w * w for w in vector.values())) or 1e-9
                new_doc_norms[d_id] = norm

        # Atomically swap all references under write lock
        with self._lock:
            self.documents = new_documents
            self.doc_meta = new_doc_meta
            self.doc_names = new_doc_names
            self.tokenized_docs = new_tokenized_docs
            self.inverted_index = new_inverted_index
            self.doc_freq = new_doc_freq
            self.idf = new_idf
            self.doc_vectors = new_doc_vectors
            self.doc_norms = new_doc_norms
            self.N = total_n

    def add_documents(self, new_docs: list[dict]):
        """Thread-safely ingests additional documents."""
        if not new_docs:
            return
        self.reindex(extra_docs=new_docs)

    # ------------------------------------------------------------------
    # Query Search & Ranking
    # ------------------------------------------------------------------
    def search(self, query: str, top_k: int = 10):
        """Thread-safe vector cosine similarity search with input bounds."""
        if not query or not isinstance(query, str):
            return []

        # Bound query length to prevent regex/token DoS
        sanitized_query = query.strip()[:500]
        q_tokens = tokenize(sanitized_query)
        if not q_tokens:
            return []

        top_k = max(1, min(int(top_k), 50))

        # Capture snapshot references under read lock
        with self._lock:
            if self.N == 0:
                return []
            idf_snap = self.idf
            inv_snap = self.inverted_index
            doc_vecs_snap = self.doc_vectors
            doc_norms_snap = self.doc_norms
            doc_meta_snap = self.doc_meta
            doc_names_snap = self.doc_names

        q_counts = Counter(q_tokens)
        q_vector = {}
        for term, tf in q_counts.items():
            if term in idf_snap:
                weighted_tf = 1.0 + math.log(tf)
                q_vector[term] = weighted_tf * idf_snap[term]

        if not q_vector:
            return []

        q_norm = math.sqrt(sum(w * w for w in q_vector.values())) or 1e-9

        # Collect candidate documents containing at least one query term
        candidate_docs = set()
        for term in q_vector:
            candidate_docs.update(inv_snap.get(term, {}).keys())

        scored = []
        for doc_id in candidate_docs:
            d_vector = doc_vecs_snap.get(doc_id)
            d_norm = doc_norms_snap.get(doc_id, 1e-9)
            if not d_vector:
                continue

            dot_product = sum(q_vector[t] * d_vector.get(t, 0.0) for t in q_vector)
            similarity = dot_product / (q_norm * d_norm)
            if similarity > 0:
                scored.append((doc_id, similarity))

        scored.sort(key=lambda pair: pair[1], reverse=True)

        results = []
        for doc_id, score in scored[:top_k]:
            meta = doc_meta_snap.get(doc_id, {})
            results.append({
                "doc_id": doc_id,
                "filename": doc_names_snap.get(doc_id, ""),
                "title": meta.get("title", doc_names_snap.get(doc_id, "")),
                "url": meta.get("url"),
                "source": meta.get("source", "file"),
                "domain": meta.get("domain"),
                "score": round(min(1.0, max(0.0, score)), 4),
                "snippet": self._make_snippet(doc_id, set(q_tokens)),
            })
        return results

    # ------------------------------------------------------------------
    # Safe Snippet Generation
    # ------------------------------------------------------------------
    def _make_snippet(self, doc_id: int, q_tokens: set, window: int = 14):
        with self._lock:
            raw = self.documents.get(doc_id, "")
        if not raw:
            return ""

        words = raw.split()
        if not words:
            return ""

        lowered = [w.lower().strip(".,!?;:\"'()[]{}<>`~@#$%^&*") for w in words]
        for i, w in enumerate(lowered):
            if w in q_tokens:
                start = max(0, i - window // 2)
                end = min(len(words), i + window // 2)
                prefix = "... " if start > 0 else ""
                suffix = " ..." if end < len(words) else ""
                return prefix + " ".join(words[start:end]) + suffix

        return " ".join(words[:window]) + (" ..." if len(words) > window else "")

    # ------------------------------------------------------------------
    # Introspection helpers
    # ------------------------------------------------------------------
    def stats(self):
        with self._lock:
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
        if not term or not isinstance(term, str):
            return {"term": "", "document_frequency": 0, "idf": 0.0, "postings": {}}

        clean_term = term.lower().strip()[:60]
        with self._lock:
            postings = dict(self.inverted_index.get(clean_term, {}))
            df = self.doc_freq.get(clean_term, 0)
            term_idf = round(self.idf.get(clean_term, 0.0), 4)
            names_snap = self.doc_names

        return {
            "term": clean_term,
            "document_frequency": df,
            "idf": term_idf,
            "postings": {names_snap.get(d, str(d)): tf for d, tf in postings.items()},
        }
