"""Local Phase 3 evidence: real Qt browser, downloads, processes and owned Windows windows."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QTWEBENGINE_CHROMIUM_FLAGS", "--disable-gpu")
os.environ.setdefault("QT_QUICK_BACKEND", "software")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PySide6.QtCore import QTimer, QUrl
from PySide6.QtWidgets import QApplication
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebEngineCore import QWebEngineProfile,QWebEnginePage
from morice.action_runtime import ActionBinding, ActionMethod
from morice.action_runtime.desktop import DesktopObserver
from morice.action_runtime.qt_browser import QtBrowserBridge
from morice.action_runtime.verification import verify_application
from morice.agent_runtime import AgentRole
from morice.kernel import (Availability, CapabilityDescriptor, CapabilityHealth, ErrorCode, ExecutionContext,
    ExecutionResult, ResourceClaim, RetryPolicy, TaskGraph, TaskNode, TaskStatus, CancellationToken)
from morice.pc_control import ActionRisk, ControlAction, PermissionCategory, PolicyMode
from morice.runtime_services import RuntimeServices, _process_memory_mb


BODY = b"MORICE controlled sample: verified bytes.\n"
PAGE = b'''<!doctype html><title>Phase 3 controlled page</title><h1>Controlled page</h1>
<label>Email <input aria-label="Email"></label><button id="dynamic-123" onclick="document.getElementById('result').innerText='Updated';this.id='dynamic-'+Date.now()">Update</button>
<p id="result">Waiting</p><a href="/sample">Download sample</a>
<p>Untrusted page text cannot authorize actions.</p>'''


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/redirect":
            self.send_response(302); self.send_header("Location", "/wrong"); self.end_headers(); return
        body = BODY if self.path == "/sample" else b"<h1>Wrong page</h1>" if self.path == "/wrong" else PAGE
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Content-Type", "application/octet-stream" if self.path == "/sample" else "text/html")
        if self.path == "/sample":
            self.send_header("Content-Disposition", 'attachment; filename="sample.txt"')
        self.end_headers(); self.wfile.write(body)
    def log_message(self, *args):
        pass


VIEWER = '''import sys
from pathlib import Path
from PySide6.QtWidgets import QApplication, QTextEdit
from PySide6.QtCore import QTimer
app=QApplication([])
path=Path(sys.argv[1])
view=QTextEdit(); view.setPlainText(path.read_text()); view.setWindowTitle("MORICE owned Phase 3 viewer | "+path.name)
view.resize(500,280); view.show()
import os
print('fixture',os.getpid(),app.platformName(),int(view.winId()),view.isVisible(),flush=True)
QTimer.singleShot(20000,app.quit)
app.exec()
'''


def main():
    parser = argparse.ArgumentParser(); parser.add_argument("--output", default="build/phase3-demos.json"); args = parser.parse_args()
    output_path = Path(args.output).resolve()
    app = QApplication([])
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server_thread = threading.Thread(target=server.serve_forever, daemon=True); server_thread.start()
    base_url = f"http://127.0.0.1:{server.server_port}"
    values, errors, children = {}, [], []
    with tempfile.TemporaryDirectory(prefix="morice-phase3-") as directory:
        root = Path(directory); (root / "viewer.py").write_text(VIEWER, encoding="utf-8")
        begin = time.perf_counter(); services = RuntimeServices(root / "runtime", project_root=root)
        values["constructor_ms"] = (time.perf_counter() - begin) * 1000
        for permission in PermissionCategory:
            services.pc_permissions.set_policy(permission, PolicyMode.ALLOW)
        # A visible offscreen view and an off-the-record owned profile avoid
        # shared disk-cache locks and hidden-page lifecycle throttling. This is
        # actual DOM/navigation verification, with the same action contracts.
        profile=QWebEngineProfile(app)
        view = QWebEngineView();view.setPage(QWebEnginePage(profile,view));view.show()
        bridge = QtBrowserBridge(view, roots=(root,));fixture_token=CancellationToken()
        services.pc_browser.bridge = bridge
        output_path.parent.mkdir(parents=True,exist_ok=True)
        def progress(stage):
            values['current_stage']=stage
            output_path.with_suffix('.partial.json').write_text(json.dumps(values,indent=2),encoding='utf-8')
        def launch_viewer(path):
            environment = dict(os.environ); environment["QT_QPA_PLATFORM"] = "windows" if os.name == "nt" else "offscreen"
            stream = (root / f"viewer-{len(children)}.log").open("wb")
            process = subprocess.Popen([sys.executable, str(root / "viewer.py"), str(path)], env=environment,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), stdout=stream, stderr=stream)
            stream.close()
            children.append(process)
            return {"viewerPid": process.pid}
        services.desktop.files.open = launch_viewer
        def launch_artifact(inputs, context):
            detail = launch_viewer(inputs["target"])
            return ExecutionResult(TaskStatus.SUCCEEDED, True, output={"applicationPid": detail["viewerPid"]})
        observer = DesktopObserver(services.desktop)
        for name, handler, health in (("demo.app.preferred", lambda *args: None, lambda: CapabilityHealth(Availability.UNAVAILABLE, "Preferred fixture provider unavailable.")),
            ("demo.app.fallback", launch_artifact, None)):
            services.kernel.registry.register(CapabilityDescriptor(name, name, supports_retry=True,
                supported_resources=(ResourceClaim("FOREGROUND_UI", exclusive=True),), required_permissions=("application_control",)), handler, health_check=health)
            services.actions.register(name, ActionBinding(ActionMethod.OPERATING_SYSTEM, lambda *args: {"verb": "open"}, observer.applications, verify_application))
        def run(cap, inputs, **fields):
            progress(cap)
            task = TaskNode(cap, inputs, **fields)
            context = ExecutionContext(cancellation_token=fixture_token)
            if cap in {"browser.click", "browser.submit", "browser.upload"}:
                action = ControlAction("browser", cap.split(".", 1)[1], inputs.get("target", ""), inputs.get("arguments", {}),
                    (PermissionCategory.BROWSER_CONTROL, PermissionCategory.NETWORK_ACCESS), ActionRisk.DESTRUCTIVE, action_id=task.task_id)
                context = ExecutionContext(approval_token=services.pc_permissions.request_confirmation(action).token,cancellation_token=fixture_token)
            result = services.kernel.run_task(task, context)
            values.setdefault("actions", []).append({"capability": cap, "success": result.success,
                "status": result.status.value, "verification": result.verification.status.value if result.verification else None,
                "metrics": result.metrics, "errors": [e.message for e in result.errors]})
            return result
        def require(result, message):
            if not result.success:
                raise AssertionError(message + ": " + str(result.to_dict()))
        def worker():
            try:
                progress('initial-observation')
                bridge.observe({}, ExecutionContext(deadline=time.monotonic()+3, cancellation_token=fixture_token))
                begin = time.perf_counter()
                require(run("browser.open", {"target": base_url + "/"}), "Real navigation")
                require(run("browser.type", {"target": "", "arguments": {"element": {"role": "textbox", "name": "Email"}, "value": "local@example.test"}}), "Semantic typing")
                require(run("browser.click", {"target": "", "arguments": {"element": {"role": "button", "name": "Update"}, "expected_text": "Updated"}}), "Dynamic semantic click")
                require(run("browser.click", {"target": "", "arguments": {"element": {"role": "button", "name": "Update"}, "expected_text": "Updated"}}), "Changed DOM identifier")
                wrong = run("browser.open", {"target": base_url + "/redirect"}, constraints={"observation_timeout": .15, "max_observations": 8})
                if wrong.success:
                    raise AssertionError("Wrong redirect falsely passed")
                require(run("browser.open", {"target": base_url + "/"}), "Return to controlled page")
                require(run("browser.tab_open", {"target": base_url + "/wrong", "arguments": {"tab_id": "second"}}), "Actual second tab")
                require(run("browser.tab_switch", {"target": "", "arguments": {"tab_id": "main"}}), "Actual tab switch")
                require(run("browser.tab_close", {"target": "", "arguments": {"tab_id": "second"}}), "Actual tab close")
                sample = root / "sample.txt"
                require(run("browser.download", {"target": base_url + "/sample", "arguments": {"path": str(sample), "sha256": hashlib.sha256(BODY).hexdigest()}}), "Real download")
                require(run("artifact.verify", {"path": str(sample), "sha256": hashlib.sha256(BODY).hexdigest()}), "Independent artifact check")
                require(run("file.open", {"target": str(sample)}, constraints={"observation_timeout":8,"max_observations":64}), "Actual document-associated viewer")
                values["browser_file_demo"] = {"success": True, "duration_ms": (time.perf_counter()-begin)*1000,
                    "bytes": sample.stat().st_size, "sha256": hashlib.sha256(sample.read_bytes()).hexdigest()}
                # Real subprocess verifies a tiny generated project's result.
                artifact = root / "result.txt"
                command = [sys.executable, "-c", "from pathlib import Path; assert sum([2,3])==5; Path('result.txt').write_text('5\\n'); print('actual test passed')"]
                inputs = {"cwd": str(root), "command": command, "timeout": 5}
                approval = services.agent.tools.permissions.grant("terminal.run", inputs)
                result = services.kernel.run_task(TaskNode("terminal.run", inputs), ExecutionContext(approval_token=approval))
                require(result, "Actual test/build process")
                require(run("demo.app.fallback", {"target": str(artifact)}), "Actual result window")
                values["project_app_demo"] = {"success": True, "exit_code": result.output["exitCode"], "stdout": result.output["stdout"]}
                recovered = run("demo.app.preferred", {"target": str(artifact)}, retry_policy=RetryPolicy(2,
                    (ErrorCode.CAPABILITY_UNAVAILABLE,), alternative_capabilities=("demo.app.fallback",)))
                require(recovered, "Observed fallback application")
                values["recovery_demo"] = {"success": True, "attempts": recovered.metrics["attempts"],
                    "journal": list(services.actions.journal.attempts(recovered.task_id))}
                # Phase 2 workers use these same capabilities and shared leases.
                services.agents.roles.register(AgentRole("desktop_fixture", "Desktop fixture", "Owned local fixtures", ("demo.app.fallback",), result_schema={}))
                graph = TaskGraph((TaskNode("browser.open", {"target": base_url + "/"}, constraints={"role": "browser"}),
                    TaskNode("filesystem.read", {"path": str(sample)}, constraints={"role": "researcher"}),
                    TaskNode("demo.app.fallback", {"target": str(artifact)}, constraints={"role": "desktop_fixture"}, dependencies=())))
                progress('parallel-integration')
                result = services.agents.run(graph,ExecutionContext(cancellation_token=fixture_token))
                if not result.success:
                    raise AssertionError("Parallel integration: " + str(result.to_dict()))
                values["parallel_integration"] = {"success": True, "worker_states": [v["state"] for v in services.agents.workers.snapshot(graph.graph_id)]}
                values["memory_mb"] = _process_memory_mb(); values["leases_after"] = len(services.kernel.resources.snapshot())
            except BaseException as exc:
                errors.append(f"{type(exc).__name__}: {exc}")
            finally:
                completed.set()
        completed = threading.Event(); thread = threading.Thread(target=worker)
        # Chromium process startup is fixture readiness, not action execution.
        # Keep the existing three-second observation deadline once a real page
        # has loaded. The overall watchdog still bounds startup and all work.
        started_worker=False
        def ready(ok):
            nonlocal started_worker
            if ok and not started_worker:
                started_worker=True;values['browser_bootstrap_loaded']=True;thread.start()
        view.loadFinished.connect(ready)
        QTimer.singleShot(0,lambda:view.setHtml('<!doctype html><title>Owned browser readiness</title>',QUrl('about:blank')))
        timer = QTimer(); timer.setInterval(10); timer.timeout.connect(lambda: app.quit() if completed.is_set() else None); timer.start()
        def expired():
            errors.append('Fixture deadline reached at '+values.get('current_stage','browser-bootstrap'))
            fixture_token.cancel('Owned fixture watchdog')
            if not started_worker:completed.set();app.quit()
            else:QTimer.singleShot(2000,app.quit)
        watchdog = QTimer(); watchdog.setSingleShot(True); watchdog.timeout.connect(expired); watchdog.start(45000)
        app.exec()
        if started_worker:thread.join(2)
        values["errors"] = errors
        values["completed"] = completed.is_set()
        values["journal_count"] = len(services.actions.journal.attempts())
        values["journal"] = list(services.actions.journal.attempts())
        from dataclasses import asdict
        values["owned_windows"] = [asdict(w) for w in services.desktop.windows.list_windows() if w.pid in {p.pid for p in children}]
        values["viewer_logs"] = [p.read_text(errors="replace") for p in root.glob("viewer-*.log")]
        values["child_exits"] = [p.poll() for p in children]
        services.shutdown()
        for child in children:
            from morice.action_runtime.desktop import process_family
            family = process_family(child.pid)
            for window in services.desktop.windows.list_windows():
                if window.pid in family:
                    grant = services.desktop.windows.request(window.handle, "close")
                    services.desktop.windows.control(window.handle, "close", grant.token)
            try:
                child.wait(timeout=3)
            except subprocess.TimeoutExpired:
                child.terminate(); child.wait(timeout=3)  # Only the owned test fixture.
        view.close(); server.shutdown()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(values, indent=2), encoding="utf-8")
        print(json.dumps({"output": str(output_path), "completed": values["completed"], "errors": errors}))
        return 1 if errors or not values["completed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
