"""
Shared pytest fixtures for Mini Search Engine test suite.
Provides:
  - temp_corpus: Isolated directory with fixed, deterministic .txt documents
  - temp_crawled_dir: Isolated directory with a fixed crawled JSON web page
  - test_engine: SearchEngine instance built from deterministic fixture documents
  - app: Flask app fixture configured for testing with a temporary SQLite database
  - client: Flask test client for API endpoint testing
  - auth_client: Helper class for multi-user authentication testing
"""

import os
import json
import pytest
from app import app as flask_app, engine as default_engine, crawler as default_crawler
from models import db, User, SavedSearch
from search_engine import SearchEngine
from crawler import WebCrawler


@pytest.fixture
def temp_corpus(tmp_path):
    """Creates a temporary documents/ directory with 3 known, small test documents."""
    doc_dir = tmp_path / "documents"
    doc_dir.mkdir(parents=True, exist_ok=True)

    (doc_dir / "doc1.txt").write_text(
        "Machine learning algorithms and deep neural networks are foundational to modern artificial intelligence systems.",
        encoding="utf-8",
    )
    (doc_dir / "doc2.txt").write_text(
        "Artificial intelligence applications in healthcare use neural networks and machine learning for diagnosis.",
        encoding="utf-8",
    )
    (doc_dir / "doc3.txt").write_text(
        "Climate change and global warming require immediate transition to renewable green energy solutions.",
        encoding="utf-8",
    )
    return str(doc_dir)


@pytest.fixture
def temp_crawled_dir(tmp_path):
    """Creates a temporary crawled_pages/ directory with 1 known web page JSON."""
    crawled_dir = tmp_path / "crawled_pages"
    crawled_dir.mkdir(parents=True, exist_ok=True)

    page_data = {
        "url": "https://example.org/python-guide",
        "title": "Python Programming Guide",
        "domain": "example.org",
        "text": "Python programming language emphasizes code readability, software engineering best practices, and clean architecture.",
        "crawled_at": "2026-09-18T10:00:00Z",
    }
    with open(crawled_dir / "page_1.json", "w", encoding="utf-8") as f:
        json.dump(page_data, f)

    return str(crawled_dir)


@pytest.fixture
def test_engine(temp_corpus, temp_crawled_dir):
    """Creates an isolated SearchEngine instance populated only by the fixture corpus."""
    return SearchEngine(doc_dir=temp_corpus, crawled_dir=temp_crawled_dir)


@pytest.fixture
def app(tmp_path, temp_corpus, temp_crawled_dir):
    """
    Configures the Flask app for testing:
      - Uses temporary SQLite database file in tmp_path
      - Sets TESTING = True and disables CSRF validation for direct API tests
      - Swaps the SearchEngine and WebCrawler instances to point to temporary fixtures
      - Drops and creates all tables cleanly before and after the test
    """
    test_db = tmp_path / "test_app.db"
    flask_app.config.update({
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": f"sqlite:///{test_db}",
        "WTF_CSRF_ENABLED": False,
        "SECRET_KEY": "test-secret-key-for-pytest-execution",
    })

    # Wire test engine and crawler into app module
    import app as app_module
    old_engine = app_module.engine
    old_crawler = app_module.crawler

    test_eng = SearchEngine(doc_dir=temp_corpus, crawled_dir=temp_crawled_dir)
    test_crw = WebCrawler(crawled_dir=temp_crawled_dir, delay_seconds=0.0)
    app_module.engine = test_eng
    app_module.crawler = test_crw

    with flask_app.app_context():
        db.create_all()
        yield flask_app
        db.session.remove()
        db.drop_all()

    # Restore originals
    app_module.engine = old_engine
    app_module.crawler = old_crawler


@pytest.fixture
def client(app):
    """Provides Flask test client."""
    return app.test_client()


class AuthHelper:
    """Helper utility for registering and signing in users within the Flask test client."""
    def __init__(self, client):
        self.client = client

    def signup(self, email="user@example.com", password="Password123!", confirm=None):
        if confirm is None:
            confirm = password
        return self.client.post(
            "/signup",
            data={"email": email, "password": password, "confirm_password": confirm},
            follow_redirects=True,
        )

    def login(self, email="user@example.com", password="Password123!"):
        return self.client.post(
            "/login",
            data={"email": email, "password": password},
            follow_redirects=True,
        )

    def logout(self):
        return self.client.post("/logout", follow_redirects=True)


@pytest.fixture
def auth(client):
    """Provides an AuthHelper instance bound to the active test client."""
    return AuthHelper(client)
