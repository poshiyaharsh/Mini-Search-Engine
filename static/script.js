/**
 * Mini Search Engine - Frontend Logic
 * Connects to Flask /api/search and /api/stats
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
const suggestionChips = document.querySelectorAll(".query-chip");

// Cache initial empty state HTML for restoration
const initialEmptyStateHtml = emptyState ? emptyState.innerHTML : "";

function escapeHtml(str) {
  return str
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

function highlightSnippet(snippet, queryWords) {
  const escaped = escapeHtml(snippet);
  if (!queryWords.length) return escaped;
  const pattern = new RegExp(
    "\\b(" + queryWords.map((w) => w.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("|") + ")\\b",
    "gi"
  );
  return escaped.replace(pattern, (m) => `<mark>${m}</mark>`);
}

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

async function runSearch(query) {
  const trimmed = query.trim();
  if (!trimmed) {
    resetToDefaultState();
    return;
  }

  // Loading state
  metaLine.textContent = "computing TF-IDF cosine similarities…";
  resultsEl.innerHTML = "";

  try {
    const res = await fetch(`/api/search?q=${encodeURIComponent(trimmed)}`);
    const data = await res.json();

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
            Try broader terms, single concepts, or click one of the suggested topics above.
          </p>
        `;
      }
      return;
    }

    // Hide empty state when results exist
    if (emptyState) {
      emptyState.classList.add("hidden");
      emptyState.style.display = "none";
    }

    metaLine.textContent = `${data.count} result${data.count === 1 ? "" : "s"} for "${data.query}" — ranked by vector cosine similarity`;

    const queryWords = data.query.toLowerCase().split(/\s+/).filter(Boolean);
    const maxScore = data.results[0].score || 1;

    data.results.forEach((r, i) => {
      const li = document.createElement("li");
      li.className = "result";
      li.style.animationDelay = `${i * 60}ms`;
      const pct = Math.max(6, Math.round((r.score / maxScore) * 100));

      li.innerHTML = `
        <div class="result-head">
          <div class="result-title-group">
            <span class="result-rank">#${i + 1}</span>
            <span class="result-title">${escapeHtml(r.filename)}</span>
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
    metaLine.textContent = "error fetching search results";
    console.error("Search fetch error:", err);
  }
}

// Form submit event
form.addEventListener("submit", (e) => {
  e.preventDefault();
  const q = input.value.trim();
  if (q) runSearch(q);
});

// Clear button logic
if (clearBtn) {
  clearBtn.addEventListener("click", () => {
    input.value = "";
    input.focus();
    resetToDefaultState();
  });
}

// Input change listener for clear button toggle
input.addEventListener("input", () => {
  if (clearBtn) {
    clearBtn.style.display = input.value.length > 0 ? "flex" : "none";
  }
  if (!input.value.trim()) {
    resetToDefaultState();
  }
});

// Suggestion chip quick search
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

// Toggle Index Stats Panel
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
      const stats = await res.json();
      indexPanelBody.innerHTML = `
        <div class="stats-header">
          <div class="stat-card">
            <span class="stat-number">${stats.num_documents}</span>
            <span class="stat-caption">Indexed Documents</span>
          </div>
          <div class="stat-card">
            <span class="stat-number">${stats.num_unique_terms}</span>
            <span class="stat-caption">Vocabulary Terms</span>
          </div>
        </div>
        <div class="stats-section">
          <div class="stats-section-title">Indexed Corpus Files</div>
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
          <div class="stats-section-title">TF-IDF Vector Space Architecture</div>
          <p><strong>1. Tokenization & Filtering:</strong> Lowercases text, cleans punctuation, strips standard English stopwords.</p>
          <p><strong>2. Inverted Index:</strong> Maps each unique word to its posting list of <code>{doc_id: term_frequency}</code>.</p>
          <p><strong>3. TF&#8209;IDF Dampened Weighting:</strong> Computes <code>tf = 1 + ln(count)</code> and <code>idf = ln((1+N)/(1+df)) + 1</code>.</p>
          <p><strong>4. Cosine Similarity Ranking:</strong> Computes the dot product between the normalized query vector and document vectors: <code>sim(q, d) = (q &middot; d) / (||q|| &times; ||d||)</code>.</p>
        </div>
      `;
      indexPanelBody.dataset.loaded = "true";
    } catch (err) {
      indexPanelBody.textContent = "Failed to load index stats.";
      console.error(err);
    }
  }
});
