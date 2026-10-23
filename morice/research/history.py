"""Indexed chat metadata with checksummed, independently compressed transcripts."""
from __future__ import annotations

import gzip
import hashlib
import io
import json
import re
import time
import uuid
from datetime import datetime,timedelta
from difflib import SequenceMatcher

from .store import ResearchStore

RETENTION = {"never": None, "10_days": 10 * 86400, "month": 30 * 86400, "session": 0}
MAX_CHAT_BYTES = 8 * 1024 * 1024

_HISTORY_STOP = frozenset("what when where why how did do does was were is are i we me my our you your the a an about of to in on for with and or that this it say said tell told choose chosen want wanted use originally original beginning first last latest earlier previous message messages chat conversation exactly quote repeat remind please design discussed decision decisions change changed finally current from at start summarize compare full history evolution evolve".split())


def history_query_terms(query):
    terms=[t for t in re.findall(r"[\w]+",str(query)[:4000].casefold()) if len(t)>1 and t not in _HISTORY_STOP and t not in {'yesterday','today'}]
    # Small documented query expansion, not a validated embedding search.
    expansions={"transparent":("glass","translucent"),"futuristic":("glass",),"colour":("color","interface"),"color":("colour","interface","ui"),"interface":("ui",),"gpu":("cuda","vram")}
    return list(dict.fromkeys([*terms,*(v for t in terms for v in expansions.get(t,()))]))[:20]


