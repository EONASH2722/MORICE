"""Small orchestration capabilities and adapters to existing MORICE services."""
from __future__ import annotations

import hashlib
import json

from ..kernel import (CapabilityDescriptor, ErrorCode, ExecutionResult, ResourceClaim, TaskStatus,
    VerificationResult, VerificationStatus)


def claim_conflicts(records):
    claims = {}
    conflicts = []
    for task_id, record in records.items():
        output = record.get("structured_output")
        if not isinstance(output, dict):
            continue
        for key, value in output.get("claims", {}).items():
            if key in claims and claims[key][1] != value:
                conflicts.append({"claim": key, "first_task": claims[key][0], "first": claims[key][1],
                    "second_task": task_id, "second": value, "status": "unresolved"})
            else:
                claims[key] = (task_id, value)
    return conflicts


def register_workflow_capabilities(kernel, state):
    def upstream(context):
        packet = context.metadata["packet"]
        return state.outputs(packet["workflow_id"], packet["upstream"].keys())

    def compare(inputs, context):
        records = upstream(context)
        conflicts = claim_conflicts(records)
        sources = []
        for task_id, record in records.items():
            output = record.get("structured_output")
            if isinstance(output, dict) and "content" in output:
                text = output["content"]
                sources.append({"task_id": task_id, "path": output["path"], "characters": len(text),
                    "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(), "excerpt": text[:500]})
        values = {key: record.get("structured_output") for key, record in records.items() if record.get("status") == "succeeded"}
        return ExecutionResult(TaskStatus.SUCCEEDED, True,
            {"sources": sources, "findings": values, "conflicts": conflicts,
                "uncertainties": ["Contradictory claims need additional evidence."] if conflicts else [], "open_questions": []})

    def verify(inputs, context):
        records = upstream(context)
        evidence, problems, sources = [], [], []
        for task_id, record in records.items():
            if record.get("status") != "succeeded":
                problems.append(f"Required upstream task {task_id}: {record.get('status')}.")
            output = record.get("structured_output")
            if not isinstance(output, dict):
                continue
            if output.get("conflicts"):
                problems.append("Conflicting claims remain unresolved.")
            if "test_status" in output:
                execution = output.get("execution") or {}
                if output["test_status"] != "passed" or execution.get("exitCode") != 0:
                    problems.append(f"Actual test command {task_id} did not pass.")
                else:
                    evidence.append(f"Test command {task_id}: exit 0; captured stdout/stderr available.")
            sources.extend(output.get("sources", []))
        for source in sources:
            read = kernel.dispatch("filesystem.read", {"path": source["path"]}, context)
            if not read.success or hashlib.sha256(read.output["content"].encode("utf-8")).hexdigest() != source["sha256"]:
                problems.append(f"Source changed or could not be read: {source['path']}.")
            else:
                evidence.append(f"Independent read of preview: {source['path']}.")
        for artifact in inputs.get("artifacts", []):
            read = kernel.dispatch("filesystem.read", {"path": artifact["path"]}, context)
            if not read.success or read.output["content"] != artifact["content"]:
                problems.append(f"Artifact bytes do not match: {artifact['path']}.")
            else:
                evidence.append(f"Approved artifact content independently read: {artifact['path']}.")
        status = VerificationStatus.FAILED if problems else VerificationStatus.VERIFIED if evidence else VerificationStatus.INCONCLUSIVE
        return ExecutionResult(TaskStatus.SUCCEEDED, True,
            {"verification": status.value, "evidence": evidence, "problems": problems},
            evidence=evidence, verification_required=True)

    def verify_verifier(result, expected, context):
        output = result.output
        return VerificationResult(VerificationStatus(output["verification"]), tuple(output["evidence"]), "; ".join(output["problems"]))

    def synthesize(inputs, context):
        records = upstream(context)
        conflicts = claim_conflicts(records)
        failures = [{"task_id": key, "status": record["status"], "errors": record.get("errors", [])}
            for key, record in records.items() if record["status"] != "succeeded"]
        verifications = [record.get("structured_output", {}).get("verification") for record in records.values()
            if record.get("role") == "verifier" and isinstance(record.get("structured_output"), dict)]
        verified = bool(verifications) and all(v == "verified" for v in verifications) and not conflicts and not failures
        output = {"summary": "Verified workflow completed." if verified else "Workflow completed with unresolved or failed results.",
            "verified": verified, "failures": failures, "conflicts": conflicts,
            "results": {key: {"role": r["role"], "status": r["status"], "summary": r["summary"],
                "output": r.get("structured_output"), "evidence": r.get("evidence", [])} for key, r in records.items()}}
        result = ExecutionResult(TaskStatus.SUCCEEDED, True, output)
        if not verified:
            result.success, result.status = False, TaskStatus.FAILED
            from ..kernel import ExecutionError
            result.errors.append(ExecutionError(ErrorCode.VERIFICATION_FAILED, "Final result lacks successful independent verification."))
        return result

    kernel.registry.register(CapabilityDescriptor("agent.compare", "Compare structured evidence", inline=True), compare)
    kernel.registry.register(CapabilityDescriptor("agent.verify", "Independent workflow verification", supports_verification=True,
        supports_cancellation=True, timeout=90, inline=True), verify, verifier=verify_verifier)
    kernel.registry.register(CapabilityDescriptor("agent.synthesize", "Synthesize verified results", inline=True), synthesize)


def register_existing_services(kernel):
    def search(inputs, context):
        from ..web_search import search_web
        content = search_web(inputs["query"], timeout=10)
        if not content:
            return ExecutionResult.failure(ErrorCode.CAPABILITY_UNAVAILABLE, "Existing web search returned no evidence.")
        return ExecutionResult(TaskStatus.SUCCEEDED, True, {"claims": {}, "evidence": [content],
            "sources": [], "uncertainties": ["Search snippets require source verification."], "open_questions": []})
    kernel.registry.register(CapabilityDescriptor("browser.search", "Existing web search", required_permissions=("network",),
        supported_resources=(ResourceClaim("IO"),), timeout=15,
        input_schema={"type": "object", "required": ["query"], "properties": {"query": {"type": "string", "maxLength": 1000}}}), search)

    def image(inputs, context):
        from ..vision import describe_image
        text = describe_image(inputs["path"])
        if not text.startswith("Image size:"):
            return ExecutionResult.failure(ErrorCode.CAPABILITY_UNAVAILABLE, text)
        return ExecutionResult(TaskStatus.SUCCEEDED, True, {"description": text, "semantic_analysis": "unavailable"},
            warnings=["Existing image adapter provides metadata only; OCR/semantic analysis were not run."])
    kernel.registry.register(CapabilityDescriptor("vision.inspect", "Existing image metadata", required_permissions=("file_read",),
        input_schema={"type": "object", "required": ["path"], "properties": {"path": {"type": "string"}}}), image)

    def simulate(inputs, context):
        from ..research.simulations import SimulationToolRegistry
        registry = SimulationToolRegistry()
        tool = registry.get(inputs["tool_id"])
        output = registry.run(inputs["tool_id"], inputs["parameters"])
        return ExecutionResult(TaskStatus.SUCCEEDED, True,
            {"values": output, "tool_id": tool.tool_id, "version": tool.version, "limitations": tool.limitations},
            evidence=["Existing fixed simulation adapter checked declared units/finite outputs."], verification_required=True)
    def verify_simulation(result, expected, context):
        valid = expected is None or result.output["values"] == expected
        return VerificationResult(VerificationStatus.VERIFIED if valid else VerificationStatus.FAILED,
            ("Deterministic simulation output compared to supplied expected values." if expected else "Simulation's existing finite-output validation completed.",))
    kernel.registry.register(CapabilityDescriptor("simulation.run", "Existing local simulation", supported_resources=(ResourceClaim("CPU"),),
        supports_verification=True, input_schema={"type": "object", "required": ["tool_id", "parameters"],
            "properties": {"tool_id": {"type": "string"}, "parameters": {"type": "object"}}}), simulate, verifier=verify_simulation)
