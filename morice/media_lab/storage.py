"""Local, atomic metadata and bounded generation history; no replay authority."""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path


def read_json(path, *, limit=4*1024*1024):
    path=Path(path)
    if path.stat().st_size > limit:
        raise ValueError("Metadata exceeds its byte budget.")
    with path.open(encoding="utf-8") as stream:
        return json.load(stream)


def atomic_json(path, value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    data=json.dumps(value,ensure_ascii=False,allow_nan=False,indent=2).encode()
    if len(data)>8*1024*1024:raise ValueError("Metadata exceeds byte budget.")
    handle,tmp=tempfile.mkstemp(prefix=".media-",suffix=".tmp",dir=path.parent)
    try:
        with os.fdopen(handle,"wb") as stream:
            stream.write(data);stream.flush();os.fsync(stream.fileno())
        os.replace(tmp,path)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)


def file_hash(path, token=None):
    digest=hashlib.sha256()
    with Path(path).open("rb") as stream:
        while chunk:=stream.read(1024*1024):
            if token:token.raise_if_cancelled()
            digest.update(chunk)
    return digest.hexdigest()


class MediaHistory:
    def __init__(self,directory,max_history=500):
        self.directory=Path(directory);self.directory.mkdir(parents=True,exist_ok=True)
        self.path=self.directory/"history.sqlite3";self.max_history=max_history
        with self.connect() as db:
            db.execute("CREATE TABLE IF NOT EXISTS media_jobs (id TEXT PRIMARY KEY, state TEXT NOT NULL, updated REAL NOT NULL, payload TEXT NOT NULL)")
            # A restart never dispatches an interrupted generation or encoder.
            rows=db.execute("SELECT id,payload FROM media_jobs WHERE state NOT IN ('SUCCEEDED','FAILED','CANCELLED','INTERRUPTED')").fetchall()
            for identifier,payload in rows:
                value=json.loads(payload);value.update(status="INTERRUPTED",errors=["Interrupted by restart; review and submit a new job explicitly."])
                db.execute("UPDATE media_jobs SET state='INTERRUPTED',payload=?,updated=? WHERE id=?",(json.dumps(value),time.time(),identifier))

    @contextmanager
    def connect(self):
        db=sqlite3.connect(self.path,timeout=5)
        try:
            with db:yield db
        finally:db.close()

    def save(self,identifier,value):
        data=json.dumps(value,ensure_ascii=False,allow_nan=False)
        if len(data.encode())>256*1024:raise ValueError("Generation history record too large.")
        with self.connect() as db:
            db.execute("INSERT INTO media_jobs VALUES(?,?,?,?) ON CONFLICT(id) DO UPDATE SET state=excluded.state,updated=excluded.updated,payload=excluded.payload",(identifier,value['status'],time.time(),data))
            db.execute("DELETE FROM media_jobs WHERE id IN (SELECT id FROM media_jobs WHERE state IN ('SUCCEEDED','FAILED','CANCELLED','INTERRUPTED') ORDER BY updated DESC LIMIT -1 OFFSET ?)",(self.max_history,))

    def get(self,identifier):
        with self.connect() as db:row=db.execute("SELECT payload FROM media_jobs WHERE id=?",(identifier,)).fetchone()
        return json.loads(row[0]) if row else None

    def list(self,limit=100):
        with self.connect() as db:rows=db.execute("SELECT payload FROM media_jobs ORDER BY updated DESC LIMIT ?",(max(1,min(self.max_history,int(limit))),)).fetchall()
        return [json.loads(row[0]) for row in rows]
