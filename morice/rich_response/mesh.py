"""Bounded parsing of actual binary/ASCII STL bytes, without a geometry generator."""
from __future__ import annotations

from array import array
from dataclasses import dataclass
import hashlib
import math
from pathlib import Path
import re
import struct


MAX_TRIANGLES=100000
MAX_BYTES=16*1024*1024


@dataclass(frozen=True)
class Mesh:
    vertices:array
    triangles:int
    minimum:tuple
    maximum:tuple
    sha256:str
    degenerate_faces:int


def load_stl(path,expected_hash,cancellation=None):
    path=Path(path)
    if cancellation is not None:cancellation.raise_if_cancelled()
    if not path.is_file() or path.stat().st_size>MAX_BYTES:raise ValueError('STL is missing or exceeds the 16 MiB viewer limit.')
    with path.open('rb') as stream:raw=stream.read(MAX_BYTES+1)
    digest=hashlib.sha256(raw).hexdigest()
    if len(raw)>MAX_BYTES or digest!=expected_hash:raise ValueError('STL bytes changed before preview.')
    vertices=array('f');count=struct.unpack_from('<I',raw,80)[0] if len(raw)>=84 else 0
    if count and len(raw)==84+50*count:
        if count>MAX_TRIANGLES:raise ValueError('STL exceeds the 100,000-triangle preview limit.')
        for index in range(count):
            if cancellation is not None and index%256==0:cancellation.raise_if_cancelled()
            vertices.extend(struct.unpack_from('<9f',raw,84+index*50+12))
    else:
        if not raw.lstrip().startswith(b'solid'):raise ValueError('STL size/header does not describe a supported mesh.')
        try:content=raw.decode('ascii')
        except UnicodeDecodeError as exc:raise ValueError('ASCII STL contains invalid bytes.') from exc
        number=r'[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?'
        matches=re.finditer(r'\bvertex\s+('+number+r')\s+('+number+r')\s+('+number+r')\s*(?=\r?\n|endloop)',content)
        for match in matches:
            if cancellation is not None:cancellation.raise_if_cancelled()
            if len(vertices)>=9*MAX_TRIANGLES:raise ValueError('STL exceeds the preview triangle bound.')
            vertices.extend(float(match[i]) for i in (1,2,3))
        if len(vertices)%9 or not vertices:raise ValueError('ASCII STL does not contain complete triangle facets.')
        count=len(vertices)//9
        if (len(re.findall(r'\bfacet\b',content))!=count or len(re.findall(r'\bendfacet\b',content))!=count
                or len(re.findall(r'\bendloop\b',content))!=count or not re.search(r'\bendsolid\b',content)):
            raise ValueError('ASCII STL facet/vertex counts do not agree.')
    if not count or any(not math.isfinite(v) or abs(v)>1e6 for v in vertices):raise ValueError('Mesh vertices must be finite and within preview bounds.')
    minimum=tuple(min(vertices[axis::3]) for axis in range(3));maximum=tuple(max(vertices[axis::3]) for axis in range(3))
    if max(high-low for low,high in zip(minimum,maximum))<=0:raise ValueError('STL has no measurable extent.')
    degenerate=0
    for start in range(0,len(vertices),9):
        if cancellation is not None and start%2304==0:cancellation.raise_if_cancelled()
        a=vertices[start:start+3];b=vertices[start+3:start+6];c=vertices[start+6:start+9]
        u=[b[i]-a[i] for i in range(3)];v=[c[i]-a[i] for i in range(3)]
        cross=(u[1]*v[2]-u[2]*v[1],u[2]*v[0]-u[0]*v[2],u[0]*v[1]-u[1]*v[0])
        if not any(cross):degenerate+=1
    return Mesh(vertices,count,minimum,maximum,digest,degenerate)
