# Resume Bullet Points: Mini Search Engine

Tailored, metric-driven bullet points for Software Engineering, Backend, and Data/IR roles. Choose the variation that best aligns with your target job description.

---

### Option 1: Software Engineer / Backend Focus (Recommended)

- **Engineered an Information Retrieval search engine from scratch in Python/Flask**, implementing inverted index construction, **Okapi BM25** ranking ($k_1=1.5, b=0.75$), and exact phrase-boosting (+30%), cutting irrelevant document retrieval and delivering sub-10ms query times.
- **Built a polite, multi-threaded breadth-first web crawler** adhering to `robots.txt` specifications and domain rate limits; implemented hardened **SSRF mitigation** blocking loopback, RFC 1918 private ranges, and AWS/GCP metadata endpoints (`169.254.169.254`).
- **Designed a secure multi-user architecture with Flask-Login & SQLAlchemy**, featuring `scrypt` password hashing, CSRF protection, and strictly isolated query bookmarking; achieved **88% test coverage across 57 automated pytest test suites** automated via GitHub Actions CI.

---

### Option 2: Data Engineering / Information Retrieval Focus

- **Implemented classic and modern IR algorithms from first principles** (Robertson-Spärck Jones BM25, TF-IDF cosine similarity, and a Prefix Trie autocompletion data structure), providing sublinear query suggestion and ranking over multi-source document indices.
- **Developed end-to-end data ingestion pipelines** combining local text corpora and live web crawling with BeautifulSoup HTML sanitization, tokenization, stopword filtering, and atomic thread-safe index reconstruction.
- **Enforced strict authorization and automated regression testing** with SQLite foreign-key associations and 57 comprehensive pytest unit and integration tests, verified on Python 3.11 and 3.12 CI matrix builds.

---

### Option 3: Full-Stack / Product Engineer Focus

- **Built a full-stack search engine with modern glassmorphism UI**, featuring debounced autocomplete, interactive ranking algorithm toggles (BM25 vs. Cosine), multi-dimensional score/source filtering, and personalized query history management.
- **Secured backend REST APIs against brute-force attacks and injection vulnerabilities**, implementing in-memory rate limiting (5 attempts/min), input sanitization, and strict ownership validation to prevent cross-user data exposure.
- **Authored complete developer documentation, architecture diagrams, and GitHub Actions CI pipelines**, maintaining 88% test coverage and zero-downtime atomic index refreshing.

---

### One-Line LinkedIn Project Summary

> **Mini Search Engine:** From-scratch Information Retrieval search engine and polite web crawler featuring Okapi BM25 & TF-IDF ranking, Prefix Trie autocomplete, SSRF-hardened crawling, Flask/SQLAlchemy auth, and 88% pytest code coverage with GitHub Actions CI.
