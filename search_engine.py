"""
Mini Search Engine - Hardened Core Logic
=========================================
Implements:
  1. Multi-source document ingestion (local .txt files + crawled web pages)
  2. Robust text preprocessing & tokenization
  3. Thread-safe, atomic index rebuilding
  4. Prefix Trie for fast, prefix-matching query autocompletion ranked by document frequency
  5. Okapi BM25 ranking with configurable k1, b, document length normalization, and phrase-match boosting
  6. Vector space TF-IDF & cosine similarity ranking (fallback and comparative ranking)
  7. Multi-dimensional filtering by source (local vs web) and minimum score threshold

Hardened for edge cases:
  - Empty corpus (N = 0)
  - Documents with zero tokens / stopwords only
  - Queries with only stopwords
  - Zero-division in norms / document length calculations
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
about into over under again further once here there when where why how
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


def check_phrase_in_text(q_tokens: list[str], raw_text: str) -> bool:
    """Checks if exact sequence of query tokens appears consecutively in raw_text."""
    if len(q_tokens) < 2 or not raw_text:
        return False
    escaped_tokens = [re.escape(t) for t in q_tokens]
    pattern = r"\b" + r"(?:[\s\W]+)".join(escaped_tokens) + r"\b"
    return bool(re.search(pattern, raw_text, re.IGNORECASE))


class PrefixTrieNode:
    """Node in the prefix trie tracking children, terminal state, and document frequency."""
    __slots__ = ("children", "is_word", "df", "word")

    def __init__(self):
        self.children: dict[str, "PrefixTrieNode"] = {}
        self.is_word: bool = False
        self.df: int = 0
        self.word: str = ""


class PrefixTrie:
    """Prefix trie for fast autocompletion over vocabulary, ranked by document frequency."""

    def __init__(self):
        self.root = PrefixTrieNode()

    def insert(self, word: str, df: int):
        if not word:
            return
        node = self.root
        for ch in word:
            if ch not in node.children:
                node.children[ch] = PrefixTrieNode()
            node = node.children[ch]
        node.is_word = True
        node.df = max(node.df, df)
        node.word = word

    def search_prefix(self, prefix: str, limit: int = 8) -> list[dict]:
        """
        Finds all words starting with `prefix`, sorted by df descending.
        Returns list of dicts: [{"term": "...", "df": int}, ...].
        """
        if not prefix or not isinstance(prefix, str):
            return []
        clean_prefix = prefix.lower().strip()
        if not clean_prefix:
            return []

        node = self.root
        for ch in clean_prefix:
            if ch not in node.children:
                return []
            node = node.children[ch]

        matches = []
        stack = [node]
        while stack:
            curr = stack.pop()
            if curr.is_word:
                matches.append({"term": curr.word, "df": curr.df})
            for child in curr.children.values():
                stack.append(child)

        matches.sort(key=lambda m: (-m["df"], m["term"]))
        return matches[:limit]


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
        self.doc_lengths: dict[int, int] = {}
        self.avgdl: float = 1.0

        self.inverted_index: dict[str, dict[int, int]] = defaultdict(dict)
        self.doc_freq: dict[str, int] = {}
        self.idf: dict[str, float] = {}
        self.bm25_idf: dict[str, float] = {}
        self.doc_vectors: dict[int, dict[str, float]] = {}
        self.doc_norms: dict[int, float] = {}
        self.trie = PrefixTrie()
        self.N: int = 0

        self.reindex(extra_docs=extra_docs)

    # ------------------------------------------------------------------
    # Atomic Multi-Source Reindexing
    # ------------------------------------------------------------------
    def reindex(self, extra_docs: list[dict] | None = None):
        """
        Atomically rebuilds the inverted index, BM25 constants, Prefix Trie,
        and TF-IDF models from all sources.
        """
        new_documents = {}
        new_doc_meta = {}
        new_doc_names = {}
        new_tokenized_docs = {}
        new_doc_lengths = {}
        new_inverted_index = defaultdict(dict)
        new_doc_freq = {}
        new_idf = {}
        new_bm25_idf = {}
        new_doc_vectors = {}
        new_doc_norms = {}
        new_trie = PrefixTrie()

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
                    "source": "local",
                    "domain": "local",
                }
                new_tokenized_docs[doc_id] = tokens
                new_doc_lengths[doc_id] = len(tokens)
                doc_id += 1

        # Source B: Crawled web pages from crawled_dir
        if self.crawled_dir and os.path.isdir(self.crawled_dir):
            canonical_crawled_dir = os.path.abspath(self.crawled_dir)
            try:
                json_files = sorted(f for f in os.listdir(self.crawled_dir) if f.endswith(".json"))
            except Exception:
                json_files = []

            for jname in json_files:
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
                new_doc_lengths[doc_id] = len(tokens)
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

                doc_src = doc.get("source", "web" if url else "local")
                if doc_src in ("file", "local"):
                    doc_src = "local"
                else:
                    doc_src = "web"

                new_documents[doc_id] = text
                new_doc_names[doc_id] = title
                new_doc_meta[doc_id] = {
                    "filename": str(doc.get("filename") or title),
                    "title": title,
                    "url": url if (url.startswith("http://") or url.startswith("https://")) else None,
                    "source": doc_src,
                    "domain": str(doc.get("domain") or ""),
                }
                new_tokenized_docs[doc_id] = tokens
                new_doc_lengths[doc_id] = len(tokens)
                doc_id += 1

        total_n = len(new_documents)

        # Compute average document length (avgdl)
        total_len = sum(new_doc_lengths.values())
        new_avgdl = (total_len / total_n) if total_n > 0 else 1.0

        # Build Inverted Index & Document Frequency
        for d_id, tokens in new_tokenized_docs.items():
            term_counts = Counter(tokens)
            for term, tf in term_counts.items():
                new_inverted_index[term][d_id] = tf

        for term, postings in new_inverted_index.items():
            new_doc_freq[term] = len(postings)

        # Populate Prefix Trie with vocabulary
        for term, df in new_doc_freq.items():
            new_trie.insert(term, df)

        # Compute Cosine IDF, BM25 Robertson-Spärck Jones IDF, and TF-IDF Vectors
        if total_n > 0:
            for term, df in new_doc_freq.items():
                # Smooth Cosine IDF: >= 1.0
                new_idf[term] = max(1.0, math.log((1 + total_n) / (1 + df)) + 1)
                # Robertson-Spärck Jones BM25 IDF: strictly non-negative
                new_bm25_idf[term] = max(1e-4, math.log((total_n - df + 0.5) / (df + 0.5) + 1.0))

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
            self.doc_lengths = new_doc_lengths
            self.avgdl = new_avgdl
            self.inverted_index = new_inverted_index
            self.doc_freq = new_doc_freq
            self.idf = new_idf
            self.bm25_idf = new_bm25_idf
            self.doc_vectors = new_doc_vectors
            self.doc_norms = new_doc_norms
            self.trie = new_trie
            self.N = total_n

    def add_documents(self, new_docs: list[dict]):
        """Thread-safely ingests additional documents."""
        if not new_docs:
            return
        self.reindex(extra_docs=new_docs)

    # ------------------------------------------------------------------
    # Autocomplete Suggestions via Prefix Trie
    # ------------------------------------------------------------------
    def suggest(self, prefix: str, limit: int = 8) -> list[dict]:
        """Returns top N terms starting with prefix, ranked by doc frequency descending."""
        limit = max(1, min(int(limit), 25))
        with self._lock:
            trie_snap = self.trie
        return trie_snap.search_prefix(prefix, limit=limit)

    # ------------------------------------------------------------------
    # BM25 Ranking Algorithm
    # ------------------------------------------------------------------
    def bm25_search(
        self,
        query: str,
        top_k: int = 10,
        k1: float = 1.5,
        b: float = 0.75,
        phrase_boost: float = 1.3,
        source_filter: str | None = None,
        min_score: float = 0.0,
    ) -> list[dict]:
        """
        Calculates Okapi BM25 relevance scores:
          score(D, Q) = sum_t IDF(t) * (tf(t, D) * (k1 + 1)) / (tf(t, D) + k1 * (1 - b + b * (|D|/avgdl)))
        Applies phrase-match boosting (exact sequence match) and multi-dimensional filters.
        """
        if not query or not isinstance(query, str):
            return []

        sanitized_query = query.strip()[:500]
        q_tokens = tokenize(sanitized_query)
        if not q_tokens:
            return []

        top_k = max(1, min(int(top_k), 50))

        with self._lock:
            if self.N == 0:
                return []
            bm25_idf_snap = self.bm25_idf
            inv_snap = self.inverted_index
            doc_len_snap = self.doc_lengths
            avgdl_snap = self.avgdl or 1.0
            doc_meta_snap = self.doc_meta
            doc_names_snap = self.doc_names
            raw_docs_snap = self.documents

        # Gather candidate documents with at least one matching term
        candidate_docs = set()
        for term in q_tokens:
            if term in inv_snap:
                candidate_docs.update(inv_snap[term].keys())

        if not candidate_docs:
            return []

        scored = []
        is_multi_word = len(q_tokens) > 1

        for doc_id in candidate_docs:
            meta = doc_meta_snap.get(doc_id, {})
            source = "local" if meta.get("source") in ("file", "local") else "web"

            # Filter by source if requested
            if source_filter and source_filter.lower() != "all":
                sf = source_filter.lower()
                if sf in ("local", "file") and source != "local":
                    continue
                elif sf == "web" and source != "web":
                    continue

            d_len = doc_len_snap.get(doc_id, 0)
            score = 0.0
            for term in set(q_tokens):
                tf = inv_snap.get(term, {}).get(doc_id, 0)
                if tf <= 0:
                    continue
                term_idf = bm25_idf_snap.get(term, 0.0)
                denom = tf + k1 * (1.0 - b + b * (d_len / avgdl_snap))
                if denom > 0:
                    score += term_idf * (tf * (k1 + 1.0)) / denom

            phrase_matched = False
            if score > 0 and is_multi_word:
                raw_text = raw_docs_snap.get(doc_id, "")
                if check_phrase_in_text(q_tokens, raw_text):
                    score *= phrase_boost
                    phrase_matched = True

            if score >= min_score and score > 0:
                scored.append((doc_id, score, phrase_matched))

        scored.sort(key=lambda pair: pair[1], reverse=True)

        results = []
        for doc_id, score, phrase_matched in scored[:top_k]:
            meta = doc_meta_snap.get(doc_id, {})
            results.append({
                "doc_id": doc_id,
                "filename": doc_names_snap.get(doc_id, ""),
                "title": meta.get("title", doc_names_snap.get(doc_id, "")),
                "url": meta.get("url"),
                "source": "local" if meta.get("source") in ("file", "local") else "web",
                "domain": meta.get("domain"),
                "score": round(score, 4),
                "algo": "bm25",
                "phrase_matched": phrase_matched,
                "snippet": self._make_snippet(doc_id, set(q_tokens)),
            })
        return results

    # ------------------------------------------------------------------
    # Cosine Similarity Ranking (Vector Space Model)
    # ------------------------------------------------------------------
    def cosine_search(
        self,
        query: str,
        top_k: int = 10,
        phrase_boost: float = 1.3,
        source_filter: str | None = None,
        min_score: float = 0.0,
    ) -> list[dict]:
        """Vector space cosine similarity search with phrase boost and filters."""
        if not query or not isinstance(query, str):
            return []

        sanitized_query = query.strip()[:500]
        q_tokens = tokenize(sanitized_query)
        if not q_tokens:
            return []

        top_k = max(1, min(int(top_k), 50))

        with self._lock:
            if self.N == 0:
                return []
            idf_snap = self.idf
            inv_snap = self.inverted_index
            doc_vecs_snap = self.doc_vectors
            doc_norms_snap = self.doc_norms
            doc_meta_snap = self.doc_meta
            doc_names_snap = self.doc_names
            raw_docs_snap = self.documents

        q_counts = Counter(q_tokens)
        q_vector = {}
        for term, tf in q_counts.items():
            if term in idf_snap:
                weighted_tf = 1.0 + math.log(tf)
                q_vector[term] = weighted_tf * idf_snap[term]

        if not q_vector:
            return []

        q_norm = math.sqrt(sum(w * w for w in q_vector.values())) or 1e-9

        candidate_docs = set()
        for term in q_vector:
            candidate_docs.update(inv_snap.get(term, {}).keys())

        scored = []
        is_multi_word = len(q_tokens) > 1

        for doc_id in candidate_docs:
            meta = doc_meta_snap.get(doc_id, {})
            source = "local" if meta.get("source") in ("file", "local") else "web"

            # Filter by source if requested
            if source_filter and source_filter.lower() != "all":
                sf = source_filter.lower()
                if sf in ("local", "file") and source != "local":
                    continue
                elif sf == "web" and source != "web":
                    continue

            d_vector = doc_vecs_snap.get(doc_id)
            d_norm = doc_norms_snap.get(doc_id, 1e-9)
            if not d_vector:
                continue

            dot_product = sum(q_vector[t] * d_vector.get(t, 0.0) for t in q_vector)
            similarity = dot_product / (q_norm * d_norm)

            phrase_matched = False
            if similarity > 0 and is_multi_word:
                raw_text = raw_docs_snap.get(doc_id, "")
                if check_phrase_in_text(q_tokens, raw_text):
                    similarity *= phrase_boost
                    phrase_matched = True

            if similarity >= min_score and similarity > 0:
                scored.append((doc_id, similarity, phrase_matched))

        scored.sort(key=lambda pair: pair[1], reverse=True)

        results = []
        for doc_id, score, phrase_matched in scored[:top_k]:
            meta = doc_meta_snap.get(doc_id, {})
            results.append({
                "doc_id": doc_id,
                "filename": doc_names_snap.get(doc_id, ""),
                "title": meta.get("title", doc_names_snap.get(doc_id, "")),
                "url": meta.get("url"),
                "source": "local" if meta.get("source") in ("file", "local") else "web",
                "domain": meta.get("domain"),
                "score": round(min(1.0, max(0.0, score)), 4),
                "algo": "cosine",
                "phrase_matched": phrase_matched,
                "snippet": self._make_snippet(doc_id, set(q_tokens)),
            })
        return results

    # ------------------------------------------------------------------
    # Unified Search Router
    # ------------------------------------------------------------------
    def search(
        self,
        query: str,
        top_k: int = 10,
        algo: str = "bm25",
        source_filter: str | None = None,
        min_score: float = 0.0,
        k1: float = 1.5,
        b: float = 0.75,
        phrase_boost: float = 1.3,
    ) -> list[dict]:
        """
        Unified search router: defaults to BM25, supports 'cosine',
        source filtering ('all', 'local', 'web'), and min_score threshold.
        """
        algo_choice = (algo or "bm25").lower().strip()
        if algo_choice == "cosine":
            return self.cosine_search(
                query=query,
                top_k=top_k,
                phrase_boost=phrase_boost,
                source_filter=source_filter,
                min_score=min_score,
            )
        return self.bm25_search(
            query=query,
            top_k=top_k,
            k1=k1,
            b=b,
            phrase_boost=phrase_boost,
            source_filter=source_filter,
            min_score=min_score,
        )

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
            local_docs = [m["filename"] for m in self.doc_meta.values() if m.get("source") in ("file", "local")]
            web_docs = [m["title"] for m in self.doc_meta.values() if m.get("source") == "web"]
            return {
                "num_documents": self.N,
                "num_local_documents": len(local_docs),
                "num_web_documents": len(web_docs),
                "num_unique_terms": len(self.inverted_index),
                "avgdl": round(self.avgdl, 2),
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


if __name__ == "__main__":
    import sys
    base_dir = os.path.dirname(os.path.abspath(__file__))
    engine = SearchEngine(
        doc_dir=os.path.join(base_dir, "documents"),
        crawled_dir=os.path.join(base_dir, "crawled_pages"),
    )
    query_str = sys.argv[1] if len(sys.argv) > 1 else "machine learning"
    algo_arg = sys.argv[2] if len(sys.argv) > 2 else "bm25"
    print(f"=== Mini Search Engine ({algo_arg.upper()}) ===")
    print(f"Query: '{query_str}' across {engine.N} documents (avgdl={engine.avgdl:.1f})")
    for hit in engine.search(query_str, top_k=5, algo=algo_arg):
        phrase_flag = " [PHRASE MATCH]" if hit["phrase_matched"] else ""
        print(f"- [{hit['source'].upper()}] {hit['title']} (Score: {hit['score']:.4f}){phrase_flag}")
        print(f"  Snippet: {hit['snippet']}\n")
