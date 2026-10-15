"""Fetch only the human-approved pinned manifest; no automatic model installer."""
from __future__ import annotations
import argparse,hashlib,json,os,shutil,time,urllib.request,uuid
from pathlib import Path


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--manifest',default='build/phase9-model-download-plan.json');parser.add_argument('--approved',action='store_true');args=parser.parse_args()
    if not args.approved:raise SystemExit('Explicit user approval required before downloading model weights.')
    path=Path(args.manifest);plan=json.loads(path.read_text(encoding='utf-8'));root=Path(plan['destination']).resolve()
    source=Path(__file__).resolve().parents[1]
    if root.is_relative_to(source):raise ValueError('Weights must be outside source tree.')
    root.mkdir(parents=True,exist_ok=True)
    if shutil.disk_usage(root).free<plan['bytes']+2*1024**3:raise ValueError('Insufficient safe disk space.')
    receipts=[]
    for item in plan['files']:
        target=(root/item['path']).resolve()
        if not target.is_relative_to(root):raise ValueError('Manifest path escape.')
        if not item['url'].startswith('https://huggingface.co/'+plan['repository']+'/resolve/'+plan['revision']+'/'):raise ValueError('Unapproved file source.')
        target.parent.mkdir(parents=True,exist_ok=True)
        def digest(p):
            h=hashlib.sha256()
            with p.open('rb') as stream:
                while chunk:=stream.read(1024*1024):h.update(chunk)
            return h.hexdigest()
        if target.exists():
            sha=digest(target)
            if target.stat().st_size!=item['bytes'] or item.get('sha256') and sha!=item['sha256']:raise ValueError('Existing model file differs; never overwrite it automatically.')
        else:
            temporary=target.parent/('.morice-download-'+uuid.uuid4().hex+'.part')
            try:
                with urllib.request.urlopen(item['url'],timeout=90) as response,temporary.open('xb') as stream:
                    count=0
                    while chunk:=response.read(1024*1024):
                        stream.write(chunk);count+=len(chunk)
                        if count>item['bytes']:raise ValueError('Download exceeds approved byte count.')
                    stream.flush();os.fsync(stream.fileno())
                if count!=item['bytes']:raise ValueError('Download size mismatch.')
                sha=digest(temporary)
                if item.get('sha256') and sha!=item['sha256']:raise ValueError('Upstream model SHA256 mismatch.')
                os.link(temporary,target)
            finally:
                if temporary.exists():temporary.unlink()
        receipts.append({'path':item['path'],'bytes':item['bytes'],'sha256':sha});print(item['path'],item['bytes'],'verified',flush=True)
    record={'status':'APPROVED_DOWNLOADED_VERIFIED','repository':plan['repository'],'revision':plan['revision'],'license':plan['license'],'source':str(path.resolve()),'destination':str(root),'files':receipts,'bytes':sum(r['bytes'] for r in receipts),'completed_at':time.time()}
    Path('build/phase9-model-download-receipt.json').write_text(json.dumps(record,indent=2),encoding='utf-8')
    print('All approved files downloaded and verified.',flush=True)

if __name__=='__main__':main()
