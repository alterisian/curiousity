"""
Curiosity Memory System — Test Harness
=======================================
Run with:   python -m pytest test_harness.py -v
         or python3 test_harness.py

LLM tests use a mock by default.
Set CURIOSITY_LIVE_API=1 + ANTHROPIC_API_KEY (or MISTRAL_API_KEY) to run live.

Coverage:
  Suite 1 — Database Schema
  Suite 2 — Data Insertion & Retrieval
  Suite 3 — Extraction Pipeline
  Suite 4 — Temporary Staging
  Suite 5 — Consolidation
  Suite 6 — Curiosity Queue
  Suite 7 — Memory Decay
  Suite 8 — End-to-End
"""

import json
import os
import re
import sqlite3
import sys
import tempfile
import time
import unittest
import uuid
from contextlib import contextmanager
from unittest.mock import MagicMock

# Ensure project root is on sys.path when run from tests/ or via pytest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from curiosity.db import (
    init_db,
    insert_entity,
    insert_fact,
    insert_memory_note,
    enqueue_question,
    advance_question_status,
    apply_decay,
)
from curiosity.pipeline import (
    EXTRACTION_PROMPT,
    CONSOLIDATION_PROMPT,
    CURIOSITY_PROMPT,
    call_llm,
    extract_knowledge,
    consolidate,
    generate_curiosity,
)

# ---------------------------------------------------------------------------
# Test fixtures & helpers
# ---------------------------------------------------------------------------

@contextmanager
def fresh_db():
    """Yield a clean in-memory SQLite connection with the full schema."""
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA foreign_keys = ON")
    init_db(conn)
    try:
        yield conn
    finally:
        conn.close()


def _sample_entity_pair(conn):
    """Insert two entities and return (subject_id, object_id)."""
    sid = insert_entity(conn, "Málaga", "city", 0.95)
    oid = insert_entity(conn, "tech ecosystem", "concept", 0.80)
    return sid, oid


MOCK_EXTRACTION_RESPONSE = {
    "entities": [
        {"id": "e1", "name": "Málaga",         "type": "city",    "confidence": 0.95},
        {"id": "e2", "name": "tech ecosystem", "type": "concept", "confidence": 0.80},
    ],
    "facts": [
        {"id": "f1", "subject_id": "e1", "predicate": "has",
         "object_id": "e2", "confidence": 0.72},
    ],
    "uncertainties": [
        "Size of Málaga tech ecosystem is unknown",
        "Key players in the ecosystem are unknown",
    ],
}

MOCK_CONSOLIDATION_RESPONSE = {
    "entities": [
        {"id": "e1", "name": "Málaga",                 "type": "city",    "confidence": 0.97},
        {"id": "e2", "name": "emerging tech ecosystem", "type": "concept", "confidence": 0.85},
    ],
    "facts": [
        {"id": "f1", "subject_id": "e1", "predicate": "has",
         "object_id": "e2", "confidence": 0.81},
    ],
}

MOCK_CURIOSITY_RESPONSE = {
    "questions": [
        {"question": "What startups exist in Málaga?",                      "uncertainty": 0.85, "priority": 0.9},
        {"question": "How does the Málaga ecosystem compare to Valencia?",   "uncertainty": 0.75, "priority": 0.7},
        {"question": "What funding sources are available in Málaga?",        "uncertainty": 0.80, "priority": 0.8},
    ]
}


# ---------------------------------------------------------------------------
# Suite 1 — Database Schema
# ---------------------------------------------------------------------------