def history_query_mode(query):
    text=str(query).casefold()
    if re.search(r"\b(compare|evolv\w*|timeline|how.*chang\w*|from the start|full history)\b",text): return "timeline"
    if re.search(r"\b(first thing|first message|original request|original sentence|say first|chat.*start|start.*conversation)\b",text): return "first_message"
    if re.search(r"\b(original\w*|beginning|initial\w*|earliest|at the start)\b",text): return "original"
    if re.search(r"\b(latest|current choice|finally|final decision|last decision)\b",text): return "latest"
    if re.search(r"\b(previous|last) (?:user )?message\b",text): return "latest_message"
    return "search"


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
                CREATE TABLE IF NOT EXISTS research_chat_messages (
                    id TEXT PRIMARY KEY, chat_id TEXT NOT NULL REFERENCES research_chats(id) ON DELETE CASCADE,
                    sequence INTEGER NOT NULL, role TEXT NOT NULL, content TEXT NOT NULL,
                    created REAL NOT NULL, updated REAL NOT NULL, revision INTEGER NOT NULL DEFAULT 1,
                    attachments TEXT NOT NULL DEFAULT '[]', UNIQUE(chat_id,sequence)
                );
                CREATE INDEX IF NOT EXISTS research_message_scope ON research_chat_messages(chat_id,role,sequence);
                CREATE TABLE IF NOT EXISTS research_chat_index_state (
                    chat_id TEXT PRIMARY KEY REFERENCES research_chats(id) ON DELETE CASCADE,
                    checksum TEXT NOT NULL, version INTEGER NOT NULL DEFAULT 1, rebuilt REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS research_chat_summaries (
                    chat_id TEXT PRIMARY KEY REFERENCES research_chats(id) ON DELETE CASCADE,
                    version INTEGER NOT NULL, sources TEXT NOT NULL, content TEXT NOT NULL
                );
                CREATE VIRTUAL TABLE IF NOT EXISTS research_message_fts USING fts5(
                    content, chat_id UNINDEXED, content='research_chat_messages', content_rowid='rowid',
                    tokenize='unicode61 remove_diacritics 2'
                );
                CREATE TRIGGER IF NOT EXISTS research_message_insert AFTER INSERT ON research_chat_messages BEGIN
                    INSERT INTO research_message_fts(rowid,content,chat_id) VALUES(new.rowid,new.content,new.chat_id);
                    DELETE FROM research_chat_summaries WHERE chat_id=new.chat_id;
                END;
                CREATE TRIGGER IF NOT EXISTS research_message_delete AFTER DELETE ON research_chat_messages BEGIN
                    INSERT INTO research_message_fts(research_message_fts,rowid,content,chat_id) VALUES('delete',old.rowid,old.content,old.chat_id);
                    DELETE FROM research_chat_summaries WHERE chat_id=old.chat_id;
                END;
                CREATE TRIGGER IF NOT EXISTS research_message_update AFTER UPDATE ON research_chat_messages BEGIN
                    INSERT INTO research_message_fts(research_message_fts,rowid,content,chat_id) VALUES('delete',old.rowid,old.content,old.chat_id);
                    INSERT INTO research_message_fts(rowid,content,chat_id) VALUES(new.rowid,new.content,new.chat_id);
                    DELETE FROM research_chat_summaries WHERE chat_id=new.chat_id;
                END;
            """)
        self.last_search_ms = 0.0
        self.last_error = ""
        self.source_invalidated = None

    def save(self, chat_id, messages, project_id="", now=None, *, merge=False):
        if not messages:
            return
        if merge:
            return self._save_window(chat_id, messages, project_id, now)
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
            self._index_snapshot(db, chat_id, clean, timestamp, hashlib.sha256(raw).hexdigest())

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

    def open(self, chat_id, now=None, *, recent=None):
        with self.store.connect() as db:
            row = db.execute("SELECT * FROM research_chats WHERE id=?", (chat_id,)).fetchone()
            if row is None:
                raise KeyError(chat_id)
            blob = bytes(row["transcript"])
            messages = self._decode(row)
            if row["codec"] == "indexed":
                rows = self._messages(db, chat_id, limit=recent, descending=recent is not None)
                messages = rows
            elif recent is not None:
                self._ensure_index(db, row)
                messages = self._messages(db, chat_id, limit=recent, descending=True)
            db.execute("UPDATE research_chats SET last_used=?,archived=0 WHERE id=?", (time.time() if now is None else now, chat_id))
        return {"id": row["id"], "name": row["name"], "messages": messages, "project_id": row["project_id"]}

    @staticmethod
    def _decode(row):
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
        return messages

    def _ensure_index(self, db, row):
        state = db.execute("SELECT checksum FROM research_chat_index_state WHERE chat_id=?", (row["id"],)).fetchone()
        if state is None or state[0] != row["checksum"]:
            if row["codec"] == "indexed":
                # Indexed chats keep their authoritative text in message rows.
                # Their archive is only an integrity-checked empty sentinel;
                # missing derived metadata must never replace those rows with it.
                self._decode(row)
                db.execute("""INSERT INTO research_chat_index_state VALUES(?,?,1,?) ON CONFLICT(chat_id)
                    DO UPDATE SET checksum=excluded.checksum,version=version+1,rebuilt=excluded.rebuilt""",
                    (row["id"],row["checksum"],time.time()))
                db.execute("DELETE FROM research_chat_summaries WHERE chat_id=?",(row["id"],))
                return
            self._index_snapshot(db, row["id"], self._decode(row), row["created"], row["checksum"])

    def _index_snapshot(self, db, chat_id, messages, timestamp, checksum):
        # Preserve IDs for unchanged sequence positions during archive migration/edits.
        for seq, message in enumerate(messages, 1):
            identifier = uuid.uuid5(uuid.NAMESPACE_URL, f"morice:{chat_id}:{seq}").hex
            db.execute("""INSERT INTO research_chat_messages(id,chat_id,sequence,role,content,created,updated)
                VALUES(?,?,?,?,?,?,?) ON CONFLICT(chat_id,sequence) DO UPDATE SET
                role=excluded.role,content=excluded.content,updated=excluded.updated,revision=revision+1
                WHERE role<>excluded.role OR content<>excluded.content""",
                (identifier,chat_id,seq,message["role"],message["content"],timestamp,timestamp))
        db.execute("DELETE FROM research_chat_messages WHERE chat_id=? AND sequence>?", (chat_id,len(messages)))
        db.execute("""INSERT INTO research_chat_index_state VALUES(?,?,1,?) ON CONFLICT(chat_id)
            DO UPDATE SET checksum=excluded.checksum,version=version+1,rebuilt=excluded.rebuilt""", (chat_id,checksum,time.time()))

    @staticmethod
    def _messages(db, chat_id, *, limit=None, descending=False, lower=0, upper=None):
        sql = "SELECT id AS message_id,chat_id,sequence,role,content,created,updated,revision,attachments FROM research_chat_messages WHERE chat_id=? AND sequence>=?"
        args = [chat_id,max(0,int(lower))]
        if upper is not None:
            sql += " AND sequence<=?"; args.append(int(upper))
        sql += " ORDER BY sequence " + ("DESC" if descending else "ASC")
        if limit is not None:
            sql += " LIMIT ?"; args.append(max(1,min(1000,int(limit))))
        rows = [dict(r) for r in db.execute(sql,args)]
        return list(reversed(rows)) if descending else rows

    def _save_window(self, chat_id, messages, project_id, now):
        timestamp = time.time() if now is None else float(now)
        clean = [m for m in messages if m.get("role") in {"user","assistant"} and m.get("content")]
        if not clean:
            return
        with self.store.connect() as db:
            # Reserve the write lock before reading sequence counters across UI/workers.
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM research_chats WHERE id=?",(chat_id,)).fetchone()
            if row is not None:
                self._ensure_index(db,row)
            else:
                empty=b"[]"
                db.execute("INSERT INTO research_chats VALUES(?,?,?,?,?,'never',0,0,?,'indexed',?,?)",
                    (chat_id," ".join(clean[0]["content"].split())[:90],"",timestamp,timestamp,project_id,hashlib.sha256(empty).hexdigest(),empty))
            seq = db.execute("SELECT COALESCE(MAX(sequence),0) FROM research_chat_messages WHERE chat_id=?",(chat_id,)).fetchone()[0]
            identities=[]
            for message in clean:
                identifier=message.get("message_id","")
                old=db.execute("SELECT * FROM research_chat_messages WHERE id=? AND chat_id=?",(identifier,chat_id)).fetchone() if identifier else None
                content=str(message["content"])
                if len(content.encode('utf-8'))>MAX_CHAT_BYTES:
                    raise ValueError("A message exceeds the 8 MiB history limit.")
                if old is not None:
                    if old["content"]!=content or old["role"]!=message["role"]:
                        db.execute("UPDATE research_chat_messages SET content=?,role=?,updated=?,revision=revision+1 WHERE id=?",(content,message["role"],timestamp,identifier))
                    identities.append((message,identifier,old["sequence"]))
                else:
                    seq+=1; identifier=uuid.uuid4().hex
                    db.execute("INSERT INTO research_chat_messages(id,chat_id,sequence,role,content,created,updated,attachments) VALUES(?,?,?,?,?,?,?,?)",
                        (identifier,chat_id,seq,message["role"],content,timestamp,timestamp,json.dumps(message.get("attachments",[])[:30])))
                    identities.append((message,identifier,seq))
            empty=b"[]"; checksum=hashlib.sha256(empty).hexdigest()
            db.execute("UPDATE research_chats SET preview=?,last_used=?,project_id=?,codec='indexed',checksum=?,transcript=?,archived=0 WHERE id=?",
                (" ".join(clean[-1]["content"].split())[:200],timestamp,project_id,checksum,empty,chat_id))
            db.execute("INSERT INTO research_chat_index_state VALUES(?,?,1,?) ON CONFLICT(chat_id) DO UPDATE SET checksum=excluded.checksum,version=version+1",(chat_id,checksum,timestamp))
        # Only update caller identities after the transaction commits.
        for message,identifier,sequence in identities:
            message.update(message_id=identifier,chat_id=chat_id,sequence=sequence)

    def _indexed_chat(self, db, chat_id):
        row=db.execute("SELECT * FROM research_chats WHERE id=?",(chat_id,)).fetchone()
        if row is not None:
            self._ensure_index(db,row)
        return row

    def fetch_message(self, chat_id, message_id):
        with self.store.connect() as db:
            self._indexed_chat(db,chat_id)
            row=db.execute("SELECT id AS message_id,* FROM research_chat_messages WHERE chat_id=? AND id=?",(chat_id,message_id)).fetchone()
            return dict(row) if row else None

    def fetch_range(self, chat_id, start=0, end=None, *, limit=100):
        with self.store.connect() as db:
            self._indexed_chat(db,chat_id)
            return self._messages(db,chat_id,lower=start,upper=end,limit=limit)

    def fetch_window(self, chat_id, message_id, *, radius=2):
        message=self.fetch_message(chat_id,message_id)
        if not message:
            return []
        radius=max(0,min(10,int(radius))); seq=message["sequence"]
        return self.fetch_range(chat_id,seq-radius,seq+radius,limit=2*radius+1)

    def search_messages(self, chat_id, query="", *, limit=12, mode="auto", role="", before_sequence=None):
        started=time.perf_counter(); limit=max(1,min(100,int(limit)))
        terms=history_query_terms(query)
        if mode=="auto":
            mode=history_query_mode(query)
        if mode in {'decisions','corrections'}:
            terms=list(dict.fromkeys([*terms,*({'decisions':['use','choose','decided','prefer'],'corrections':['actually','change','instead','correction']}[mode])]))
        with self.store.connect() as db:
            if self._indexed_chat(db,chat_id) is None:
                return []
            filters="m.chat_id=?"; args=[chat_id]
            if role in {"user","assistant"}:
                filters+=" AND m.role=?"; args.append(role)
            if before_sequence is not None:
                filters+=" AND m.sequence<?"; args.append(int(before_sequence))
            if re.search(r'\b(?:yesterday|today)\b',str(query),re.I):
                day=datetime.now().astimezone().replace(hour=0,minute=0,second=0,microsecond=0)
                if re.search(r'\byesterday\b',str(query),re.I): day-=timedelta(days=1)
                filters+=' AND m.created>=? AND m.created<?';args.extend([day.timestamp(),(day+timedelta(days=1)).timestamp()])
                if not terms: mode='timeline'
            if terms and mode not in {"first_message","latest_message"}:
                expression=" OR ".join('"'+term.replace('"','""')+'"' for term in terms[:20])
                order="bm25(research_message_fts),m.sequence"
                if mode=="original": order="m.sequence"
                elif mode=="latest": order="m.sequence DESC"
                rows=[dict(r) for r in db.execute(
                    "SELECT m.id AS message_id,m.* FROM research_message_fts JOIN research_chat_messages m ON m.rowid=research_message_fts.rowid WHERE research_message_fts MATCH ? AND "+filters+" ORDER BY "+order+" LIMIT ?",[expression,*args,limit])]
                if mode=="timeline":
                    early=[dict(r) for r in db.execute("SELECT m.id AS message_id,m.* FROM research_message_fts JOIN research_chat_messages m ON m.rowid=research_message_fts.rowid WHERE research_message_fts MATCH ? AND "+filters+" ORDER BY m.sequence LIMIT ?",[expression,*args,max(1,limit//3)])]
                    late=[dict(r) for r in db.execute("SELECT m.id AS message_id,m.* FROM research_message_fts JOIN research_chat_messages m ON m.rowid=research_message_fts.rowid WHERE research_message_fts MATCH ? AND "+filters+" ORDER BY m.sequence DESC LIMIT ?",[expression,*args,max(1,limit//3)])]
                    rows=list({r["message_id"]:r for r in [*early,*late,*rows]}.values())[:limit]
                    rows.sort(key=lambda r:r["sequence"])
            elif mode=='timeline':
                rows=[]
                count=db.execute('SELECT COUNT(*) FROM research_chat_messages m WHERE '+filters,args).fetchone()[0]
                for offset in (0,max(0,count//2-limit//6),max(0,count-limit//3)):
                    rows.extend(dict(r) for r in db.execute('SELECT m.id AS message_id,m.* FROM research_chat_messages m WHERE '+filters+' ORDER BY sequence LIMIT ? OFFSET ?',[*args,max(1,limit//3),offset]))
                rows=sorted({r['message_id']:r for r in rows}.values(),key=lambda r:r['sequence'])
            elif mode!="search":
                desc=mode in {"latest","latest_message"}
                rows=[dict(r) for r in db.execute("SELECT m.id AS message_id,m.* FROM research_chat_messages m WHERE "+filters+" ORDER BY m.sequence "+("DESC" if desc else "ASC")+" LIMIT ?",[*args,limit])]
            else:
                rows=[]
        self.last_search_ms=(time.perf_counter()-started)*1000
        return rows

    def edit_message(self, chat_id, message_id, content):
        if not str(content).strip(): raise ValueError("Message cannot be empty.")
        with self.store.connect() as db:
            if not self._indexed_chat(db,chat_id): raise KeyError(chat_id)
            changed=db.execute("UPDATE research_chat_messages SET content=?,revision=revision+1,updated=? WHERE chat_id=? AND id=?",(str(content),time.time(),chat_id,message_id)).rowcount
            self._retire_archive(db,chat_id)
        if changed and self.source_invalidated: self.source_invalidated(chat_id,message_id)
        return bool(changed)

    def delete_message(self, chat_id, message_id):
        with self.store.connect() as db:
            self._indexed_chat(db,chat_id)
            changed=db.execute("DELETE FROM research_chat_messages WHERE chat_id=? AND id=?",(chat_id,message_id)).rowcount
            self._retire_archive(db,chat_id)
        if changed and self.source_invalidated: self.source_invalidated(chat_id,message_id)
        return bool(changed)

    @staticmethod
    def _retire_archive(db,chat_id):
        empty=b"[]"; checksum=hashlib.sha256(empty).hexdigest()
        db.execute("UPDATE research_chats SET codec='indexed',checksum=?,transcript=? WHERE id=?",(checksum,empty,chat_id))
        db.execute("UPDATE research_chat_index_state SET checksum=?,version=version+1 WHERE chat_id=?",(checksum,chat_id))

    def summary(self, chat_id):
        # Source-linked extractive summary. No model inference and no invented facts.
        with self.store.connect() as db:
            if self._indexed_chat(db,chat_id) is None: return {}
            version=db.execute("SELECT version FROM research_chat_index_state WHERE chat_id=?",(chat_id,)).fetchone()[0]
            cached=db.execute("SELECT * FROM research_chat_summaries WHERE chat_id=? AND version=?",(chat_id,version)).fetchone()
            if cached: return {"version":version,"content":cached["content"],"sources":json.loads(cached["sources"])}
            first=self._messages(db,chat_id,limit=2)
            recent=self._messages(db,chat_id,limit=8,descending=True)
            chosen=list({r["message_id"]:r for r in [*first,*recent]}.values())
            from ..redaction import redact_text
            content="\n".join(f"[{r['sequence']} {r['role']}] {redact_text(r['content'])[:180]}" for r in chosen)[:2000]
            sources=[r["message_id"] for r in chosen]
            db.execute("INSERT OR REPLACE INTO research_chat_summaries VALUES(?,?,?,?)",(chat_id,version,json.dumps(sources),content))
            return {"version":version,"content":content,"sources":sources}

    def rebuild_index(self, *, cancel_event=None, progress=None):
        # One transaction: cancellation/exception leaves the previous searchable index intact.
        with self.store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            cursor=db.execute("SELECT * FROM research_chats ORDER BY id")
            count=0
            while batch:=cursor.fetchmany(20):
                for row in batch:
                    if cancel_event is not None and cancel_event.is_set(): raise InterruptedError("Index rebuild cancelled.")
                    self._ensure_index(db,row); count+=1
                    if progress: progress(count)
            db.execute("INSERT INTO research_message_fts(research_message_fts) VALUES('rebuild')")
            db.execute("UPDATE research_chat_index_state SET rebuilt=?",(time.time(),))
            return count

    def diagnostics(self, chat_id=""):
        with self.store.connect() as db:
            count=db.execute("SELECT COUNT(*) FROM research_chat_messages"+(" WHERE chat_id=?" if chat_id else ""),(chat_id,) if chat_id else ()).fetchone()[0]
            rebuilt=db.execute('SELECT MAX(rebuilt) FROM research_chat_index_state').fetchone()[0]
        return {"indexed_messages":count,"retrieval_ms":self.last_search_ms,"last_rebuild":rebuilt,
            "database_bytes":self.store.database.stat().st_size,"semantic_backend":"query expansion; embeddings unavailable","last_error":self.last_error}

    def is_private(self,chat_id):
        with self.store.connect() as db:
            row=db.execute('SELECT retention FROM research_chats WHERE id=?',(chat_id,)).fetchone()
            return bool(row and row[0]=='session')

    def execute(self,capability,args,context):
        from ..kernel import ExecutionResult,TaskStatus,ErrorCode
        chat_id=context.conversation_id
        if not chat_id or args.get('chat_id',chat_id)!=chat_id:
            return ExecutionResult.failure(ErrorCode.PERMISSION_DENIED,'History lookup requires the active conversation identity.')
        if context.cancellation_token: context.cancellation_token.raise_if_cancelled()
        operation=capability.rsplit('.',1)[-1]
        limit=max(1,min(60,int(args.get('limit',12))))
        if operation=='fetch_message':
            row=self.fetch_message(chat_id,args.get('message_id','')); rows=[row] if row else []
        elif operation=='fetch_window': rows=self.fetch_window(chat_id,args.get('message_id',''),radius=args.get('radius',2))
        elif operation=='fetch_range': rows=self.fetch_range(chat_id,args.get('start',0),args.get('end'),limit=limit)
        else:
            query=str(args.get('query',''))[:2000]
            if operation=='find_decisions': query=query or 'use choose decide prefer'
            if operation=='find_corrections': query=query or 'actually change instead correction'
            mode={'timeline':'timeline','find_decisions':'decisions','find_corrections':'corrections'}.get(operation,'auto')
            rows=self.search_messages(chat_id,query,limit=limit,mode=mode)
        return ExecutionResult(TaskStatus.SUCCEEDED,True,output={'chat_id':chat_id,'messages':rows},
            evidence=[f'{len(rows)} retained source messages in the active conversation.'],verification_required=True)

    def verify(self,result,context):
        from ..kernel import VerificationResult,VerificationStatus
        output=result.output or {}; rows=output.get('messages',[])
        valid=output.get('chat_id')==context.conversation_id
        for row in rows:
            source=self.fetch_message(context.conversation_id,row.get('message_id',''))
            valid=valid and bool(source and source['content']==row['content'] and source['revision']==row['revision'])
        return VerificationResult(VerificationStatus.VERIFIED if valid else VerificationStatus.FAILED,
            ('Re-read source messages under the active chat identity.',))

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


def register_history_capabilities(kernel,get_history,enabled=lambda:True):
    from ..kernel import CapabilityDescriptor,ExecutionResult,ErrorCode
    for operation in ('search','fetch_message','fetch_window','fetch_range','timeline','find_decisions','find_corrections'):
        capability='chat.history.'+operation
        def execute(args,context,cap=capability):
            if not enabled(): return ExecutionResult.failure(ErrorCode.PERMISSION_DENIED,'Current-chat memory is disabled.')
            return get_history().execute(cap,args,context)
        kernel.registry.register(CapabilityDescriptor(capability,'Current-chat '+operation.replace('_',' '),category='memory',inline=True,
            supports_verification=True,supports_cancellation=True,timeout=10),execute,
            verifier=lambda result,expected,ctx:get_history().verify(result,ctx))
