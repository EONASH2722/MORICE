"""Inspect local wheel/source parity and Android artifacts; no publication."""
import hashlib
import json
import zipfile
from pathlib import Path

root = Path(__file__).resolve().parents[1]
wheel = next((root / "build/phase5-package").glob("*.whl"))
with zipfile.ZipFile(wheel) as archive:
    assert archive.testzip() is None
    modules = []
    for package in ("kernel", "agent_runtime", "action_runtime", "project_build", "device_mesh"):
        for source in (root / "morice" / package).glob("*.py"):
            name = source.relative_to(root).as_posix()
            assert archive.read(name) == source.read_bytes(), name
            modules.append(name)
    entrypoints = ["morice/node_protocol.py", "morice/runtime_services.py", "morice/settings.py", "morice/pyside_app.py"]
    for name in entrypoints:
        assert archive.read(name) == (root / name).read_bytes(), name
result = {"wheel": str(wheel), "bytes": wheel.stat().st_size,
          "sha256": hashlib.sha256(wheel.read_bytes()).hexdigest(),
          "source_equal_runtime_modules": len(modules), "mesh_modules": sum("/device_mesh/" in name for name in modules), "zip_integrity": True}
result["source_equal_entrypoint_modules"] = len(entrypoints)
result["android"] = []
for apk in (root / "android/app/build/outputs/apk/debug/app-debug.apk", root / "android/app/build/outputs/apk/androidTest/debug/app-debug-androidTest.apk"):
    with zipfile.ZipFile(apk) as archive: assert archive.testzip() is None
    result["android"].append({"path": str(apk), "bytes": apk.stat().st_size, "sha256": hashlib.sha256(apk.read_bytes()).hexdigest(), "compiled_only": True})
(root / "build/phase5-package.json").write_text(json.dumps(result, indent=2))
print(json.dumps(result, indent=2))