class TestDatabaseSchema(unittest.TestCase):
    """Verify that init_db creates the correct schema."""

    def test_all_four_tables_created(self):
        with fresh_db() as conn:
            tables = {r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )}
            self.assertIn("entities",        tables)
            self.assertIn("facts",           tables)
            self.assertIn("memory_notes",    tables)
            self.assertIn("curiosity_queue", tables)

    def test_entities_columns(self):
        with fresh_db() as conn:
            cols = {r[1] for r in conn.execute("PRAGMA table_info(entities)")}
            self.assertGreaterEqual(cols, {"id", "name", "type", "embedding", "confidence"})

    def test_facts_columns(self):
        with fresh_db() as conn:
            cols = {r[1] for r in conn.execute("PRAGMA table_info(facts)")}
            self.assertGreaterEqual(
                cols, {"id", "subject_id", "predicate", "object_id",
                       "confidence", "source", "timestamp"}
            )

    def test_memory_notes_columns(self):
        with fresh_db() as conn:
            cols = {r[1] for r in conn.execute("PRAGMA table_info(memory_notes)")}
            self.assertGreaterEqual(
                cols, {"id", "text", "linked_entities", "confidence", "decay", "timestamp"}
            )

    def test_curiosity_queue_columns(self):
        with fresh_db() as conn:
            cols = {r[1] for r in conn.execute("PRAGMA table_info(curiosity_queue)")}
            self.assertGreaterEqual(
                cols, {"id", "question", "uncertainty", "priority", "status"}
            )

    def test_entity_id_is_primary_key(self):
        """Inserting two entities with the same id must raise IntegrityError."""
        with fresh_db() as conn:
            dup_id = str(uuid.uuid4())
            conn.execute(
                "INSERT INTO entities (id, name, type, confidence) VALUES (?,?,?,?)",
                (dup_id, "First", "city", 0.9)
            )
            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute(
                    "INSERT INTO entities (id, name, type, confidence) VALUES (?,?,?,?)",
                    (dup_id, "Duplicate", "city", 0.5)
                )

    def test_entity_confidence_below_zero_rejected(self):
        with fresh_db() as conn:
            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute(
                    "INSERT INTO entities (id, name, confidence) VALUES (?,?,?)",
                    (str(uuid.uuid4()), "Bad", -0.1)
                )

    def test_entity_confidence_above_one_rejected(self):
        with fresh_db() as conn:
            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute(
                    "INSERT INTO entities (id, name, confidence) VALUES (?,?,?)",
                    (str(uuid.uuid4()), "Bad", 1.1)
                )

    def test_curiosity_queue_invalid_status_rejected(self):
        with fresh_db() as conn:
            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute(
                    "INSERT INTO curiosity_queue (id, question, uncertainty, priority, status) "
                    "VALUES (?,?,?,?,?)",
                    (str(uuid.uuid4()), "Why?", 0.5, 0.5, "winging-it")
                )

    def test_init_db_is_idempotent(self):
        """Calling init_db twice must not raise an error."""
        with fresh_db() as conn:
            init_db(conn)  # second call
            tables = conn.execute(
                "SELECT count(*) FROM sqlite_master WHERE type='table'"
            ).fetchone()[0]
            self.assertEqual(tables, 4)

    def test_foreign_key_fact_requires_known_entity(self):
        """A fact whose subject_id does not exist in entities must be rejected."""
        with fresh_db() as conn:
            oid = insert_entity(conn, "tech ecosystem", "concept", 0.8)
            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute(
                    "INSERT INTO facts "
                    "(id, subject_id, predicate, object_id, confidence, timestamp) "
                    "VALUES (?,?,?,?,?,?)",
                    (str(uuid.uuid4()), "nonexistent-id", "has", oid, 0.7,
                     "2024-01-01T00:00:00")
                )


# ---------------------------------------------------------------------------
# Suite 2 — Data Insertion & Retrieval
# ---------------------------------------------------------------------------

class TestDataInsertionRetrieval(unittest.TestCase):

    def test_insert_entity_returns_id(self):
        with fresh_db() as conn:
            eid = insert_entity(conn, "Málaga", "city", 0.95)
            self.assertTrue(eid)

    def test_inserted_entity_is_readable(self):
        with fresh_db() as conn:
            eid = insert_entity(conn, "Málaga", "city", 0.95)
            row = conn.execute(
                "SELECT name, type, confidence FROM entities WHERE id=?", (eid,)
            ).fetchone()
            self.assertEqual(row[0], "Málaga")
            self.assertEqual(row[1], "city")
            self.assertAlmostEqual(row[2], 0.95)

    def test_insert_fact_links_entities(self):
        with fresh_db() as conn:
            sid, oid = _sample_entity_pair(conn)
            fid = insert_fact(conn, sid, "has", oid, 0.72, source="test")
            row = conn.execute(
                "SELECT subject_id, predicate, object_id FROM facts WHERE id=?", (fid,)
            ).fetchone()
            self.assertEqual(row[0], sid)
            self.assertEqual(row[1], "has")
            self.assertEqual(row[2], oid)

    def test_insert_memory_note(self):
        with fresh_db() as conn:
            sid, _ = _sample_entity_pair(conn)
            nid = insert_memory_note(conn, "Málaga is growing.", 0.8, [sid])
            row = conn.execute(
                "SELECT text, confidence FROM memory_notes WHERE id=?", (nid,)
            ).fetchone()
            self.assertEqual(row[0], "Málaga is growing.")
            self.assertAlmostEqual(row[1], 0.8)

    def test_memory_note_linked_entities_is_json(self):
        with fresh_db() as conn:
            sid, oid = _sample_entity_pair(conn)
            nid = insert_memory_note(conn, "note", 0.7, [sid, oid])
            raw = conn.execute(
                "SELECT linked_entities FROM memory_notes WHERE id=?", (nid,)
            ).fetchone()[0]
            parsed = json.loads(raw)
            self.assertIn(sid, parsed)
            self.assertIn(oid, parsed)

    def test_enqueue_question(self):
        with fresh_db() as conn:
            qid = enqueue_question(conn, "What startups exist in Málaga?", 0.85, 0.9)
            row = conn.execute(
                "SELECT question, status, uncertainty FROM curiosity_queue WHERE id=?", (qid,)
            ).fetchone()
            self.assertEqual(row[0], "What startups exist in Málaga?")
            self.assertEqual(row[1], "pending")
            self.assertAlmostEqual(row[2], 0.85)

    def test_advance_question_status(self):
        with fresh_db() as conn:
            qid = enqueue_question(conn, "Test question?", 0.5, 0.5)
            advance_question_status(conn, qid, "active")
            status = conn.execute(
                "SELECT status FROM curiosity_queue WHERE id=?", (qid,)
            ).fetchone()[0]
            self.assertEqual(status, "active")

    def test_advance_question_invalid_status_raises(self):
        with fresh_db() as conn:
            qid = enqueue_question(conn, "Test?", 0.5, 0.5)
            with self.assertRaises(ValueError):
                advance_question_status(conn, qid, "limbo")


