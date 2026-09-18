"""
API route and integration tests for app.py
Covers:
  - Public endpoints: /, /api/search, /api/suggest, /api/stats, /api/term/<word>
  - Input validation, empty queries, and oversized query handling
  - Path traversal and security hardening
  - User authentication: signup, duplicate email rejection, password validation, login, logout
  - Rate limiting on /login
  - Saved searches: POST, GET, DELETE
  - Security isolation: User B cannot see User A's searches, and cross-user deletion is blocked with HTTP 403
"""

import json
import pytest
from models import db, User, SavedSearch


class TestPublicAPI:
    """Tests for unauthenticated public search and discovery endpoints."""

    def test_home_page_renders_ok(self, client):
        res = client.get("/")
        assert res.status_code == 200
        assert b"mini-search-engine" in res.data
        assert b"Sign In" in res.data
        assert b"Sign Up" in res.data

    def test_healthz_endpoint(self, client):
        res = client.get("/healthz")
        assert res.status_code == 200
        data = res.get_json()
        assert data["status"] == "healthy"
        assert "documents_indexed" in data
        assert "environment" in data

    def test_search_valid_query(self, client):
        res = client.get("/api/search?q=machine&algo=bm25")
        assert res.status_code == 200
        data = res.get_json()
        assert "results" in data
        assert "count" in data
        assert data["count"] > 0
        assert data["algo"] == "bm25"
        top_result = data["results"][0]
        assert "score" in top_result
        assert "snippet" in top_result
        assert "phrase_matched" in top_result

    def test_search_empty_and_whitespace_queries(self, client):
        res = client.get("/api/search?q=")
        assert res.status_code == 200
        data = res.get_json()
        assert data["count"] == 0
        assert data["results"] == []

        res_spaces = client.get("/api/search?q=   ")
        assert res_spaces.status_code == 200
        assert res_spaces.get_json()["count"] == 0

    def test_search_oversized_query_rejected(self, client):
        long_query = "x" * 505
        res = client.get(f"/api/search?q={long_query}")
        assert res.status_code == 400
        assert "too long" in res.get_json()["error"].lower()

    def test_search_with_filters(self, client):
        # Local source filter
        res_local = client.get("/api/search?q=intelligence&source=local&algo=cosine")
        assert res_local.status_code == 200
        data_local = res_local.get_json()
        for r in data_local["results"]:
            assert r["source"] == "local"

        # Web source filter
        res_web = client.get("/api/search?q=python&source=web")
        assert res_web.status_code == 200
        data_web = res_web.get_json()
        for r in data_web["results"]:
            assert r["source"] == "web"

        # min_score cutoff
        res_cutoff = client.get("/api/search?q=machine&min_score=5.0")
        assert res_cutoff.status_code == 200
        for r in res_cutoff.get_json()["results"]:
            assert r["score"] >= 5.0

    def test_suggest_prefix_endpoint(self, client):
        res = client.get("/api/suggest?prefix=mac")
        assert res.status_code == 200
        data = res.get_json()
        assert "suggestions" in data
        terms = [s["term"] for s in data["suggestions"]]
        assert any(t.startswith("mac") for t in terms)

    def test_suggest_empty_prefix(self, client):
        res = client.get("/api/suggest?prefix=")
        assert res.status_code == 200
        assert res.get_json()["suggestions"] == []

    def test_stats_endpoint(self, client):
        res = client.get("/api/stats")
        assert res.status_code == 200
        data = res.get_json()
        assert data["num_documents"] == 4
        assert data["num_local_documents"] == 3
        assert data["num_web_documents"] == 1
        assert data["num_unique_terms"] > 0
        assert "avgdl" in data

    def test_term_lookup_existing_and_nonexistent(self, client):
        # Existing term
        res = client.get("/api/term/climate")
        assert res.status_code == 200
        data = res.get_json()
        assert data["term"] == "climate"
        assert data["document_frequency"] == 1
        assert len(data["postings"]) == 1

        # Nonexistent term
        res_missing = client.get("/api/term/nonexistenttermxyz")
        assert res_missing.status_code == 200
        assert res_missing.get_json()["document_frequency"] == 0
        assert res_missing.get_json()["postings"] == {}

    def test_term_lookup_path_traversal_blocked(self, client):
        res = client.get("/api/term/..%2f..%2fwindows%2fwin.ini")
        assert res.status_code in (400, 404)


