"""Versioned reproducibility packages, verified by reopening actual outputs."""
from __future__ import annotations
from ..numeric_format import format_number

import csv
import hashlib
import html
import json
import uuid
from pathlib import Path
from xml.etree import ElementTree

from .ingestion import checkpoint


def verify_project(snapshot):
    records = {r["id"]: r for r in snapshot["records"]}
    issues = []
    for record in records.values():
        if record["stale"]:
            issues.append({"record": record["id"], "issue": "STALE / requires recomputation"})
        if record["kind"] == "source":
            source = record["payload"]
            path = Path(source["blob"])
            if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != source["sha256"]:
                issues.append({"record": record["id"], "issue": "Evidence blob missing or checksum mismatch"})
    for edge in snapshot["edges"]:
        if edge["source"] not in records or edge["target"] not in records:
            issues.append({"record": edge["source"], "issue": "Dangling research relationship"})
        if edge["relation"] == "contradicted_by":
            issues.append({"record": edge["source"], "issue": "Conflicting evidence recorded; no consensus assumed"})
    return {"integrity_passed": not issues, "issues": issues,
            "scope": "Stored file checksums, dependency freshness and relationship integrity only; not scientific peer review."}


def export_package(snapshot, root, cancel=None):
    checkpoint(cancel)
    destination = Path(root) / (snapshot["id"] + "-" + uuid.uuid4().hex[:10])
    destination.mkdir(parents=True, exist_ok=False)
    files = []
    manifest = destination / "project_manifest.json"
    manifest.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    json.loads(manifest.read_text(encoding="utf-8"))
    files.append(manifest)
    validation = verify_project(snapshot)
    report = ["# " + snapshot["objective"].replace("\n", " "), "",
              "Research records and provenance. Model interpretations are unverified.", "",
              "## Integrity checks", json.dumps(validation, ensure_ascii=False), ""]
    for record in snapshot["records"]:
        checkpoint(cancel)
        report += [f"## {record['title']}",
                   f"Record: {record['id']} | {record['provenance']} | {'STALE' if record['stale'] else 'recorded'}", ""]
        payload = record["payload"]
        if record["kind"] == "result" and "text" in payload:
            report += [payload["text"], ""]
        if record["kind"] == "source":
            source_path = Path(payload["blob"])
            if not source_path.is_file():
                continue
            raw = source_path.read_bytes()
            if hashlib.sha256(raw).hexdigest() != payload["sha256"]:
                raise ValueError("Cannot export evidence with a failing checksum.")
            sources = destination / "sources"
            sources.mkdir(exist_ok=True)
            copy = sources / (payload["sha256"] + payload["format"])
            copy.write_bytes(raw)
            files.append(copy)
        if record["kind"] == "dataset":
            table = payload["result"]
            table_path = destination / (record["id"] + "-statistics.csv")
            with table_path.open("w", encoding="utf-8", newline="") as stream:
                writer = csv.writer(stream)
                writer.writerow(["column", "count", "missing", "mean", "median", "min", "max", "sample_std"])
                for column in table["columns"]:
                    # Spreadsheet formula injection is data, not executable export.
                    label = column["name"]
                    if label.lstrip().startswith(("=", "+", "-", "@")):
                        label = "'" + label
                    writer.writerow([label] + [column.get(k, "") for k in ("count", "missing", "mean", "median", "min", "max", "sample_std")])
            with table_path.open(encoding="utf-8", newline="") as stream:
                if len(list(csv.reader(stream))) != len(table["columns"]) + 1:
                    raise ValueError("Generated statistics CSV failed verification.")
            files.append(table_path)
            for index, column in enumerate(table["columns"]):
                points = column.get("plot_sample", [])
                if not points:
                    continue
                low, high = min(p[1] for p in points), max(p[1] for p in points)
                span = high - low or 1
                coords = " ".join(f"{50 + (x - 1) * 700 / max(1, points[-1][0] - 1):.2f},{240 - (y - low) * 180 / span:.2f}" for x, y in points)
                svg = ('<svg xmlns="http://www.w3.org/2000/svg" width="820" height="300" viewBox="0 0 820 300">'
                       '<rect width="820" height="300" fill="white"/>'
                       f'<text x="50" y="25">{html.escape(column["name"])} — first 500 rows, original row index</text>'
                       '<path d="M50 50V240H750" fill="none" stroke="#444"/>'
                       f'<text x="4" y="65">{format_number(high)}</text><text x="4" y="240">{format_number(low)}</text>'
                       + ''.join(f'<circle cx="{xy.split(",")[0]}" cy="{xy.split(",")[1]}" r="2" fill="#14657b"/>' for xy in coords.split())
                       + '</svg>')
                plot = destination / f"{record['id']}-{index}.svg"
                plot.write_text(svg, encoding="utf-8")
                ElementTree.parse(plot)
                files.append(plot)
    report_path = destination / "README.md"
    report_path.write_text("\n".join(report), encoding="utf-8")
    files.append(report_path)
    checksums = {str(p.relative_to(destination)): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    (destination / "checksums.json").write_text(json.dumps(checksums, indent=2), encoding="utf-8")
    return {"directory": str(destination), "files": list(checksums), "checksums": checksums,
            "verification": validation}
