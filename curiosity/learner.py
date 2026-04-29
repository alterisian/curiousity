import sqlite3


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


def learn_one(conn, llm_fn=None, search_fn=None) -> dict | None:
    raise NotImplementedError
