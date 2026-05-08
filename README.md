# Curiosity Memory System

Author: Ian Moss

A minimal, local-first knowledge engine that ingests information, extracts structured knowledge using an LLM, stores it efficiently, and actively generates questions about what it does not know.

> The system does not just store knowledge — it actively manages uncertainty.

Summary
- Compact, demo-ready prototype that visualises an agent's epistemic state using the Rumsfeld matrix (Known Knowns / Known Unknowns / Unknown Knowns / Unknown Unknowns).
- Demonstrates a testable interaction model for curiosity-driven discovery: entities, questions, memory notes and observable transitions between epistemic states.
- Public-facing artifact intended to support technical discussions, interviews and early-stage evaluation.

Why this matters
- Translates a broad "superlearner" claim into measurable components: curiosity queue (intrinsic drive), memory consolidation (notes), recognition (entities + confidence) and actionable metrics.
- Enables constrained-domain experiments and repeatable demos that surface product judgement, safety thinking and engineering delivery.

Repository contents (high level)
- web/index.html — single-page interactive dashboard that:
  - Maps entities, curiosity queue and memory notes into the Rumsfeld quadrants.
  - Streams a recent activity log and provides click-to-action interactions.
  - Polls two minimal endpoints: GET /activity and POST /action.
- Optionally add a small mock server and a short notebook for toy experiments (recommended for live demos).

Quick demo (local)
- Static-only (UI visible; dynamic endpoints absent):
  - From repo root: python3 -m http.server 8000 --directory web
  - Open: http://localhost:8000/index.html
  - Note: the UI will attempt to fetch /activity and POST /action; without a mock server those calls will 404.
- For full interactivity:
  - Run a tiny mock server (Flask/Express/Node) that implements GET /activity and POST /action with deterministic data for reliable demos and recordings.

API surface (for wiring a mock)
- GET /activity
  - Response shape: { activity: [...], db: { entities: [...], curiosity_queue: [...], memory_notes: [...] } }
- POST /action
  - Body: { id, kind } — used to cycle or advance a node's state in the demo

For technical reviewers and hiring teams (single section)
- Product narrative: begin with a single constrained domain (example: simulated object manipulation + language labels) where Rumsfeld flows are measurable and actionable.
- Evaluation metrics: sample-efficiency, time-to-transfer, novelty discovery rate, safe-error-rate, human-intervention frequency.
- Technical approach: focus on sample-efficient methods (world models / model-based RL), intrinsic curiosity modules, curriculum generation, memory consolidation and representation learning aimed at symbolic abstraction and transfer.
- Safety & governance: prefer staged experiments, sandboxed environments, internal red-team reviews, immutable logging/audit trails and controlled knowledge gating.
- Deliverables demonstrated here: frontend instrumentation, minimal backend endpoints for repeatable demos, a synthetic simulator adapter, and an evaluation harness with reproducible metrics.

---

## Seeing it live

Start the web server, seed the DB with a sample pipeline run, then open the UI:

```bash
# 1. Start the server (runs on port 8000)
PYTHONPATH=. python3 web/serve_web.py

# 2. In a second terminal, run the pipeline to populate the DB
source .envrc && PYTHONPATH=. python3 web/run_malaga.py

# 3. Open in your browser
open http://localhost:8000/index.html   # macOS
xdg-open http://localhost:8000/index.html  # Linux
```

You should see the **Rumsfeld Matrix** — four dark quadrants with coloured pill nodes:

| Colour | Quadrant | What it shows |
|---|---|---|
| Green | Known Knowns | Entities extracted from text (e.g. "Málaga", "tech startup ecosystem") |
| Yellow | Known Unknowns | Curiosity questions the LLM generated about gaps |
| Blue | Unknown Knowns | Memory notes linked to known entities |
| Purple | Unknown Unknowns | Memory notes with no entity links |

The page auto-refreshes every 1.4 seconds. Run `run_malaga.py` again (with different input text) to watch new nodes appear.

---

## Overview

| Property | Value |
|---|---|
| Storage | SQLite, ~100MB budget |
| Language | Python 3.10+ |
| LLM | Mistral API or Gemini API (free tier) |
| Build time | ~4–6 hours |

---

## Running the tests

All tests live under `tests/`. Python 3.10+ required.

```bash
# 74 mock + live tests (requires MISTRAL_API_KEY for the live suite)
source .envrc && CURIOSITY_LIVE_API=1 pytest tests/test_harness.py

# 1 Playwright UI test (requires the web server to be running on port 8000)
.venv/bin/pytest tests/test_grid_visible.py

# TFDD-formatted output with line numbers, re-run commands, and auto-saved logs
source .envrc && CURIOSITY_LIVE_API=1 python3 tests/test_harness.py
```

