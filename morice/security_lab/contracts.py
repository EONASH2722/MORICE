from __future__ import annotations
from dataclasses import dataclass, asdict
from enum import Enum
from pathlib import Path, PurePosixPath
import hashlib, math, os, re, time

class Outcome(str, Enum):
    RECOVERED='RECOVERED'
    WRONG_KEY='WRONG_KEY'
    UNSUPPORTED_FORMAT='UNSUPPORTED_FORMAT'
    MISSING_KEY='MISSING_KEY'
    CANDIDATES_EXHAUSTED='CANDIDATES_EXHAUSTED'
    RESOURCE_LIMIT_REACHED='RESOURCE_LIMIT_REACHED'
    CANCELLED='CANCELLED'
    INTEGRITY_CHECK_FAILED='INTEGRITY_CHECK_FAILED'

@dataclass(frozen=True)
class Limits:
    seconds: float=60
    candidates: int=1000
    input_bytes: int=64*1024**2
    output_bytes: int=128*1024**2
    members: int=256
    layers: int=5
    expansion_ratio: int=200
    def __post_init__(self):
        ranges={'seconds':(0.05,1200),'candidates':(1,100000),'input_bytes':(1,128*1024**2),
            'output_bytes':(1,256*1024**2),'members':(1,512),'layers':(1,8),'expansion_ratio':(1,250)}
        for key,(low,high) in ranges.items():
            value=getattr(self,key)
            if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or not low<=value<=high:
                raise ValueError('Invalid recovery resource budget: '+key)
            if key!='seconds' and not isinstance(value,int):raise ValueError('Resource counts must be integers.')
    def to_dict(self):return asdict(self)

class LimitReached(Exception):pass
class Cancelled(Exception):pass
class WrongKey(Exception):pass
class IntegrityFailure(Exception):pass
class Unsupported(Exception):pass

class Budget:
    def __init__(self,limits,cancel=lambda:False):
        self.limits=limits;self.cancel=cancel;self.started=time.monotonic();self.written=0
    def check(self,amount=0):
        if self.cancel():raise Cancelled()
        if time.monotonic()-self.started>self.limits.seconds:raise LimitReached()
        self.written+=amount
        if self.written>self.limits.output_bytes:raise LimitReached()

def sha256(path):
    digest=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda:stream.read(65536),b''):digest.update(chunk)
    return digest.hexdigest()

def local_file(path,maximum):
    path=Path(path).expanduser()
    if str(path).startswith(('\\\\','//')) or path.is_symlink():raise ValueError('Select an ordinary local file.')
    path=path.resolve(strict=True)
    if not path.is_file() or path.stat().st_size>maximum:raise LimitReached()
    return path

def member_name(name):
    # Windows ADS, device names, absolute paths and case aliases are never export paths.
    value=name.replace('\\','/')
    parts=PurePosixPath(value).parts
    if (not parts or value.startswith('/') or any(p in {'.','..'} or ':' in p or p.endswith((' ','.'))
        or re.match(r'^(?:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\.|$)',p,re.I) for p in parts)):
        raise IntegrityFailure('Unsafe archive path')
    return '/'.join(parts)

def redacted(text):
    from ..redaction import redact_text
    return redact_text(str(text))[:16000]
