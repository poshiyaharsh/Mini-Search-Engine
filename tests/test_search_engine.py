"""
Unit tests for search_engine.py
Covers:
  - Tokenization, punctuation stripping, stopwords, and edge cases
  - Prefix Trie insertion, prefix matching, and document frequency ordering
  - Inverted index construction and postings validation
  - Okapi BM25 and Cosine TF-IDF ranking algorithms
  - Phrase-match boosting (+30% multiplier)
  - Edge cases: empty queries, stopwords-only, words outside corpus
  - Filtering by source (local vs web) and min_score threshold
"""

import math
import pytest
from search_engine import tokenize, check_phrase_in_text, PrefixTrie, SearchEngine


class TestTokenize:
    """Tests for the tokenize() function."""

    def test_lowercase_and_punctuation_stripping(self):
        text = "Hello, World! This is a TEST: tokenize-this."
        tokens = tokenize(text)
        assert "hello" in tokens
        assert "world" in tokens
        assert "test" in tokens
        assert "tokenize" in tokens
        # Stopwords removed
        assert "this" not in tokens
        assert "is" not in tokens
        assert "a" not in tokens

    def test_stopwords_removed(self):
        text = "and the or but if then so as at by for"
        tokens = tokenize(text)
        assert tokens == []

    def test_empty_and_whitespace_input(self):
        assert tokenize("") == []
        assert tokenize("   \t\n  ") == []
        assert tokenize(None) == []
        assert tokenize(12345) == []

    def test_numbers_and_apostrophes_handled(self):
        text = "Python's release in 2026 was version 3.12!"
        tokens = tokenize(text)
        assert "python's" in tokens
        assert "2026" in tokens
        assert "release" in tokens
        assert "version" in tokens

    def test_token_length_boundaries(self):
        # Single-character tokens must be dropped
        assert tokenize("a b c x y z") == []
        # Normal tokens retained
        tokens = tokenize("ai ml data")
        assert tokens == ["ai", "ml", "data"]
        # Extremely long tokens (>60 chars) dropped
        long_word = "a" * 65
        assert tokenize(long_word) == []


class TestPrefixTrie:
    """Tests for the PrefixTrie autocompletion data structure."""

    def test_trie_insert_and_prefix_search(self):
        trie = PrefixTrie()
        trie.insert("machine", df=5)
        trie.insert("machinery", df=2)
        trie.insert("macro", df=8)
        trie.insert("python", df=10)

        matches = trie.search_prefix("mac")
        terms = [m["term"] for m in matches]
        assert "macro" in terms
        assert "machine" in terms
        assert "machinery" in terms
        assert "python" not in terms

        # Verify sorted descending by df
        assert matches[0]["term"] == "macro"  # df 8
        assert matches[1]["term"] == "machine"  # df 5
        assert matches[2]["term"] == "machinery"  # df 2

    def test_trie_limit_parameter(self):
        trie = PrefixTrie()
        for i in range(15):
            trie.insert(f"testword{i}", df=i)

        matches = trie.search_prefix("test", limit=5)
        assert len(matches) == 5

    def test_trie_case_insensitivity_and_empty(self):
        trie = PrefixTrie()
        trie.insert("neural", df=3)

        assert len(trie.search_prefix("NEUR")) == 1
        assert trie.search_prefix("") == []
        assert trie.search_prefix("   ") == []
        assert trie.search_prefix("unknownprefix") == []
        assert trie.search_prefix(None) == []


class TestInvertedIndex:
    """Tests for the inverted index created from the test_engine fixture."""

    def test_corpus_document_count(self, test_engine):
        # 3 local documents + 1 crawled web page from fixture
        assert test_engine.N == 4
        assert len(test_engine.documents) == 4

    def test_postings_for_known_words(self, test_engine):
        # "climate" should appear ONLY in doc3
        climate_postings = test_engine.inverted_index.get("climate", {})
        assert len(climate_postings) == 1
        doc_id = list(climate_postings.keys())[0]
        assert test_engine.doc_meta[doc_id]["filename"] == "doc3.txt"
        assert test_engine.doc_freq["climate"] == 1

        # "neural" should appear in doc1 and doc2 (df == 2)
        neural_postings = test_engine.inverted_index.get("neural", {})
        assert len(neural_postings) == 2
        assert test_engine.doc_freq["neural"] == 2

    def test_average_document_length(self, test_engine):
        assert test_engine.avgdl > 0
        total_tokens = sum(test_engine.doc_lengths.values())
        expected_avgdl = total_tokens / test_engine.N
        assert pytest.approx(test_engine.avgdl, 0.001) == expected_avgdl


