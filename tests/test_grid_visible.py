import os
import sqlite3
import sys
from playwright.sync_api import sync_playwright

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
DB_PATH = os.path.join(ROOT, 'curiosity_data.db')
sys.path.insert(0, ROOT)

from curiosity.db import init_db, insert_entity, insert_memory_note, enqueue_question


def _seed():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    init_db(conn)
    eid = insert_entity(conn, "_pw_test_entity", "concept", 0.9)
    enqueue_question(conn, "_pw_test_question?", 0.8, 0.7)
    insert_memory_note(conn, "_pw_test_note", 0.75, [eid])
    conn.close()


def _cleanup():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("DELETE FROM entities WHERE name = '_pw_test_entity'")
    conn.execute("DELETE FROM curiosity_queue WHERE question = '_pw_test_question?'")
    conn.execute("DELETE FROM memory_notes WHERE text = '_pw_test_note'")
    conn.commit()
    conn.close()


def test_grid_shows_nodes():
    _seed()
    try:
        url = os.environ.get('CURIO_UI', 'http://localhost:8000/index.html')
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(url)
            page.wait_for_timeout(1500)
            nodes = page.query_selector_all('.node')
            assert len(nodes) > 0, 'No .node elements found on the page'
            for n in nodes[:5]:
                style = n.evaluate('(el) => { return {left: el.style.left, top: el.style.top, width: el.offsetWidth, height: el.offsetHeight} }')
                assert style['left'] != '' and style['top'] != '', f'Node has no position: {style}'
            browser.close()
    finally:
        _cleanup()
