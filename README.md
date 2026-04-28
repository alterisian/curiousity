# Curiosity Memory System

A minimal, local-first knowledge engine that ingests information, extracts structured knowledge using an LLM, stores it efficiently, and actively generates questions about what it does not know.

> The system does not just store knowledge — it actively manages uncertainty.

---

## Overview

| Property | Value |
|---|---|
| Storage | SQLite, ~100MB budget |
| Language | Python 3.10+ |
| LLM | Mistral API or Gemini API (free tier) |
| Build time | ~4–6 hours |

---

## Running the test harness

No external dependencies. Uses Python stdlib only.

```bash
python test_harness.py
```

**Python 3.10+ required** (uses `list[str]` type hints).

### Live LLM tests

The live suite is skipped by default. To run it against the Mistral API:

```bash
CURIOSITY_LIVE_API=1 MISTRAL_API_KEY=your-key python3 test_harness.py
```

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

66 tests across 8 suites.

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

## Design guarantees (proven by 66 tests)

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
