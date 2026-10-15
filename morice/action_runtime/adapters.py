"""Bind existing providers to independent observations and desired-state checks."""
from __future__ import annotations

import hashlib
from pathlib import Path

from ..kernel import CapabilityDescriptor, ErrorCode, ExecutionResult, ResourceClaim, ResourceDescriptor, TaskStatus, VerificationResult, VerificationStatus
from .contracts import ActionBinding, ActionMethod, Observation
from .desktop import DesktopObserver
from .verification import checked, observe_files, verify_files, verify_application, verify_browser


def install_action_adapters(runtime, desktop, browser, pc_registry, tools):
    kernel = runtime.kernel
    observer = DesktopObserver(desktop)
    for verb in ("open", "focus", "restore", "maximize", "minimize", "close", "close_others"):
        runtime.register(f"application.{verb}", ActionBinding(ActionMethod.OPERATING_SYSTEM,
            lambda inputs, expected, v=verb: {"verb": v}, observer.applications, verify_application,
            idempotent=verb not in {"close", "close_others"}))
    for verb in ("open", "reveal", "open_recent"):
        runtime.register(f"file.{verb}", ActionBinding(ActionMethod.OPERATING_SYSTEM,
            lambda inputs, expected: {"document": str(Path(inputs.get("target", "")).resolve())}, observer.file_viewer,
            lambda spec, observed, before: checked(observed.state.get("document_association") is True,
                observed, "The requested document/viewer association was not independently observed.")))

    def patch_desired(inputs, expected):
        root = Path(inputs["root"]).resolve()
        files = []
        for change in inputs["changes"]:
            path = (root / change["path"]).resolve()
            if not path.is_relative_to(root):
                raise ValueError("Patch target escapes the approved workspace.")
            files.append({"path": str(path), "sha256": hashlib.sha256(change["content"].encode("utf-8")).hexdigest()})
        return {"files": files}
    runtime.register("filesystem.apply_patch", ActionBinding(ActionMethod.FILESYSTEM,
        patch_desired, observe_files, verify_files, idempotent=False))  # Preserve existing approved baseline checks/undo metadata.

    def undo_desired(inputs, expected):
        import json
        record = tools.undo_store.directory / inputs["undo_id"]
        manifest = json.loads((record / "manifest.json").read_text(encoding="utf-8"))
        root = Path(manifest["root"]).resolve()
        files = []
        for item in manifest["entries"]:
            path = (root / item["path"]).resolve()
            if not path.is_relative_to(root):
                raise ValueError("Undo target escapes its recorded workspace.")
            if item["existed"]:
                backup = (record / item["backup"]).resolve()
                if not backup.is_relative_to(record.resolve()):
                    raise ValueError("Undo backup escapes its record.")
                files.append({"path": str(path), "sha256": hashlib.sha256(backup.read_bytes()).hexdigest()})
            else:
                files.append({"path": str(path), "exists": False})
        return {"files": files}
    runtime.register("action.undo", ActionBinding(ActionMethod.FILESYSTEM, undo_desired, observe_files, verify_files))

    def process_observe(spec, context, result=None, before=None):
        value = result.output if result and isinstance(result.output, dict) else {}
        code = value.get("exitCode")
        return Observation(spec.action_id, "owned_process.communicate", {"exit_code": code,
            "timed_out": value.get("timedOut", False), "cancelled": value.get("cancelled", False)},
            (f"Owned subprocess was reaped with exit code {code}.",) if code is not None else ())
    runtime.register("terminal.run", ActionBinding(ActionMethod.CLI,
        lambda inputs, expected: {"exit_code": 0}, process_observe,
        lambda spec, observed, before: checked(observed.state.get("exit_code") == 0
            and not observed.state.get("timed_out") and not observed.state.get("cancelled"), observed,
            "The owned command did not finish successfully.")))

    for verb in ("open", "navigate", "back", "forward", "reload", "find", "click", "type", "submit", "extract", "tab_open", "tab_switch", "tab_close", "upload", "download"):
        def desired(inputs, expected, v=verb):
            args = inputs.get("arguments", {})
            result = {"verb": v}
            if v in {"open", "navigate", "tab_open"}:
                from ..pc_control import BrowserAdapter
                result["url"] = BrowserAdapter._validated_url(inputs.get("target", ""))
            if v in {"find", "type", "click", "submit", "upload"}:
                result["element"] = args.get("element", {})
            if v == "type":
                if "value" not in args:
                    raise ValueError("An explicit input value is required.")
                result["value"] = str(args.get("value", ""))
            if args.get("expected_url"):
                result["url"] = args["expected_url"]
            if args.get("expected_text"):
                result["text"] = args["expected_text"]
            if v in {"back", "forward"}:
                result["url_changed"] = True
            if v == "reload":
                result["generation_after"] = True
            if v.startswith("tab_"):
                result["tab_id"] = args.get("tab_id", "")
            if v == "download":
                result["files"] = [{"path": str(Path(args["path"]).resolve()), "min_size": int(args.get("min_size", 1)),
                    "sha256": args.get("sha256", "")}]
            if v in {"click", "submit"} and not result.get("url") and not result.get("text"):
                result["missing_outcome"] = True
            return result
        def observe(spec, context, result=None, before=None):
            observed = browser.observe(spec.desired_state, context)
            if not isinstance(observed, dict):
                raise ValueError("Browser observation unavailable.")
            # Browser text is untrusted data. Retain only goal comparisons and
            # bounded text in the transient verifier; journal redacts its contents.
            if before is None and spec.desired_state["verb"] in {"open", "navigate", "tab_open", "tab_switch", "tab_close"}:
                observed["waiting_for_user"] = False
            evidence = (f"Observed browser URL {observed.get('url', '')}; loaded={observed.get('loaded', False)}.",)
            if spec.desired_state["verb"] == "download":
                files = observe_files(spec, context, result, before)
                observed.update(files.state)
                evidence += files.evidence
            return Observation(spec.action_id, "qt.browser.dom", observed,
                evidence,
                timestamp=float(observed.get("timestamp", __import__("time").time())))
        def verify(spec, observed, before):
            v = spec.desired_state["verb"]
            if spec.desired_state.get("missing_outcome") or v == "upload":
                return VerificationResult(VerificationStatus.INCONCLUSIVE, message="An independently observable outcome is required.")
            if v == "download":
                file_check = verify_files(spec, observed, before)
                complete = all(observed.state.get("downloads", {}).get(f["path"], {}).get("completed") is True for f in spec.desired_state["files"])
                return file_check if complete else VerificationResult(VerificationStatus.FAILED, message="Download completion has not been observed.")
            if v == "tab_close":
                return checked(spec.desired_state["tab_id"] not in observed.state.get("tabs", []), observed, "Tab remains open.")
            if v in {"tab_open", "tab_switch"} and observed.state.get("tab_id") != spec.desired_state["tab_id"]:
                return VerificationResult(VerificationStatus.FAILED, message="Requested tab is not active.")
            return verify_browser(spec, observed, before)
        runtime.register(f"browser.{verb}", ActionBinding(ActionMethod.BROWSER_DOM, desired, observe, verify,
            idempotent=verb in {"open", "navigate", "find"}))

    from ..pc_control import DesktopMediaAdapter
    for verb in ("set_volume", "pause", "resume", "mute", "volume", "next", "previous", "restart", "play_query", "status"):
        def media_desired(inputs, expected, v=verb):
            return {"verb": v, "percent": float(inputs.get("arguments", {}).get("percent", 0)),
                "arguments": inputs.get("arguments", {}), "target": inputs.get("target", "")}
        def media_observe(spec, context, result=None, before=None):
            args = context.metadata["task_inputs"].get("arguments", {})
            state = DesktopMediaAdapter._status(desktop.media, str(args.get("provider", "")), fast=True)
            return Observation(spec.action_id, "media.session", state, ("Actual media session queried after command.",))
        def media_verify(spec, observed, before):
            v = spec.desired_state["verb"]
            state = observed.state
            if v == "set_volume":
                volume = state.get("volume")
                valid = isinstance(volume, (int, float)) and abs(volume - spec.desired_state["percent"]) <= 1
            elif v == "mute":
                valid = state.get("muted") is True
            elif v in {"volume", "next", "previous", "restart", "play_query"}:
                from ..pc_control import ControlAction
                action = ControlAction("media", v, spec.desired_state["target"], spec.desired_state["arguments"])
                valid = bool(before) and DesktopMediaAdapter(desktop)._verify(action, before.state, state)
                if v == "play_query":
                    query = str(action.arguments.get("query", action.target)).casefold()
                    valid = valid and bool(query) and query in str(state.get("currentTrack", "")).casefold()
            elif v == "status":
                valid = bool(state.get("sessionAvailable") or state.get("amazonUi"))
            else:
                valid = DesktopMediaAdapter._playback_state(state) == ("paused" if v == "pause" else "playing")
            return checked(valid, observed, "The desired media state was not observed.")
        runtime.register(f"media.{verb}", ActionBinding(ActionMethod.APPLICATION_API, media_desired, media_observe, media_verify,
            idempotent=verb in {"set_volume", "pause", "resume", "mute"}))

    kernel.registry.register(CapabilityDescriptor("artifact.verify", "Verify artifact bytes", supports_verification=True,
        required_permissions=("file_read",), input_schema={"type": "object", "required": ["path"], "properties": {"path": {"type": "string"}}}),
        lambda inputs, ctx: ExecutionResult(TaskStatus.SUCCEEDED, True, output={"path": inputs["path"]}),
        verifier=lambda *args: VerificationResult(VerificationStatus.INCONCLUSIVE))
    runtime.register("artifact.verify", ActionBinding(ActionMethod.FILESYSTEM,
        lambda inputs, expected: {"files": [{"path": str(Path(inputs["path"]).resolve()), "min_size": inputs.get("min_size", 1), "sha256": inputs.get("sha256", "")}]},
        observe_files, verify_files, idempotent=True))
