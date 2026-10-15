"""Developer/user Media API entry point without a Phase 10 UI redesign."""
from __future__ import annotations
import argparse,json,time
from pathlib import Path


def main(arguments=None):
    parser=argparse.ArgumentParser(prog='morice-media',description='Local Generative Media Lab')
    parser.add_argument('command',choices=['status','discover','inspect','generate','benchmark'])
    parser.add_argument('--model',default='');parser.add_argument('--prompt',default='');parser.add_argument('--width',type=int,default=512);parser.add_argument('--height',type=int,default=512)
    parser.add_argument('--steps',type=int);parser.add_argument('--seed',type=int,default=0);parser.add_argument('--count',type=int,default=1);parser.add_argument('--reference',action='append',default=[])
    parser.add_argument('--request-json');args=parser.parse_args(arguments)
    from ..runtime_services import get_runtime_services
    from .contracts import ImageRequest
    from ..kernel import ExecutionContext
    runtime=get_runtime_services()
    try:
        media=runtime.media
        if args.command=='status':value=media.status()
        elif args.command=='discover':value=[m.to_dict() for m in media.discover()]
        elif args.command=='inspect':value=media.inspect_model(args.model).to_dict()
        elif args.command=='generate':
            if args.request_json:
                path=Path(args.request_json)
                if path.stat().st_size>64*1024:raise ValueError('Request JSON too large.')
                request=media.request(json.loads(path.read_text(encoding='utf-8')))
            else:request=ImageRequest(args.prompt,args.model,width=args.width,height=args.height,steps=args.steps,seed=args.seed,count=args.count,reference_images=tuple(args.reference),intent='IMAGE_TO_IMAGE' if args.reference else 'TEXT_TO_IMAGE')
            identifier,future=media.submit(request,ExecutionContext(active_files=tuple(args.reference)))
            value=future.result(timeout=1805).to_dict()
        else:
            value=runtime.kernel.dispatch('media.model.benchmark',{'model_ids':[args.model] if args.model else []},ExecutionContext(active_files=tuple(args.reference))).to_dict()
            if value['success']:
                while getattr(media,'_benchmark_active',None):time.sleep(.1)
                value=json.loads(Path(value['output']['json_path']).read_text(encoding='utf-8'))
        print(json.dumps(value,ensure_ascii=False,indent=2,default=str));return 0 if not isinstance(value,dict) or value.get('success',True) else 1
    finally:runtime.shutdown()


if __name__=='__main__':raise SystemExit(main())
