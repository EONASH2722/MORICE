"""Research workflow used by the existing MORICE chat worker."""
from __future__ import annotations

import json
import re
import time
from pathlib import Path

from .artifacts import export_package, verify_project
from .ingestion import ResearchIngestion, checkpoint
from .providers import ResearchModelRouter
from .store import ResearchStore
from .tools import ScientificTools


def research_intent(text: str, attached=(), active=False):
    if attached or "```research" in text or "```calculation" in text:
        return True
    return bool(re.search(
        r"\b(?:research|hypothesis|hypotheses|dataset|experiment|scientific|parameter sweep|"
        r"analy[sz]e (?:these|this|the) (?:data|papers)|compare (?:these|the) papers|"
        r"literature review|calculate|simulate|monte carlo)\b", text, re.I
    ) or (active and re.search(r"\b(?:continue|resume|evidence|assumption|research status|export research|test this|sweep|optimize)\b", text, re.I)))


class ResearchService:
    def __init__(self, database, directory, *, runtime=None):
        from .runtime import ResearchRuntime
        self.runtime = runtime or ResearchRuntime(database, directory)
        self.store = self.runtime.store
        self.directory = Path(directory)
        self.ingestion = self.runtime.ingestion
        self.tools = self.runtime.tools
        self.models = ResearchModelRouter()

    def run(self, objective, *, project_id=None, chat_id="", attachments=(),
            cancel=None, progress=None, synthesize=False, new_project=False):
        started = time.perf_counter()
        from .safety import check_research_purpose
        from ..kernel import ExecutionContext, CancellationToken
        check_research_purpose(objective)
        # Link an existing legacy chat event to the shared token without a
        # watcher thread or a second cancellation authority.
        from .ingestion import EventToken
        token = EventToken(cancel) if cancel is not None else CancellationToken()
        context = ExecutionContext(cancellation_token=token, active_files=tuple(str(p) for p in attachments))
        report = progress or (lambda _: None)
        checkpoint(cancel)
        if new_project:
            project_id = self.runtime.create(objective, chat_id)
        elif project_id:
            self.store.snapshot(project_id)  # Reject invalid cross-project requests before writes.
            if chat_id and self.store.project_for_chat(chat_id) != project_id:
                self.store.link_chat(project_id, chat_id)
        else:
            project_id = self.store.project_for_chat(chat_id) if chat_id else None
            project_id = project_id or self.runtime.create(objective, chat_id)
        failures, timings = [], {}
        try:
            if len(attachments) > 20:
                raise ValueError("Attach at most 20 research files per request.")
            for filename in attachments:
                checkpoint(cancel)
                stage = time.perf_counter()
                report("Reading research evidence: " + Path(filename).name)
                try:
                    execution = self.runtime.execute("research.ingest", {"source": str(filename)}, context=context)
                    checkpoint(cancel)
                    if not execution.success:
                        raise ValueError("; ".join(e.message + ": " + e.detail for e in execution.errors))
                    source = execution.output
                    for previous in self.store.snapshot(project_id)["records"]:
                        if previous["kind"]=="source" and previous["payload"].get("original_path")==source["original_path"] and previous["payload"]["sha256"]!=source["sha256"]:
                            self.store.invalidate(project_id,previous["id"],"Selected input changed; previous version preserved.")
                    source_id = self.store.add(project_id, "source", source["name"], source, "USER_DATA")
                    if source.get("pixel_analysis"):
                        linked=tuple(r["id"] for r in self.store.snapshot(project_id)["records"] if r["kind"] in {"experiment","hypothesis","design"} and not r["stale"])[-10:]
                        self.store.add(project_id,"observation","Research image intensity — no semantic conclusion",
                            {"source_id":source_id,"pixel_analysis":source["pixel_analysis"],"context":list(linked),
                             "interpretation":"Compare actual intensity metadata with linked experiment context; physical meaning remains unverified."},"USER_DATA",(source_id,*linked))
                    tables = source.get("tables", [])
                    if "dataset" in source:
                        tables = [source["dataset"]]
                    for table in tables:
                        self.store.add(project_id, "dataset", source["name"] + " data quality",
                                       {"inputs": {"source": source_id, "sha256": source["sha256"]},
                                        "method": table["method"], "result": table}, "CALCULATED", (source_id,))
                except InterruptedError:
                    raise
                except Exception as exc:
                    failure = f"{Path(filename).name}: {type(exc).__name__}: {exc}"
                    failures.append(failure)
                    self.store.add(project_id, "failure", "Ingestion failed", {"error": failure})
                timings["ingest:" + Path(filename).name] = (time.perf_counter() - stage) * 1000

            # Explicit structured calculation instructions keep numeric claims
            # on a deterministic path even when no language model is installed.
            calculation = re.search(r"```(?:research|calculation)\s*\n(.*?)```", objective, re.S)
            if calculation:
                report("Checking units and calculating")
                spec = json.loads(calculation.group(1))
                stage = time.perf_counter()
                execution = self.runtime.execute("research.calculate", spec, context=context)
                checkpoint(cancel)
                if not execution.success:
                    raise ValueError("; ".join(e.message + ": " + e.detail for e in execution.errors))
                result = execution.output
                self.store.add(project_id, "calculation", spec["expression"], result, "CALCULATED", spec.get("dependencies",()))
                timings["calculation_ms"] = (time.perf_counter() - stage) * 1000

            experiment = re.search(r"```experiment\s*\n(.*?)```", objective, re.S)
            if experiment:
                report("Compiling a bounded computational experiment")
                prepared = self.runtime.laboratory.prepare(json.loads(experiment.group(1)),project_id=project_id,chat_id=chat_id)
                self.runtime.laboratory.start(prepared["id"])
                report(f"Experiment {prepared['id']} queued: {prepared['estimate']['planned_runs']} actual planned runs")
            elif re.search(r"\b(?:simulate|sweep|monte carlo|optimize|test this from)\b",objective,re.I):
                previous=[r for r in self.store.snapshot(project_id)['records'] if r['kind']=='experiment' and not r['stale']]
                experiment_context=previous[-1]['payload']['specification'] if previous else None
                try:
                    prepared=self.runtime.laboratory.prepare(objective,project_id=project_id,chat_id=chat_id,context=experiment_context)
                    self.runtime.laboratory.start(prepared['id'])
                    report(f"Experiment {prepared['id']} queued: {prepared['estimate']['planned_runs']} actual planned runs")
                except ValueError as exc:
                    failures.append(str(exc))
                    self.store.add(project_id,'failure','Experiment needs details',{'error':str(exc),'incomplete':True})

            snapshot = self.store.snapshot(project_id)
            if synthesize:
                report("Comparing stored evidence using the selected model")
                try:
                    interpretation = self.models.synthesize(objective, self.context(snapshot), cancel)
                    dependencies = tuple(r["id"] for r in snapshot["records"] if r["kind"] in {"source", "dataset", "calculation"} and not r["stale"])
                    self.store.add(project_id, "result", "Model interpretation — unverified", interpretation, "INFERRED", dependencies)
                except InterruptedError:
                    raise
                except Exception as exc:
                    failures.append("Model interpretation unavailable: " + str(exc))
                    self.store.add(project_id, "failure", "Model interpretation unavailable", {"error": str(exc)})
            report("Verifying research evidence and dependencies")
            verification = verify_project(self.store.snapshot(project_id))
            self.store.add(project_id, "validation", "Integrity verification", verification)
            package = None
            if re.search(r"\bexport\b", objective, re.I):
                report("Writing and reopening the research package")
                package = export_package(self.store.snapshot(project_id), self.directory / "exports", cancel)
                dependencies = tuple(r["id"] for r in self.store.snapshot(project_id)["records"] if r["kind"] != "artifact")
                self.store.add(project_id, "artifact", "Research package", package, dependencies=dependencies)
            timings["total_ms"] = (time.perf_counter() - started) * 1000
            return {"project_id": project_id, "snapshot": self.store.snapshot(project_id),
                    "failures": failures, "verification": verification, "package": package, "timings": timings}
        except Exception as exc:
            self.store.add(project_id, "failure", "Cancelled" if isinstance(exc, InterruptedError) else "Research stopped",
                           {"error": str(exc), "incomplete": True})
            raise

    @staticmethod
    def context(snapshot):
        records = []
        for r in snapshot["records"][-60:]:
            if r["kind"] in {"artifact", "validation"}:
                continue
            p = r["payload"]
            if r["kind"] == "source":
                p = {k: p[k] for k in ("name", "sha256", "metadata", "warnings", "text", "sections") if k in p}
            records.append({"id": r["id"], "kind": r["kind"], "provenance": r["provenance"],
                            "stale": r["stale"], "content": json.dumps(p, ensure_ascii=False)[:4500]})
        selected = []
        budget = 28000
        # Prefer recent evidence but preserve valid JSON; do not slice a JSON
        # object halfway through a source boundary.
        for record in reversed(records):
            size = len(json.dumps(record, ensure_ascii=False))
            if size <= budget:
                selected.append(record)
                budget -= size
        return json.dumps({"objective": snapshot["objective"], "records": list(reversed(selected)),
                           "omitted_records": len(records) - len(selected)}, ensure_ascii=False)

    @staticmethod
    def reply(result):
        lines = [f"Research project: {result['project_id']}", ""]
        for record in result["snapshot"]["records"][-30:]:
            data = record["payload"]
            stale = " [STALE]" if record["stale"] else ""
            if record["kind"] == "source":
                lines.append(f"USER_DATA: {record['title']}{stale} · SHA-256 {data['sha256'][:16]}")
                lines.extend("Warning: " + w for w in data["warnings"])
            elif record["kind"] == "dataset":
                table = data["result"]
                lines.append(f"CALCULATED: {record['title']}{stale}: {table['rows']} rows; {table['duplicate_rows']} duplicates.")
                for column in table["columns"]:
                    if "mean" in column:
                        lines.append(f"• {column['name']}: n={column['count']}, mean={column['mean']:.6g}, median={column['median']:.6g}, missing={column['missing']}.")
                lines.extend("Warning: " + w for w in table["warnings"])
            elif record["kind"] == "calculation":
                lines.append(f"CALCULATED{stale}: {record['title']} → {json.dumps(data['result'], ensure_ascii=False)}")
            elif record["kind"] == "result":
                if "text" in data:
                    lines += ["", "INFERRED — model interpretation, not independently validated:" + stale, data["text"]]
                else:
                    lines.append(record['provenance']+stale+": "+json.dumps(data.get('result'),ensure_ascii=False)[:1500])
        lines += ["", "Integrity check: " + ("passed" if result["verification"]["integrity_passed"] else "issues found")]
        lines.append("Integrity covers stored evidence and dependencies, not scientific correctness.")
        lines.extend(issue["issue"] for issue in result["verification"]["issues"])
        lines.extend(result["failures"])
        if result["package"]:
            lines.append("Verified export: " + result["package"]["directory"])
        for experiment in (r for r in result["snapshot"]["records"] if r["kind"] == "experiment"):
            lines.append(f"Computational experiment: {experiment['payload']['experiment_id']}. Use the Research panel for actual progress, pause, cancel and resume.")
        if not any(r["kind"] in {"source", "calculation", "experiment"} for r in result["snapshot"]["records"]):
            lines.append("No evidence or deterministic calculation has been supplied yet; no scientific result is established.")
        return "\n".join(lines)
