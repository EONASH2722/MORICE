"""A real bounded parametric STL adapter and BOM, without pretending CAD solvers exist."""
from __future__ import annotations

import hashlib
import json
import math
import struct
import uuid
from pathlib import Path

from .ingestion import checkpoint
from .tools import ScientificTools


def create_box(root, spec, cancel=None):
    dimensions={name:ScientificTools().calculate("x",{"x":spec[name]},"m")["result"]["value"] for name in ("width","height","depth")}
    if any(not 1e-6 <= v <= 100 for v in dimensions.values()):
        raise ValueError("Box dimensions must be between one micrometre and 100 metres.")
    if type(spec.get("quantity",1)) is not int or not 1<=spec.get("quantity",1)<=10000:
        raise ValueError("BOM quantity must be 1–10,000.")
    material=str(spec.get("material","user-specified material"))[:200]
    directory=Path(root)/uuid.uuid4().hex
    directory.mkdir(parents=True,exist_ok=False)
    w,h,d=(dimensions[n] for n in ("width","height","depth"))
    vertices=[(0,0,0),(w,0,0),(w,h,0),(0,h,0),(0,0,d),(w,0,d),(w,h,d),(0,h,d)]
    faces=[(0,2,1),(0,3,2),(4,5,6),(4,6,7),(0,1,5),(0,5,4),(1,2,6),(1,6,5),(2,3,7),(2,7,6),(3,0,4),(3,4,7)]
    path=directory/"box.stl"
    with path.open("wb") as stream:
        stream.write(b"MORICE parametric box; coordinates in metres".ljust(80,b" "))
        stream.write(struct.pack("<I",len(faces)))
        for face in faces:
            checkpoint(cancel)
            a,b,c=(vertices[i] for i in face)
            u,v=tuple(y-x for x,y in zip(a,b)),tuple(y-x for x,y in zip(a,c))
            normal=(u[1]*v[2]-u[2]*v[1],u[2]*v[0]-u[0]*v[2],u[0]*v[1]-u[1]*v[0])
            length=math.sqrt(sum(x*x for x in normal))
            stream.write(struct.pack("<12fH",*(x/length for x in normal),*a,*b,*c,0))
    bom={"part":"parametric rectangular solid","quantity":spec.get("quantity",1),"material":material,
         "dimensions_m":dimensions,"volume_m3":w*h*d,"reference":str(spec.get("reference","user-specified design"))[:1000],
         "limitations":"Geometry only; no material strength, manufacturability, supplier pricing or structural validation."}
    if "density" in spec:
        density=ScientificTools().calculate("x",{"x":spec["density"]},"kg/m^3")["result"]["value"]
        if density<=0: raise ValueError("Density must be positive.")
        bom["modeled_unit_mass_kg"]=density*w*h*d
    bom_path=directory/"bom.json"
    bom_path.write_text(json.dumps(bom,indent=2,allow_nan=False),encoding="utf-8")
    manifest={"directory":str(directory),"stl":str(path),"bom":str(bom_path),"dimensions_m":dimensions,
              "triangles":12,"units":"m","sha256":hashlib.sha256(path.read_bytes()).hexdigest(),
              "bom_sha256":hashlib.sha256(bom_path.read_bytes()).hexdigest(),"provenance":"CALCULATED"}
    if not verify_box(manifest): raise ValueError("Actual generated design failed verification.")
    return manifest


def verify_box(manifest):
    raw=Path(manifest["stl"]).read_bytes()
    if hashlib.sha256(raw).hexdigest()!=manifest["sha256"] or len(raw)!=684 or struct.unpack_from("<I",raw,80)[0]!=12:
        return False
    points=[]
    for offset in range(84,len(raw),50):
        row=struct.unpack_from("<12fH",raw,offset)
        if not all(math.isfinite(v) for v in row[:12]): return False
        points.extend((row[3:6],row[6:9],row[9:12]))
    edges={}
    for i in range(0,len(points),3):
        a,b,c=points[i:i+3]
        for pair in ((a,b),(b,c),(c,a)):
            key=tuple(sorted(pair)); edges[key]=edges.get(key,0)+1
    if any(count!=2 for count in edges.values()): return False
    for axis,name in enumerate(("width","height","depth")):
        if min(p[axis] for p in points)!=0 or not math.isclose(max(p[axis] for p in points),manifest["dimensions_m"][name],rel_tol=1e-6): return False
    bom_raw=Path(manifest["bom"]).read_bytes()
    bom=json.loads(bom_raw)
    return hashlib.sha256(bom_raw).hexdigest()==manifest["bom_sha256"] and bom["dimensions_m"]==manifest["dimensions_m"] and bom["quantity"]>0