The live suite is skipped when `CURIOSITY_LIVE_API` is not set. Mock tests have no external dependencies.

---

## Optional dependencies

For embeddings and vector search (from the spec):

```
# requirements.txt
sentence-transformers>=2.2
faiss-cpu>=1.7
requests>=2.31
```

Install with:

```bash
pip install -r requirements.txt
```

Isolated environment (recommended):

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python test_harness.py
```

---

## Data model

```sql
entities        -- id, name, type, embedding, confidence
facts           -- id, subject_id, predicate, object_id, confidence, source, timestamp
memory_notes    -- id, text, linked_entities, confidence, decay, timestamp
curiosity_queue -- id, question, uncertainty, priority, status
```

All confidence values are in `[0.0, 1.0]`. Foreign keys are enforced. `curiosity_queue.status` is constrained to `pending | active | resolved | dropped`.

---

## What it does

The system ingests raw text, extracts structured knowledge from it, stores that knowledge efficiently, and actively generates questions about what it doesn't know. Everything runs locally in SQLite with no external dependencies beyond an LLM API.

### Pipeline

```
Input → Extract → Stage → Consolidate → Store → Curiosity → Decay
```

**1. Ingestion**
Accepts raw text input — user messages, search results, API responses.

**2. Extraction**
Sends the text to an LLM with a structured prompt. The LLM returns:
- **Entities** — named things (cities, concepts, people) with a confidence score
- **Facts** — triples of (subject → predicate → object) with confidence
- **Uncertainties** — gaps in knowledge the LLM noticed

All output is validated: correct keys present, confidence values in `[0.0, 1.0]`.

**3. Staging**
Extracted data is held in a temporary in-memory buffer. Nothing is written to the database yet. Multiple extractions can accumulate before committing.

**4. Consolidation**
The staged batch is sent to the LLM again. It merges duplicate entities, collapses overlapping facts, and raises confidence when multiple sources agree. The result is a canonical, deduplicated knowledge graph.

**5. Long-term Storage**
The canonical entities and facts are written to SQLite. Memory notes (compressed summaries) are also stored, each linked to the entities they reference.

**6. Curiosity Generation**
The current knowledge graph is sent to the LLM, which identifies gaps, contradictions, and missing links. Each becomes a question stored in the `curiosity_queue` with an uncertainty score and priority, starting in `pending` status. Questions can progress through `pending → active → resolved → dropped`.

**7. Decay & Cleanup**
Each cycle, memory notes have their confidence multiplied by a decay factor (default 0.95). Notes that fall below a prune threshold (default 0.1) are deleted. Entities and facts are never decayed — only memory notes are perishable. This keeps the database lean and under the 100MB budget even after many cycles.

---

## Test coverage

75 tests across 9 suites.

| Suite | Tests | What it covers |
|---|---|---|
| Database Schema | 11 | Table creation, column sets, PK/FK/CHECK constraints, idempotent init |
| Data Insertion & Retrieval | 8 | Insert/read all four tables, JSON linked entities, status transitions |
| Extraction Pipeline | 12 | Response structure, confidence range, triples shape, prompt content, error handling |
| Temporary Staging | 5 | No premature writes, data preserved, uncertainties present |
| Consolidation | 7 | Deduplication, confidence non-regression, prompt content, error handling |
| Curiosity Queue | 8 | Question structure, DB storage, priority ordering, status lifecycle |
| Memory Decay | 7 | Confidence reduction, pruning, non-negative floor, entities/facts unaffected |
| End-to-End | 8 | Full Málaga pipeline, referential integrity, 100MB storage budget |
| Live LLM Smoke | 8 | Real Mistral API calls — extraction, consolidation, curiosity, full pipeline |
| UI (Playwright) | 1 | Rumsfeld Matrix grid renders nodes with correct positions |

---

## Storage budget

| Allocation | Size |
|---|---|
| Knowledge graph (facts + entities) | 40MB |
| Memory notes | 30MB |
| Embeddings | 20MB |
| Indexes + overhead | 10MB |
| **Total** | **100MB** |

---

## Design guarantees (proven by 75 tests)

- Every fact references entities that exist — no orphaned triples
- Every confidence value is in `[0.0, 1.0]` — enforced by both DB constraints and validation
- Staging never writes to the database prematurely
- Consolidation never reduces confidence below its source value
- Decay only touches memory notes — the knowledge graph is permanent
- The full pipeline fits within 100MB over 50 ingestion cycles with decay active

---

## Design rules

1. **No raw storage in long-term memory** — everything is compressed first.
2. **Every fact has confidence** — nothing is absolute except explicitly defined constants.
3. **Curiosity drives learning** — the system actively generates questions.
4. **Aggressive deduplication** — multiple observations collapse into one belief.

## License
- This repository is provided as demonstration material, as is. Let the user beware. 
