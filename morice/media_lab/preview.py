"""Bounded derived previews. Only MORICE-named cache files may be evicted."""
from __future__ import annotations
import hashlib, json, os, re, uuid
from pathlib import Path

from .artifacts import verify_image

OWNED = re.compile(r'contact-sheet-[0-9a-f]{64}\.png\Z')


def clear_cache(directory, *, limit_bytes=0):
    root=Path(directory).resolve()
    files=[p for p in root.iterdir() if OWNED.fullmatch(p.name) and p.is_file() and not p.is_symlink()]
    files.sort(key=lambda p:p.stat().st_mtime,reverse=True)
    retained=0;removed=0;bytes_removed=0
    for path in files:
        size=path.stat().st_size
        if retained+size<=limit_bytes:retained+=size;continue
        bytes_removed+=size;removed+=1;path.unlink()
    return {'removed_files':removed,'removed_bytes':bytes_removed,'retained_bytes':retained}


def contact_sheet(directory,artifacts,*,limit_bytes,token=None):
    if not 1<=len(artifacts)<=16:raise ValueError('Contact sheets require 1..16 verified artifacts.')
    from PIL import Image,ImageOps,ImageDraw
    root=Path(directory).resolve()
    key=hashlib.sha256(json.dumps([a['sha256'] for a in artifacts]).encode()).hexdigest()
    target=root/('contact-sheet-'+key+'.png')
    if target.is_symlink():raise ValueError('Preview cache path is a symlink.')
    columns=min(4,len(artifacts));rows=(len(artifacts)+columns-1)//columns
    canvas=Image.new('RGB',(columns*256,rows*280),'#202328');draw=ImageDraw.Draw(canvas)
    for index,artifact in enumerate(artifacts):
        if token:token.raise_if_cancelled()
        with Image.open(artifact['path']) as image:
            if image.width*image.height>16*1024*1024:raise ValueError('Preview input exceeds decode budget.')
            image.load();thumb=ImageOps.contain(image.convert('RGB'),(248,248))
        x=(index%columns)*256;y=(index//columns)*280
        canvas.paste(thumb,(x+(256-thumb.width)//2,y+(256-thumb.height)//2))
        draw.text((x+6,y+258),artifact['generation_id'][:12],fill='white')
    stage=root/('.preview-'+uuid.uuid4().hex+'.png')
    try:
        canvas.save(stage,format='PNG');metadata=verify_image(stage,allow_constant=True,token=token)
        if metadata['bytes']>limit_bytes:raise ValueError('Preview exceeds configured cache limit.')
        # Replace only this owned derived cache entry, never an output/model.
        os.replace(stage,target)
        clear_cache(root,limit_bytes=limit_bytes)
        return {**metadata,'path':str(target),'derived_preview':True,'provenance':'GENERATED_VISUAL'}
    finally:
        if stage.exists():stage.unlink()


def storage_stats(directory,models):
    root=Path(directory).resolve();result={};scanned=0;bounded=False
    for name in ('outputs','temp','cache','metadata','benchmarks'):
        total=0;files=0
        for current,dirs,names in os.walk(root/name,followlinks=False):
            dirs[:]=[d for d in dirs if not (Path(current)/d).is_symlink()]
            for leaf in names:
                path=Path(current)/leaf;scanned+=1
                if scanned>10000:bounded=True;break
                if not path.is_symlink():total+=path.stat().st_size;files+=1
            if bounded:break
        result[name]={'bytes':total,'files':files}
        if bounded:break
    result['models']={'bytes':sum(sum(f.get('bytes',0) for f in m.files) for m in {m.model_path:m for m in models}.values()),'scope':'registered inspected manifests'}
    result['scan_truncated']=bounded
    return result