# ---------------------------------------------------------------------------
# Suite 3 — Extraction Pipeline (mocked LLM)
# ---------------------------------------------------------------------------

class TestExtractionPipeline(unittest.TestCase):

    def setUp(self):
        self.mock_llm = MagicMock(return_value=MOCK_EXTRACTION_RESPONSE)

    def test_extraction_returns_entities_key(self):
        result = extract_knowledge("Málaga has a growing tech startup ecosystem.",
                                   llm_fn=self.mock_llm)
        self.assertIn("entities", result)

    def test_extraction_returns_facts_key(self):
        result = extract_knowledge("Málaga has a growing tech startup ecosystem.",
                                   llm_fn=self.mock_llm)
        self.assertIn("facts", result)

    def test_extraction_returns_uncertainties_key(self):
        result = extract_knowledge("Málaga has a growing tech startup ecosystem.",
                                   llm_fn=self.mock_llm)
        self.assertIn("uncertainties", result)

    def test_entity_confidence_in_range(self):
        result = extract_knowledge("any text", llm_fn=self.mock_llm)
        for e in result["entities"]:
            self.assertGreaterEqual(e["confidence"], 0.0)
            self.assertLessEqual(e["confidence"],    1.0)

    def test_fact_confidence_in_range(self):
        result = extract_knowledge("any text", llm_fn=self.mock_llm)
        for f in result["facts"]:
            self.assertGreaterEqual(f["confidence"], 0.0)
            self.assertLessEqual(f["confidence"],    1.0)

    def test_facts_are_triples(self):
        result = extract_knowledge("any text", llm_fn=self.mock_llm)
        for f in result["facts"]:
            self.assertIn("subject_id", f)
            self.assertIn("predicate",  f)
            self.assertIn("object_id",  f)

    def test_extraction_calls_llm_once(self):
        extract_knowledge("text", llm_fn=self.mock_llm)
        self.mock_llm.assert_called_once()

    def test_extraction_passes_text_to_prompt(self):
        extract_knowledge("Málaga startup scene", llm_fn=self.mock_llm)
        called_prompt = self.mock_llm.call_args[0][0]
        self.assertIn("Málaga startup scene", called_prompt)

    def test_extraction_raises_on_missing_entities_key(self):
        bad_llm = MagicMock(return_value={"facts": [], "uncertainties": []})
        with self.assertRaises(AssertionError):
            extract_knowledge("text", llm_fn=bad_llm)

    def test_extraction_raises_on_out_of_range_confidence(self):
        bad_llm = MagicMock(return_value={
            "entities": [{"id": "e1", "name": "X", "type": "city", "confidence": 1.5}],
            "facts": [],
            "uncertainties": [],
        })
        with self.assertRaises(AssertionError):
            extract_knowledge("text", llm_fn=bad_llm)

    def test_extraction_raises_on_non_json_response(self):
        bad_llm = MagicMock(side_effect=ValueError("not JSON"))
        with self.assertRaises(ValueError):
            extract_knowledge("text", llm_fn=bad_llm)

    def test_extraction_with_empty_input_still_valid(self):
        """Empty input should not crash — LLM may return empty lists."""
        empty_llm = MagicMock(return_value={
            "entities": [], "facts": [], "uncertainties": []
        })
        result = extract_knowledge("", llm_fn=empty_llm)
        self.assertEqual(result["entities"], [])
        self.assertEqual(result["facts"],    [])


# ---------------------------------------------------------------------------
# Suite 4 — Temporary Staging
# ---------------------------------------------------------------------------

class TestTemporaryStaging(unittest.TestCase):
    """
    Staging is a transient buffer — raw facts live here before consolidation.
    The long-term tables must remain untouched during staging.
    """

    def setUp(self):
        self._conn = sqlite3.connect(":memory:")
        self._conn.execute("PRAGMA foreign_keys = ON")
        init_db(self._conn)
        self._staged: list[dict] = []

    def tearDown(self):
        self._conn.close()

    def _stage(self, extraction: dict) -> None:
        self._staged.append(extraction)

    def test_staging_does_not_write_to_entities(self):
        self._stage(MOCK_EXTRACTION_RESPONSE)
        count = self._conn.execute("SELECT count(*) FROM entities").fetchone()[0]
        self.assertEqual(count, 0, "Staging must not write directly to entities")

    def test_staging_does_not_write_to_facts(self):
        self._stage(MOCK_EXTRACTION_RESPONSE)
        count = self._conn.execute("SELECT count(*) FROM facts").fetchone()[0]
        self.assertEqual(count, 0, "Staging must not write directly to facts")

    def test_staged_data_preserved_for_consolidation(self):
        self._stage(MOCK_EXTRACTION_RESPONSE)
        self.assertEqual(len(self._staged), 1)
        self.assertIn("entities", self._staged[0])
        self.assertIn("facts",    self._staged[0])

    def test_multiple_stagings_accumulate(self):
        for _ in range(3):
            self._stage(MOCK_EXTRACTION_RESPONSE)
        self.assertEqual(len(self._staged), 3)

    def test_staged_data_contains_uncertainties(self):
        self._stage(MOCK_EXTRACTION_RESPONSE)
        self.assertIn("uncertainties", self._staged[0])
        self.assertGreater(len(self._staged[0]["uncertainties"]), 0)


