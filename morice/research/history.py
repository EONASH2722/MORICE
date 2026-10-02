"""Indexed chat metadata with checksummed, independently compressed transcripts."""
from __future__ import annotations

import gzip
import hashlib
import io
import json
import time
from difflib import SequenceMatcher

from .store import ResearchStore

RETENTION = {"never": None, "10_days": 10 * 86400, "month": 30 * 86400, "session": 0}
MAX_CHAT_BYTES = 8 * 1024 * 1024


class ChatHistory:
    def __init__(self, database):
        self.store = ResearchStore(database)
        with self.store.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS research_chats (
                    id TEXT PRIMARY KEY, name TEXT NOT NULL, preview TEXT NOT NULL,
                    created REAL NOT NULL, last_used REAL NOT NULL,
                    retention TEXT NOT NULL DEFAULT 'never', protected INTEGER NOT NULL DEFAULT 0,
                    archived INTEGER NOT NULL DEFAULT 0, project_id TEXT NOT NULL DEFAULT '',
                    codec TEXT NOT NULL, checksum TEXT NOT NULL, transcript BLOB NOT NULL
                );
                CREATE INDEX IF NOT EXISTS research_chat_recency ON research_chats(last_used);
                CREATE INDEX IF NOT EXISTS research_chat_names ON research_chats(name COLLATE NOCASE);
            """)

    def save(self, chat_id, messages, project_id="", now=None):
        if not messages:
            return
        clean = [{"role": m["role"], "content": str(m["content"])} for m in messages if m.get("role") in {"user", "assistant"} and m.get("content")]
        raw = json.dumps(clean, ensure_ascii=False).encode("utf-8")
        if len(raw) > MAX_CHAT_BYTES:
            raise ValueError("Chat exceeds the 8 MiB history limit.")
        zipped = gzip.compress(raw, mtime=0)
        codec, blob = ("gzip", zipped) if len(zipped) < len(raw) else ("json", raw)
        name = next((m["content"] for m in clean if m["role"] == "user"), "Conversation")
        name = " ".join(name.split())[:90]
        preview = " ".join(clean[-1]["content"].split())[:200] if clean else ""
        timestamp = time.time() if now is None else now
        with self.store.connect() as db:
            db.execute("""INSERT INTO research_chats(id,name,preview,created,last_used,project_id,codec,checksum,transcript)
                VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET
                preview=excluded.preview,last_used=excluded.last_used,project_id=excluded.project_id,
                codec=excluded.codec,checksum=excluded.checksum,transcript=excluded.transcript,archived=0""",
                       (chat_id, name, preview, timestamp, timestamp, project_id, codec, hashlib.sha256(raw).hexdigest(), blob))

    def search(self, query="", limit=100):
        query = query.strip().casefold()
        with self.store.connect() as db:
            # Metadata only. Never decompress transcripts to draw a history list.
            rows = [dict(r) for r in db.execute("SELECT id,name,preview,created,last_used,retention,protected,archived,project_id,LENGTH(transcript) AS stored_bytes FROM research_chats ORDER BY last_used DESC LIMIT 10000")]
        if query:
            def score(row):
                name = row["name"].casefold()
                if query == name:
                    return 3
                if all(word in name for word in query.split()):
                    return 2
                return max((SequenceMatcher(None, query, name).ratio(),
                            *(SequenceMatcher(None, query, word).ratio() for word in name.split())))
            rows = sorted(((score(r), r) for r in rows), key=lambda pair: pair[0], reverse=True)
            rows = [r for rating, r in rows if rating >= 0.55]
        return rows[:max(1, min(limit, 1000))]

    def open(self, chat_id, now=None):
        with self.store.connect() as db:
            row = db.execute("SELECT * FROM research_chats WHERE id=?", (chat_id,)).fetchone()
            if row is None:
                raise KeyError(chat_id)
            blob = bytes(row["transcript"])
            if row["codec"] == "gzip":
                with gzip.GzipFile(fileobj=io.BytesIO(blob)) as stream:
                    raw = stream.read(MAX_CHAT_BYTES + 1)
            else:
                raw = blob
            if len(raw) > MAX_CHAT_BYTES or hashlib.sha256(raw).hexdigest() != row["checksum"]:
                raise ValueError("Chat archive failed integrity checks; its stored copy was preserved.")
            messages = json.loads(raw)
            if not isinstance(messages, list):
                raise ValueError("Invalid chat archive structure.")
            db.execute("UPDATE research_chats SET last_used=?,archived=0 WHERE id=?", (time.time() if now is None else now, chat_id))
        return {"id": row["id"], "name": row["name"], "messages": messages, "project_id": row["project_id"]}

    def configure(self, chat_id, name, retention="never", protected=False):
        if retention not in RETENTION or not name.strip():
            raise ValueError("Choose a nonempty chat name and a valid retention policy.")
        with self.store.connect() as db:
            db.execute("UPDATE research_chats SET name=?,retention=?,protected=? WHERE id=?", (name.strip()[:120], retention, int(protected), chat_id))

    def archive(self, chat_id):
        with self.store.connect() as db:
            db.execute("UPDATE research_chats SET archived=1 WHERE id=?", (chat_id,))

    def delete(self, chat_id):
        # Research records and content-addressed evidence survive chat deletion.
        with self.store.connect() as db:
            db.execute("DELETE FROM research_chats WHERE id=?", (chat_id,))
            db.execute("DELETE FROM research_chat_links WHERE chat_id=?", (chat_id,))

    def expire(self, *, now=None, active_id="", ended_id=""):
        current = time.time() if now is None else now
        removed = []
        with self.store.connect() as db:
            rows = db.execute("SELECT id,retention,last_used,protected FROM research_chats").fetchall()
            for row in rows:
                if row["protected"] or row["id"] == active_id:
                    continue
                duration = RETENTION.get(row["retention"])
                expired = (row["id"] == ended_id) if row["retention"] == "session" else (duration is not None and current - row["last_used"] >= duration)
                if expired:
                    db.execute("DELETE FROM research_chats WHERE id=?", (row["id"],))
                    db.execute("DELETE FROM research_chat_links WHERE chat_id=?", (row["id"],))
                    removed.append(row["id"])
        return removed
