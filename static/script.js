/**
 * Mini Search Engine - Hardened Frontend Logic
 * Connects to Flask /api/search, /api/stats, and /api/crawl
 *
 * Security & Bug Hardening:
 *  - Comprehensive HTML escaping (&, <, >, ", ')
 *  - Protocol sanitization on links (strictly http/https, blocking javascript:/data:)
 *  - Injection-safe snippet highlighting
 *  - Robust fetch error handling with explicit status checks & user-facing error reporting
 */

const form = document.getElementById("searchForm");
const input = document.getElementById("queryInput");
const resultsEl = document.getElementById("results");
const metaLine = document.getElementById("metaLine");
const emptyState = document.getElementById("emptyState");
const toggleIndexBtn = document.getElementById("toggleIndex");
const indexPanel = document.getElementById("indexPanel");
const indexPanelBody = document.getElementById("indexPanelBody");
const clearBtn = document.getElementById("clearBtn");
const docCountBadge = document.getElementById("docCountBadge");

// Crawler Elements
const toggleCrawlerEl = document.getElementById("toggleCrawler");
const crawlerToggleBtn = document.getElementById("crawlerToggleBtn");
const crawlerBody = document.getElementById("crawlerBody");
const crawlerForm = document.getElementById("crawlerForm");
const seedUrlsInput = document.getElementById("seedUrlsInput");
const maxPagesInput = document.getElementById("maxPagesInput");
const maxDepthInput = document.getElementById("maxDepthInput");
const crawlSubmitBtn = document.getElementById("crawlSubmitBtn");
const crawlerStatus = document.getElementById("crawlerStatus");

const initialEmptyStateHtml = emptyState ? emptyState.innerHTML : "";