class TestRankingAlgorithms:
    """Tests for BM25, Cosine similarity, and phrase match boosting."""

    def test_bm25_positive_idf(self, test_engine):
        for term, idf_val in test_engine.bm25_idf.items():
            assert idf_val > 0, f"BM25 IDF for '{term}' must be positive, got {idf_val}"

    def test_bm25_known_query_ranking(self, test_engine):
        results = test_engine.search("climate change", algo="bm25")
        assert len(results) > 0
        top_hit = results[0]
        # Top hit must be doc3.txt
        assert top_hit["filename"] == "doc3.txt"
        assert top_hit["score"] > 0
        assert top_hit["phrase_matched"] is True

    def test_cosine_similarity_ranking(self, test_engine):
        results = test_engine.search("climate change", algo="cosine")
        assert len(results) > 0
        top_hit = results[0]
        assert top_hit["filename"] == "doc3.txt"
        # Cosine score normalized
        assert 0.0 <= top_hit["score"] <= 1.5

    def test_phrase_match_boost(self, test_engine):
        # "neural networks" is an exact contiguous phrase in doc1 and doc2
        results = test_engine.search("neural networks", algo="bm25")
        assert len(results) >= 2
        for r in results[:2]:
            assert r["phrase_matched"] is True

    def test_phrase_match_helper(self):
        assert check_phrase_in_text(["machine", "learning"], "We study machine learning today.") is True
        assert check_phrase_in_text(["machine", "learning"], "Machine! Learning is fun.") is True
        assert check_phrase_in_text(["machine", "learning"], "Learning machine algorithms.") is False
        assert check_phrase_in_text([], "Any text") is False
        assert check_phrase_in_text(["single"], "Single word check returns False") is False

    def test_term_saturation_property(self):
        # A document with 10 repetitions should NOT score 10x a document with 1 repetition under BM25
        engine = SearchEngine(extra_docs=[
            {"title": "Doc1", "text": "quantum quantum quantum quantum quantum quantum quantum quantum quantum quantum physics"},
            {"title": "Doc2", "text": "quantum physics"},
        ])
        results = engine.search("quantum", algo="bm25")
        assert len(results) == 2
        score_doc1 = next(r["score"] for r in results if r["title"] == "Doc1")
        score_doc2 = next(r["score"] for r in results if r["title"] == "Doc2")
        # Due to term saturation (k1=1.5), ratio should be far below 10.0
        assert (score_doc1 / score_doc2) < 3.0


class TestSearchEngineQueriesAndFilters:
    """Tests for SearchEngine.search() queries, edge cases, and filters."""

    def test_empty_query_returns_empty_list(self, test_engine):
        assert test_engine.search("") == []
        assert test_engine.search("    ") == []
        assert test_engine.search(None) == []

    def test_stopwords_only_query_returns_empty_list(self, test_engine):
        assert test_engine.search("and the or but if") == []

    def test_query_outside_corpus_returns_empty_list(self, test_engine):
        assert test_engine.search("xylophone zeppelin pterodactyl") == []

    def test_filter_by_source_local(self, test_engine):
        # Searching for a term that appears in both local and web or all
        results = test_engine.search("intelligence", source_filter="local")
        assert len(results) > 0
        for r in results:
            assert r["source"] == "local"

    def test_filter_by_source_web(self, test_engine):
        results = test_engine.search("python programming", source_filter="web")
        assert len(results) > 0
        for r in results:
            assert r["source"] == "web"
            assert r["domain"] == "example.org"

    def test_filter_by_min_score(self, test_engine):
        all_results = test_engine.search("machine learning", min_score=0.0)
        filtered_results = test_engine.search("machine learning", min_score=2.0)
        assert len(filtered_results) <= len(all_results)
        for r in filtered_results:
            assert r["score"] >= 2.0
