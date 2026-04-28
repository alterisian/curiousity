"""Run the Málaga ingestion pipeline and persist results to curiosity_data.db

This script uses the project's pipeline and DB helpers to:
 - Extract knowledge from a short text
 - Insert entities, facts, and memory notes into a persistent DB
 - Generate curiosity questions and enqueue them

Logs and LLM calls are recorded by the existing activity logger.
"""
import os
import sqlite3
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
DB_PATH = os.path.join(ROOT, 'curiosity_data.db')

from curiosity.pipeline import extract_knowledge, generate_curiosity
from curiosity.db import (
    init_db, insert_entity, insert_fact, insert_memory_note, enqueue_question
)


def run(text: str):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    init_db(conn)

    print('Extracting knowledge...')
    extraction = extract_knowledge(text)

    # Map LLM entity ids to DB ids
    mapping = {}
    for e in extraction.get('entities', []):
        name = e.get('name')
        etype = e.get('type', '')
        confidence = float(e.get('confidence', 0.5))
        dbid = insert_entity(conn, name, etype, confidence)
        mapping[e.get('id')] = dbid

    for f in extraction.get('facts', []):
        sid = mapping.get(f.get('subject_id'))
        oid = mapping.get(f.get('object_id'))
        if sid and oid:
            pred = f.get('predicate')
            confidence = float(f.get('confidence', 0.5))
            insert_fact(conn, sid, pred, oid, confidence, source='malaga-run')

    for u in extraction.get('uncertainties', []):
        insert_memory_note(conn, u, 0.5, [])

    print('Generating curiosity questions...')
    knowledge = {'entities': extraction.get('entities', []), 'facts': extraction.get('facts', [])}
    questions = generate_curiosity(knowledge)
    for q in questions:
        enqueue_question(conn, q['question'], float(q['uncertainty']), float(q['priority']))

    conn.close()
    print(f'Done — persisted to {DB_PATH}')


if __name__ == '__main__':
    text = ' '.join(sys.argv[1:]) if len(sys.argv) > 1 else 'Málaga has a growing tech startup ecosystem.'
    run(text)
