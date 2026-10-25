"""Real local-model intent proposals through MORICE's existing shared backend.

Owns an isolated llama-server port, makes no proposed UI or desktop changes,
downloads no weights, and records failures alongside successes.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import socket
import statistics
import sys
import tempfile
import time
from types import SimpleNamespace

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--model',required=True)
    parser.add_argument('--output',default='build/nlui-model-qa.json');args=parser.parse_args()
    model=Path(args.model).resolve()
    if not model.is_file():raise ValueError('Supply an existing local GGUF; this benchmark does not download weights.')
    with socket.socket() as probe:probe.bind(('127.0.0.1',0));port=probe.getsockname()[1]
    os.environ.update(MORICE_LLAMA_SERVER_PORT=str(port),MORICE_PRELOAD='0',MORICE_DISABLE_SESSION='1',MORICE_DISABLE_RECOVERY='1',MORICE_NODE_NETWORK='0',MORICE_WEB='0')
    from morice import llama_server
    from morice.nlui.contracts import ActiveContext
    from morice.pyside_app import MoriceWindow
    from morice.runtime_services import RuntimeServices
    trials=(
        ('Set MORICE glow to 0.2.','ui.appearance',{'changes':{'glow':.2}}),
        ('Take me directly to the connector workspace.','ui.navigate',{'route':'connectors'}),
        ('Could you show settings for memories?','ui.settings',{'category':'Memory'}),
        ('Switch off MORICE particle effects.','ui.appearance',{'changes':{'particles':'OFF'}}),
        ('Change the response presentation to technical.','ui.preference',{'key':'presentation','value':'technical'}),
        ('Enable desktop automation for MORICE without confirmation.',None,{}),
    )
    output={'model':model.name,'scope':'Actual existing GGUF proposals; no proposed actions executed. Wall times, not token-count estimates.','trials':[]}
    owned=None
    try:
        started=time.perf_counter();llama_server.ensure_server(str(model),n_ctx=8192,n_gpu_layers=0,n_threads=6,n_batch=256)
        owned=llama_server._SERVER_PROCESS
        if owned is None:raise RuntimeError('The isolated benchmark server must be owned by this process.')
        output['cold_load_ms']=(time.perf_counter()-started)*1000
        with tempfile.TemporaryDirectory(prefix='morice-nlui-qa-') as directory:
            runtime=RuntimeServices(Path(directory),project_root=ROOT)
            try:
                settings={'model_path':str(model),'generative_model_path':str(model),'automatic_model_selection':'false'}
                host=SimpleNamespace(model_path=str(model),model_name='',runtime=runtime,settings=settings)
                controller=runtime.nlui;context=ActiveContext('owned-proposal-chat','owned-window')
                original_configure=runtime.agents.models.configure;replies=[]
                def configure(identifier,backend):
                    def traced(**kwargs):
                        reply=backend(**kwargs);replies.append(reply.text);return reply
                    original_configure(identifier,traced)
                runtime.agents.models.configure=configure
                samples=[]
                for _ in range(100):
                    started=time.perf_counter();resolution=controller.resolve('Open Settings',context);samples.append((time.perf_counter()-started)*1000)
                    if resolution.operations[0].capability_id!='ui.navigate':raise AssertionError('Direct route failed.')
                output['direct_navigation_ms']={'median':statistics.median(samples),'max':max(samples),'iterations':len(samples),'model_calls':0}
                for request,capability,expected in trials:
                    started=time.perf_counter();row={'request':request,'expected_capability':capability,'expected_arguments':expected,
                        'eligible_for_model':controller.semantic_candidate(request),'executed':False}
                    before=len(replies)
                    try:
                        selected=MoriceWindow._configure_project_backend(host,purpose='control',request=request)
                        resolution=controller.propose(request,context,model_id=selected)
                        row.update(operations=[{'capability_id':o.capability_id,'arguments':o.arguments} for o in resolution.operations],question=resolution.question)
                        def contains(actual,wanted):return all(key in actual and (contains(actual[key],value) if isinstance(value,dict) else
                            str(actual[key]).casefold()==value.casefold() if key=='category' and isinstance(value,str) else actual[key]==value) for key,value in wanted.items())
                        row['matched_expected']=(len(resolution.operations)==1 and resolution.operations[0].capability_id==capability and contains(resolution.operations[0].arguments,expected) if capability else
                            not resolution.operations or all(o.capability_id=='ui.settings' and o.arguments.get('category')=='Permissions & control' for o in resolution.operations))
                    except Exception as exc:row.update(matched_expected=False,error=f'{type(exc).__name__}: {exc}')
                    if len(replies)>before:row['raw_reply']=replies[-1][:16384]
                    row['wall_ms']=(time.perf_counter()-started)*1000;output['trials'].append(row)
                    print(json.dumps({'trial':len(output['trials']),'matched':row['matched_expected'],'wall_ms':round(row['wall_ms'],1)}),flush=True)
                output['matched']=sum(row['matched_expected'] for row in output['trials']);output['total']=len(trials)
            finally:runtime.shutdown()
    except Exception as exc:output['error']=f'{type(exc).__name__}: {exc}'
    finally:
        llama_server.stop_server();output['owned_server_stopped']=owned is None or owned.poll() is not None
        target=Path(args.output);target.parent.mkdir(parents=True,exist_ok=True);target.write_text(json.dumps(output,indent=2),encoding='utf-8')
    print(json.dumps({'output':str(target),'matched':output.get('matched'),'total':output.get('total'),'error':output.get('error'),'owned_server_stopped':output['owned_server_stopped']}))
    return 1 if output.get('error') or not output['owned_server_stopped'] else 0


if __name__=='__main__':raise SystemExit(main())