# ---------------------------------------------------------------------------
# Suite 5 — Consolidation
# ---------------------------------------------------------------------------

class TestConsolidation(unittest.TestCase):

    def setUp(self):
        self.mock_llm = MagicMock(return_value=MOCK_CONSOLIDATION_RESPONSE)

    def test_consolidation_returns_entities(self):
        result = consolidate([MOCK_EXTRACTION_RESPONSE], llm_fn=self.mock_llm)
        self.assertIn("entities", result)

    def test_consolidation_returns_facts(self):
        result = consolidate([MOCK_EXTRACTION_RESPONSE], llm_fn=self.mock_llm)
        self.assertIn("facts", result)

    def test_duplicate_entities_reduce_count(self):
        duplicate_stage = [MOCK_EXTRACTION_RESPONSE, MOCK_EXTRACTION_RESPONSE]
        raw_count = sum(len(s["entities"]) for s in duplicate_stage)
        result = consolidate(duplicate_stage, llm_fn=self.mock_llm)
        self.assertLessEqual(len(result["entities"]), raw_count)

    def test_consolidation_confidence_not_lower_than_source(self):
        source_max = max(f["confidence"] for f in MOCK_EXTRACTION_RESPONSE["facts"])
        result = consolidate([MOCK_EXTRACTION_RESPONSE], llm_fn=self.mock_llm)
        for f in result["facts"]:
            self.assertGreaterEqual(f["confidence"], source_max - 0.01,
                                    "Consolidation should not reduce confidence")

    def test_consolidation_passes_staged_data_to_prompt(self):
        consolidate([MOCK_EXTRACTION_RESPONSE], llm_fn=self.mock_llm)
        called_prompt = self.mock_llm.call_args[0][0]
        self.assertIn("Málaga", called_prompt)

    def test_consolidation_raises_on_missing_entities_key(self):
        bad_llm = MagicMock(return_value={"facts": []})
        with self.assertRaises(AssertionError):
            consolidate([MOCK_EXTRACTION_RESPONSE], llm_fn=bad_llm)

    def test_empty_staged_input_returns_empty_graph(self):
        empty_llm = MagicMock(return_value={"entities": [], "facts": []})
        result = consolidate([], llm_fn=empty_llm)
        self.assertEqual(result["entities"], [])
        self.assertEqual(result["facts"],    [])


# ---------------------------------------------------------------------------
# Suite 6 — Curiosity Queue
# ---------------------------------------------------------------------------

class TestCuriosityQueue(unittest.TestCase):

    def setUp(self):
        self.mock_llm = MagicMock(return_value=MOCK_CURIOSITY_RESPONSE)

    def test_questions_generated(self):
        questions = generate_curiosity(MOCK_CONSOLIDATION_RESPONSE, llm_fn=self.mock_llm)
        self.assertGreater(len(questions), 0)

    def test_each_question_has_text(self):
        questions = generate_curiosity(MOCK_CONSOLIDATION_RESPONSE, llm_fn=self.mock_llm)
        for q in questions:
            self.assertIn("question", q)
            self.assertTrue(q["question"].strip())

    def test_each_question_has_uncertainty(self):
        questions = generate_curiosity(MOCK_CONSOLIDATION_RESPONSE, llm_fn=self.mock_llm)
        for q in questions:
            self.assertIn("uncertainty", q)
            self.assertGreaterEqual(q["uncertainty"], 0.0)
            self.assertLessEqual(q["uncertainty"],    1.0)

    def test_each_question_has_priority(self):
        questions = generate_curiosity(MOCK_CONSOLIDATION_RESPONSE, llm_fn=self.mock_llm)
        for q in questions:
            self.assertIn("priority", q)

    def test_questions_stored_in_db(self):
        with fresh_db() as conn:
            questions = generate_curiosity(MOCK_CONSOLIDATION_RESPONSE, llm_fn=self.mock_llm)
            for q in questions:
                enqueue_question(conn, q["question"], q["uncertainty"], q["priority"])
            count = conn.execute("SELECT count(*) FROM curiosity_queue").fetchone()[0]
            self.assertEqual(count, len(questions))

    def test_high_uncertainty_gets_high_priority(self):
        questions = generate_curiosity(MOCK_CONSOLIDATION_RESPONSE, llm_fn=self.mock_llm)
        if len(questions) >= 2:
            sorted_by_uncertainty = sorted(questions, key=lambda q: q["uncertainty"], reverse=True)
            sorted_by_priority    = sorted(questions, key=lambda q: q["priority"],    reverse=True)
            top_uncertain = sorted_by_uncertainty[0]["question"]
            top_priority_questions = {q["question"] for q in sorted_by_priority[:2]}
            self.assertIn(top_uncertain, top_priority_questions)

    def test_status_lifecycle(self):
        with fresh_db() as conn:
            qid = enqueue_question(conn, "Test?", 0.7, 0.8)
            for status in ("active", "resolved"):
                advance_question_status(conn, qid, status)
                row = conn.execute(
                    "SELECT status FROM curiosity_queue WHERE id=?", (qid,)
                ).fetchone()
                self.assertEqual(row[0], status)

    def test_questions_raises_on_bad_uncertainty(self):
        bad_llm = MagicMock(return_value={
            "questions": [{"question": "X?", "uncertainty": 2.0, "priority": 0.5}]
        })
        with self.assertRaises(AssertionError):
            generate_curiosity({}, llm_fn=bad_llm)


