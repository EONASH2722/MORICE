"""Rule/schedule driver; actual work belongs to the existing AgentCoordinator.

The one timing thread never sleeps in the worker pool, performs model inference,
or performs provider I/O. EventBus callbacks only enqueue bounded envelopes.
"""
from __future__ import annotations

import heapq
import operator
import re
import threading
import time
from collections import deque
from dataclasses import asdict, replace

from ..kernel import (CapabilityDescriptor, CancellationToken, ExecutionContext, ExecutionResult,
                      EventType, KernelEvent, Priority, TaskGraph, TaskNode, TaskStatus,
                      VerificationPolicy, VerificationResult, VerificationStatus)
from ..unified_intelligence import RiskClass
from .contracts import AmbientBudget, AmbientEvent, Autonomy, Trigger, Trust
from .store import AmbientStore


SEVERITY = {"INFO": 0, "LOW": 1, "MEDIUM": 2, "HIGH": 3, "CRITICAL": 4}
OPERATORS = {"eq": operator.eq, "ne": operator.ne, "lt": operator.lt, "le": operator.le, "gt": operator.gt, "ge": operator.ge}


class AmbientService:
    def __init__(self, kernel, agents, automation, notifications, database, *, budget=None):
        self.kernel, self.agents = kernel, agents
        self.automation, self.notifications = automation, notifications
        self.budget = budget or AmbientBudget()
        self.store = AmbientStore(database, self.budget.max_history)
        self._watches = {}
        for watch in self.store.watches():
            if watch.expires_at is not None and watch.expires_at<=time.time():
                self.store.delete(watch.trigger_id)
            else:self._watches[watch.trigger_id]=watch
        self._queue, self._queued_keys, self._inflight, self._polls = [], set(), {}, {}
        self._lock = threading.RLock()
        self._queue_lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = None
        self._sequence = 0
        self._action_times, self._network_times = deque(), deque()
        self.metrics = {"received":0,"dispatched":0,"dropped":0,"duplicates":0,"matched":0,"model_calls":0,"tick_errors":0}
        self.health = "DISABLED"
        self.last_error = ""
        self._closed = False
        self.connectors = None
        self.security = None
        self._subscription = kernel.events.subscribe(self._on_kernel_event)
        automation.attach_ambient(self)
        self._register_notifications()

    @property
    def enabled(self):
        return self._thread is not None and self._thread.is_alive() and not self._stop.is_set()

    def start(self, *, user_confirmed=False):
        if not user_confirmed:
            raise PermissionError("Ambient monitoring requires explicit enablement.")
        with self._lock:
            if self._closed:
                raise RuntimeError("Ambient service is closed.")
            if self.enabled:
                return
            self._stop.clear()
            self.health = "RUNNING"
            self._thread = threading.Thread(target=self._loop, name="morice-ambient-timing", daemon=True)
            self._thread.start()

    def _loop(self):
        while not self._stop.wait(.1):
            try:
                self.tick()
            except Exception as exc:
                self.metrics["tick_errors"] += 1
                self.health = "DEGRADED"
                self.last_error = type(exc).__name__

    def stop(self):
        self._stop.set()
        thread = self._thread
        if thread and thread is not threading.current_thread():
            thread.join(2)
        self._thread = None
        with self._lock:
            for job in self._inflight.values():
                job["token"].cancel("Ambient monitoring disabled.")
                self.agents.cancel(job["graph"].graph_id)
            with self._queue_lock:
                self._queue.clear()
                self._queued_keys.clear()
        self.health = "DISABLED"

    def close(self):
        if self._closed:return
        self.stop()
        self.kernel.events.unsubscribe(self._subscription)
        if self.connectors:self.connectors.close()
        deadline = time.monotonic() + 10
        for job in tuple(self._inflight.values()):
            try:
                job["future"].result(timeout=max(.01,deadline-time.monotonic()))
            except Exception:
                pass
        if self.security:
            self.security.close()
        self.store.close()
        self._closed = True

    def _register_notifications(self):
        if self.kernel.registry.lookup("notification.publish"):
            return
        def publish(arguments, context):
            note = self.notifications.publish_once(arguments.get("_event_key",context.task_id),arguments.get("title", "MORICE watch"),
                arguments.get("message", "A configured watch matched."), category="ambient",
                metadata={"task_id":context.task_id})
            return ExecutionResult(TaskStatus.SUCCEEDED, True, {"notification_id":note.notification_id}, evidence=["Existing notification manager receipt."])
        def verify(result, expected, context):
            observed = any(n.notification_id == result.output.get("notification_id") for n in self.notifications.history(limit=2000))
            return VerificationResult(VerificationStatus.VERIFIED if observed else VerificationStatus.FAILED,
                ("Notification retrieved from existing manager.",))
        self.kernel.registry.register(CapabilityDescriptor("notification.publish", "Publish an in-app notification",
            inline=True, supports_verification=True, timeout=2), publish, verifier=verify)

    def publish(self, event, *, context=None):
        if not isinstance(event, AmbientEvent):
            raise TypeError("Ambient input requires a validated event envelope.")
        # A copied payload prevents the producer mutating accepted data later.
        event = replace(event, payload=dict(event.payload), trust=Trust(event.trust))
        if context and context.metadata.get("ambient"):
            event=replace(event,depth=context.metadata.get("ambient_depth",0)+1,
                correlation_id=context.metadata.get("ambient_correlation",context.task_id))
        self.kernel.events.publish(KernelEvent(EventType.AMBIENT_INPUT, source="ambient.adapter",
            payload={"event":event}, project_id=event.project_id, severity=event.severity.lower()))
        return True

    def _on_kernel_event(self, kernel_event):
        if self._closed:
            return
        event = None
        if kernel_event.event_type == EventType.AMBIENT_INPUT:
            event = kernel_event.payload.get("event")
        elif kernel_event.event_type in {EventType.BUILD_FINISHED, EventType.RESEARCH_FINISHED, EventType.DEVICE_CHANGED, EventType.SECURITY_FINDING,
                EventType.MEDIA_COMPLETED, EventType.MEDIA_FAILED, EventType.MEDIA_CANCELLED, EventType.MEDIA_OOM}:
            p = kernel_event.payload
            if kernel_event.event_type in {EventType.MEDIA_COMPLETED, EventType.MEDIA_FAILED, EventType.MEDIA_CANCELLED, EventType.MEDIA_OOM}:
                kind = {EventType.MEDIA_COMPLETED:"media.completed",EventType.MEDIA_FAILED:"media.failed",EventType.MEDIA_CANCELLED:"media.cancelled",EventType.MEDIA_OOM:"media.oom"}[kernel_event.event_type]
            elif kernel_event.event_type == EventType.BUILD_FINISHED:
                kind = {"verified":"build.completed","failed":"build.failed","cancelled":"build.cancelled"}.get(p.get("status"),"build.incomplete")
            elif kernel_event.event_type == EventType.RESEARCH_FINISHED:
                kind = "research.completed" if p.get("status", "").startswith("COMPLETED") else "research.cancelled" if p.get("status")=="CANCELLED" else "research.failed"
            elif kernel_event.event_type == EventType.DEVICE_CHANGED:
                kind = "device.battery_low" if p.get("type") == "battery_low" else "device." + p.get("type", "changed")
            else:
                kind = "security.finding"
            node = p.get("node_id", "")
            event = AmbientEvent(kind, kernel_event.source, p.get("generation_id",p.get("session_id",p.get("experiment_id",p.get("finding_id", node)))),
                {k:v for k,v in p.items() if k in {"status","value","type","severity","battery_percent","category"}},
                trust=Trust.TRUSTED_NODE if node else Trust.LOCAL_OS, device_id=node,
                project_id=kernel_event.project_id, dedupe_key=p.get("revision", kernel_event.event_id),
                event_id=kernel_event.event_id, timestamp=kernel_event.timestamp,
                severity=p.get("severity", "INFO"))
        if not isinstance(event, AmbientEvent):
            return
        key = (event.source,event.source_id,event.dedupe_key or event.event_id)
        with self._queue_lock:
            self.metrics["received"] += 1
            if event.depth > 3:
                self.metrics["dropped"] += 1
                return
            if key in self._queued_keys:
                self.metrics["duplicates"] += 1
                return
            # Lower values run first. Security-critical bypasses normal backlog;
            # direct interactive capabilities never enter this queue.
            priority = -10 if event.severity == "CRITICAL" else 0 if event.severity == "HIGH" else 20
            if len(self._queue) >= self.budget.max_pending:
                if priority >= 20:
                    self.metrics["dropped"] += 1
                    return
                worst = max(range(len(self._queue)), key=lambda i:self._queue[i][:2])
                if priority >= self._queue[worst][0]:
                    self.metrics["dropped"] += 1
                    return
                removed = self._queue.pop(worst)
                self._queued_keys.discard(removed[3])
                heapq.heapify(self._queue)
                self.metrics["dropped"] += 1
            self._sequence += 1
            heapq.heappush(self._queue,(priority,self._sequence,event,key))
            self._queued_keys.add(key)

    def create(self, trigger, *, user_confirmed=False):
        if not isinstance(trigger,Trigger):
            raise TypeError("Create a structured trigger.")
        if len(self._watches) >= 200:
            raise ValueError("Watch limit reached.")
        if trigger.enabled and not user_confirmed:
            raise PermissionError("Enabling a watch requires explicit user authorization.")
        self._validate_action(trigger)
        trigger=replace(trigger,created_at=time.time())
        with self._lock:
            self.store.save(trigger)
            self._watches[trigger.trigger_id] = trigger
        return trigger

    def _validate_action(self, watch):
        entry = self.kernel.registry.lookup(watch.action,watch.target_node_id)
        if entry is None:
            raise ValueError("Watch action must be an existing registered capability.")
        if watch.level == Autonomy.NOTIFY and watch.action != "notification.publish":
            raise ValueError("Level 0 can only notify.")
        if watch.level < Autonomy.CONFIRM and entry.descriptor.risk_level in {RiskClass.HIGH,RiskClass.CRITICAL}:
            raise ValueError("Consequential actions require level 3 and an exact user confirmation.")
        if watch.level == Autonomy.READ and not (watch.action.endswith(".read") or watch.action in {"project.inspect","research.verify","research.refresh_source","security.scan","kernel.echo","python.calculate","device.status"}):
            raise ValueError("Level 1 requires a read/analysis capability.")
        if watch.level == Autonomy.LOCAL_REVERSIBLE and entry.descriptor.category == "connector" and not watch.action.endswith(".read"):
            raise ValueError("Reversible-local policy cannot authorize an external write.")
        # Model inference is disabled by the default background budget. A future
        # semantic adapter must use the existing SharedModelAdapter/ModelBudget.
        if watch.action == "agent.reason":
            raise ValueError("Unbounded semantic watches are unavailable; deterministic templates are supported.")
        if any(isinstance(watch.arguments.get(key),str) and "${" in watch.arguments[key] for key in ("source","path","root","cwd")):
            raise ValueError("File scopes must be fixed by the user; event content cannot select disk paths.")
        if watch.level == Autonomy.CONFIRM and any("${" in str(v) for v in watch.arguments.values()):
            raise ValueError("Consequential templates require fixed arguments for an exact reviewable action.")

    def preview_confirmation(self,key):
        import hashlib
        receipt=next((r for r in self.store.receipts(500) if r["key"]==key),None)
        if not receipt or receipt["state"]!="awaiting_exact_confirmation":
            raise ValueError("This action is not awaiting confirmation.")
        watch=self._watches.get(receipt["watch"])
        if not watch or not watch.enabled or watch.paused:
            raise ValueError("The requesting watch is disabled or paused.")
        return TaskNode(watch.action,dict(watch.arguments),task_id=hashlib.sha256(key.encode()).hexdigest()[:32],
            constraints={"node_id":watch.target_node_id},verification_policy=VerificationPolicy(True,watch.expected_outcome))

    def confirm(self,key,approval_token):
        task=self.preview_confirmation(key)
        if not self.store.claim_confirmation(key,task.task_id):
            raise ValueError("This pending action has already been claimed; review its receipt.")
        result=self.kernel.run_task(task,ExecutionContext(approval_token=approval_token))
        self.store.receipt(key,"verified" if result.success else "failed",task.task_id)
        return result

    def update(self, identifier, *, user_confirmed=False, **changes):
        old = self._watches[identifier]
        if any(k in changes for k in {"action","arguments","level","conditions","trust","event_type","source_id","project_id","device_id","target_node_id","expected_outcome"}) and old.enabled:
            if not user_confirmed:
                raise PermissionError("Changing an active watch requires explicit authorization.")
        value = replace(old, **changes)
        if value.enabled and not old.enabled and not user_confirmed:
            raise PermissionError("Enabling a watch requires explicit authorization.")
        self._validate_action(value)
        self.cancel(identifier)
        with self._lock:
            self._watches[identifier] = value
            self.store.save(value)
        return value

    def cancel(self, identifier):
        for job in tuple(self._inflight.values()):
            if job["watch"] == identifier:
                job["token"].cancel("Watch disabled or edited.")
                self.agents.cancel(job["graph"].graph_id)

    def delete(self, identifier):
        self.cancel(identifier)
        with self._lock:
            self._watches.pop(identifier,None)
            self.store.delete(identifier)

    def disconnect_source(self, cid):
        self._polls.pop(cid,None)
        self.store.cursor("ambient.poll."+cid,{"enabled":False})
        for w in tuple(self._watches.values()):
            if w.source_id == cid or w.action.startswith("connector." + cid + "."):
                self.update(w.trigger_id, enabled=False)
        for job in tuple(self._inflight.values()):
            if job.get("source") == cid:
                job["token"].cancel("Connector disconnected.")
                self.agents.cancel(job["graph"].graph_id)

    @staticmethod
    def matches(watch, event, *, now=None):
        now = time.time() if now is None else now
        if not watch.enabled or watch.paused or watch.expires_at is not None and now >= watch.expires_at:
            return False
        if watch.event_type != event.event_type or event.trust.value not in watch.trust:
            return False
        if watch.source_id and watch.source_id != event.source_id or watch.project_id and watch.project_id != event.project_id or watch.device_id and watch.device_id != event.device_id:
            return False
        if SEVERITY[event.severity] < SEVERITY[watch.min_severity]:
            return False
        for key, condition in watch.conditions.items():
            try:
                if key not in event.payload or not OPERATORS[condition["op"]](event.payload[key],condition["value"]):
                    return False
            except (TypeError, ValueError):
                return False
        return True

    def dry_run(self, identifier, event):
        watch = self._watches[identifier]
        return {"matches":self.matches(replace(watch,enabled=True),event),"action":watch.action,
                "requires_confirmation":watch.level == Autonomy.CONFIRM,"executed":False}

    def from_request(self, text, *, project_id="", device_id=""):
        lower = text.lower().strip()
        if 'battery' in lower:
            match=re.search(r'(?:below|under|less than)\s*(\d{1,3}(?:\.\d+)?)\s*(?:%|percent)?',lower)
            threshold=float(match[1]) if match else 15 if 'low' in lower else None
            if threshold is None or not 0<threshold<=100:raise ValueError('Supply a battery threshold above 0 and at most 100 percent.')
            label=f'{threshold:g}%'
            return Trigger('Notify when battery is below '+label,'device.battery_low',
                conditions={'battery_percent':{'op':'lt','value':threshold}},device_id=device_id,
                arguments={'title':'Low battery','message':'A permitted device battery event reports a value below '+label+'.'})
        if "build" in lower and ("finish" in lower or "complete" in lower or "fail" in lower):
            failed = "fail" in lower
            return Trigger("Notify when build " + ("fails" if failed else "completes"), "build.failed" if failed else "build.completed",
                project_id=project_id, arguments={"title":"Build status","message":"The configured build watch matched."})
        if "research" in lower or "experiment" in lower:
            failed = "fail" in lower
            return Trigger("Research progress", "research.failed" if failed else "research.completed",project_id=project_id,
                arguments={"title":"Research status","message":"The configured research watch matched."})
        if "issue" in lower and "assign" in lower:
            return Trigger("Assigned GitHub issue", "github.issue.assigned",arguments={"title":"Assigned issue","message":"An issue was assigned in the configured repository."})
        raise ValueError('Supported watches: build completion/failure, research completion/failure, an explicit battery percentage, assigned issue.')

    def configure_poll(self, cid, *, interval_seconds=60, user_confirmed=False):
        if not user_confirmed or not self.connectors or cid not in self.connectors.providers:
            raise PermissionError("Polling requires an explicitly authorized connector.")
        if not self.budget.poll_min_seconds <= interval_seconds <= 86400:
            raise ValueError("Polling interval exceeds its frequency budget.")
        self._polls[cid] = {"interval":interval_seconds,"next":time.time(),"failures":0}
        self.store.cursor("ambient.poll." + cid,{"interval":interval_seconds,"enabled":True})

    def _submit(self, capability, arguments, *, key="", watch="", source="", project="", target_node_id="local",expected_outcome=None,event=None):
        from ..agent_runtime.models import ModelBudget
        token = CancellationToken()
        node = TaskNode(capability_requirement=capability, inputs=arguments, priority=Priority.BACKGROUND,
            timeout=10, verification_policy=VerificationPolicy(required=True,expected_outcome=expected_outcome),constraints={"node_id":target_node_id})
        graph = TaskGraph([node])
        context = ExecutionContext(project_id=project,cancellation_token=token,active_files=(arguments["source"],) if isinstance(arguments.get("source"),str) else (),
            metadata={"ambient":True,"model_budget":ModelBudget(0,0),"event_receipt":key,
                "ambient_depth":event.depth if event else 0,"ambient_correlation":(event.correlation_id or event.event_id) if event else ""}, resource_budget={"model_calls":0})
        future = self.agents.submit(graph,context,sequential=True)
        self._inflight[graph.graph_id] = {"future":future,"graph":graph,"token":token,"key":key,"watch":watch,"source":source}
        if key:
            self.store.receipt(key,"running",node.task_id)

    def _notify_allowed(self, watch, event, now):
        if watch.notification_policy == "quiet" or watch.notification_policy == "failed_only" and event.severity not in {"HIGH","CRITICAL"} and not event.event_type.endswith("failed"):
            return False
        if watch.quiet_start_hour is not None and watch.quiet_end_hour is not None:
            hour = time.localtime(now).tm_hour
            start,end = watch.quiet_start_hour,watch.quiet_end_hour
            quiet = start <= hour < end if start <= end else hour >= start or hour < end
            if quiet and not (watch.critical_override and event.severity == "CRITICAL"):
                return False
        return True

    def tick(self, *, now=None):
        if self._closed or self._stop.is_set():
            return
        now = time.time() if now is None else now
        started = time.monotonic()
        with self._lock, self.store.transaction():
            for graph_id,job in tuple(self._inflight.items()):
                if not job["future"].done():
                    continue
                try:
                    result = job["future"].result()
                    state = "verified" if result.success else "failed"
                except Exception:
                    state = "failed"
                if job["key"]:
                    self.store.receipt(job["key"],state,job["graph"].tasks[0].task_id)
                if job["source"] in self._polls:
                    p = self._polls[job["source"]]
                    p["failures"] = 0 if state == "verified" else min(6,p["failures"]+1)
                    retry = self.connectors.providers[job["source"]].retry_at
                    p["next"] = max(retry,now + min(3600,p["interval"] * 2 ** p["failures"]))
                if job["source"] and self.connectors:
                    self.connectors.complete_authorization(job["source"])
                self._inflight.pop(graph_id,None)
            for times in (self._action_times,self._network_times):
                while times and times[0] < now - 60:
                    times.popleft()
            for watch in tuple(self._watches.values()):
                if watch.schedule_at is not None and watch.schedule_at <= now and watch.enabled and not watch.paused:
                    due = watch.schedule_at
                    self.publish(AmbientEvent(watch.event_type,"schedule",watch.trigger_id,trust=Trust.LOCAL_OS,
                        dedupe_key="schedule:" + str(due)))
                    next_at = now + watch.interval_seconds if watch.interval_seconds else None
                    watch.schedule_at = next_at
                    self.store.save(watch)
            for _ in range(self.budget.max_events_per_tick):
                with self._queue_lock:
                    if not self._queue or time.monotonic()-started >= self.budget.max_tick_seconds:
                        break
                    _,_,event,queue_key = heapq.heappop(self._queue)
                    self._queued_keys.discard(queue_key)
                if not self.store.accept(event):
                    self.metrics["duplicates"] += 1
                    continue
                self.metrics["dispatched"] += 1
                for watch in tuple(self._watches.values()):
                    if not self.matches(watch,event,now=now):
                        continue
                    key = self.store.claim(watch,event,now)
                    if not key:
                        continue
                    self.metrics["matched"] += 1
                    if watch.level == Autonomy.CONFIRM:
                        self.store.receipt(key,"awaiting_exact_confirmation",detail=watch.action)
                        continue
                    if len(self._action_times) >= self.budget.max_actions_per_minute:
                        self.store.receipt(key,"budget_limited")
                        continue
                    arguments = {k:(event.payload.get(v[2:-1]) if isinstance(v,str) and v.startswith("${") and v.endswith("}") else v)
                                 for k,v in watch.arguments.items()}
                    if watch.action == "notification.publish":
                        if not self._notify_allowed(watch,event,now):
                            self.store.receipt(key,"notification_suppressed")
                            continue
                        arguments["_event_key"]=key
                        result = self.kernel.run_task(TaskNode(capability_requirement=watch.action,inputs=arguments,
                            verification_policy=VerificationPolicy(required=True)),ExecutionContext(project_id=event.project_id))
                        self.store.receipt(key,"verified" if result.success else "failed",result.task_id)
                    elif len(self._inflight) >= self.budget.max_inflight:
                        self.store.receipt(key,"capacity_limited")
                        continue
                    else:
                        try:
                            self._submit(watch.action,arguments,key=key,watch=watch.trigger_id,project=event.project_id,target_node_id=watch.target_node_id,expected_outcome=watch.expected_outcome,event=event)
                        except (ValueError,PermissionError):
                            self.store.receipt(key,"blocked",detail="Existing runtime admission/permission rejected action.")
                            continue
                    self._action_times.append(now)
            if self.connectors and len(self._inflight) < self.budget.max_inflight and len(self._network_times) < self.budget.max_network_calls_per_minute:
                for cid,provider in self.connectors.providers.items():
                    operation=provider.next_auth_operation(now)
                    if operation:
                        try:
                            self._submit("connector."+cid+"."+operation,{},source=cid)
                            self._network_times.append(now)
                        except (ValueError,PermissionError):
                            self.last_error="Provider authentication admission rejected."
                        return
                for cid,poll in tuple(self._polls.items()):
                    if poll["next"] <= now and not any(j["source"] == cid for j in self._inflight.values()):
                        try:
                            self._submit("connector." + cid + ".events.poll",{},source=cid)
                            self._network_times.append(now)
                            poll["next"] = now + poll["interval"]
                        except (ValueError,PermissionError):
                            poll["next"] = now + max(60,poll["interval"])
                        break

    def snapshot(self):
        with self._lock:
            return {"enabled":self.enabled,"health":self.health,"last_error":self.last_error,
                "queue_depth":len(self._queue),"inflight":len(self._inflight),"metrics":dict(self.metrics),
                "watches":[asdict(w) for w in self._watches.values()],"receipts":self.store.receipts(),
                "connectors":self.connectors.snapshot() if self.connectors else [],
                "security":self.security.snapshot() if self.security else {"enabled":False,"status":"Monitoring off"}}
