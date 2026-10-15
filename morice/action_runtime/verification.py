"""Domain comparisons operate on observed values, never command acknowledgements."""
from __future__ import annotations

import hashlib
from pathlib import Path
from urllib.parse import urlsplit, parse_qsl, urlencode

from ..kernel import VerificationResult, VerificationStatus
from .contracts import Observation


def checked(valid, observation, message):
    return VerificationResult(VerificationStatus.VERIFIED if valid else VerificationStatus.FAILED,
        observation.evidence if valid else (), "" if valid else message)


def normalized_url(value):
    parsed = urlsplit(value)
    port = parsed.port
    host = (parsed.hostname or "").casefold()
    if port and not (parsed.scheme == "http" and port == 80 or parsed.scheme == "https" and port == 443):
        host += f":{port}"
    query = urlencode(sorted((k, v) for k, v in parse_qsl(parsed.query, keep_blank_values=True)
        if not k.casefold().startswith("utm_") and k.casefold() not in {"gclid", "fbclid"}))
    return parsed.scheme.casefold(), host, parsed.path or "/", query


def verify_application(spec, observation, before):
    windows = observation.state.get("windows", [])
    verb = spec.desired_state["verb"]
    usable = [w for w in windows if w.get("visible", True) and w.get("enabled", True)
        and not w.get("minimized") and w["rect"][2] > w["rect"][0] and w["rect"][3] > w["rect"][1]]
    if verb in {"close", "close_others"}:
        valid = bool(before and (before.state.get("windows") or verb == "close_others")) and not windows
    elif verb == "focus":
        valid = len(usable) == 1 and observation.state.get("active_handle") == usable[0]["handle"]
    elif verb == "minimize":
        valid = len(windows) == 1 and windows[0].get("minimized", False)
    elif verb == "maximize":
        valid = len(usable) == 1 and usable[0].get("maximized", False)
    else:
        valid = len(usable) == 1
    return checked(valid, observation, "A usable window in the requested state was not observed.")


def observe_files(spec, context, result=None, before=None):
    files = []
    for desired in spec.desired_state.get("files", []):
        path = Path(desired["path"]).resolve()
        if desired.get("exists") is False:
            files.append({"path": str(path), "exists": path.exists()})
            continue
        if not path.is_file() or path.suffix.casefold() in {".part", ".tmp", ".crdownload"}:
            files.append({"path": str(path), "exists": False})
            continue
        # Streaming checks are bounded by the task deadline and cancellation.
        digest = hashlib.sha256()
        count = 0
        with path.open("rb") as stream:
            while chunk := stream.read(1024 * 1024):
                context.cancellation_token.raise_if_cancelled()
                if __import__("time").monotonic() >= context.deadline:
                    raise TimeoutError("Artifact observation deadline.")
                digest.update(chunk)
                count += len(chunk)
        files.append({"path": str(path), "exists": True, "size": count, "sha256": digest.hexdigest()})
    return Observation(spec.action_id, "filesystem.readback", {"files": files},
        tuple(f"Read back {v['path']}: {v.get('size', 0)} bytes; SHA-256 {v.get('sha256', 'missing')}." for v in files))


def verify_files(spec, observation, before):
    desired = spec.desired_state.get("files", [])
    actual = observation.state.get("files", [])
    valid = bool(desired) and len(desired) == len(actual)
    for expected, value in zip(desired, actual):
        if expected.get("exists") is False:
            valid = valid and value.get("exists") is False
            continue
        valid = valid and value.get("exists", False) and value.get("size", 0) >= expected.get("min_size", 0)
        if expected.get("sha256"):
            valid = valid and expected["sha256"] == value.get("sha256")
    return checked(valid, observation, "The actual artifact bytes do not match the requested result.")


def verify_browser(spec, observation, before):
    state = observation.state
    desired = spec.desired_state
    if state.get("available") is not True:
        return VerificationResult(VerificationStatus.INCONCLUSIVE, message="Browser state cannot be observed with this provider.")
    valid = state.get("loaded") is True
    if desired.get("url"):
        valid = valid and normalized_url(state.get("url", "")) == normalized_url(desired["url"])
    if desired.get("text"):
        valid = valid and desired["text"] in state.get("text", "")
    if desired.get("element"):
        element = state.get("element", {})
        valid = valid and element.get("count") == 1
        if "value" in desired:
            valid = valid and element.get("value") == desired["value"]
    if desired.get("generation_after") and before:
        valid = valid and state.get("generation", 0) > before.state.get("generation", 0)
    if desired.get("url_changed") and before:
        valid = valid and state.get("url") != before.state.get("url")
    return checked(valid, observation, "The requested page or element state was not observed.")