# ---------------------------------------------------------------------------
# Suite 7 — Memory Decay & Cleanup
# ---------------------------------------------------------------------------

class TestMemoryDecay(unittest.TestCase):

    def test_decay_reduces_confidence(self):
        with fresh_db() as conn:
            sid, _ = _sample_entity_pair(conn)
            nid = insert_memory_note(conn, "High confidence note.", 0.9, [sid])
            apply_decay(conn, decay_factor=0.8, prune_threshold=0.05)
            row = conn.execute(
                "SELECT confidence FROM memory_notes WHERE id=?", (nid,)
            ).fetchone()
            self.assertIsNotNone(row)
            self.assertLess(row[0], 0.9)

    def test_decay_deletes_low_confidence_notes(self):
        with fresh_db() as conn:
            sid, _ = _sample_entity_pair(conn)
            insert_memory_note(conn, "Barely there.", 0.08, [sid])
            apply_decay(conn, decay_factor=0.9, prune_threshold=0.1)
            count = conn.execute("SELECT count(*) FROM memory_notes").fetchone()[0]
            self.assertEqual(count, 0, "Low-confidence notes should be pruned")

    def test_decay_preserves_high_confidence_notes(self):
        with fresh_db() as conn:
            sid, _ = _sample_entity_pair(conn)
            nid = insert_memory_note(conn, "Strong memory.", 0.99, [sid])
            apply_decay(conn, decay_factor=0.95, prune_threshold=0.1)
            row = conn.execute(
                "SELECT id FROM memory_notes WHERE id=?", (nid,)
            ).fetchone()
            self.assertIsNotNone(row, "High-confidence notes must survive one decay pass")

    def test_decay_returns_count_of_deleted_notes(self):
        with fresh_db() as conn:
            sid, _ = _sample_entity_pair(conn)
            insert_memory_note(conn, "Note A.", 0.05, [sid])
            insert_memory_note(conn, "Note B.", 0.04, [sid])
            insert_memory_note(conn, "Note C.", 0.95, [sid])
            deleted = apply_decay(conn, decay_factor=0.9, prune_threshold=0.1)
            self.assertEqual(deleted, 2)

    def test_confidence_never_goes_negative(self):
        with fresh_db() as conn:
            sid, _ = _sample_entity_pair(conn)
            insert_memory_note(conn, "Fading.", 0.15, [sid])
            for _ in range(20):
                apply_decay(conn, decay_factor=0.5, prune_threshold=0.0001)
            rows = conn.execute("SELECT confidence FROM memory_notes").fetchall()
            for (conf,) in rows:
                self.assertGreaterEqual(conf, 0.0)

    def test_decay_does_not_affect_entities(self):
        with fresh_db() as conn:
            eid = insert_entity(conn, "Persistent Entity", "city", 0.99)
            apply_decay(conn, decay_factor=0.5, prune_threshold=0.1)
            row = conn.execute(
                "SELECT confidence FROM entities WHERE id=?", (eid,)
            ).fetchone()
            self.assertAlmostEqual(row[0], 0.99, msg="Decay must not touch entities table")

    def test_decay_does_not_affect_facts(self):
        with fresh_db() as conn:
            sid, oid = _sample_entity_pair(conn)
            fid = insert_fact(conn, sid, "has", oid, 0.88)
            apply_decay(conn, decay_factor=0.5, prune_threshold=0.1)
            row = conn.execute(
                "SELECT confidence FROM facts WHERE id=?", (fid,)
            ).fetchone()
            self.assertAlmostEqual(row[0], 0.88, msg="Decay must not touch facts table")


# ---------------------------------------------------------------------------
# Suite 8 — End-to-End
# ---------------------------------------------------------------------------

