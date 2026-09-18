# Technical Interview Preparation Guide: Mini Search Engine

Anticipated interview questions, system design deep-dives, and structured model answers based directly on this codebase's architecture and trade-offs.

---

### 1. Why use an inverted index and BM25 instead of SQL `LIKE %query%` or basic keyword matching?
> **Model Answer:**  
> A SQL `LIKE '%term%'` query requires a full table scan ($O(N)$), cannot leverage B-tree indexes effectively, and binary-matches terms without any notion of document relevance or frequency. An inverted index maps vocabulary terms directly to document postings in $O(1)$ dictionary lookup time. Furthermore, Okapi BM25 mathematically ranks results based on term rarity across the corpus (IDF), limits keyword-stuffing bias via asymptotic term saturation ($k_1$), and normalizes for document length ($b$).

---

### 2. What is the fundamental difference between classic TF-IDF and Okapi BM25?
> **Model Answer:**  
> Classic TF-IDF assumes relevance scales linearly or logarithmically with term frequency, which allows keyword-stuffed documents or lengthy documents to artificially dominate search results. BM25 solves this by introducing **term saturation**—as term frequency grows, its marginal score contribution asymptotically approaches an upper bound controlled by $k_1$ (1.5). Additionally, BM25 normalizes document length relative to the corpus average (`avgdl`), penalizing verbosity while rewarding concise, highly relevant documents.

---

### 3. How did you implement real-time autocomplete suggestions without relying on external APIs?
> **Model Answer:**  
> I built an in-memory **Prefix Trie** populated during inverted index construction with every unique vocabulary token and its corpus document frequency (`df`). When a user types, the frontend debounces the input by 250ms and queries the `/api/suggest` endpoint, which traverses the trie in $O(L)$ time (where $L$ is prefix length) and gathers matching completions via depth-first search. The suggestions are sorted descending by `df` so the most common, informative terms across the corpus appear first.

---

### 4. How would you scale this inverted index beyond a single machine's RAM to millions of documents?
> **Model Answer:**  
> To scale past memory limits, I would transition the inverted index from in-memory Python dictionaries to **immutable, disk-backed segmented posting lists** (similar to Lucene/Elasticsearch SSTables), with memory-mapped term dictionaries (FSTs) pointing to on-disk byte offsets. At multi-node scale, documents would be **horizontally partitioned (sharded)** across a cluster using document-ID hashing. A coordinator node would broadcast queries to all shards, execute parallel BM25 scoring, and perform a $k$-way merge of the top results, backed by a distributed cache (like Redis) for frequent queries.

---

### 5. How do you prevent cross-user data leakage and IDOR (Insecure Direct Object References) in saved searches?
> **Model Answer:**  
> In Flask-SQLAlchemy, every `SavedSearch` row has a foreign key `user_id` linked to the authenticated `User` record. On read operations (`GET /api/searches`), the query strictly filters by `SavedSearch.user_id == current_user.id`, guaranteeing users only retrieve their own rows. On mutating operations (`DELETE /api/searches/<id>`), the endpoint retrieves the record and explicitly verifies `search.user_id == current_user.id`, instantly aborting with `403 Forbidden` if another user attempts deletion, verified by automated unit tests.

---

### 6. What security defenses did you implement in the web crawler to prevent SSRF and crawler traps?
> **Model Answer:**  
> To prevent Server-Side Request Forgery (SSRF), every seed URL and extracted redirect hop is pre-screened with `socket.getaddrinfo` and validated using Python's `ipaddress` module against loopback (`127.0.0.1`), private RFC 1918 subnets, link-local metadata addresses (like AWS `169.254.169.254`), and non-HTTP schemes. To prevent spider traps and denial of service, the crawler enforces a strict `max_depth` (2), caps visited pages (`max_pages`), enforces a polite 1.0-second delay per domain, and honors `robots.txt` Disallow directives via `urllib.robotparser`.

---

### 7. How does the system maintain thread safety when a crawl triggers a reindex while users are searching?
> **Model Answer:**  
> The `SearchEngine` class uses a re-entrant lock (`threading.RLock`) and an **atomic swap strategy**. During indexing, documents and posting lists are compiled into new temporary data structures completely outside the critical lock path. Once computation finishes, the lock is acquired for a few microseconds solely to reassign the pointers (`self.inverted_index`, `self.doc_vectors`, `self.trie`), ensuring active search threads always read a consistent snapshot with zero race conditions or index corruption.

---

### 8. What was the hardest bug you encountered in this project, and how did you diagnose and solve it?
> **Model Answer:**  
> The trickiest issue was a UI state desynchronization where the user dropdown and saved searches panel remained permanently open on the page after login. The root cause was that the HTML elements had the `hidden` class applied, but the CSS stylesheet only defined `.crawler-body.hidden` without a universal `.hidden { display: none !important; }` rule, rendering JavaScript class toggles completely ineffective visually. I solved it by creating a universal utility rule, adding explicit component-scoped `.user-dropdown.hidden` styles, and setting `position: relative; z-index: 100` on the topbar to resolve stacking context conflicts.

---

### 9. Why choose SQLite over PostgreSQL for this application?
> **Model Answer:**  
> SQLite is zero-configuration, serverless, and stores the entire database in a single file (`instance/app.db`), making the project completely self-contained and reproducible with zero infrastructure overhead for local evaluation or CI testing. For our application—handling user authentication sessions and dozens of saved searches per user—SQLite's read concurrency and write-ahead logging (WAL) are more than fast enough. If we scaled to thousands of concurrent writes, migrating to PostgreSQL would require changing only the SQLAlchemy connection URI.

---

### 10. How did you design the automated test suite to run reliably without network dependencies or flaky tests?
> **Model Answer:**  
> I used `pytest` with isolated fixtures in `conftest.py`: search algorithm tests use a temporary fixture directory populated with 3 deterministic text files with known term frequencies, guaranteeing mathematical assertions never break due to real corpus changes. Database tests run against an isolated temporary SQLite database created and dropped per test run, and all external HTTP calls in crawler tests are mocked using the `responses` library, achieving **88% overall code coverage across 57 tests** with sub-3-second execution time.
