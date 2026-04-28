import json
import sqlite3
import time
import uuid
from curiosity.logger import log_db_write


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS entities (
            id          TEXT PRIMARY KEY,
            name        TEXT NOT NULL,
            type        TEXT,
            embedding   BLOB,
            confidence  REAL NOT NULL CHECK(confidence >= 0.0 AND confidence <= 1.0)
        );

        CREATE TABLE IF NOT EXISTS facts (
            id          TEXT PRIMARY KEY,
            subject_id  TEXT NOT NULL,
            predicate   TEXT NOT NULL,
            object_id   TEXT NOT NULL,
            confidence  REAL NOT NULL CHECK(confidence >= 0.0 AND confidence <= 1.0),
            source      TEXT,
            timestamp   TEXT NOT NULL,
            FOREIGN KEY (subject_id) REFERENCES entities(id),
            FOREIGN KEY (object_id)  REFERENCES entities(id)
        );

        CREATE TABLE IF NOT EXISTS memory_notes (
            id              TEXT PRIMARY KEY,
            text            TEXT NOT NULL,
            linked_entities TEXT,
            confidence      REAL NOT NULL CHECK(confidence >= 0.0 AND confidence <= 1.0),
            decay           REAL NOT NULL DEFAULT 1.0,
            timestamp       TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS curiosity_queue (
            id          TEXT PRIMARY KEY,
            question    TEXT NOT NULL,
            uncertainty REAL NOT NULL CHECK(uncertainty >= 0.0 AND uncertainty <= 1.0),
            priority    REAL NOT NULL,
            status      TEXT NOT NULL CHECK(status IN ('pending','active','resolved','dropped'))
        );
    """)
    conn.commit()


def insert_entity(conn: sqlite3.Connection, name: str, entity_type: str,
                  confidence: float, embedding: bytes = None) -> str:
    entity_id = str(uuid.uuid4())
    conn.execute(
        "INSERT INTO entities (id, name, type, embedding, confidence) VALUES (?,?,?,?,?)",
        (entity_id, name, entity_type, embedding, confidence)
    )
    conn.commit()
    try:
        log_db_write('insert', 'entities', {'id': entity_id, 'name': name, 'type': entity_type, 'confidence': confidence})
    except Exception:
        pass
    return entity_id


def insert_fact(conn: sqlite3.Connection, subject_id: str, predicate: str,
                object_id: str, confidence: float, source: str = None) -> str:
    fact_id = str(uuid.uuid4())
    conn.execute(
        "INSERT INTO facts (id, subject_id, predicate, object_id, confidence, source, timestamp) "
        "VALUES (?,?,?,?,?,?,?)",
        (fact_id, subject_id, predicate, object_id, confidence, source,
         time.strftime("%Y-%m-%dT%H:%M:%S"))
    )
    conn.commit()
    try:
        log_db_write('insert', 'facts', {'id': fact_id, 'subject_id': subject_id, 'predicate': predicate, 'object_id': object_id, 'confidence': confidence, 'source': source})
    except Exception:
        pass
    return fact_id


def insert_memory_note(conn: sqlite3.Connection, text: str, confidence: float,
                       linked_entities: list[str] = None) -> str:
    note_id = str(uuid.uuid4())
    conn.execute(
        "INSERT INTO memory_notes (id, text, linked_entities, confidence, decay, timestamp) "
        "VALUES (?,?,?,?,?,?)",
        (note_id, text, json.dumps(linked_entities or []), confidence, 1.0,
         time.strftime("%Y-%m-%dT%H:%M:%S"))
    )
    conn.commit()
    try:
        log_db_write('insert', 'memory_notes', {'id': note_id, 'text': text, 'linked_entities': linked_entities or [], 'confidence': confidence})
    except Exception:
        pass
    return note_id


def enqueue_question(conn: sqlite3.Connection, question: str,
                     uncertainty: float, priority: float) -> str:
    q_id = str(uuid.uuid4())
    conn.execute(
        "INSERT INTO curiosity_queue (id, question, uncertainty, priority, status) "
        "VALUES (?,?,?,?,'pending')",
        (q_id, question, uncertainty, priority)
    )
    conn.commit()
    try:
        log_db_write('insert', 'curiosity_queue', {'id': q_id, 'question': question, 'uncertainty': uncertainty, 'priority': priority})
    except Exception:
        pass
    return q_id


def advance_question_status(conn: sqlite3.Connection, q_id: str, new_status: str) -> None:
    valid = {"pending", "active", "resolved", "dropped"}
    if new_status not in valid:
        raise ValueError(f"Invalid status: {new_status}")
    conn.execute("UPDATE curiosity_queue SET status=? WHERE id=?", (new_status, q_id))
    conn.commit()
    try:
        log_db_write('update', 'curiosity_queue', {'id': q_id, 'status': new_status})
    except Exception:
        pass


def apply_decay(conn: sqlite3.Connection, decay_factor: float = 0.95,
                prune_threshold: float = 0.1) -> int:
    conn.execute(
        "UPDATE memory_notes SET confidence = confidence * ?, decay = decay * ? "
        "WHERE confidence * decay > ?",
        (decay_factor, decay_factor, prune_threshold)
    )
    cursor = conn.execute(
        "DELETE FROM memory_notes WHERE confidence * decay <= ?",
        (prune_threshold,)
    )
    conn.commit()
    try:
        log_db_write('update', 'memory_notes', {'decay_factor': decay_factor, 'prune_threshold': prune_threshold})
    except Exception:
        pass
    return cursor.rowcount
