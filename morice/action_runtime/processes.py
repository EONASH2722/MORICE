"""Owned background process lifecycle extends existing tools and resource leases."""
from __future__ import annotations

import os
import subprocess
import threading
import uuid
from pathlib import Path

from ..agent_tools import _terminate_process_tree
from ..process_ownership import spawn_owned_process,owned_process_running
from ..agent_types import ToolCall
from ..kernel import CapabilityDescriptor, ErrorCode, ExecutionResult, ResourceClaim, ResourceDescriptor, TaskStatus, VerificationResult, VerificationStatus
from ..unified_intelligence import PermissionDecision, RiskClass
from .contracts import ActionBinding, ActionMethod, Observation
from .verification import checked


class OwnedProcessLifecycle:
    def __init__(self, kernel, tools):
        self.kernel, self.tools = kernel, tools
        self._records = {}
        self._lock = threading.RLock()
        if kernel.resources.descriptor("RUNNING_APP") is None:
            kernel.resources.register(ResourceDescriptor("RUNNING_APP", 2))

    @staticmethod
    def terminal_arguments(inputs):
        return {"cwd": inputs["cwd"], "command": inputs["command"], "timeout": 30}

    def authorize_start(self, inputs, context):
        allowed = self.tools.permissions.check(ToolCall("terminal.run", self.terminal_arguments(inputs), permission_token=context.approval_token))
        return PermissionDecision(allowed, reason="" if allowed else "Exact permission for the owned launch command is required.")

    def authorize_owned(self, inputs, context):
        owner = context.metadata.get("project_session_id", context.metadata.get("workflow_id", ""))
        with self._lock:
            record = self._records.get(inputs["process_id"])
        allowed = bool(owner and record and owner == record["owner"])
        return PermissionDecision(allowed, reason="" if allowed else "Process belongs to another session or is unknown.")

    def start(self, inputs, context):
        owner = context.metadata.get("project_session_id", context.metadata.get("workflow_id", ""))
        if not owner:
            return ExecutionResult.failure(ErrorCode.INVALID_INPUT, "Owned process launch requires a session identity.")
        process_id = uuid.uuid4().hex
        lease = "owned-process-" + process_id
        if not self.kernel.resources.acquire(lease, (ResourceClaim("RUNNING_APP"),)):
            return ExecutionResult.failure(ErrorCode.RESOURCE_UNAVAILABLE, "Owned application capacity is occupied.")
        try:
            context.cancellation_token.raise_if_cancelled()
            process = spawn_owned_process(inputs["command"], cwd=inputs["cwd"], stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=False,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), start_new_session=os.name != "nt")
        except BaseException:
            self.kernel.resources.release(lease)
            raise
        record = {"process": process, "owner": owner, "lease": lease, "tail": bytearray(), "stopped": False, "drained": False}
        def drain():
            try:
                while chunk := process.stdout.read1(4096):
                    with self._lock:
                        record["tail"].extend(chunk)
                        del record["tail"][:-8192]
            finally:
                process.stdout.close()
                record["drained"] = True
        # Two RUNNING_APP leases bound these pipe readers. They perform no
        # agent work and cannot accumulate unbounded stdout in RAM or on disk.
        reader = threading.Thread(target=drain, name="morice-owned-process-log", daemon=True)
        record["reader"] = reader
        with self._lock:
            self._records[process_id] = record
        reader.start()
        with self.tools._process_lock:
            self.tools._active_processes[process_id] = process
        if context.cancellation_token.cancelled:
            self._stop_record(process_id)
            return ExecutionResult.failure(ErrorCode.CANCELLED, "Launch cancelled; owned process stopped.")
        return ExecutionResult(TaskStatus.SUCCEEDED, True, output={"process_id": process_id, "pid": process.pid})

    def state(self, process_id):
        with self._lock:
            record = self._records.get(process_id)
            if record is None:
                return {"known": False, "alive": False, "stopped": False}
            process = record["process"]
            output = bytes(record["tail"]).decode("utf-8", errors="replace")
            return {"known": True, "alive": owned_process_running(process), "stopped": record["stopped"],
                "pid": process.pid, "exit_code": process.poll(), "output": output}

    def _stop_record(self, process_id):
        with self._lock:
            record = self._records.get(process_id)
            if record is None or record["stopped"]:
                return
            process = record["process"]
            _terminate_process_tree(process)
            process.wait(timeout=3)
        record["reader"].join(.5)
        with self._lock:
            if not record["drained"]:
                # A descendant still owning the pipe remains an unresolved
                # process lifetime; retain capacity instead of admitting more.
                return
            record["stopped"] = True
            self.kernel.resources.release(record["lease"])
            with self.tools._process_lock:
                self.tools._active_processes.pop(process_id, None)
            # Bounded terminal metadata; no process log is retained here.
            stopped = [key for key, value in self._records.items() if value["stopped"]]
            for key in stopped[:-100]:
                self._records.pop(key)

    def stop(self, inputs, context):
        self._stop_record(inputs["process_id"])
        return ExecutionResult(TaskStatus.SUCCEEDED, True, output={"process_id": inputs["process_id"]})

    def shutdown(self):
        for process_id in tuple(self._records):
            self._stop_record(process_id)


def register_owned_processes(kernel, tools, actions):
    lifecycle = OwnedProcessLifecycle(kernel, tools)
    start_schema = {"type": "object", "required": ["cwd", "command"], "properties": {
        "cwd": {"type": "string"}, "command": {"type": "array", "minItems": 1, "maxItems": 100, "items": {"type": "string"}}}}
    kernel.registry.register(CapabilityDescriptor("process.start", "Start owned local process", input_schema=start_schema,
        risk_level=RiskClass.HIGH, supports_cancellation=True, supports_verification=True),
        lifecycle.start, permission_check=lifecycle.authorize_start,
        verifier=lambda *args: VerificationResult(VerificationStatus.INCONCLUSIVE, message="Owned process observation is required."))
    owned_schema = {"type": "object", "required": ["process_id"], "properties": {"process_id": {"type": "string"}}}
    kernel.registry.register(CapabilityDescriptor("process.stop", "Stop this session's process", input_schema=owned_schema,
        supports_cancellation=True, supports_verification=True), lifecycle.stop, permission_check=lifecycle.authorize_owned,
        verifier=lambda *args: VerificationResult(VerificationStatus.INCONCLUSIVE, message="Owned process observation is required."))
    def observe(spec, context, result=None, before=None):
        process_id = context.metadata["task_inputs"].get("process_id") or (result.output or {}).get("process_id") if result else context.metadata["task_inputs"].get("process_id")
        state = lifecycle.state(process_id)
        # Raw runtime logs are read separately by the project diagnostic stage.
        state.pop("output", None)
        return Observation(spec.action_id, "owned_process.poll", state, (f"Owned process {process_id} polled; alive={state['alive']}.",))
    for verb, field in (("start", "alive"), ("stop", "stopped")):
        actions.register(f"process.{verb}", ActionBinding(ActionMethod.CLI,
            lambda inputs, expected, f=field: {f: True}, observe,
            lambda spec, observed, before, f=field: checked(observed.state.get("known") and observed.state.get(f) is True,
                observed, "Owned process lifecycle state was not observed.")))
    return lifecycle
