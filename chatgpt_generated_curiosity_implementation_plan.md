Curiosity Memory System (Half-Day Build Plan)

1. Overview

This is a minimal, local-first “Curiosity Engine” that ingests information, extracts structured knowledge using an LLM, stores it efficiently, and actively generates questions about what it does not know.

It is designed to fit within ~100MB local storage and be implementable in ~4–6 hours.

Core idea:

> The system does not just store knowledge — it actively manages uncertainty.




---

2. Goals

Extract structured knowledge (entities + facts)

Store only compressed, high-value memory

Track uncertainty explicitly

Generate curiosity-driven questions

Continuously consolidate and clean memory



---

3. Tech Stack

Core

Python 3.10+

SQLite (primary storage)


Optional but recommended

sentence-transformers (all-MiniLM-L6-v2) for embeddings

FAISS (vector search)

requests (Google Search API / SerpAPI)


LLM API

Mistral API or Gemini API (free tier assumed)



---

4. Data Model

4.1 Entities Table

CREATE TABLE entities (
    id TEXT PRIMARY KEY,
    name TEXT,
    type TEXT,
    embedding BLOB,
    confidence REAL
);


---

4.2 Facts Table (Triples)

CREATE TABLE facts (
    id TEXT PRIMARY KEY,
    subject_id TEXT,
    predicate TEXT,
    object_id TEXT,
    confidence REAL,
    source TEXT,
    timestamp TEXT
);


---

4.3 Memory Notes (Compressed Text)

CREATE TABLE memory_notes (
    id TEXT PRIMARY KEY,
    text TEXT,
    linked_entities TEXT,
    confidence REAL,
    decay REAL,
    timestamp TEXT
);


---

4.4 Curiosity Queue

CREATE TABLE curiosity_queue (
    id TEXT PRIMARY KEY,
    question TEXT,
    uncertainty REAL,
    priority REAL,
    status TEXT
);


---

5. System Pipeline

Step 1 — Ingestion

Input sources:

User text

Google search results

API responses



---

Step 2 — LLM Extraction

LLM extracts:

entities

facts (triples)

uncertainties / missing knowledge


Output is structured JSON.


---

Step 3 — Temporary Staging

Store raw extracted facts temporarily

No long-term writes yet



---

Step 4 — Consolidation (LLM pass)

LLM merges:

duplicate entities

overlapping facts

redundant statements


Outputs:

canonical facts

normalized entities



---

Step 5 — Long-Term Storage

Store:

entities

facts (triples)

compressed memory notes

embeddings (optional)



---

Step 6 — Curiosity Generation

LLM identifies:

unknowns

contradictions

missing links


Stored in curiosity_queue.


---

Step 7 — Decay & Cleanup

Reduce confidence of unused facts

Delete low-value or redundant memory notes

Keep only structured knowledge graph



---

6. Memory Lifecycle

Short-term

raw inputs

unverified observations

discarded quickly


Consolidation layer

merge + normalize + compress via LLM


Long-term memory

structured graph (facts + entities)

confidence-scored beliefs



---

7. Key Design Rules

1. No raw storage in long-term memory

Everything must be compressed first.

2. Every fact has confidence

Nothing is absolute except explicitly defined constants.

3. Curiosity drives learning

The system actively generates questions.

4. Aggressive deduplication

Multiple observations collapse into one belief.


---

8. Example End-to-End Flow

Input

"Málaga has a growing tech startup ecosystem."


---

Extraction (LLM)

Entities:

Málaga (city)

tech ecosystem (concept)


Fact:

Málaga → has → tech ecosystem confidence: 0.72



---

Consolidation

Merged into:

Málaga → has → emerging tech ecosystem confidence: 0.81



---

Storage

Entities:

Málaga

Málaga Tech Ecosystem


Fact:

(Málaga → has → Málaga Tech Ecosystem)


Memory Note: "Málaga is developing an emerging tech ecosystem."


---

Curiosity Output

What startups exist in Málaga?

How large is ecosystem vs Valencia?

What funding exists?



---

Cleanup

raw text discarded

duplicate observations removed

only canonical fact retained



---

9. Storage Budget (~100MB)

Approximate allocation:

40MB graph (facts + entities)

30MB memory notes

20MB embeddings

10MB overhead/indexes



---

10. Outcome

A minimal system that:

builds structured knowledge

tracks uncertainty

generates curiosity-driven exploration

continuously compresses and cleans memory



---

11. Implementation Time Estimate

SQLite schema: 30–60 min

LLM extraction pipeline: 1–2 hours

consolidation logic: 1 hour

curiosity queue + loop: 1 hour

embeddings (optional): 1 hour


Total: ~4–6 hours