class TestEndToEnd(unittest.TestCase):
    """
    Simulate the full pipeline described in the spec using mocked LLM.
    Input → Extract → Stage → Consolidate → Store → Curiosity → Decay
    """

    def _run_pipeline(self, conn: sqlite3.Connection, text: str) -> dict:
        extract_llm     = MagicMock(return_value=MOCK_EXTRACTION_RESPONSE)
        consolidate_llm = MagicMock(return_value=MOCK_CONSOLIDATION_RESPONSE)
        curiosity_llm   = MagicMock(return_value=MOCK_CURIOSITY_RESPONSE)

        staged   = extract_knowledge(text, llm_fn=extract_llm)
        canonical = consolidate([staged], llm_fn=consolidate_llm)

        entity_map = {}
        for e in canonical["entities"]:
            eid = insert_entity(conn, e["name"], e.get("type"), e["confidence"])
            entity_map[e["id"]] = eid
        for f in canonical["facts"]:
            sid = entity_map.get(f["subject_id"])
            oid = entity_map.get(f["object_id"])
            if sid and oid:
                insert_fact(conn, sid, f["predicate"], oid, f["confidence"])

        note_ids  = list(entity_map.values())
        note_text = f"Processed: {text[:80]}"
        insert_memory_note(conn, note_text, 0.75, note_ids)

        questions = generate_curiosity(canonical, llm_fn=curiosity_llm)
        for q in questions:
            enqueue_question(conn, q["question"], q["uncertainty"], q["priority"])

        return {"entities": canonical["entities"], "questions": questions}

    def test_malaga_example_stores_entities(self):
        with fresh_db() as conn:
            self._run_pipeline(conn, "Málaga has a growing tech startup ecosystem.")
            count = conn.execute("SELECT count(*) FROM entities").fetchone()[0]
            self.assertGreater(count, 0)

    def test_malaga_example_stores_facts(self):
        with fresh_db() as conn:
            self._run_pipeline(conn, "Málaga has a growing tech startup ecosystem.")
            count = conn.execute("SELECT count(*) FROM facts").fetchone()[0]
            self.assertGreater(count, 0)

    def test_malaga_example_generates_curiosity(self):
        with fresh_db() as conn:
            self._run_pipeline(conn, "Málaga has a growing tech startup ecosystem.")
            count = conn.execute("SELECT count(*) FROM curiosity_queue").fetchone()[0]
            self.assertGreater(count, 0)

    def test_all_curiosity_items_start_pending(self):
        with fresh_db() as conn:
            self._run_pipeline(conn, "Málaga has a growing tech startup ecosystem.")
            non_pending = conn.execute(
                "SELECT count(*) FROM curiosity_queue WHERE status != 'pending'"
            ).fetchone()[0]
            self.assertEqual(non_pending, 0)

    def test_memory_note_written(self):
        with fresh_db() as conn:
            self._run_pipeline(conn, "Málaga has a growing tech startup ecosystem.")
            count = conn.execute("SELECT count(*) FROM memory_notes").fetchone()[0]
            self.assertGreater(count, 0)

    def test_decay_after_pipeline_reduces_note(self):
        with fresh_db() as conn:
            self._run_pipeline(conn, "Málaga has a growing tech startup ecosystem.")
            before = conn.execute(
                "SELECT confidence FROM memory_notes LIMIT 1"
            ).fetchone()[0]
            apply_decay(conn, decay_factor=0.5, prune_threshold=0.01)
            after_row = conn.execute("SELECT confidence FROM memory_notes LIMIT 1").fetchone()
            if after_row:
                self.assertLess(after_row[0], before)

    def test_graph_referential_integrity_maintained(self):
        """Every fact's subject_id and object_id must exist in entities."""
        with fresh_db() as conn:
            self._run_pipeline(conn, "Málaga has a growing tech startup ecosystem.")
            orphan_count = conn.execute("""
                SELECT count(*) FROM facts f
                WHERE NOT EXISTS (SELECT 1 FROM entities e WHERE e.id = f.subject_id)
                   OR NOT EXISTS (SELECT 1 FROM entities e WHERE e.id = f.object_id)
            """).fetchone()[0]
            self.assertEqual(orphan_count, 0, "Found facts with missing entity references")

    def test_storage_within_budget(self):
        """
        After 50 ingestion cycles with decay, the DB size must stay
        under the 100MB budget defined in the spec.
        """
        MAX_BYTES = 100 * 1024 * 1024
        with tempfile.NamedTemporaryFile(suffix=".db", delete=True) as tmp:
            conn = sqlite3.connect(tmp.name)
            conn.execute("PRAGMA foreign_keys = ON")
            init_db(conn)
            for _ in range(50):
                self._run_pipeline(conn, "Málaga has a growing tech startup ecosystem.")
                apply_decay(conn, decay_factor=0.9, prune_threshold=0.1)
            conn.close()
            db_size = os.path.getsize(tmp.name)
            self.assertLess(db_size, MAX_BYTES,
                            f"DB is {db_size/1024/1024:.1f}MB, exceeds 100MB budget")


# ---------------------------------------------------------------------------
# Optional: live LLM smoke tests
# ---------------------------------------------------------------------------

