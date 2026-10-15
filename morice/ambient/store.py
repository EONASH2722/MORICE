"""Bounded SQLite watch and action receipts; never stores provider content."""
from __future__ import annotations

import json
import sqlite3
import threading
import time
from contextlib import contextmanager
from dataclasses import asdict
from pathlib import Path
from .contracts import Trigger


class AmbientStore:
    def __init__(self, path, max_history=5000):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.max_history = max_history
        self.lock = threading.RLock()
        self._transaction_depth=0
        self.db = sqlite3.connect(self.path, check_same_thread=False, timeout=2)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.executescript("""
          CREATE TABLE IF NOT EXISTS ambient_watches(id TEXT PRIMARY KEY, config TEXT NOT NULL, last_run REAL DEFAULT 0);
          CREATE TABLE IF NOT EXISTS ambient_events(dedupe TEXT PRIMARY KEY,id TEXT,time REAL,type TEXT,source TEXT,ref TEXT,trust TEXT);
          CREATE TABLE IF NOT EXISTS ambient_receipts(key TEXT PRIMARY KEY,watch TEXT,event TEXT,state TEXT,task TEXT DEFAULT '',detail TEXT DEFAULT '',time REAL);
          CREATE TABLE IF NOT EXISTS ambient_cursors(id TEXT PRIMARY KEY,value TEXT);
          CREATE TABLE IF NOT EXISTS ambient_causes(key TEXT PRIMARY KEY,time REAL);
        """)
        # Never replay an action which may already have reached a provider.
        self.db.execute("UPDATE ambient_receipts SET state='interrupted_review' WHERE state IN ('claimed','running')")
        self.db.commit()

    @contextmanager
    def transaction(self):
        with self.lock:
            outer=self._transaction_depth==0
            if outer:self.db.execute("BEGIN")
            self._transaction_depth+=1
            try:
                yield
            except BaseException:
                if outer:self.db.rollback()
                raise
            else:
                if outer:self.db.commit()
            finally:self._transaction_depth-=1

    def save(self, trigger):
        with self.transaction():
            self.db.execute("INSERT INTO ambient_watches(id,config) VALUES(?,?) ON CONFLICT(id) DO UPDATE SET config=excluded.config",
                            (trigger.trigger_id, json.dumps(asdict(trigger))))

    def watches(self):
        with self.lock:
            return [Trigger(**json.loads(r[0])) for r in self.db.execute("SELECT config FROM ambient_watches ORDER BY rowid")]

    def delete(self, trigger_id):
        with self.transaction():
            self.db.execute("DELETE FROM ambient_watches WHERE id=?", (trigger_id,))

    def accept(self, event):
        key = event.source + ":" + event.source_id + ":" + (event.dedupe_key or event.event_id)
        with self.transaction():
            inserted = self.db.execute("INSERT OR IGNORE INTO ambient_events VALUES(?,?,?,?,?,?,?)",
                (key, event.event_id, event.timestamp, event.event_type, event.source, event.source_id, event.trust.value)).rowcount
            self.db.execute("DELETE FROM ambient_events WHERE rowid IN (SELECT rowid FROM ambient_events ORDER BY rowid DESC LIMIT -1 OFFSET ?)", (self.max_history,))
        return bool(inserted)

    def claim(self, watch, event, now):
        key = watch.trigger_id + ":" + event.source + ":" + event.source_id + ":" + (event.dedupe_key or event.event_id)
        with self.transaction():
            last = self.db.execute("SELECT last_run FROM ambient_watches WHERE id=?", (watch.trigger_id,)).fetchone()
            if last is None or now - last[0] < watch.cooldown_seconds:
                return ""
            cause=watch.trigger_id+":"+(event.correlation_id or event.event_id)
            if not self.db.execute("INSERT OR IGNORE INTO ambient_causes VALUES(?,?)",(cause,now)).rowcount:return ""
            inserted = self.db.execute("INSERT OR IGNORE INTO ambient_receipts(key,watch,event,state,time) VALUES(?,?,?,?,?)",
                                      (key, watch.trigger_id, event.event_id, "claimed", now)).rowcount
            if not inserted:
                return ""
            self.db.execute("UPDATE ambient_watches SET last_run=? WHERE id=?", (now, watch.trigger_id))
            self.db.execute("DELETE FROM ambient_receipts WHERE rowid IN (SELECT rowid FROM ambient_receipts ORDER BY rowid DESC LIMIT -1 OFFSET ?)", (self.max_history,))
            self.db.execute("DELETE FROM ambient_causes WHERE rowid IN (SELECT rowid FROM ambient_causes ORDER BY rowid DESC LIMIT -1 OFFSET ?)",(self.max_history,))
        return key

    def receipt(self, key, state, task="", detail=""):
        with self.transaction():
            self.db.execute("UPDATE ambient_receipts SET state=?,task=?,detail=? WHERE key=?", (state, task, detail[:200], key))

    def claim_confirmation(self, key, task):
        # Commit the claim before a possible provider effect. Concurrent exact
        # approvals must not dispatch the same pending consequence twice.
        with self.transaction():
            changed = self.db.execute("UPDATE ambient_receipts SET state='running',task=? WHERE key=? AND state='awaiting_exact_confirmation'",
                                      (task, key)).rowcount
        return changed == 1

    def receipts(self, limit=100):
        with self.lock:
            return [dict(zip(("key", "watch", "event", "state", "task", "detail", "time"), row))
                    for row in self.db.execute("SELECT * FROM ambient_receipts ORDER BY rowid DESC LIMIT ?", (min(500,limit),))]

    def cursor(self, key, value=None):
        with self.transaction():
            if value is not None:
                self.db.execute("INSERT OR REPLACE INTO ambient_cursors VALUES(?,?)", (key, json.dumps(value)))
            row = self.db.execute("SELECT value FROM ambient_cursors WHERE id=?", (key,)).fetchone()
            return json.loads(row[0]) if row else None

    def close(self):
        with self.lock:
            self.db.close()
