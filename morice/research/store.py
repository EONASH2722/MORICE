"""Additive research records in MORICE's existing knowledge SQLite database."""
from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path


PROVENANCE = frozenset({
    "CITED", "USER_DATA", "CALCULATED", "SIMULATED", "MEASURED", "INFERRED",
    "ESTIMATED", "HYPOTHESIS", "UNKNOWN",
})
KINDS = frozenset({
    "constraint", "hypothesis", "assumption", "source", "dataset", "calculation",
    "experiment", "simulation", "observation", "result", "design", "artifact",
    "failure", "open_question", "validation", "parameter",
})
HYPOTHESIS_STATES = frozenset({
    "PROPOSED", "TESTING", "SUPPORTED", "WEAKLY_SUPPORTED", "INCONCLUSIVE",
    "CONTRADICTED", "REJECTED",
})
RELATIONS = frozenset({
    "supported_by", "contradicted_by", "derived_from", "tested_by", "produced",
    "depends_on", "replaced_by", "uses_parameter", "generated_artifact",
})


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def encode(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True)


class ResearchStore:
    def __init__(self, database: str | Path):
        self.database = Path(database)
        self.database.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS research_schema (version INTEGER PRIMARY KEY);
                INSERT OR IGNORE INTO research_schema VALUES (1);
                CREATE TABLE IF NOT EXISTS research_projects (
                    id TEXT PRIMARY KEY, objective TEXT NOT NULL,
                    created TEXT NOT NULL, updated TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS research_records (
                    id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES research_projects(id),
                    kind TEXT NOT NULL, title TEXT NOT NULL, provenance TEXT NOT NULL,
                    payload TEXT NOT NULL, stale INTEGER NOT NULL DEFAULT 0,
                    revision INTEGER NOT NULL DEFAULT 1, created TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS research_project_records
                    ON research_records(project_id, kind);
                CREATE TABLE IF NOT EXISTS research_edges (
                    source TEXT NOT NULL REFERENCES research_records(id),
                    target TEXT NOT NULL REFERENCES research_records(id),
                    relation TEXT NOT NULL, PRIMARY KEY(source, target, relation)
                );
                CREATE TABLE IF NOT EXISTS research_timeline (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id TEXT NOT NULL REFERENCES research_projects(id),
                    time TEXT NOT NULL, action TEXT NOT NULL, payload TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS research_chat_links (
                    chat_id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES research_projects(id)
                );
            """)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.database, timeout=15)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        try:
            with db:
                yield db
        finally:
            db.close()

    @staticmethod
    def _log(db, project_id, action, payload):
        now = utc_now()
        db.execute("INSERT INTO research_timeline(project_id,time,action,payload) VALUES(?,?,?,?)",
                   (project_id, now, action, encode(payload)))
        db.execute("UPDATE research_projects SET updated=? WHERE id=?", (now, project_id))

    def create(self, objective: str, chat_id: str = "") -> str:
        if not objective.strip() or len(objective) > 20000:
            raise ValueError("Research objective must contain 1–20,000 characters.")
        identifier, now = uuid.uuid4().hex, utc_now()
        with self.connect() as db:
            db.execute("INSERT INTO research_projects VALUES(?,?,?,?)", (identifier, objective, now, now))
            if chat_id:
                db.execute("INSERT OR REPLACE INTO research_chat_links VALUES(?,?)", (chat_id, identifier))
            self._log(db, identifier, "project_created", {"objective": objective})
        return identifier

    def project_for_chat(self, chat_id: str) -> str | None:
        with self.connect() as db:
            row = db.execute("SELECT project_id FROM research_chat_links WHERE chat_id=?", (chat_id,)).fetchone()
        return row[0] if row else None

    def link_chat(self, project_id: str, chat_id: str):
        with self.connect() as db:
            db.execute("INSERT OR REPLACE INTO research_chat_links VALUES(?,?)", (chat_id, project_id))
            self._log(db, project_id, "chat_linked", {"chat_id": chat_id})

    def add(self, project_id: str, kind: str, title: str, payload: dict,
            provenance: str = "UNKNOWN", dependencies=()) -> str:
        if kind not in KINDS or provenance not in PROVENANCE:
            raise ValueError("Invalid research kind or provenance.")
        if provenance == "CITED" and not dependencies:
            raise ValueError("Cited claims require a stored source dependency.")
        if provenance in {"CALCULATED", "SIMULATED"} and not all(k in payload for k in ("inputs", "method", "result")):
            raise ValueError("Computed claims require inputs, method and actual result.")
        if kind == "hypothesis" and payload.get("status", "PROPOSED") not in HYPOTHESIS_STATES:
            raise ValueError("Invalid hypothesis status.")
        identifier = uuid.uuid4().hex
        with self.connect() as db:
            has_source = False
            for dependency in dependencies:
                row = db.execute("SELECT project_id,kind,stale FROM research_records WHERE id=?", (dependency,)).fetchone()
                if row is None or row[0] != project_id:
                    raise ValueError("Dependencies must belong to this research project.")
                has_source = has_source or row["kind"] == "source"
                if row["stale"] and provenance in {"CITED", "CALCULATED", "SIMULATED"}:
                    raise ValueError("Verified provenance cannot depend on stale inputs.")
            if provenance == "CITED" and not has_source:
                raise ValueError("Cited claims require a stored source dependency.")
            db.execute("INSERT INTO research_records VALUES(?,?,?,?,?,?,0,1,?)",
                       (identifier, project_id, kind, title[:1000], provenance, encode(payload), utc_now()))
            for dependency in dependencies:
                db.execute("INSERT INTO research_edges VALUES(?,?,?)", (identifier, dependency, "depends_on"))
            self._log(db, project_id, "record_added", {"id": identifier, "kind": kind, "title": title[:1000]})
        return identifier

    def relate(self, project_id, source, target, relation):
        if relation not in RELATIONS or source == target:
            raise ValueError("Invalid research relation.")
        with self.connect() as db:
            rows = db.execute("SELECT id FROM research_records WHERE project_id=? AND id IN (?,?)",
                              (project_id, source, target)).fetchall()
            if len(rows) != 2:
                raise ValueError("Both research records must belong to the project.")
            db.execute("INSERT OR IGNORE INTO research_edges VALUES(?,?,?)", (source, target, relation))
            self._log(db, project_id, "relation_added", {"source": source, "target": target, "relation": relation})

    def revise(self, project_id, record_id, payload):
        """Preserve the previous value and invalidate the transitive dependent closure."""
        with self.connect() as db:
            row = db.execute("SELECT * FROM research_records WHERE id=? AND project_id=?",
                             (record_id, project_id)).fetchone()
            if row is None:
                raise KeyError(record_id)
            if row["kind"] not in {"parameter", "assumption", "hypothesis", "constraint"}:
                raise ValueError("Immutable evidence/results must be replaced by a new record.")
            if row["kind"] == "hypothesis" and payload.get("status") not in HYPOTHESIS_STATES:
                raise ValueError("Invalid hypothesis status.")
            self._log(db, project_id, "record_revised", {"id": record_id, "previous": json.loads(row["payload"]), "next": payload})
            db.execute("UPDATE research_records SET payload=?,revision=revision+1 WHERE id=?", (encode(payload), record_id))
            db.execute("""WITH RECURSIVE affected(id) AS (
                SELECT source FROM research_edges WHERE target=? AND relation IN ('depends_on','derived_from','uses_parameter','supported_by')
                UNION SELECT e.source FROM research_edges e JOIN affected a ON e.target=a.id
                  WHERE e.relation IN ('depends_on','derived_from','uses_parameter','supported_by')
            ) UPDATE research_records SET stale=1 WHERE id IN (SELECT id FROM affected)""", (record_id,))

    def snapshot(self, project_id):
        with self.connect() as db:
            project = db.execute("SELECT * FROM research_projects WHERE id=?", (project_id,)).fetchone()
            if project is None:
                raise KeyError(project_id)
            records = [dict(r) for r in db.execute("SELECT * FROM research_records WHERE project_id=? ORDER BY created,id", (project_id,))]
            for record in records:
                record["payload"] = json.loads(record["payload"])
                record["stale"] = bool(record["stale"])
            edges = [dict(r) for r in db.execute("SELECT e.* FROM research_edges e JOIN research_records r ON e.source=r.id WHERE r.project_id=?", (project_id,))]
            timeline = [dict(r) for r in db.execute("SELECT * FROM research_timeline WHERE project_id=? ORDER BY seq", (project_id,))]
            chats = [r[0] for r in db.execute("SELECT chat_id FROM research_chat_links WHERE project_id=?", (project_id,))]
        return {**dict(project), "records": records, "edges": edges, "timeline": timeline, "related_chats": chats}

    def list_projects(self):
        with self.connect() as db:
            return [dict(r) for r in db.execute("SELECT * FROM research_projects ORDER BY updated DESC LIMIT 100")]
