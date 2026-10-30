"""Data-only owned subprocess; never executes inspected files or tool instructions."""
import json,sys,traceback
from pathlib import Path
from .contracts import Limits,LimitReached,IntegrityFailure,Cancelled

def emit(value):print(json.dumps(value,ensure_ascii=True),flush=True)
def main():
    try:
        import os
        if os.name!='nt' and os.environ.get('MORICE_WORKER_MEMORY_LIMIT'):
            import resource
            amount=int(os.environ['MORICE_WORKER_MEMORY_LIMIT']);resource.setrlimit(resource.RLIMIT_AS,(amount,amount))
        raw=sys.stdin.buffer.read(2*1024**2+1)
        if len(raw)>2*1024**2:raise LimitReached()
        request=json.loads(raw);limits=Limits(**request.get('limits',{}));action=request['action']
        progress=lambda value:emit({'type':'progress','value':value})
        if action in {'inspect','decode'}:
            from .forensics import inspect,decode
            value=inspect(request['path'],limits) if action=='inspect' else decode(request['path'],request['output'],limits)
        elif action in {'estimate','recover'}:
            from .recovery import recover,feasibility,candidate_values,binary
            candidates=candidate_values(request.get('passwords',[]),request.get('conventions',[]));key=binary(request['key'],64) if request.get('key') else None
            value=(feasibility(request['path'],candidates,key,limits) if action=='estimate' else
                recover(request['path'],request['output'],candidates,key,limits,progress))
        elif action=='audit':
            from .audit import scan
            value=scan(request['path'],limits)
        elif action=='cipher':
            from .ciphers import decode_cipher
            value=decode_cipher(request['path'],request['output'],request['cipher_method'],request.get('passwords',[''])[0],limits)
        elif action=='challenge':
            from .challenge import run_challenge
            value=run_challenge(progress=progress,repair=not bool(request.get('policy_path')),policy_path=request.get('policy_path'),expected_secure=request.get('expected_secure',False))
        elif action=='endpoint':
            from .webtests import assess_endpoint
            value=assess_endpoint(request['origin'])
        elif action=='vox':
            from .webtests import vox_delivery
            value=vox_delivery(request['path'],request.get('credential_material',{}),progress=progress)
        else:raise ValueError('Unsupported operation')
        emit({'type':'result','value':value});return 0
    except LimitReached:emit({'type':'result','value':{'status':'RESOURCE_LIMIT_REACHED','artifacts':[]}})
    except Cancelled:emit({'type':'result','value':{'status':'CANCELLED','artifacts':[]}})
    except (IntegrityFailure,ValueError,KeyError,TypeError):emit({'type':'result','value':{'status':'PARTIAL' if locals().get('action')=='vox' else 'INTEGRITY_CHECK_FAILED','artifacts':[],'message':'Input or verification failed. For messaging, delivery is unverified; no automatic retry is performed.'}})
    except Exception as exc:
        # Exception strings can contain secrets supplied to third-party readers.
        emit({'type':'result','value':{'status':'UNSUPPORTED_FORMAT','artifacts':[],'error_type':type(exc).__name__,
            'message':'The installed format adapter could not complete this operation; no success is claimed.'}})
    return 0
if __name__=='__main__':raise SystemExit(main())
