"""Bounded job dispatch and durable batches over MORICE's existing agent workers."""
from __future__ import annotations

import csv
import hashlib
import html
import json
import math
import os
import platform
import queue
import shutil
import statistics
import threading
import time
import uuid
from pathlib import Path
from xml.etree import ElementTree

from .experiments import ExperimentCompiler, ResearchExperiment
from .store import ResearchStore, encode, utc_now


class VirtualLaboratory:
    """One manager per application. Completed runs survive pause/cancel/crashes."""

    def __init__(self, database, directory, *, runtime=None):
        from .runtime import ResearchRuntime
        self._owns_runtime = runtime is None
        self.runtime = runtime or ResearchRuntime(database, directory)
        self.store = self.runtime.store
        self.directory = Path(directory)
        self.compiler = ExperimentCompiler(self.runtime.simulations)
        self.registry = self.compiler.registry
        self.jobs = queue.PriorityQueue()
        self.lock = threading.RLock()
        self.controls = {}
        self.closing = threading.Event()
        self.counter = 0
        with self.store.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS lab_experiments (
                    id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES research_projects(id),
                    record_id TEXT NOT NULL REFERENCES research_records(id),
                    title TEXT NOT NULL, spec TEXT NOT NULL, estimate TEXT NOT NULL,
                    status TEXT NOT NULL, created TEXT NOT NULL, updated TEXT NOT NULL,
                    summary TEXT NOT NULL DEFAULT '{}', error TEXT NOT NULL DEFAULT ''
                );
                CREATE TABLE IF NOT EXISTS lab_runs (
                    experiment_id TEXT NOT NULL REFERENCES lab_experiments(id),
                    run_index INTEGER NOT NULL, parameters TEXT NOT NULL, outputs TEXT NOT NULL,
                    status TEXT NOT NULL, error TEXT NOT NULL, elapsed_ms REAL NOT NULL,
                    PRIMARY KEY(experiment_id,run_index)
                );
            """)
        self.worker = threading.Thread(target=self._work, name="morice-research-job-dispatch", daemon=True)
        self.worker.start()

    def prepare(self, request, *, project_id=None, chat_id="", context=None):
        started = time.perf_counter()
        experiment, estimate = self.compiler.compile(request, context)
        estimate["compilation_ms"] = (time.perf_counter() - started) * 1000
        self.directory.mkdir(parents=True, exist_ok=True)
        if shutil.disk_usage(self.directory).free < estimate["approximate_result_bytes"] * 3 + 20 * 1024**2:
            raise ValueError("Insufficient free disk space for this bounded experiment.")
        project_id = project_id or self.store.project_for_chat(chat_id) or self.runtime.create(experiment.objective, chat_id)
        self.store.snapshot(project_id)
        identifier = uuid.uuid4().hex
        record = self.store.add(project_id, "experiment", experiment.title,
                                {"experiment_id": identifier, "specification": experiment.to_dict(), "estimate": estimate,
                                 "computational_only": True}, "USER_DATA", experiment.dependencies)
        now = utc_now()
        with self.store.connect() as db:
            db.execute("INSERT INTO lab_experiments(id,project_id,record_id,title,spec,estimate,status,created,updated) VALUES(?,?,?,?,?,?,?,?,?)",
                       (identifier, project_id, record, experiment.title, encode(experiment.to_dict()), encode(estimate), "PREPARED", now, now))
        return self.get(identifier)

    def get(self, experiment_id, include_runs=False, *, run_limit=None, run_filter=""):
        if run_limit is not None and (type(run_limit) is not int or run_limit < 1):
            raise ValueError("A result page limit must be a positive integer.")
        with self.store.connect() as db:
            row = db.execute("SELECT * FROM lab_experiments WHERE id=?", (experiment_id,)).fetchone()
            if row is None:
                raise KeyError(experiment_id)
            result = dict(row)
            result["completed_runs"] = db.execute("SELECT count(*) FROM lab_runs WHERE experiment_id=?", (experiment_id,)).fetchone()[0]
            if include_runs:
                where = "experiment_id=?"; arguments = [experiment_id]
                if run_filter:
                    # Search the displayed columns, including Unicode text.
                    # Bound decoded objects at the SQL page, not after loading
                    # every stored run on a shared interactive worker.
                    db.create_function("morice_casefold", 1, lambda value: str(value).casefold(), deterministic=True)
                    where += " AND instr(morice_casefold(CAST(run_index AS TEXT)||' '||parameters||' '||status||' '||outputs||' '||error),?)>0"
                    arguments.append(str(run_filter).casefold())
                result["matching_runs"] = db.execute("SELECT count(*) FROM lab_runs WHERE "+where, arguments).fetchone()[0]
                query = "SELECT * FROM lab_runs WHERE "+where+" ORDER BY run_index"
                if run_limit is not None: query += " LIMIT ?"; arguments.append(run_limit)
                stored_runs = db.execute(query, arguments).fetchall()
        # Release SQLite cursors/read locks before JSON decoding can yield to
        # GUI painting or cyclic GC. Full exports retain the unbounded default;
        # the presentation explicitly requests a bounded page.
        for name in ("spec", "estimate", "summary"):
            result[name] = json.loads(result[name])
        if include_runs:
            result["runs"] = [{**dict(r), "parameters": json.loads(r["parameters"]), "outputs": json.loads(r["outputs"])}
                              for r in stored_runs]
        # A terminal database checkpoint may be visible just before the worker
        # finishes its event callback and releases the run control. Expose the
        # terminal state only after that acknowledgement, so immediate explicit
        # resume cannot be silently rejected while the old run still owns it.
        with self.lock:
            if experiment_id in self.controls and result["status"] in {"PAUSED", "CANCELLED", "COMPLETED", "COMPLETED_WITH_WARNINGS", "FAILED"}:
                result["status"] = "RUNNING"
        return result

    def list(self, project_id=None):
        with self.store.connect() as db:
            rows = db.execute("SELECT id FROM lab_experiments" + (" WHERE project_id=?" if project_id else "") + " ORDER BY created DESC LIMIT 100",
                              (project_id,) if project_id else ()).fetchall()
        return [self.get(row[0]) for row in rows]

    def _status(self, identifier, status, error="", summary=None):
        with self.store.connect() as db:
            db.execute("UPDATE lab_experiments SET status=?,error=?,updated=? WHERE id=?", (status, error, utc_now(), identifier))
            if summary is not None:
                db.execute("UPDATE lab_experiments SET summary=? WHERE id=?", (encode(summary), identifier))
        if status in {"COMPLETED","COMPLETED_WITH_WARNINGS","FAILED","CANCELLED"}:
            from ..kernel import EventType, KernelEvent
            row = self.get(identifier)
            self.runtime.kernel.events.publish(KernelEvent(EventType.RESEARCH_FINISHED,source="research_lab",
                project_id=row["project_id"],payload={"experiment_id":identifier,"status":status,
                    "revision":identifier+":"+status+":"+str(row["updated"])}))

    def start(self, identifier):
        with self.lock:
            if self.closing.is_set():
                raise RuntimeError("The laboratory is shutting down.")
            if identifier in self.controls:
                return False
            row = self.get(identifier)
            if row["estimate"].get("model_fingerprint")!=self.registry.fingerprint(row["spec"]["simulation_engine"]):
                self.store.invalidate(row["project_id"],row["record_id"],"Model or compiler changed; prepare a new version.")
                raise ValueError("Model or compiler changed; prepare a new experiment version.")
            if next(r for r in self.store.snapshot(row["project_id"])["records"] if r["id"]==row["record_id"])["stale"]:
                raise ValueError("Experiment dependencies are stale; prepare a new version.")
            if row["status"] in {"COMPLETED", "COMPLETED_WITH_WARNINGS", "FAILED"}:
                raise ValueError("Completed/failed experiments are immutable; prepare a new variant.")
            if len(self.controls) >= 16:
                raise ValueError("The local queue holds at most 16 experiments.")
            # No silent resumption after a crash; the user explicitly starts the saved plan.
            from ..kernel import CancellationToken
            self.controls[identifier] = {"pause": threading.Event(), "cancel": threading.Event(), "token": CancellationToken()}
            self._status(identifier, "QUEUED")
            self.counter += 1
            self.jobs.put((row["spec"]["priority"], self.counter, identifier))
            return True

    def pause(self, identifier):
        with self.lock:
            control = self.controls.get(identifier)
            if control:
                control["pause"].set()
                control["token"].cancel("Research paused; completed runs retained.")
            elif self.get(identifier)["status"] not in {"COMPLETED", "COMPLETED_WITH_WARNINGS", "FAILED"}:
                self._status(identifier, "PAUSED")

    def cancel(self, identifier):
        with self.lock:
            control = self.controls.get(identifier)
            if control:
                control["cancel"].set()
                control["token"].cancel("Research cancelled.")
            elif self.get(identifier)["status"] not in {"COMPLETED", "COMPLETED_WITH_WARNINGS", "FAILED"}:
                self._status(identifier, "CANCELLED")

    def close(self):
        self.closing.set()
        with self.lock:
            for control in self.controls.values():
                control["pause"].set()
                control["token"].cancel("Research application closing.")
        self.worker.join(timeout=3)
        if self._owns_runtime:
            self.runtime.close()

    def _work(self):
        while not self.closing.is_set():
            try:
                _, _, identifier = self.jobs.get(timeout=.1)
            except queue.Empty:
                continue
            try:
                self._execute(identifier, self.controls[identifier])
            except Exception as exc:
                self._status(identifier, "FAILED", f"{type(exc).__name__}: {exc}")
            finally:
                with self.lock:
                    self.controls.pop(identifier, None)
                self.jobs.task_done()
        # Queued jobs remain inspectable and explicitly resumable after shutdown.
        with self.lock:
            for identifier in self.controls:
                self._status(identifier, "PAUSED", "Application closed before execution.")
            self.controls.clear()

    def _checkpoint(self, identifier, pending):
        if not pending:
            return
        with self.store.connect() as db:
            db.executemany("INSERT INTO lab_runs VALUES(?,?,?,?,?,?,?)", pending)
            db.execute("UPDATE lab_experiments SET updated=? WHERE id=?", (utc_now(), identifier))
        pending.clear()

    def _execute(self, identifier, control):
        row = self.get(identifier, include_runs=True)
        experiment = ResearchExperiment(**row["spec"])
        tool = self.registry.get(experiment.simulation_engine)
        if tool.version != row["estimate"]["tool_version"] or self.registry.fingerprint(tool.tool_id)!=row["estimate"].get("model_fingerprint"):
            raise ValueError("Tool version changed. Create a new experiment rather than mixing versions.")
        plan = self.compiler.plan(experiment)
        completed_indices = {r["run_index"] for r in row["runs"]}
        self._status(identifier, "RUNNING")
        began = time.perf_counter()
        pending = []
        constraints = {name: {side: self.registry.quantity(value, tool.supported_outputs[name]) for side, value in bounds.items()}
                       for name, bounds in experiment.constraints.items()}
        # Refined stage is derived deterministically from persisted coarse results.
        coarse_count = len(plan)
        total = row["estimate"]["planned_runs"]
        from ..kernel import ExecutionContext, TaskGraph, TaskNode, Priority, TaskStatus
        for index in range(total):
            if index in completed_indices:
                continue
            if control["cancel"].is_set() or control["pause"].is_set() or self.closing.is_set() or time.perf_counter() - began >= experiment.time_limit_seconds:
                self._checkpoint(identifier, pending)
                self._status(identifier, "CANCELLED" if control["cancel"].is_set() else "PAUSED",
                             "Partial runs preserved. Resume explicitly to continue.")
                return
            if experiment.strategy == "coarse_refine" and index >= coarse_count and len(plan) == coarse_count:
                self._checkpoint(identifier, pending)
                completed = self.get(identifier, True)["runs"][:coarse_count]
                valid = [r for r in completed if r["status"] == "VALID"]
                if not valid:
                    raise ValueError("No feasible coarse candidates; refinement cannot proceed.")
                best = (max if experiment.direction == "maximize" else min)(valid, key=lambda r: r["outputs"][experiment.metric])
                axis = next(iter(experiment.parameter_ranges))
                step = (plan[-1][axis] - plan[0][axis]) / (coarse_count - 1)
                lo, hi = max(plan[0][axis], best["parameters"][axis] - step), min(plan[-1][axis], best["parameters"][axis] + step)
                plan += [{**plan[0], axis: lo + (hi-lo)*i/(coarse_count-1)} for i in range(coarse_count)]
            # Dispatch a bounded batch through the shared Phase 2 runtime.
            # Commit every completed result before honoring pause/cancel, even
            # if another task in the same batch was cancelled earlier.
            indices=[i for i in range(index,min(total,len(plan),index+25)) if i not in completed_indices]
            tasks=tuple(TaskNode("research.simulate",{"tool_id":tool.tool_id,"parameters":plan[i]},
                        description=f"Research run {i}",priority=Priority.BACKGROUND,
                        constraints={"role":"simulation","approach":f"run-{i}"}) for i in indices)
            graph=TaskGraph(tasks,goal=experiment.objective)
            context=ExecutionContext(research_project_id=row["project_id"],cancellation_token=control["token"],
                deadline=time.monotonic()+max(.1,experiment.time_limit_seconds-(time.perf_counter()-began)))
            # These four built-in models cost microseconds. The shared runtime's
            # serial option avoids parallel overhead and leaves a CPU lease for
            # interactive work on multicore hosts; independent research tools
            # still use normal parallel TaskGraphs when requested.
            self.runtime.agents.run(graph,context,sequential=True)
            for run_index,task in zip(indices,tasks):
                result=task.result
                if result is None or result.status in {TaskStatus.CANCELLED,TaskStatus.SKIPPED}: continue
                outputs=result.output["outputs"] if result.success else {}
                status="VALID" if result.success else "INVALID"
                error="; ".join(e.message+": "+e.detail for e in result.errors)
                if result.success and any(outputs[name]<bounds.get("min",-math.inf) or outputs[name]>bounds.get("max",math.inf) for name,bounds in constraints.items()):
                    status="INFEASIBLE"
                pending.append((identifier,run_index,encode(plan[run_index]),encode(outputs),status,error,result.metrics.get("wall_ms",0)))
                completed_indices.add(run_index)
            self._checkpoint(identifier,pending)
            if any(task.result is None or task.result.status in {TaskStatus.CANCELLED,TaskStatus.SKIPPED} for task in tasks):
                self._status(identifier,"CANCELLED" if control["cancel"].is_set() else "PAUSED","Completed runs retained; resume explicitly.")
                return
        self._checkpoint(identifier, pending)
        complete = self.get(identifier, True)
        summary = self.summarize(complete)
        summary["execution_slice_seconds"] = time.perf_counter() - began
        summary["method"] = tool.method
        summary["limitations"] = tool.limitations
        summary["python_version"] = platform.python_version()
        summary["random_generator"] = "Python random.Random (MT19937), independent uniform inputs"
        summary["seed"] = experiment.seed
        summary["tool_version"] = tool.version
        summary["model_fingerprint"] = row["estimate"]["model_fingerprint"]
        if experiment.baseline:
            baseline = {k: self.registry.quantity(v, tool.required_units[k]) for k, v in experiment.baseline.items()}
            baseline_result = self.runtime.execute("research.simulate", {"tool_id":tool.tool_id,"parameters":baseline})
            if not baseline_result.success: raise ValueError("Baseline failed verification.")
            outputs = baseline_result.output["outputs"]
            summary["baseline"] = {"parameters": baseline, "outputs": outputs}
            if summary.get("best_observed"):
                summary["best_minus_baseline"] = summary["best_observed"]["outputs"][experiment.metric] - outputs[experiment.metric]
        summary["artifacts"] = self.export(complete, summary)
        stale=next(r for r in self.store.snapshot(row["project_id"])["records"] if r["id"]==row["record_id"])["stale"]
        result_id=self.store.add(row["project_id"], "simulation", experiment.title,
                       {"inputs": row["spec"], "method": tool.method, "result": summary,
                        "experiment_id": identifier, "computational_only": True}, "UNKNOWN" if stale else "SIMULATED", [row["record_id"]])
        if stale:
            self.store.invalidate(row["project_id"],result_id,"Inputs changed during execution; results require recomputation.")
            self._status(identifier,"COMPLETED_WITH_WARNINGS","Inputs changed during execution; results are stale.",summary)
            return
        self._status(identifier, "FAILED" if not summary["valid_runs"] else ("COMPLETED_WITH_WARNINGS" if summary["invalid_runs"] else "COMPLETED"), summary=summary)

    @staticmethod
    def summarize(row):
        runs, spec = row["runs"], row["spec"]
        valid = [r for r in runs if r["status"] == "VALID"]
        result = {"valid_runs": len(valid), "invalid_runs": sum(r["status"] == "INVALID" for r in runs),
                  "infeasible_runs": sum(r["status"] == "INFEASIBLE" for r in runs), "statistics": {},
                  "claim": "Computational model predictions only; not physical validation."}
        if not valid:
            return result
        metric = spec["metric"]
        result["best_observed"] = (max if spec["direction"] == "maximize" else min)(valid, key=lambda r: r["outputs"][metric])
        for name in valid[0]["outputs"]:
            values = sorted(r["outputs"][name] for r in valid)
            def quantile(q):
                k = (len(values)-1)*q
                i = int(k)
                return values[i] + (values[min(i+1, len(values)-1)]-values[i])*(k-i)
            result["statistics"][name] = {"count": len(values), "mean": statistics.fmean(values),
                "median": statistics.median(values), "sample_variance": statistics.variance(values) if len(values)>1 else None,
                "min": values[0], "max": values[-1], "p05": quantile(.05), "p95": quantile(.95)}
        if spec["experiment_type"] == "MONTE_CARLO":
            result["constraint_violation_fraction"] = result["infeasible_runs"] / max(1, len(runs)-result["invalid_runs"])
            result["uncertainty_note"] = "Empirical variation under supplied independent uniform distributions; percentiles are not confidence intervals. Invalid runs are excluded and counted separately."
        else:
            result["uncertainty_note"] = "Grid summaries describe tested candidates, not probability or confidence intervals."
        if spec["experiment_type"] == "SENSITIVITY_ANALYSIS":
            baseline = runs[0]
            sensitivities = {}
            for parameter in spec["parameter_ranges"]:
                selected = [r for r in valid if all(r["parameters"][k] == baseline["parameters"][k] for k in r["parameters"] if k != parameter)]
                xs = [r["parameters"][parameter] for r in selected]
                ys = [r["outputs"][metric] for r in selected]
                if len(xs)>1 and max(xs)>min(xs):
                    sensitivities[parameter] = {"output_span": max(ys)-min(ys), "input_span": max(xs)-min(xs),
                                                "span_ratio": (max(ys)-min(ys))/(max(xs)-min(xs))}
            result["one_at_a_time_sensitivity"] = sensitivities
        return result

    def export(self, row, summary):
        directory = self.directory / "experiments" / (row["id"] + "-" + uuid.uuid4().hex[:8])
        directory.mkdir(parents=True, exist_ok=False)
        tool = self.registry.get(row["spec"]["simulation_engine"])
        manifest = {"experiment_id": row["id"], "project_id": row["project_id"], "specification": row["spec"],
                    "estimate": row["estimate"], "summary": summary, "input_units": tool.required_units, "output_units": tool.supported_outputs}
        (directory / "experiment.json").write_text(json.dumps(manifest, indent=2, allow_nan=False), encoding="utf-8")
        json.loads((directory / "experiment.json").read_text(encoding="utf-8"))
        parameters, outputs = list(tool.required_units), list(tool.supported_outputs)
        with (directory / "results.csv").open("w", newline="", encoding="utf-8") as stream:
            writer = csv.writer(stream)
            writer.writerow(["run", "status"] + [f"{p} [{tool.required_units[p]}]" for p in parameters] + [f"{p} [{tool.supported_outputs[p]}]" for p in outputs] + ["elapsed_ms"])
            for run in row["runs"]:
                writer.writerow([run["run_index"], run["status"]] + [run["parameters"][p] for p in parameters] + [run["outputs"].get(p, "") for p in outputs] + [run["elapsed_ms"]])
        with (directory / "results.csv").open(newline="", encoding="utf-8") as stream:
            if sum(1 for _ in csv.reader(stream)) != len(row["runs"]) + 1:
                raise ValueError("Result CSV failed verification.")
        valid = [r for r in row["runs"] if r["status"] == "VALID"]
        metric = row["spec"]["metric"]
        axis = next(iter(row["spec"]["parameter_ranges"]), "run_index")
        if valid:
            stride = max(1, math.ceil(len(valid)/1000))
            points = [(r["run_index"] if axis == "run_index" else r["parameters"][axis], r["outputs"][metric]) for r in valid[::stride]]
            x0, x1 = min(x for x,y in points), max(x for x,y in points)
            y0, y1 = min(y for x,y in points), max(y for x,y in points)
            circles = ''.join(f'<circle cx="{70+(x-x0)*700/(x1-x0 or 1):.3f}" cy="{300-(y-y0)*240/(y1-y0 or 1):.3f}" r="2" fill="#167a98"/>' for x,y in points)
            svg = f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 850 360"><rect width="850" height="360" fill="white"/><text x="70" y="25">{html.escape(metric)} [{html.escape(tool.supported_outputs[metric])}] vs {html.escape(axis)} — sampled actual runs</text><path d="M70 50V300H800" fill="none" stroke="black"/>{circles}<text x="70" y="335">x: {x0:.6g} to {x1:.6g}; y: {y0:.6g} to {y1:.6g}</text></svg>'
            (directory / "plot.svg").write_text(svg, encoding="utf-8")
            ElementTree.parse(directory / "plot.svg")
        report = f"# {row['title']}\n\nComputational experiment; not a physical experiment.\n\nMethod: {tool.method}\n\nLimits: {tool.limitations}\n\nThe complete inputs, seed, units and summary are in experiment.json. All actual runs are in results.csv. No universal compatibility score or scientific validation is claimed.\n"
        (directory / "report.md").write_text(report, encoding="utf-8")
        checksums = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in directory.iterdir() if p.is_file()}
        (directory / "checksums.json").write_text(json.dumps(checksums, indent=2), encoding="utf-8")
        return {"directory": str(directory), "checksums": checksums}

    def compare(self, first, second):
        a, b = self.get(first, True), self.get(second, True)
        if a["spec"]["simulation_engine"] != b["spec"]["simulation_engine"]:
            raise ValueError("Compare experiments using the same model and output units.")
        return {"first": first, "second": second, "first_summary": a["summary"], "second_summary": b["summary"],
                "changed_specification_fields": [k for k in a["spec"] if a["spec"][k] != b["spec"][k]],
                "limitation": "Different inputs do not alone establish causality; compare controls and uncertainty."}


def compare_measurements(predicted, measured):
    """Explicit aligned, same-unit values; no hidden calibration or time alignment."""
    if not predicted or len(predicted) != len(measured) or any(not math.isfinite(v) for v in [*predicted, *measured]):
        raise ValueError("Supply equal-length, nonempty finite arrays in the same units and alignment.")
    residuals = [a-b for a,b in zip(predicted, measured)]
    mse = statistics.fmean(r*r for r in residuals)
    center = statistics.fmean(measured)
    total = sum((v-center)**2 for v in measured)
    return {"rmse": math.sqrt(mse), "mae": statistics.fmean(abs(r) for r in residuals),
            "r_squared": 1-sum(r*r for r in residuals)/total if total else None,
            "residuals": residuals, "samples": len(measured),
            "limitation": "User-supplied alignment/units; calibration and validation datasets must remain distinct."}
