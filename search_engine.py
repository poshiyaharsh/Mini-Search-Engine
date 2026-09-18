"""
Mini Search Engine - Core Logic
=================================
Implements:
  1. Text preprocessing (tokenization, stopword removal)
  2. An inverted index (word -> which documents contain it, and how often)
  3. TF-IDF weighting (how important a word is to a document, relative to the corpus)
  4. Cosine similarity ranking (compares the query vector to each document vector)

This is deliberately written without any external NLP/search libraries so every
step of "how Google-style search actually works" is visible and hackable.
"""

import os
import re
import math
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
    text = text.lower()
    tokens = TOKEN_PATTERN.findall(text)
    return [t for t in tokens if t not in STOPWORDS and len(t) > 1]


class SearchEngine:
    def __init__(self, doc_dir: str):
        self.doc_dir = doc_dir
        self.documents = {}        # doc_id -> raw text
        self.doc_names = {}        # doc_id -> filename
        self.tokenized_docs = {}   # doc_id -> list of tokens
        self.inverted_index = defaultdict(dict)  # term -> {doc_id: term_frequency}
        self.doc_freq = {}         # term -> number of documents containing it
        self.idf = {}              # term -> inverse document frequency
        self.doc_vectors = {}      # doc_id -> {term: tf_idf_weight}
        self.doc_norms = {}        # doc_id -> vector length (for cosine similarity)
        self.N = 0                 # total number of documents

        self._load_documents()
        self._build_inverted_index()
        self._compute_tfidf()

    # ------------------------------------------------------------------
    # STEP 1: Load and tokenize the corpus
    # ------------------------------------------------------------------
    def _load_documents(self):
        files = sorted(f for f in os.listdir(self.doc_dir) if f.endswith(".txt"))
        for doc_id, fname in enumerate(files):
            path = os.path.join(self.doc_dir, fname)
            with open(path, "r", encoding="utf-8") as f:
                text = f.read()
            self.documents[doc_id] = text
            self.doc_names[doc_id] = fname
            self.tokenized_docs[doc_id] = tokenize(text)
        self.N = len(self.documents)

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
        if not q_tokens:
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
        # (this is exactly why the inverted index exists - it lets us avoid
        # scanning every document for every query).
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
            results.append({
                "doc_id": doc_id,
                "filename": self.doc_names[doc_id],
                "score": round(score, 4),
                "snippet": self._make_snippet(doc_id, set(q_tokens)),
            })
        return results

    # ------------------------------------------------------------------
    # Helper: build a short preview around the first matching query word
    # ------------------------------------------------------------------
    def _make_snippet(self, doc_id: int, q_tokens: set, window: int = 14):
        words = self.documents[doc_id].split()
        lowered = [w.lower().strip(".,!?;:\"'()") for w in words]
        for i, w in enumerate(lowered):
            if w in q_tokens:
                start = max(0, i - window // 2)
                end = min(len(words), i + window // 2)
                return " ".join(words[start:end]) + " ..."
        return " ".join(words[:window]) + " ..."

    # ------------------------------------------------------------------
    # Introspection helpers, handy for a "how does this work" debug view
    # ------------------------------------------------------------------
    def stats(self):
        return {
            "num_documents": self.N,
            "num_unique_terms": len(self.inverted_index),
            "documents": [self.doc_names[i] for i in range(self.N)],
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
    # Quick manual test from the command line:
    #   python search_engine.py "machine learning ranking"
    import sys
    base_dir = os.path.dirname(os.path.abspath(__file__))
    engine = SearchEngine(os.path.join(base_dir, "documents"))
    query = " ".join(sys.argv[1:]) or "machine learning search ranking"
    print(f"\nQuery: {query!r}")
    print(f"Indexed {engine.N} documents, {len(engine.inverted_index)} unique terms\n")
    for rank, r in enumerate(engine.search(query), start=1):
        print(f"{rank}. {r['filename']}  (score={r['score']})")
        print(f"   ...{r['snippet']}\n")
