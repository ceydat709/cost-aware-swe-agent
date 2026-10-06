"""SQLite cache for LLM responses.

Re-running an experiment with the same prompts costs $0 and gives identical
results, which makes runs reproducible.
"""

import hashlib
import json
import sqlite3
from pathlib import Path


def cache_key(model: str, messages: list[dict], params: dict) -> str:
    payload = json.dumps({"model": model, "messages": messages, "params": params}, sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()


class ResponseCache:
    def __init__(self, path: str | Path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(path))
        self.conn.execute("CREATE TABLE IF NOT EXISTS responses (key TEXT PRIMARY KEY, value TEXT NOT NULL)")

    def get(self, key: str) -> dict | None:
        row = self.conn.execute("SELECT value FROM responses WHERE key = ?", (key,)).fetchone()
        return json.loads(row[0]) if row else None

    def put(self, key: str, value: dict) -> None:
        self.conn.execute("INSERT OR REPLACE INTO responses VALUES (?, ?)", (key, json.dumps(value)))
        self.conn.commit()
