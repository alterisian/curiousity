import sqlite3

from curiosity.db import (
    insert_entity, insert_fact, insert_memory_note,
    advance_question_status,
)
from curiosity.pipeline import extract_knowledge, consolidate, generate_curiosity
from curiosity.search import fetch_snippets


def related(conn: sqlite3.Connection, entity_id: str) -> list[dict]:
    rows = conn.execute("""
        SELECT e.id, e.name, e.type, e.confidence, f.predicate, 'object' AS role
        FROM facts f JOIN entities e ON e.id = f.object_id
        WHERE f.subject_id = ?
        UNION
        SELECT e.id, e.name, e.type, e.confidence, f.predicate, 'subject' AS role
        FROM facts f JOIN entities e ON e.id = f.subject_id
        WHERE f.object_id = ?
    """, (entity_id, entity_id)).fetchall()
    return [
        {"id": r[0], "name": r[1], "type": r[2], "confidence": r[3],
         "predicate": r[4], "role": r[5]}
        for r in rows
    ]


def learn_one(conn: sqlite3.Connection, llm_fn=None, search_fn=None) -> dict | None:
    if search_fn is None:
        search_fn = fetch_snippets
    if llm_fn is None:
        llm_fn = None  # extract_knowledge/consolidate/generate_curiosity use call_llm by default

    row = conn.execute("""
        SELECT id, question FROM curiosity_queue
        WHERE status = 'pending'
        ORDER BY priority DESC
        LIMIT 1
    """).fetchone()

    if row is None:
        return None

    q_id, question = row
    advance_question_status(conn, q_id, "active")

    snippets = search_fn(question)
    staged = []
    for snippet in snippets:
        extraction = extract_knowledge(snippet, llm_fn=llm_fn)
        staged.append(extraction)

    if staged:
        canonical = consolidate(staged, llm_fn=llm_fn)
    else:
        canonical = {"entities": [], "facts": []}

    entity_map = {}
    for e in canonical.get("entities", []):
        eid = insert_entity(conn, e["name"], e.get("type"), e["confidence"])
        entity_map[e["id"]] = eid

    for f in canonical.get("facts", []):
        sid = entity_map.get(f["subject_id"])
        oid = entity_map.get(f["object_id"])
        if sid and oid:
            insert_fact(conn, sid, f["predicate"], oid, f["confidence"])

    entity_db_ids = list(entity_map.values())
    summary_text = f"Learned from: {question}"[:120]
    insert_memory_note(conn, summary_text, 0.75, entity_db_ids)

    advance_question_status(conn, q_id, "resolved")

    return {
        "question": question,
        "snippets_fetched": len(snippets),
        "entities_stored": len(entity_db_ids),
        "facts_stored": len(canonical.get("facts", [])),
    }