// ------------------------------------------------------------------
// XSS Sanitization & URL Verification
// ------------------------------------------------------------------
function escapeHtml(str) {
  if (str === null || str === undefined) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function sanitizeUrl(url) {
  if (!url || typeof url !== "string") return "";
  const trimmed = url.trim();
  // Strictly enforce http and https schemes to prevent javascript: or data: XSS
  if (/^https?:\/\//i.test(trimmed)) {
    return trimmed;
  }
  return "";
}

function highlightSnippet(snippet, queryWords) {
  if (!snippet) return "";
  if (!queryWords || !queryWords.length) return escapeHtml(snippet);

  const escapedWords = queryWords
    .filter(Boolean)
    .map((w) => w.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"));

  if (!escapedWords.length) return escapeHtml(snippet);

  const pattern = new RegExp("\\b(" + escapedWords.join("|") + ")\\b", "gi");

  let result = "";
  let lastIndex = 0;
  let match;

  // Split on raw text to guarantee HTML entities cannot be corrupted
  while ((match = pattern.exec(snippet)) !== null) {
    result += escapeHtml(snippet.slice(lastIndex, match.index));
    result += `<mark>${escapeHtml(match[0])}</mark>`;
    lastIndex = pattern.lastIndex;
  }
  result += escapeHtml(snippet.slice(lastIndex));
  return result;
}

// ------------------------------------------------------------------
// UI State Helpers
// ------------------------------------------------------------------
function resetToDefaultState() {
  resultsEl.innerHTML = "";
  metaLine.innerHTML = "";
  if (emptyState) {
    emptyState.classList.remove("hidden");
    emptyState.style.display = "block";
    emptyState.innerHTML = initialEmptyStateHtml;
  }
  if (clearBtn) {
    clearBtn.style.display = "none";
  }
}

// ------------------------------------------------------------------
// Search Execution
// ------------------------------------------------------------------
async function runSearch(query) {
  const trimmed = query.trim();
  if (!trimmed) {
    resetToDefaultState();
    return;
  }

  metaLine.textContent = "computing TF-IDF cosine similarities…";
  resultsEl.innerHTML = "";

  try {
    const res = await fetch(`/api/search?q=${encodeURIComponent(trimmed)}`);
    const data = await res.json().catch(() => ({}));

    if (!res.ok) {
      throw new Error(data.error || `Server returned error code ${res.status}`);
    }

    if (data.total_indexed !== undefined && docCountBadge) {
      docCountBadge.textContent = data.total_indexed;
    }

    if (data.count === 0) {
      metaLine.textContent = `no documents matched "${data.query}"`;
      if (emptyState) {
        emptyState.classList.remove("hidden");
        emptyState.style.display = "block";
        emptyState.innerHTML = `
          <div class="empty-icon">
            <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round">
              <circle cx="11" cy="11" r="8"></circle>
              <line x1="21" y1="21" x2="16.65" y2="16.65"></line>
              <line x1="8" y1="11" x2="14" y2="11"></line>
            </svg>
          </div>
          <h3 class="empty-title">No matching terms</h3>
          <p class="empty-desc">
            None of the indexed documents contain words from <strong>"${escapeHtml(data.query)}"</strong>.
            Try broader terms, single concepts, or crawl relevant web pages using the Live Web Crawler above.
          </p>
        `;
      }
      return;
    }

    if (emptyState) {
      emptyState.classList.add("hidden");
      emptyState.style.display = "none";
    }

    metaLine.textContent = `${data.count} result${data.count === 1 ? "" : "s"} for "${data.query}" — ranked by vector cosine similarity`;

    const queryWords = data.query.toLowerCase().split(/\s+/).filter(Boolean);
    const maxScore = (data.results[0] && data.results[0].score) || 1;

    data.results.forEach((r, i) => {
      const li = document.createElement("li");
      li.className = "result";
      li.style.animationDelay = `${Math.min(i * 50, 400)}ms`;
      const pct = Math.max(6, Math.round((r.score / maxScore) * 100));

      const isWeb = r.source === "web";
      const safeLink = sanitizeUrl(r.url);

      const sourceBadgeHtml = isWeb
        ? `<span class="source-tag source-web" title="Crawled from live web page">
            <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"></circle><line x1="2" y1="12" x2="22" y2="12"></line><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"></path></svg>
            ${escapeHtml(r.domain || "Web Page")}
          </span>`
        : `<span class="source-tag source-file" title="Local document file">
            <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline></svg>
            Local Doc
          </span>`;

      const titleHtml = (isWeb && safeLink)
        ? `<a href="${escapeHtml(safeLink)}" target="_blank" rel="noopener noreferrer" class="result-link" title="Open ${escapeHtml(safeLink)} in new tab">
            ${escapeHtml(r.title || r.filename)}
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"></path><polyline points="15 3 21 3 21 9"></polyline><line x1="10" y1="14" x2="21" y2="3"></line></svg>
          </a>`
        : escapeHtml(r.title || r.filename);

      li.innerHTML = `
        <div class="result-head">
          <div class="result-title-group">
            <span class="result-rank">#${i + 1}</span>
            ${sourceBadgeHtml}
            <span class="result-title">${titleHtml}</span>
          </div>
          <span class="result-score">
            <span class="score-label">similarity</span>
            <span class="score-value">${r.score.toFixed(4)}</span>
          </span>
        </div>
        <div class="score-bar" title="Relative similarity match: ${pct}%">
          <div style="width: ${pct}%"></div>
        </div>
        <div class="result-snippet">${highlightSnippet(r.snippet, queryWords)}</div>
      `;
      resultsEl.appendChild(li);
    });
  } catch (err) {
    metaLine.textContent = `Search error: ${err.message}`;
    console.error("Search fetch error:", err);
  }
}

// ------------------------------------------------------------------
// Event Listeners
// ------------------------------------------------------------------
form.addEventListener("submit", (e) => {
  e.preventDefault();
  const q = input.value.trim();
  if (q) runSearch(q);
});

if (clearBtn) {
  clearBtn.addEventListener("click", () => {
    input.value = "";
    input.focus();
    resetToDefaultState();
  });
}

input.addEventListener("input", () => {
  if (clearBtn) {
    clearBtn.style.display = input.value.length > 0 ? "flex" : "none";
  }
  if (!input.value.trim()) {
    resetToDefaultState();
  }
});

document.addEventListener("click", (e) => {
  const chip = e.target.closest(".query-chip");
  if (chip && chip.dataset.query) {
    const q = chip.dataset.query;
    input.value = q;
    if (clearBtn) clearBtn.style.display = "flex";
    runSearch(q);
    window.scrollTo({ top: form.offsetTop - 40, behavior: "smooth" });
  }
});

// ------------------------------------------------------------------
// Web Crawler UI Controls
// ------------------------------------------------------------------
function toggleCrawler() {
  const isHidden = crawlerBody.classList.contains("hidden");
  crawlerBody.classList.toggle("hidden");
  crawlerToggleBtn.classList.toggle("expanded", isHidden);
  const btnText = crawlerToggleBtn.querySelector(".btn-text");
  if (btnText) {
    btnText.textContent = isHidden ? "Close Crawler" : "Open Crawler";
  }
  crawlerToggleBtn.setAttribute("aria-expanded", isHidden ? "true" : "false");
}

if (toggleCrawlerEl) {
  toggleCrawlerEl.addEventListener("click", (e) => {
    if (e.target.closest("#crawlerToggleBtn") && e.currentTarget !== e.target) return;
    toggleCrawler();
  });
}
if (crawlerToggleBtn) {
  crawlerToggleBtn.addEventListener("click", (e) => {
    e.stopPropagation();
    toggleCrawler();
  });
}

if (crawlerForm) {
  crawlerForm.addEventListener("submit", async (e) => {
    e.preventDefault();

    const rawSeeds = seedUrlsInput.value.trim();
    if (!rawSeeds) return;

    const seed_urls = rawSeeds.split(/[\n,]+/).map((s) => s.trim()).filter(Boolean);
    const max_pages = parseInt(maxPagesInput.value, 10) || 5;
    const max_depth = parseInt(maxDepthInput.value, 10) || 1;

    // Loading State
    crawlSubmitBtn.disabled = true;
    crawlSubmitBtn.innerHTML = `<span class="spinner"></span> <span>Crawling...</span>`;
    crawlerStatus.className = "crawler-status status-loading";
    crawlerStatus.classList.remove("hidden");
    crawlerStatus.innerHTML = `
      <span class="spinner"></span>
      <span>Checking robots.txt & SSRF safety rules, crawling up to <strong>${max_pages}</strong> page(s)...</span>
    `;

    try {
      const res = await fetch("/api/crawl", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ seed_urls, max_pages, max_depth }),
      });
      const data = await res.json().catch(() => ({}));

      if (!res.ok) {
        throw new Error(data.error || `Crawl request failed with HTTP ${res.status}`);
      }

      if (data.success) {
        crawlerStatus.className = "crawler-status status-success";
        let summaryHtml = `
          <div>
            <strong>Crawl Complete!</strong> Successfully indexed <strong>${data.pages_crawled}</strong> page(s)
            (${data.pages_skipped} skipped/disallowed). Total index now contains <strong>${data.total_documents}</strong> documents.
          </div>
        `;
        if (data.crawled_pages && data.crawled_pages.length > 0) {
          summaryHtml += `<ul class="crawled-summary-list">`;
          data.crawled_pages.forEach((p) => {
            const safePUrl = sanitizeUrl(p.url);
            summaryHtml += `<li><strong>${escapeHtml(p.title)}</strong> &mdash; <a href="${escapeHtml(safePUrl || '#')}" target="_blank" rel="noopener noreferrer" style="color:inherit; text-decoration:underline;">${escapeHtml(p.url)}</a></li>`;
          });
          summaryHtml += `</ul>`;
        }
        if (data.errors && data.errors.length > 0) {
          summaryHtml += `<div style="margin-top:8px; font-size:12px; opacity:0.85;">Warnings: ${data.errors.map(escapeHtml).join("; ")}</div>`;
        }
        crawlerStatus.innerHTML = summaryHtml;

        if (docCountBadge && data.total_documents !== undefined) {
          docCountBadge.textContent = data.total_documents;
        }
        if (indexPanelBody) delete indexPanelBody.dataset.loaded;

        const currentQ = input.value.trim();
        if (currentQ) runSearch(currentQ);
      } else {
        crawlerStatus.className = "crawler-status status-error";
        crawlerStatus.textContent = `Crawl failed: ${data.error || "Unknown error"}`;
      }
    } catch (err) {
      crawlerStatus.className = "crawler-status status-error";
      crawlerStatus.textContent = `Crawl error: ${err.message}`;
      console.error("Crawl error:", err);
    } finally {
      crawlSubmitBtn.disabled = false;
      crawlSubmitBtn.innerHTML = `
        <span class="btn-text">Crawl &amp; Index</span>
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
          <polyline points="13 17 18 12 13 7"></polyline>
          <polyline points="6 17 11 12 6 7"></polyline>
        </svg>
      `;
    }
  });
}