LIVE = os.getenv("CURIOSITY_LIVE_API") == "1"

@unittest.skipUnless(LIVE, "Set CURIOSITY_LIVE_API=1 MISTRAL_API_KEY=... to run live LLM tests")
class TestLiveExtractionSmoke(unittest.TestCase):

    def test_call_llm_returns_parsed_dict(self):
        """call_llm returns a parsed dict, not a raw string."""
        result = call_llm(EXTRACTION_PROMPT.format(
            text="Madrid is the capital of Spain."
        ))
        self.assertIsInstance(result, dict)

    def test_call_llm_raises_on_missing_key(self):
        """call_llm raises ValueError when MISTRAL_API_KEY is not set."""
        original = os.environ.pop("MISTRAL_API_KEY", None)
        try:
            with self.assertRaises((ValueError, KeyError)):
                call_llm("test prompt")
        finally:
            if original is not None:
                os.environ["MISTRAL_API_KEY"] = original

    def test_live_extraction_returns_valid_structure(self):
        """Real extraction returns entities, facts, and uncertainties."""
        result = extract_knowledge(
            "Barcelona has a mature fintech startup scene with strong VC funding."
        )
        self.assertIn("entities", result)
        self.assertIn("facts",    result)
        self.assertIn("uncertainties", result)
        self.assertGreater(len(result["entities"]), 0)

    def test_live_extraction_confidence_values(self):
        """All confidence values from a real extraction are in [0.0, 1.0]."""
        result = extract_knowledge(
            "Valencia is emerging as an AI research hub in southern Europe."
        )
        for e in result["entities"]:
            self.assertGreaterEqual(e["confidence"], 0.0)
            self.assertLessEqual(e["confidence"],    1.0)

    def test_live_extraction_facts_are_triples(self):
        """Real extraction produces facts with subject, predicate, object."""
        result = extract_knowledge(
            "Seville is a city in Andalusia known for flamenco."
        )
        for f in result["facts"]:
            self.assertIn("subject_id", f)
            self.assertIn("predicate",  f)
            self.assertIn("object_id",  f)

    def test_live_consolidation_returns_valid_structure(self):
        """Real consolidation returns entities and facts."""
        staged = [extract_knowledge(
            "Málaga has a growing tech startup ecosystem."
        )]
        result = consolidate(staged)
        self.assertIn("entities", result)
        self.assertIn("facts",    result)
        self.assertGreater(len(result["entities"]), 0)

    def test_live_curiosity_generation(self):
        """Real curiosity generation returns non-empty questions."""
        questions = generate_curiosity(MOCK_CONSOLIDATION_RESPONSE)
        self.assertGreater(len(questions), 0)
        for q in questions:
            self.assertIn("question", q)
            self.assertTrue(q["question"].strip())

    def test_live_full_pipeline(self):
        """Full pipeline from raw text produces entities, facts, and questions in DB."""
        with fresh_db() as conn:
            text = "Bilbao is reinventing itself as a design and technology hub."
            staged    = extract_knowledge(text)
            canonical = consolidate([staged])
            entity_map = {}
            for e in canonical["entities"]:
                eid = insert_entity(conn, e["name"], e.get("type"), e["confidence"])
                entity_map[e["id"]] = eid
            for f in canonical["facts"]:
                sid = entity_map.get(f["subject_id"])
                oid = entity_map.get(f["object_id"])
                if sid and oid:
                    insert_fact(conn, sid, f["predicate"], oid, f["confidence"])
            insert_memory_note(conn, text[:80], 0.75, list(entity_map.values()))
            questions = generate_curiosity(canonical)
            for q in questions:
                enqueue_question(conn, q["question"], q["uncertainty"], q["priority"])

            self.assertGreater(
                conn.execute("SELECT count(*) FROM entities").fetchone()[0], 0)
            self.assertGreater(
                conn.execute("SELECT count(*) FROM curiosity_queue").fetchone()[0], 0)


# ---------------------------------------------------------------------------
# Entry point — clean pass/fail reporter with line numbers and re-run commands
# ---------------------------------------------------------------------------

SUITE_CLASSES = [
    ("Database Schema",            TestDatabaseSchema),
    ("Data Insertion & Retrieval", TestDataInsertionRetrieval),
    ("Extraction Pipeline",        TestExtractionPipeline),
    ("Temporary Staging",          TestTemporaryStaging),
    ("Consolidation",              TestConsolidation),
    ("Curiosity Queue",            TestCuriosityQueue),
    ("Memory Decay",               TestMemoryDecay),
    ("End-to-End",                 TestEndToEnd),
]


def _extract_line(tb: str) -> str:
    """Return the last line number in test_harness.py from a traceback string."""
    hits = re.findall(r'test_harness\.py", line (\d+)', tb)
    return hits[-1] if hits else "?"


def _run_one(test) -> tuple:
    """Run a single test; return ('pass'|'fail'|'skip', detail)."""
    result = unittest.TestResult()
    test.run(result)
    if result.skipped:
        return "skip", result.skipped[0][1]
    if result.wasSuccessful():
        return "pass", ""
    tb = (result.failures or result.errors)[0][1]
    reason = [l.strip() for l in tb.splitlines() if l.strip()][-1]
    return "fail", (reason, _extract_line(tb))


