from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
import textwrap
import zipfile
from pathlib import Path

from .plugin_manager import PluginManager
from .plugin_sdk import PluginManifest, PluginValidationError


MANIFEST_TEMPLATE = {
    "id": "example.hello",
    "name": "Hello MORICE",
    "version": "1.0.0",
    "apiVersion": "1.0",
    "description": "A minimal MORICE extension.",
    "author": "Plugin developer",
    "entryPoint": "plugin.py",
    "license": "MIT",
    "categories": ["tool", "productivity"],
    "permissions": ["notifications"],
    "platforms": ["any"],
    "minMoriceVersion": "0.6.0",
    "contributions": {
        "commands": [
            {
                "id": "say-hello",
                "title": "Say hello",
                "description": "Show a greeting from the sample plugin.",
                "keywords": ["sample", "hello"],
            }
        ],
        "tools": [
            {
                "id": "example.hello.greet",
                "title": "Plugin greeting",
                "description": "Return a greeting for a supplied name.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "maxLength": 120}
                    },
                    "required": ["name"],
                    "additionalProperties": False,
                },
                "outputSchema": {"type": "object"},
                "timeoutSeconds": 5,
            }
        ],
    },
}


PLUGIN_TEMPLATE = textwrap.dedent(
    """\
    class Plugin:
        def __init__(self, api):
            self.api = api

        def on_start(self):
            self.api.log("INFO", "Hello MORICE plugin started.")

        def on_stop(self):
            self.api.log("INFO", "Hello MORICE plugin stopped.")

        def handle_command(self, command_id, arguments):
            if command_id == "say-hello":
                if self.api.has_permission("notifications"):
                    self.api.notify("Hello MORICE", "The sample plugin is running.")
                return {"message": "Hello from the MORICE Plugin SDK."}
            raise ValueError(f"Unknown command: {command_id}")

        def handle_tool(self, tool_id, arguments):
            if tool_id == "example.hello.greet":
                name = str(arguments.get("name", "there")).strip()[:120]
                return {"greeting": f"Hello, {name}."}
            raise ValueError(f"Unknown tool: {tool_id}")
    """
)


README_TEMPLATE = textwrap.dedent(
    """\
    # Hello MORICE Plugin

    This is a minimal process-isolated MORICE Plugin SDK sample.

    ## Develop

    Validate it:

    ```powershell
    python -m morice.plugin_cli validate .
    ```

    Package it:

    ```powershell
    python -m morice.plugin_cli pack . --output hello-morice.zip
    ```

    MORICE always shows the declared permission list before the plugin starts.
    """
)


def create_plugin(directory: Path, plugin_id: str, name: str) -> Path:
    if directory.exists() and any(directory.iterdir()):
        raise FileExistsError(f"Destination is not empty: {directory}")
    directory.mkdir(parents=True, exist_ok=True)
    manifest = json.loads(json.dumps(MANIFEST_TEMPLATE))
    manifest["id"] = plugin_id
    manifest["name"] = name
    manifest["contributions"]["tools"][0]["id"] = f"{plugin_id}.greet"
    (directory / "plugin.json").write_text(
        json.dumps(manifest, ensure_ascii=True, indent=2),
        encoding="utf-8",
    )
    (directory / "plugin.py").write_text(
        PLUGIN_TEMPLATE.replace("example.hello.greet", f"{plugin_id}.greet"),
        encoding="utf-8",
    )
    (directory / "README.md").write_text(README_TEMPLATE, encoding="utf-8")
    return directory


def validate_plugin(directory: Path) -> PluginManifest:
    manifest = PluginManifest.from_path(directory / "plugin.json")
    entry = (directory / manifest.entry_point).resolve()
    entry.relative_to(directory.resolve())
    if not entry.is_file():
        raise PluginValidationError(
            f"Plugin entry point does not exist: {manifest.entry_point}"
        )
    compile(entry.read_text(encoding="utf-8"), str(entry), "exec")
    return manifest


def pack_plugin(directory: Path, output: Path) -> Path:
    manifest = validate_plugin(directory)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary_dir = Path(tempfile.mkdtemp(prefix="morice-pack-"))
    try:
        archive = temporary_dir / output.name
        ignored = {".git", "__pycache__", ".pytest_cache", ".mypy_cache"}
        with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as bundle:
            for path in sorted(directory.rglob("*")):
                relative = path.relative_to(directory)
                if any(part in ignored for part in relative.parts) or path.is_symlink():
                    continue
                if path.is_file():
                    bundle.write(path, relative.as_posix())
        shutil.move(str(archive), str(output))
    finally:
        shutil.rmtree(temporary_dir, ignore_errors=True)
    print(f"Packed {manifest.plugin_id} {manifest.version}: {output}")
    return output


def _manager(args: argparse.Namespace) -> PluginManager:
    return PluginManager(
        Path(args.runtime).expanduser(),
        core_root=Path(__file__).resolve().parents[1],
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="morice-plugin",
        description="Build, validate, package, and inspect MORICE plugins.",
    )
    parser.add_argument(
        "--runtime",
        default=str(Path.home() / ".morice-plugin-dev"),
        help="Plugin runtime directory for install/list/doctor commands.",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    init = commands.add_parser("init", help="Create a sample plugin.")
    init.add_argument("directory")
    init.add_argument("--id", default="example.hello")
    init.add_argument("--name", default="Hello MORICE")
    validate = commands.add_parser("validate", help="Validate a plugin directory.")
    validate.add_argument("directory")
    pack = commands.add_parser("pack", help="Create a safe plugin ZIP package.")
    pack.add_argument("directory")
    pack.add_argument("--output", required=True)
    install = commands.add_parser("install", help="Install a plugin ZIP.")
    install.add_argument("package")
    commands.add_parser("list", help="List installed plugins.")
    commands.add_parser("doctor", help="Print plugin diagnostics.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "init":
            path = create_plugin(Path(args.directory), args.id, args.name)
            print(f"Created MORICE plugin at {path.resolve()}")
        elif args.command == "validate":
            manifest = validate_plugin(Path(args.directory))
            print(f"Valid: {manifest.plugin_id} {manifest.version}")
        elif args.command == "pack":
            pack_plugin(Path(args.directory), Path(args.output))
        elif args.command == "install":
            manager = _manager(args)
            manager.discover()
            record = manager.install(args.package)
            print(f"Installed: {record.manifest.plugin_id} {record.manifest.version}")
        elif args.command == "list":
            manager = _manager(args)
            records = manager.discover()
            for record in records:
                print(
                    f"{record.manifest.plugin_id}\t{record.manifest.version}\t"
                    f"{record.state.value}"
                )
        elif args.command == "doctor":
            manager = _manager(args)
            manager.discover()
            print(json.dumps(manager.diagnostics(), ensure_ascii=True, indent=2))
        return 0
    except (OSError, ValueError, PluginValidationError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
