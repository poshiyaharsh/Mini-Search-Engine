# Graph Report - mini-search-engine  (2026-09-11)

## Corpus Check
- cluster-only mode — file stats not available

## Summary
- 33 nodes · 44 edges · 5 communities (4 shown, 1 thin omitted)
- Extraction: 100% EXTRACTED · 0% INFERRED · 0% AMBIGUOUS
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- Community 0
- Community 1
- Community 2
- Community 3
- Community 4

## God Nodes (most connected - your core abstractions)
1. `SearchEngine` - 10 edges
2. `tokenize()` - 4 edges
3. `api_term()` - 3 edges
4. `escapeHtml()` - 3 edges
5. `highlightSnippet()` - 3 edges
6. `runSearch()` - 3 edges
7. `api_search()` - 2 edges
8. `api_stats()` - 2 edges
9. `home()` - 2 edges
10. `emptyState` - 1 edges

## Surprising Connections (you probably didn't know these)
- None detected - all connections are within the same source files.

## Import Cycles
- None detected.

## Communities (5 total, 1 thin omitted)

### Community 1 - "Community 1"
Cohesion: 0.22
Nodes (8): emptyState, form, indexPanel, indexPanelBody, input, metaLine, resultsEl, toggleIndexBtn

### Community 2 - "Community 2"
Cohesion: 0.36
Nodes (7): api_search(), api_stats(), api_term(), home(), Mini Search Engine - Flask Backend ==================================== Serves…, Debug endpoint: inspect the inverted index / IDF for a single word., route

### Community 3 - "Community 3"
Cohesion: 0.50
Nodes (3): Mini Search Engine - Core Logic ================================= Implements:…, Lowercase, strip punctuation, split into words, drop stopwords/short tokens., tokenize()

### Community 4 - "Community 4"
Cohesion: 1.00
Nodes (3): escapeHtml(), highlightSnippet(), runSearch()

## Knowledge Gaps
- **8 isolated node(s):** `emptyState`, `form`, `indexPanel`, `indexPanelBody`, `input` (+3 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 14 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **1 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `SearchEngine` connect `Community 0` to `Community 2`, `Community 3`?**
  _High betweenness centrality (0.216) - this node is a cross-community bridge._
- **Why does `tokenize()` connect `Community 3` to `Community 0`?**
  _High betweenness centrality (0.043) - this node is a cross-community bridge._
- **What connects `emptyState`, `form`, `indexPanel` to the rest of the system?**
  _8 weakly-connected nodes found - possible documentation gaps or missing edges._