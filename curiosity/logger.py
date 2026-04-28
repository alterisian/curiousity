"""Simple JSONL activity logger for LLM queries and DB writes.

Writes events to ../logs/activity.jsonl (one JSON object per line).
Designed to be safe to import and inexpensive.
"""
from __future__ import annotations

import json
import os
import time
from typing import Any


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
LOG_DIR = os.path.join(ROOT, 'logs')
os.makedirs(LOG_DIR, exist_ok=True)
ACTIVITY_PATH = os.path.join(LOG_DIR, 'activity.jsonl')


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def log_event(kind: str, payload: dict[str, Any]) -> None:
    entry = {
        'ts': _now_iso(),
        'kind': kind,
        'payload': payload,
    }
    try:
        with open(ACTIVITY_PATH, 'a', encoding='utf-8') as f:
            f.write(json.dumps(entry, ensure_ascii=False) + '\n')
    except Exception:
        # Never raise during normal operation; logging is best-effort
        pass


def log_llm_call(prompt: str, response_raw: Any) -> None:
    try:
        payload = {'prompt': prompt, 'response': response_raw}
        log_event('llm_call', payload)
    except Exception:
        pass


def log_db_write(action: str, table: str, row: dict[str, Any]) -> None:
    try:
        payload = {'action': action, 'table': table, 'row': row}
        log_event('db_write', payload)
    except Exception:
        pass