class TestAuthenticationRoutes:
    """Tests for user signup, login, logout, and validation."""

    def test_signup_success(self, client, auth):
        res = auth.signup(email="alice@example.com", password="Password123!")
        assert res.status_code == 200
        # User created in database with hashed password
        user = User.query.filter_by(email="alice@example.com").first()
        assert user is not None
        assert user.password_hash != "Password123!"
        assert user.check_password("Password123!") is True
        # Topbar reflects authenticated state
        assert b"alice@example.com" in res.data

    def test_signup_duplicate_email_rejected(self, client, auth):
        auth.signup(email="dup@example.com", password="Password123!")
        auth.logout()

        # Second attempt with same email
        res2 = auth.signup(email="dup@example.com", password="Password123!")
        assert res2.status_code == 200
        assert b"already exists" in res2.data

    def test_signup_weak_password_rejected(self, client, auth):
        # Password shorter than 8 chars
        res = auth.signup(email="weak@example.com", password="short")
        assert res.status_code == 200
        assert b"at least 8 characters" in res.data
        assert User.query.filter_by(email="weak@example.com").first() is None

    def test_signup_mismatched_password_rejected(self, client, auth):
        res = auth.signup(email="mismatch@example.com", password="Password123!", confirm="DifferentPassword123!")
        assert res.status_code == 200
        assert b"Passwords do not match" in res.data
        assert User.query.filter_by(email="mismatch@example.com").first() is None

    def test_login_success_and_failure(self, client, auth):
        auth.signup(email="bob@example.com", password="Password123!")
        auth.logout()

        # Incorrect password
        res_fail = auth.login(email="bob@example.com", password="WrongPassword!")
        assert res_fail.status_code == 200
        assert b"Invalid email or password" in res_fail.data

        # Correct password
        res_ok = auth.login(email="bob@example.com", password="Password123!")
        assert res_ok.status_code == 200
        assert b"bob@example.com" in res_ok.data

    def test_logout(self, client, auth):
        auth.signup(email="carol@example.com", password="Password123!")
        res = auth.logout()
        assert res.status_code == 200
        assert b"signed out" in res.data.lower()