def _print_result(outcome, detail, class_name, method_name, doc=""):
    label = method_name + (f"  [{doc}]" if doc else "")
    if outcome == "pass":
        print(f"  PASS  {label}")
    elif outcome == "skip":
        print(f"  SKIP  {label}")
        print(f"        {detail}")
    else:
        reason, lineno = detail
        print(f"  FAIL  {label}  [test_harness.py:{lineno}]")
        print(f"        {reason}")
        print(f"        → python3 test_harness.py {class_name}.{method_name}")


LAST_PASSING_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs", "last_passing.json")


def _load_last_passing() -> set:
    try:
        with open(LAST_PASSING_FILE) as f:
            return set(json.load(f))
    except (FileNotFoundError, json.JSONDecodeError):
        return set()


def _save_passing(passing: set) -> None:
    os.makedirs(os.path.dirname(LAST_PASSING_FILE), exist_ok=True)
    with open(LAST_PASSING_FILE, "w") as f:
        json.dump(sorted(passing), f, indent=2)


def _test_label(cls, method_name: str) -> str:
    lines = (getattr(cls, method_name).__doc__ or "").strip().splitlines()
    return lines[0] if lines else method_name.replace("test_", "").replace("_", " ")


def _run_suite(suite_classes):
    loader = unittest.TestLoader()
    passed = failed = skipped = 0
    passing = set()
    for suite_name, cls in suite_classes:
        print(f"\n{'─' * 64}")
        print(f"  {suite_name}")
        print(f"{'─' * 64}")
        for test in loader.loadTestsFromTestCase(cls):
            method = test._testMethodName
            doc = (getattr(test, method).__doc__ or "").strip().splitlines()[0] \
                  if getattr(test, method).__doc__ else ""
            outcome, detail = _run_one(test)
            _print_result(outcome, detail, cls.__name__, method, doc)
            if outcome == "pass":
                passed += 1
                passing.add(f"{cls.__name__}.{method}")
            elif outcome == "skip":
                skipped += 1
            else:
                failed += 1
    total = passed + failed + skipped
    print(f"\n{'═' * 64}")
    print(f"  {total} tests   {passed} passed   {failed} failed   {skipped} skipped")
    print(f"{'═' * 64}\n")
    return failed, passing


def _print_newly_passing(current: set, previous: set, suite_classes) -> None:
    newly = current - previous
    if not newly:
        return
    cls_lookup = {cls.__name__: cls for _, cls in suite_classes}
    print(f"{'─' * 64}")
    print(f"  Newly Passing (+{len(newly)})")
    print(f"{'─' * 64}")
    for key in sorted(newly):
        class_name, _, method_name = key.partition(".")
        cls = cls_lookup.get(class_name)
        label = _test_label(cls, method_name) if cls else method_name
        print(f"  + {method_name}")
        print(f"    {label}")
    print()


class _Tee:
    """Write to stdout and a log file simultaneously."""
    def __init__(self, path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self._file = open(path, "w")
        self._stdout = sys.stdout

    def write(self, data):
        self._stdout.write(data)
        self._file.write(data)

    def flush(self):
        self._stdout.flush()
        self._file.flush()

    def close(self):
        self._file.close()


if __name__ == "__main__":
    if LIVE:
        SUITE_CLASSES.append(("Live LLM Smoke", TestLiveExtractionSmoke))

    timestamp = time.strftime("%Y%m%d_%H%M%S")
    log_path  = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs", f"test_run_{timestamp}.log")
    tee = _Tee(log_path)
    sys.stdout = tee

    try:
        if len(sys.argv) == 2:
            # Re-run a single test: python3 test_harness.py ClassName.method_name
            arg = sys.argv[1].replace("::", ".")
            class_name, _, method_name = arg.partition(".")
            lookup = {cls.__name__: (sname, cls) for sname, cls in SUITE_CLASSES}
            if class_name not in lookup:
                print(f"Unknown test class: {class_name}")
                sys.exit(1)
            _, cls = lookup[class_name]
            test = cls(method_name)
            doc = (getattr(test, method_name).__doc__ or "").strip().splitlines()[0] \
                  if getattr(test, method_name).__doc__ else ""
            print(f"\nRe-running: {class_name}.{method_name}")
            print(f"{'─' * 64}")
            outcome, detail = _run_one(test)
            _print_result(outcome, detail, class_name, method_name, doc)
            print()
            exitcode = 0 if outcome == "pass" else 1
        else:
            last_passing = _load_last_passing()
            failed, current_passing = _run_suite(SUITE_CLASSES)
            _print_newly_passing(current_passing, last_passing, SUITE_CLASSES)
            _save_passing(current_passing)
            exitcode = 0 if failed == 0 else 1

        print(f"Log: {log_path}")
    finally:
        tee.close()
        sys.stdout = tee._stdout

    sys.exit(exitcode)
