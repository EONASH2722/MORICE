"""Versioned reproducibility packages, verified by reopening actual outputs."""
from __future__ import annotations
from ..numeric_format import format_number

import csv
import hashlib
import html
import json
import ast
import textwrap
import importlib.util
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
    package_records = {}
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
        if record["kind"] in {"question","hypothesis","assumption","calculation","simulation","failure","validation","design","observation","result"}:
            encoded=json.dumps(payload,ensure_ascii=False,indent=2,allow_nan=False)
            report += ["```json",encoded[:5000],"```",("Payload excerpt truncated; full value is in project_manifest.json." if len(encoded)>5000 else "")]
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
            package_records[record['id']]={"source":str(copy.relative_to(destination)),"sha256":payload['sha256']}
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
        # Include only verified generated experiment outputs, never arbitrary
        # files referenced by source text. Current hashes are checked again.
        generated = payload.get("result",{}).get("artifacts",{}) if isinstance(payload.get("result"),dict) else {}
        if generated.get("directory") and generated.get("checksums"):
            from ..project_build.workspace import safe_path
            generated_root=Path(generated["directory"]).resolve(strict=True)
            for name,expected in generated["checksums"].items():
                source=safe_path(generated_root,name)
                raw=source.read_bytes()
                if len(raw)>25*1024**2 or hashlib.sha256(raw).hexdigest()!=expected:
                    raise ValueError("Generated experiment artifact changed or exceeded export limits.")
                target=safe_path(destination,f"experiments/{record['id']}/{name}")
                target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(raw);files.append(target)
            package_records.setdefault(record['id'],{})['experiment']=f"experiments/{record['id']}/experiment.json"
        design=payload.get("result",{})
        if isinstance(design,dict) and design.get("stl") and design.get("bom") and payload.get("method")=="research.cad":
            from .engineering import verify_box
            from ..project_build.workspace import safe_path
            if not verify_box(design): raise ValueError("Generated design changed; cannot export it as verified.")
            for key,hash_key in (("stl","sha256"),("bom","bom_sha256")):
                source=Path(design[key]);raw=source.read_bytes()
                target=safe_path(destination,f"designs/{record['id']}/{source.name}")
                target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(raw);files.append(target)
                package_records.setdefault(record['id'],{})[key]=str(target.relative_to(destination))
    index=destination/'package_index.json'
    index.write_text(json.dumps({"records":package_records,"path_base":"package directory","original_manifest":"project_manifest.json"},indent=2),encoding='utf-8')
    json.loads(index.read_text());files.append(index)
    calculations=[r["payload"] for r in snapshot["records"] if r["kind"]=="calculation" and not r["stale"]]
    calculations += [r['payload']['result'] for r in snapshot['records'] if not r['stale'] and r['payload'].get('method')=='research.calculate' and r['payload'].get('execution',{}).get('success')]
    calculation_path=destination/"calculations.json"
    calculation_path.write_text(json.dumps(calculations,indent=2,allow_nan=False),encoding="utf-8")
    json.loads(calculation_path.read_text());files.append(calculation_path)
    reproduction = 'from pathlib import Path\nimport json\nfrom morice.research.tools import ScientificTools\n'
    reproduction += 'root = Path(__file__).resolve().parent\nfor item in json.loads((root / "calculations.json").read_text(encoding="utf-8")):\n'
    reproduction += '    if "expression" in item and "parameter" not in item:\n        actual = ScientificTools().calculate(item["expression"], item["inputs"], item.get("requested_unit", ""))\n        assert actual["result"] == item["result"], "Reproduction differs"\n        print(actual["result"])\n'
    reproduction += '    elif "parameter" in item:\n        actual = ScientificTools().sweep(item["expression"], item["inputs"], item["parameter"], [r["parameter"] for r in item["result"]], item.get("requested_unit", ""))\n        assert actual["result"] == item["result"], "Sweep reproduction differs"\n'
    reproduction += 'import csv, math\nfrom morice.research.simulations import SimulationToolRegistry\nregistry = SimulationToolRegistry()\nfor manifest in root.glob("experiments/*/experiment.json"):\n'
    reproduction += '    experiment = json.loads(manifest.read_text(encoding="utf-8"))\n    tool_id = experiment["specification"]["simulation_engine"]\n    assert registry.fingerprint(tool_id) == experiment["estimate"]["model_fingerprint"], "Model/compiler version differs"\n'
    reproduction += '    tool = registry.get(tool_id)\n    count = 0\n    with manifest.with_name("results.csv").open(encoding="utf-8", newline="") as stream:\n        for row in csv.DictReader(stream):\n            if row["status"] == "INVALID": continue\n            parameters = {name: float(row[name + " [" + unit + "]"]) for name, unit in tool.required_units.items()}\n            actual = registry.run(tool_id, parameters)\n            assert all(math.isclose(actual[name], float(row[name + " [" + unit + "]"]), rel_tol=1e-10, abs_tol=1e-12) for name, unit in tool.supported_outputs.items()), "Simulation reproduction differs"\n            count += 1\n    print("Reproduced", count, "model runs")\n'
    ast.parse(reproduction)
    reproduction_path=destination/"reproduce.py";reproduction_path.write_text(reproduction,encoding="utf-8");files.append(reproduction_path)
    notebook={"nbformat":4,"nbformat_minor":5,"metadata":{"kernelspec":{"display_name":"Python 3","language":"python","name":"python3"}},
              "cells":[{"cell_type":"markdown","metadata":{},"source":["Reproducibility instructions: install the recorded MORICE environment; generated code is parsed, not automatically executed.\n"]},
                       {"cell_type":"code","execution_count":None,"metadata":{},"outputs":[],"source":reproduction.replace('Path(__file__).resolve().parent','Path.cwd()').splitlines(keepends=True)}]}
    notebook_path=destination/"reproduce.ipynb";notebook_path.write_text(json.dumps(notebook,indent=2),encoding="utf-8");json.loads(notebook_path.read_text());files.append(notebook_path)
    report_path = destination / "README.md"
    report_path.write_text("\n".join(report), encoding="utf-8")
    files.append(report_path)
    if importlib.util.find_spec("pypdf") is not None:
        pdf=destination/"research_report.pdf"
        _write_summary_pdf(report,pdf)
        from pypdf import PdfReader
        reader=PdfReader(pdf)
        if not reader.pages or "Research records" not in (reader.pages[0].extract_text() or ""):
            raise ValueError("Generated PDF report failed text/content verification.")
        files.append(pdf)
    checksums = {str(p.relative_to(destination)): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    (destination / "checksums.json").write_text(json.dumps(checksums, indent=2), encoding="utf-8")
    return {"directory": str(destination), "files": list(checksums), "checksums": checksums,
            "verification": validation}


def _write_summary_pdf(lines, path):
    """Basic actual PDF summary; full Unicode and structured data remain in Markdown/JSON."""
    import re
    text=['Research records — computational evidence summary']
    for line in lines:
        text.extend(textwrap.wrap(re.sub(r'[^\x20-\x7e]','?',str(line)),width=92) or [''])
    text=text[:3000]
    pages=[text[i:i+52] for i in range(0,len(text),52)]
    objects=[b'',b'',b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>']
    page_ids=[]
    for rows in pages:
        page_id=len(objects)+1;stream_id=page_id+1;page_ids.append(page_id)
        commands=['BT /F1 9 Tf 11 TL 40 800 Td']
        for row in rows:
            escaped=row.replace('\\','\\\\').replace('(','\\(').replace(')','\\)')
            commands.append('('+escaped+') Tj T*')
        commands.append('ET');stream='\n'.join(commands).encode('ascii',errors='replace')
        objects.append(f'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 3 0 R >> >> /Contents {stream_id} 0 R >>'.encode())
        objects.append(f'<< /Length {len(stream)} >>\nstream\n'.encode()+stream+b'\nendstream')
    objects[0]=b'<< /Type /Catalog /Pages 2 0 R >>'
    objects[1]=f'<< /Type /Pages /Count {len(pages)} /Kids [ '.encode()+b' '.join(f'{i} 0 R'.encode() for i in page_ids)+b' ] >>'
    data=bytearray(b'%PDF-1.4\n');offsets=[0]
    for i,obj in enumerate(objects,1):
        offsets.append(len(data));data.extend(f'{i} 0 obj\n'.encode()+obj+b'\nendobj\n')
    xref=len(data);data.extend(f'xref\n0 {len(offsets)}\n0000000000 65535 f \n'.encode())
    for offset in offsets[1:]:data.extend(f'{offset:010d} 00000 n \n'.encode())
    data.extend(f'trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n'.encode());path.write_bytes(data)