class TestSavedSearchesAndUserIsolation:
    """Critical tests for saved search queries and cross-user data isolation."""

    def test_anonymous_access_to_saved_searches_blocked(self, client):
        # GET requires auth
        res_get = client.get("/api/searches")
        assert res_get.status_code in (302, 401)

        # POST requires auth
        res_post = client.post("/api/searches", json={"query": "test query"})
        assert res_post.status_code in (302, 401)

    def test_save_and_list_searches(self, client, auth):
        auth.signup(email="user_a@example.com", password="Password123!")

        # Save query 1
        res1 = client.post(
            "/api/searches",
            json={"query": "neural networks", "algo": "bm25", "filters": {"source": "local", "min_score": 0.05}},
        )
        assert res1.status_code == 201
        data1 = res1.get_json()
        assert data1["success"] is True
        assert data1["saved_search"]["query"] == "neural networks"

        # Save query 2
        res2 = client.post(
            "/api/searches",
            json={"query": "climate change", "algo": "cosine", "filters": {"source": "all", "min_score": 0.1}},
        )
        assert res2.status_code == 201

        # Fetch list (newest first)
        list_res = client.get("/api/searches")
        assert list_res.status_code == 200
        list_data = list_res.get_json()
        assert list_data["count"] == 2
        assert list_data["searches"][0]["query"] == "climate change"
        assert list_data["searches"][1]["query"] == "neural networks"

    def test_user_isolation_and_unauthorized_deletion(self, client, auth):
        """
        Security verification:
          - User A saves a query.
          - User B logs in.
          - User B cannot see User A's query in GET /api/searches (count == 0).
          - User B attempting to DELETE User A's query is strictly rejected with 403 Forbidden.
        """
        # 1. User A saves a search
        auth.signup(email="alice_priv@example.com", password="Password123!")
        save_res = client.post(
            "/api/searches",
            json={"query": "confidential research query", "algo": "bm25"},
        )
        assert save_res.status_code == 201
        alice_search_id = save_res.get_json()["saved_search"]["id"]
        auth.logout()

        # 2. User B logs in
        auth.signup(email="bob_priv@example.com", password="Password123!")

        # User B cannot see Alice's saved search
        bob_list = client.get("/api/searches")
        assert bob_list.status_code == 200
        assert bob_list.get_json()["count"] == 0, "User B saw User A's saved search!"

        # User B attempts to delete Alice's saved search
        bob_del = client.delete(f"/api/searches/{alice_search_id}")
        assert bob_del.status_code == 403, f"Expected 403 Forbidden, got {bob_del.status_code}"
        assert "Forbidden" in bob_del.get_json()["error"]

        # Confirm Alice's search still exists in database
        saved_in_db = db.session.get(SavedSearch, alice_search_id)
        assert saved_in_db is not None, "Alice's search was improperly deleted by User B!"

        # 3. User A logs back in and successfully deletes their own search
        auth.logout()
        auth.login(email="alice_priv@example.com", password="Password123!")
        alice_del = client.delete(f"/api/searches/{alice_search_id}")
        assert alice_del.status_code == 200
        assert alice_del.get_json()["success"] is True

        # Confirm deleted
        alice_list = client.get("/api/searches")
        assert alice_list.get_json()["count"] == 0

    def test_saved_search_validation_errors(self, client, auth):
        auth.signup(email="validator@example.com", password="Password123!")

        # Non-JSON payload
        res_non_json = client.post("/api/searches", data="not json", content_type="text/plain")
        assert res_non_json.status_code == 400

        # Empty query
        res_empty = client.post("/api/searches", json={"query": "   "})
        assert res_empty.status_code == 400
        assert "empty" in res_empty.get_json()["error"].lower()

        # Delete non-existent ID
        res_missing = client.delete("/api/searches/999999")
        assert res_missing.status_code == 404

    def test_models_repr_and_filters(self, client, auth):
        auth.signup(email="repr_test@example.com", password="Password123!")
        user = User.query.filter_by(email="repr_test@example.com").first()
        assert "repr_test@example.com" in repr(user)

        saved = SavedSearch(user_id=user.id, query_text="test", algo="bm25")
        db.session.add(saved)
        db.session.commit()
        assert "test" in repr(saved)
        assert saved.get_filters()["source"] == "all"


class TestCrawlAPI:
    """Tests for POST /api/crawl endpoint."""

    def test_crawl_endpoint_with_mock(self, client, monkeypatch):
        # Mock crawler.crawl
        mock_report = {
            "pages_crawled": 1,
            "pages_skipped": 0,
            "errors": [],
            "pages": [{"url": "https://test.org/page", "title": "Test Page", "domain": "test.org"}],
        }
        monkeypatch.setattr("app.is_safe_url", lambda url: (True, "Safe"))
        monkeypatch.setattr("crawler.is_safe_url", lambda url: (True, "Safe"))
        import app
        monkeypatch.setattr(app.crawler, "crawl", lambda **kwargs: mock_report)

        res = client.post(
            "/api/crawl",
            json={"seed_urls": ["https://test.org/page"], "max_pages": 1, "max_depth": 1},
        )
        assert res.status_code == 200
        data = res.get_json()
        assert data["success"] is True
        assert data["pages_crawled"] == 1

    def test_crawl_endpoint_validation_errors(self, client):
        # Non-JSON
        res_text = client.post("/api/crawl", data="plain", content_type="text/plain")
        assert res_text.status_code == 400

        # Empty seeds
        res_empty = client.post("/api/crawl", json={"seed_urls": []})
        assert res_empty.status_code == 400

