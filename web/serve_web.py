"""Serve the web UI and provide endpoints for activity and DB snapshot."""
from http.server import SimpleHTTPRequestHandler, HTTPServer
import json
import os
import sqlite3
import time
from urllib.parse import urlparse

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
LOG_PATH = os.path.join(ROOT, 'logs', 'activity.jsonl')
DB_PATH = os.path.join(ROOT, 'curiosity_data.db')

class Handler(SimpleHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == '/activity':
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            activities = []
            try:
                with open(LOG_PATH, 'r', encoding='utf-8') as f:
                    for line in f:
                        activities.append(json.loads(line))
            except FileNotFoundError:
                activities = []
            self.wfile.write(json.dumps({'activity': activities, 'db': self._db_snapshot()}).encode())
            return
        return super().do_GET()

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path == '/action':
            length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(length)
            try:
                payload = json.loads(body.decode('utf-8'))
            except Exception:
                self.send_response(400)
                self.end_headers()
                return
            # Append to activity.jsonl with server timestamp
            entry = {'ts': time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), 'kind': 'ui_action', 'payload': payload}
            try:
                with open(LOG_PATH, 'a', encoding='utf-8') as f:
                    f.write(json.dumps(entry, ensure_ascii=False) + '\n')
            except Exception:
                pass
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'OK')
            return
        return super().do_POST()

    def _db_snapshot(self):
        # Return a small snapshot: entities, facts, curiosity_queue (top 20 rows)
        if not os.path.exists(DB_PATH):
            return {}
        try:
            conn = sqlite3.connect(DB_PATH)
            cur = conn.cursor()
            def fetch(q):
                cur.execute(q)
                cols = [d[0] for d in cur.description]
                rows = [dict(zip(cols, r)) for r in cur.fetchall()]
                # Normalize JSON columns (linked_entities) into Python lists for the UI
                for row in rows:
                    if 'linked_entities' in row and isinstance(row['linked_entities'], str):
                        try:
                            row['linked_entities'] = json.loads(row['linked_entities'])
                        except Exception:
                            # leave as raw string if parsing fails
                            pass
                return rows
            snapshot = {
                'entities': fetch('SELECT id, name, type, confidence FROM entities LIMIT 50'),
                'facts': fetch('SELECT id, subject_id, predicate, object_id, confidence FROM facts LIMIT 200'),
                'curiosity_queue': fetch('SELECT id, question, uncertainty, priority, status FROM curiosity_queue LIMIT 200'),
                'memory_notes': fetch('SELECT id, text, linked_entities, confidence FROM memory_notes LIMIT 200'),
            }
            conn.close()
            return snapshot
        except Exception:
            return {}

if __name__ == '__main__':
    os.chdir(os.path.dirname(__file__))
    port = int(os.environ.get('PORT', '8000'))
    print(f'Serving on http://0.0.0.0:{port}')
    HTTPServer(('0.0.0.0', port), Handler).serve_forever()
