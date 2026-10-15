"""Scoped findings, incident receipts and existing verified-action containment."""
from __future__ import annotations

import hashlib
import json
import os
import stat
import subprocess
import time
import uuid
from itertools import islice
from dataclasses import asdict
from pathlib import Path

from ..action_runtime.contracts import ActionBinding, ActionMethod, Observation
from ..kernel import (CapabilityDescriptor, ErrorCode, EventType, ExecutionResult, KernelEvent,
                      ResourceClaim, TaskStatus, VerificationResult, VerificationStatus)
from ..unified_intelligence import PermissionState, RiskClass
from .collectors import ProcessHandle, LockedFile, file_hash, processes, powershell_metadata
from .contracts import IncidentState, SecurityFinding


class SecurityService:
    def __init__(self, kernel, actions, ambient, vault, directory, *, mesh=None):
        self.kernel,self.actions,self.ambient,self.vault = kernel,actions,ambient,vault
        self.store = ambient.store
        self.directory = Path(directory).resolve()
        self.quarantine = self.directory / "quarantine"
        self.quarantine.mkdir(parents=True,exist_ok=True)
        self.mesh = mesh
        self.enabled = False
        self.sources,self.roots,self.pids = (),(),()
        self.errors = {}
        self.last_scan = 0
        self._process_handles = {}
        with self.store.lock,self.store.db:
            self.store.db.executescript("""
              CREATE TABLE IF NOT EXISTS security_findings(id TEXT PRIMARY KEY,fingerprint TEXT UNIQUE,data TEXT);
              CREATE TABLE IF NOT EXISTS security_incidents(id TEXT PRIMARY KEY,ref TEXT UNIQUE,state TEXT,data TEXT);
              CREATE TABLE IF NOT EXISTS security_rules(ref TEXT PRIMARY KEY,reason TEXT,time REAL);
              CREATE TABLE IF NOT EXISTS security_baseline(ref TEXT PRIMARY KEY,value TEXT);
              CREATE TABLE IF NOT EXISTS security_indicators(hash TEXT PRIMARY KEY,origin TEXT,description TEXT);
              CREATE TABLE IF NOT EXISTS security_quarantine(id TEXT PRIMARY KEY,data TEXT);
            """)
        self._register()

    def _register(self):
        self.kernel.registry.register(CapabilityDescriptor("security.scan","Collect selected defensive metadata",
            category="security",required_permissions=("security.read",),supports_verification=True,
            supports_cancellation=True,timeout=15,supported_resources=(ResourceClaim("IO"),)),self.scan,
            verifier=lambda result,expected,context: VerificationResult(VerificationStatus.VERIFIED if result.success and result.output.get("collected_at",0)>time.time()-20 else VerificationStatus.INCONCLUSIVE,
                ("Scoped collection receipt; this does not establish the machine is safe.",)))
        for operation,handler in (("process.terminate",self.terminate),("file.quarantine",self.quarantine_file),("file.restore",self.restore_file)):
            cap = "security." + operation
            self.kernel.registry.register(CapabilityDescriptor(cap,operation,category="security",
                required_permissions=("security.contain",),risk_level=RiskClass.HIGH,
                supports_verification=True,supports_cancellation=True,timeout=10,
                supported_resources=(ResourceClaim("DISK"),) if "file" in operation else ()),handler,
                verifier=self._verify_result,on_completed=lambda result,context,operation=operation:self._action_completed(operation,result,context))
            self.actions.register(cap,ActionBinding(ActionMethod.FILESYSTEM if "file" in operation else ActionMethod.OPERATING_SYSTEM,
                desired=lambda inputs,expected,operation=operation: {**inputs,"operation":operation},
                observe=self._observe,verify=self._verify_observation,idempotent=False))

    def enable(self, *, sources=("processes",), directories=(), process_ids=(), user_confirmed=False):
        if not user_confirmed:
            raise PermissionError("Security monitoring requires explicit consent and selected sources.")
        if not sources or not set(sources).issubset({"processes","files","network","startup","logs"}):
            raise ValueError("Select supported local metadata sources.")
        roots = tuple(Path(p).resolve() for p in directories)
        if len(roots)>8 or any(str(p).startswith("\\\\") or not p.is_dir() or p == Path(p.anchor) or p == self.directory or self.directory.is_relative_to(p) for p in roots):
            raise ValueError("Select at most eight bounded directories, excluding disk roots and security storage.")
        if "files" in sources and not roots:
            raise ValueError("File monitoring requires explicit directory scopes.")
        self.sources,self.roots,self.pids = tuple(sources),roots,tuple(process_ids)
        self.kernel.permissions.controller.set_state("security.read",PermissionState.GRANTED)
        self.enabled = True
        self.errors = {}

    def disable(self):
        self.enabled = False
        self.kernel.permissions.controller.set_state("security.read",PermissionState.DENIED)
        for watch in tuple(self.ambient._watches.values()):
            if watch.action == "security.scan":
                self.ambient.update(watch.trigger_id,enabled=False)

    def authorize_containment(self, *, user_confirmed=False):
        if not user_confirmed:
            raise PermissionError("Containment permission requires explicit user authorization.")
        self.kernel.permissions.controller.set_state("security.contain",PermissionState.GRANTED)

    def monitor_every(self, seconds=60, *, user_confirmed=False):
        if not self.enabled or not user_confirmed or seconds < 60:
            raise PermissionError("An explicitly enabled monitor with an interval of at least 60 seconds is required.")
        from ..ambient.contracts import Trigger,Autonomy
        return self.ambient.create(Trigger("Selected security metadata","security.schedule",action="security.scan",
            level=Autonomy.READ,enabled=True,schedule_at=time.time(),interval_seconds=seconds,cooldown_seconds=seconds-1),user_confirmed=True)

    def indicator(self, digest, origin, description, *, user_confirmed=False):
        if not user_confirmed or len(digest)!=64 or any(c not in "0123456789abcdef" for c in digest) or not origin.strip():
            raise ValueError("An explicitly trusted SHA-256 indicator with source provenance is required.")
        with self.store.lock,self.store.db:
            if self.store.db.execute("SELECT count(*) FROM security_indicators").fetchone()[0]>=512:
                raise ValueError("Trusted indicator capacity reached.")
            self.store.db.execute("INSERT OR REPLACE INTO security_indicators VALUES(?,?,?)",(digest,origin[:512],description[:512]))

    def ignore(self, finding_id, reason, *, user_confirmed=False):
        if not user_confirmed or not reason.strip():
            raise PermissionError("Suppressing a finding requires an explicit reason.")
        with self.store.lock,self.store.db:
            row = self.store.db.execute("SELECT fingerprint,data FROM security_findings WHERE id=?",(finding_id,)).fetchone()
            if not row:
                raise KeyError(finding_id)
            self.store.db.execute("INSERT OR REPLACE INTO security_rules VALUES(?,?,?)",(row[0],reason[:512],time.time()))
            data = json.loads(row[1]); data["status"]="FALSE_POSITIVE"
            self.store.db.execute("UPDATE security_findings SET data=? WHERE id=?",(json.dumps(data),finding_id))
            self.set_incident_state(row[0],IncidentState.FALSE_POSITIVE)

    def set_incident_state(self, ref, state):
        state = IncidentState(state)
        with self.store.lock,self.store.db:
            self.store.db.execute("UPDATE security_incidents SET state=? WHERE ref=?",(state.value,ref))

    def _record(self, finding):
        fingerprint = hashlib.sha256((finding.category+":"+finding.object_ref+":"+finding.indicator_origin).encode()).hexdigest()
        with self.store.lock,self.store.db:
            if self.store.db.execute("SELECT 1 FROM security_rules WHERE ref=?",(fingerprint,)).fetchone():
                return False
            if self.store.db.execute("SELECT count(*) FROM security_findings").fetchone()[0]>=2000:
                self.errors["findings"]="capacity_limit"
                return False
            inserted = self.store.db.execute("INSERT OR IGNORE INTO security_findings VALUES(?,?,?)",
                (finding.finding_id,fingerprint,json.dumps(asdict(finding)))).rowcount
            if not inserted:
                return False
            incident = {"node_id":finding.node_id,"severity":finding.severity,"finding_ids":[finding.finding_id],
                        "timeline":[{"time":finding.timestamp,"finding":finding.finding_id}],"actions":[],"resolution":""}
            self.store.db.execute("INSERT OR IGNORE INTO security_incidents VALUES(?,?,?,?)",
                (uuid.uuid4().hex,fingerprint,IncidentState.OPEN.value,json.dumps(incident)))
        self.kernel.events.publish(KernelEvent(EventType.SECURITY_FINDING,source="security",payload={"finding_id":finding.finding_id,
            "category":finding.category,"severity":finding.severity},severity=finding.severity.lower()))
        return True

    def _baseline(self, ref, value):
        encoded = json.dumps(value,sort_keys=True)
        with self.store.lock,self.store.db:
            old = self.store.db.execute("SELECT value FROM security_baseline WHERE ref=?",(ref,)).fetchone()
            self.store.db.execute("INSERT OR REPLACE INTO security_baseline VALUES(?,?)",(ref,encoded))
            self.store.db.execute("DELETE FROM security_baseline WHERE rowid IN (SELECT rowid FROM security_baseline ORDER BY rowid DESC LIMIT -1 OFFSET 5000)")
        return old is not None and old[0] != encoded

    def scan(self, inputs, context):
        if not self.enabled:
            return ExecutionResult.failure(ErrorCode.CAPABILITY_UNAVAILABLE,"Security monitoring is off.")
        self.errors = {}
        counts = {}
        for source in self.sources:
            context.cancellation_token.raise_if_cancelled()
            try:
                if source == "processes":
                    data = processes(self.pids)
                    counts[source] = len(data["records"])
                    counts["inaccessible_processes"] = data["inaccessible"]
                    for value in data["records"]:
                        self._baseline("process:"+value["executable"],{"executable":value["executable"]})
                        # Hash matching is restricted to explicitly selected PIDs
                        # and an explicitly configured indicator set.
                        if self.pids:
                            with self.store.lock:
                                has_indicators=self.store.db.execute("SELECT 1 FROM security_indicators LIMIT 1").fetchone()
                            if has_indicators:
                                digest=file_hash(value["executable"])
                                with self.store.lock:
                                    indicator=self.store.db.execute("SELECT origin FROM security_indicators WHERE hash=?",(digest,)).fetchone()
                                if indicator:
                                    self._record(SecurityFinding("KNOWN_HASH","HIGH","A selected process executable matches an explicitly trusted indicator.",
                                        ("sha256:"+digest,"start_identity:"+str(value["start_time"])),"process:"+str(value["pid"])+":"+str(value["start_time"]),
                                        process_id=value["pid"],file_path=value["executable"],indicator_origin=indicator[0]))
                    # Process names/new executables alone do not establish a threat.
                elif source == "files":
                    count = 0
                    for root in self.roots:
                        for path in islice(root.iterdir(),64):
                            context.cancellation_token.raise_if_cancelled()
                            if count >= 64:
                                break
                            if not path.is_file() or path.is_symlink() or (os.name == "nt" and path.stat().st_file_attributes & 0x400):
                                continue
                            count += 1
                            digest = file_hash(path)
                            with self.store.lock:
                                indicator = self.store.db.execute("SELECT origin,description FROM security_indicators WHERE hash=?",(digest,)).fetchone()
                            if indicator:
                                self._record(SecurityFinding("KNOWN_HASH","HIGH","Selected file matches an explicitly trusted indicator.",
                                    ("sha256:"+digest,"indicator:"+indicator[0]),digest,file_path=str(path),indicator_origin=indicator[0]))
                            elif self._baseline("file:"+str(path),digest):
                                self._record(SecurityFinding("FILE_CHANGE","LOW","A selected file changed since the previous observation.",
                                    ("sha256:"+digest,),str(path)+":"+digest,file_path=str(path)))
                    counts[source] = count
                else:
                    records = powershell_metadata(source)
                    counts[source] = len(records)
                    for record in records:
                        identity = json.dumps(record,sort_keys=True)
                        ref = source+":"+hashlib.sha256(identity.encode()).hexdigest()
                        prior = self.store.cursor("security.seen."+source) or []
                        if prior and ref not in prior and source in {"startup","network"}:
                            self._record(SecurityFinding("UNEXPECTED_STARTUP" if source == "startup" else "NETWORK_LISTENER","LOW",
                                "New entry in an authorized metadata source; review context.",(identity[:1024],),ref))
                    self.store.cursor("security.seen."+source,[source+":"+hashlib.sha256(json.dumps(r,sort_keys=True).encode()).hexdigest() for r in records])
            except (ValueError,OSError,RuntimeError,subprocess.TimeoutExpired) as exc:
                self.errors[source] = type(exc).__name__
        self.last_scan = time.time()
        success = bool(counts) and not self.errors
        return ExecutionResult(TaskStatus.SUCCEEDED if success else TaskStatus.FAILED,success,
            {"collected_at":self.last_scan,"sources":counts,"errors":dict(self.errors),"monitoring_complete":success},
            evidence=["Authorized local metadata sources collected; unsupported sources remain visible."])

    def select_process(self, pid):
        with ProcessHandle(pid) as process:
            return dict(process.identity)

    def terminate(self, inputs, context):
        expected = {k:inputs[k] for k in ("pid","executable","start_time")}
        process = ProcessHandle(inputs["pid"],terminate=True)
        windows=Path(os.environ.get("WINDIR","C:/Windows")).resolve()
        if Path(process.identity["executable"]).is_relative_to(windows):
            process.close()
            return ExecutionResult.failure(ErrorCode.PERMISSION_DENIED,"Core Windows executables are excluded from this containment adapter.")
        if process.identity != expected:
            process.close()
            return ExecutionResult.failure(ErrorCode.INVALID_INPUT,"Process identity changed; select it again before approving termination.")
        self._process_handles[context.task_id] = process
        if not process.terminate():
            return ExecutionResult.failure(ErrorCode.VERIFICATION_FAILED,"Selected process exit was not observed.")
        return ExecutionResult(TaskStatus.SUCCEEDED,True,{"identity":expected,"stopped":True},evidence=["Retained OS process handle signalled exit."])

    def _selected_file(self, raw):
        path = Path(raw)
        if path.is_symlink() or any(p.is_symlink() for p in path.parents):
            raise ValueError("Quarantine/restore refuses symlink paths.")
        resolved = path.resolve()
        if not any(resolved.is_relative_to(root) and resolved != root for root in self.roots):
            raise PermissionError("The file is outside explicitly authorized directory scopes.")
        if os.name == "nt" and any(p.exists() and p.stat().st_file_attributes & 0x400 for p in (path,*path.parents)):
            raise ValueError("Quarantine/restore refuses Windows reparse points.")
        if resolved.exists() and resolved.stat().st_nlink>1:
            raise ValueError("Quarantine/restore refuses files with multiple hard links.")
        return resolved

    def quarantine_file(self, inputs, context):
        if not self.vault.available:
            return ExecutionResult.failure(ErrorCode.CAPABILITY_UNAVAILABLE,"OS-protected quarantine storage is unavailable.")
        entries=list(islice(self.quarantine.iterdir(),257))
        if len(entries)>=256 or sum(p.stat().st_size for p in entries if p.is_file())>=128*1024*1024:
            return ExecutionResult.failure(ErrorCode.CAPABILITY_UNAVAILABLE,"Quarantine capacity reached; explicitly archive evidence before another transfer.")
        original = self._selected_file(inputs["path"])
        digest = file_hash(original)
        if digest != inputs["sha256"]:
            return ExecutionResult.failure(ErrorCode.INVALID_INPUT,"File changed after approval.")
        with LockedFile(original) as locked:
            raw=locked.read()
            if hashlib.sha256(raw).hexdigest()!=digest:
                return ExecutionResult.failure(ErrorCode.INVALID_INPUT,"File changed while preserving evidence.")
            return self._preserve_locked_file(original,digest,raw,locked,inputs,context)

    def _preserve_locked_file(self,original,digest,raw,locked,inputs,context):
        identifier = uuid.uuid4().hex
        target = self.quarantine / (identifier+".dpapi")
        protected = self.vault.protect(raw)
        with target.open("xb") as stream:
            stream.write(protected); stream.flush(); os.fsync(stream.fileno())
        # Persist intent before removal: a crash leaves a reviewable protected copy.
        record = {"id":identifier,"original_path":str(original),"sha256":digest,"reason":str(inputs.get("reason","User-selected containment"))[:512],
                  "time":time.time(),"state":"COPY_PRESERVED","evidence":["sha256:"+digest],"task_id":context.task_id}
        with self.store.lock,self.store.db:
            self.store.db.execute("INSERT INTO security_quarantine VALUES(?,?)",(identifier,json.dumps(record)))
        context.cancellation_token.raise_if_cancelled()
        locked.delete_on_close()
        locked.close()
        record["state"]="QUARANTINED"
        with self.store.lock,self.store.db:
            self.store.db.execute("UPDATE security_quarantine SET data=? WHERE id=?",(json.dumps(record),identifier))
        return ExecutionResult(TaskStatus.SUCCEEDED,True,{"quarantine_id":identifier,"sha256":digest},evidence=["Protected evidence copy preserved and original removed from selected location."])

    def _action_completed(self,operation,result,context):
        handle=self._process_handles.pop(context.task_id,None)
        if handle:handle.close()
        if not result.success or not result.verification or result.verification.status!=VerificationStatus.VERIFIED:
            return
        inputs=context.metadata.get("task_inputs",{}) or result.output.get("identity",{})
        ref=inputs.get("sha256") or result.output.get("sha256") or "process:"+str(inputs.get("pid",""))
        fingerprint=hashlib.sha256(("containment:"+str(ref)).encode()).hexdigest()
        state=IncidentState.RESOLVED.value if operation=="file.restore" else IncidentState.CONTAINED.value
        with self.store.lock,self.store.db:
            row=self.store.db.execute("SELECT data FROM security_incidents WHERE ref=?",(fingerprint,)).fetchone()
            data=json.loads(row[0]) if row else {"node_id":"local","severity":"INFO","finding_ids":[],"timeline":[],"actions":[],"resolution":"User-selected verified containment"}
            action={"task_id":context.task_id,"operation":operation,"verified":True,"time":time.time()}
            data["actions"]=(data["actions"]+[action])[-100:]
            data["timeline"]=(data["timeline"]+[{"time":action["time"],"action":context.task_id}])[-100:]
            self.store.db.execute("INSERT INTO security_incidents VALUES(?,?,?,?) ON CONFLICT(ref) DO UPDATE SET state=excluded.state,data=excluded.data",
                (uuid.uuid4().hex,fingerprint,state,json.dumps(data)))

    def restore_file(self, inputs, context):
        identifier = inputs["quarantine_id"]
        record = self._quarantine_record(identifier)
        original = self._selected_file(record["original_path"])
        target = self.quarantine / (record["id"]+".dpapi")
        raw = self.vault.unprotect(target.read_bytes())
        if hashlib.sha256(raw).hexdigest() != record["sha256"]:
            return ExecutionResult.failure(ErrorCode.VERIFICATION_FAILED,"Quarantine evidence hash changed; restoration refused.")
        context.cancellation_token.raise_if_cancelled()
        try:
            with LockedFile(original,create=True) as output:
                output.write(raw,context.cancellation_token)
        except FileExistsError:
            return ExecutionResult.failure(ErrorCode.INVALID_INPUT,"Restore would overwrite an existing file.")
        record["state"]="RESTORED"
        record["restored_at"]=time.time()
        with self.store.lock,self.store.db:
            self.store.db.execute("UPDATE security_quarantine SET data=? WHERE id=?",(json.dumps(record),record["id"]))
        return ExecutionResult(TaskStatus.SUCCEEDED,True,{"quarantine_id":record["id"],"sha256":record["sha256"]},
            evidence=["Restored bytes independently hashed at the original path."])

    def _quarantine_record(self, identifier):
        if not isinstance(identifier,str) or len(identifier)!=32 or any(c not in "0123456789abcdef" for c in identifier):
            raise ValueError("Invalid quarantine reference.")
        with self.store.lock:
            row = self.store.db.execute("SELECT data FROM security_quarantine WHERE id=?",(identifier,)).fetchone()
        if not row:
            raise KeyError(identifier)
        return json.loads(row[0])

    def _observe(self, spec, context, result=None, before=None):
        desired = spec.desired_state
        operation = desired["operation"]
        if operation == "process.terminate":
            handle = self._process_handles.get(context.task_id)
            if handle:
                state = {"stopped":handle.stopped(),"identity":dict(handle.identity)}
            else:
                state = {"stopped":False,"identity":self.select_process(desired["pid"])}
        else:
            identifier = result.output.get("quarantine_id") if result and isinstance(result.output,dict) else desired.get("quarantine_id")
            if identifier:
                record = self._quarantine_record(identifier)
                path = self._selected_file(record["original_path"])
                protected = self.quarantine / (identifier+".dpapi")
                protected_hash = hashlib.sha256(self.vault.unprotect(protected.read_bytes())).hexdigest()
                state = {"quarantine_id":identifier,"state":record["state"],"protected_hash":protected_hash,
                         "original_exists":path.exists(),"original_hash":file_hash(path) if path.exists() else "","expected_hash":record["sha256"]}
            else:
                path = self._selected_file(desired["path"])
                state = {"original_exists":path.exists(),"original_hash":file_hash(path) if path.exists() else ""}
        return Observation(spec.action_id,"authorized.local_os",state,evidence=("Independent OS/file observation.",))

    def _verify_observation(self, spec, observation, before):
        state = observation.state
        operation = spec.desired_state["operation"]
        if operation == "process.terminate":
            valid = state.get("stopped") and state.get("identity") == {k:spec.desired_state[k] for k in ("pid","executable","start_time")}
        elif operation == "file.quarantine":
            valid = state.get("state") == "QUARANTINED" and not state.get("original_exists") and state.get("protected_hash") == spec.desired_state["sha256"]
        else:
            valid = state.get("state") == "RESTORED" and state.get("original_exists") and state.get("original_hash") == state.get("expected_hash") == state.get("protected_hash")
        return VerificationResult(VerificationStatus.VERIFIED if valid else VerificationStatus.FAILED,observation.evidence,
            "Selected action observed." if valid else "Desired containment state was not observed.")

    @staticmethod
    def _verify_result(result,expected,context):
        return VerificationResult(VerificationStatus.INCONCLUSIVE,message="Containment requires the existing VerifiedActionRuntime observation binding.")

    def snapshot(self):
        with self.store.lock:
            findings=[json.loads(r[0]) for r in self.store.db.execute("SELECT data FROM security_findings ORDER BY rowid DESC LIMIT 200")]
            incidents=[{"id":r[0],"state":r[1],**json.loads(r[2])} for r in self.store.db.execute("SELECT id,state,data FROM security_incidents ORDER BY rowid DESC LIMIT 100")]
            quarantine=[json.loads(r[0]) for r in self.store.db.execute("SELECT data FROM security_quarantine ORDER BY rowid DESC LIMIT 100")]
            rules=[{"reference":r[0],"reason":r[1]} for r in self.store.db.execute("SELECT ref,reason FROM security_rules LIMIT 200")]
        high=any(f["severity"] in {"HIGH","CRITICAL"} and f["status"]!="FALSE_POSITIVE" for f in findings)
        status = "Monitoring off" if not self.enabled else "Selected collector failed" if self.errors else "Monitoring configured; first scan pending" if not self.last_scan else "Review high-severity findings" if high else "No high-severity finding in monitored sources"
        return {"enabled":self.enabled,"status":status,"sources":self.sources,"last_scan":self.last_scan,"errors":self.errors,
                "findings":findings,"incidents":incidents,"quarantine":quarantine,"rules":rules,
                "network_isolation":"Unavailable: no authorized OS firewall adapter is installed."}

    def close(self):
        self.disable()
        for handle in self._process_handles.values():
            handle.close()
        self._process_handles.clear()