// ------------------------------------------------------------------
// Toggle Index Stats Panel
// ------------------------------------------------------------------
toggleIndexBtn.addEventListener("click", async () => {
  const isHidden = indexPanel.classList.contains("hidden");
  indexPanel.classList.toggle("hidden");
  toggleIndexBtn.classList.toggle("expanded", isHidden);

  const toggleText = toggleIndexBtn.querySelector(".toggle-text");
  if (toggleText) {
    toggleText.textContent = isHidden
      ? "Hide index architecture"
      : "How the index works";
  } else {
    toggleIndexBtn.textContent = isHidden
      ? "How the index works ↑"
      : "How the index works ↓";
  }

  if (isHidden && indexPanelBody.dataset.loaded !== "true") {
    try {
      const res = await fetch("/api/stats");
      if (!res.ok) {
        throw new Error(`Server returned status ${res.status}`);
      }
      const stats = await res.json();
      const localCount = stats.num_local_documents || stats.num_documents;
      const webCount = stats.num_web_documents || 0;

      indexPanelBody.innerHTML = `
        <div class="stats-header">
          <div class="stat-card">
            <span class="stat-number">${stats.num_documents}</span>
            <span class="stat-caption">Total Documents</span>
          </div>
          <div class="stat-card">
            <span class="stat-number">${localCount}</span>
            <span class="stat-caption">Local Files</span>
          </div>
          <div class="stat-card">
            <span class="stat-number">${webCount}</span>
            <span class="stat-caption">Crawled Web Pages</span>
          </div>
          <div class="stat-card">
            <span class="stat-number">${stats.num_unique_terms}</span>
            <span class="stat-caption">Unique Terms</span>
          </div>
        </div>
        <div class="stats-section">
          <div class="stats-section-title">Corpus Documents (${stats.num_documents})</div>
          <div class="doc-list">
            ${stats.documents.map((d) => `
              <span class="doc-badge">
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
                  <polyline points="14 2 14 8 20 8"></polyline>
                </svg>
                ${escapeHtml(d)}
              </span>
            `).join("")}
          </div>
        </div>
        <div class="stats-algorithm">
          <div class="stats-section-title">TF-IDF &amp; Crawler Architecture</div>
          <p><strong>1. Web Crawler:</strong> Breadth-first crawl respecting <code>robots.txt</code> and SSRF defenses, extracting sanitized text.</p>
          <p><strong>2. Inverted Index:</strong> Maps each unique word to a posting list of <code>{document_id: term_frequency}</code> across local notes and web pages.</p>
          <p><strong>3. Dampened TF-IDF:</strong> Weights balance occurrence with rarity: <code>weight = (1 + ln(tf)) &times; (ln((1+N)/(1+df)) + 1)</code>.</p>
          <p><strong>4. Cosine Similarity Ranking:</strong> Measures the normalized angle between the query vector and candidate document vectors: <code>sim(q, d) = (q &middot; d) / (||q|| &times; ||d||)</code>.</p>
        </div>
      `;
      indexPanelBody.dataset.loaded = "true";
    } catch (err) {
      indexPanelBody.textContent = `Failed to load index stats: ${err.message}`;
      console.error(err);
    }
  }
});
