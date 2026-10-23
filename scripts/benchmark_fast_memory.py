"""Reproducible synthetic history and optional real local-model benchmarks."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import statistics
import subprocess
import sys
import tempfile
import threading
import time

ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))


def timed(function):
    started=time.perf_counter(); value=function()
    return value,(time.perf_counter()-started)*1000


def gpu():
    try:
        return subprocess.check_output(['nvidia-smi','--query-gpu=name,memory.total,memory.used','--format=csv,noheader'],text=True,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0)).strip()
    except (OSError,subprocess.SubprocessError): return 'unavailable'


def memory_benchmark(sizes):
    from morice.research.history import ChatHistory
    evidence=[]
    for size in sizes:
        with tempfile.TemporaryDirectory(prefix='morice-history-benchmark-') as directory:
            path=Path(directory)/'knowledge.db'
            history,startup=timed(lambda:ChatHistory(path))
            messages=[{'role':'user' if i%2==0 else 'assistant','content':f'Controlled update {i}: routine work remains pending.'} for i in range(size)]
            positions=sorted(set([0,min(50,size-1),min(500,size-1),size//2,size-1]))
            for pos in positions: messages[pos]={'role':'user','content':f'Beacon{pos} records exact fixture decision number {pos}.'}
            messages[0]={'role':'user','content':'Use the name Project Orion. Beacon0 is the earliest fixture.'}
            _,index_ms=timed(lambda:history.save('benchmark',messages,merge=True))
            durations=[]; correct=0; leaked=0
            for repeat in range(30):
                pos=positions[repeat%len(positions)]
                found,elapsed=timed(lambda:history.search_messages('benchmark',f'Beacon{pos}',limit=5))
                durations.append(elapsed); correct+=int(bool(found) and found[0]['sequence']==pos+1)
            history.save('other',[{'role':'user','content':'A hidden scope sentinel.'}],merge=True)
            leaked=len(history.search_messages('benchmark','hidden scope sentinel'))
            first=history.search_messages('benchmark','What was the first thing I told you?',role='user',limit=1)
            _,update_ms=timed(lambda:history.save('benchmark',[{'role':'user','content':'Incremental append fixture.'}],merge=True))
            _,reopen_ms=timed(lambda:ChatHistory(path).open('benchmark',recent=160))
            _,rebuild_ms=timed(history.rebuild_index)
            evidence.append({'messages':size,'index_ms':index_ms,'append_ms':update_ms,'startup_ms':startup,'bounded_reopen_ms':reopen_ms,
                'search_p50_ms':statistics.median(durations),'search_p95_ms':sorted(durations)[int(.95*(len(durations)-1))],
                'top1_accuracy':correct/len(durations),'scope_leak_failures':leaked,'first_message_found':bool(first and first[0]['sequence']==1),
                'database_bytes':path.stat().st_size,'bytes_per_message':path.stat().st_size/size,'rebuild_ms':rebuild_ms})
    return evidence


def inference_benchmark(fast,thinking):
    from morice.config import load_environment
    load_environment()
    from morice import llm_client
    from morice.llama_server import selected_server_path,stop_server
    report={'backend':selected_server_path(),'gpu_before':gpu(),'gpu_layers_setting':os.getenv('MORICE_GPU_LAYERS','auto'),'scenarios':[]}
    try:
        for label,path,prompt in [('fast_cold',fast,'Explain gravity simply in two sentences.'),
                                  ('fast_warm',fast,'What is the capital of France? Answer in one sentence.'),
                                  ('thinking_after_switch',thinking,'Compare using a queue and a lock for a single writer. Give two brief points.'),
                                  ('fast_after_switch',fast,'Reply with only: Ready.')]:
            started=time.perf_counter(); first=None; parts=[]; events=[]
            for delta in llm_client.stream_chat([],prompt,gguf_path=str(path),max_tokens=96,
                    enable_reasoning=label.startswith('thinking'),telemetry=lambda e,m:events.append((e,m))):
                if first is None: first=time.perf_counter()
                parts.append(delta)
            elapsed=time.perf_counter()-started; text=''.join(parts)
            usage=next((m.get('usage',{}) for e,m in reversed(events) if e=='model_usage'),{})
            tokens=usage.get('completion_tokens',0)
            report['scenarios'].append({'scenario':label,'model_file':str(path),'ttft_ms':(first-started)*1000 if first else None,
                'duration_ms':elapsed*1000,'usage':usage,'tokens_per_second_total':tokens/elapsed if tokens else None,
                'output':text,'backend_error':text.startswith('(MORICE)'),'gpu_after':gpu(),
                'prepare_ms':next((m.get('prepareMs') for e,m in events if e=='model_ready'),None)})
        cancel=threading.Event(); stream=llm_client.stream_chat([],'Write a long explanation of gravity.',gguf_path=str(fast),max_tokens=200,cancel_event=cancel)
        start=time.perf_counter(); first=next(stream); cancel.set(); remainder=list(stream)
        report['cancellation']={'first_chunk_received':bool(first),'additional_chunks':len(remainder),'duration_ms':(time.perf_counter()-start)*1000}
    finally:
        _,unload_ms=timed(stop_server); report['unload_ms']=unload_ms; report['gpu_after_unload']=gpu()
    return report


def main():
    parser=argparse.ArgumentParser(); parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--sizes',nargs='+',type=int,default=[1000,10000,100000]);parser.add_argument('--fast',type=Path);parser.add_argument('--thinking',type=Path)
    args=parser.parse_args(); report={'kind':'controlled local fixtures','history':memory_benchmark(args.sizes)}
    if args.fast and args.thinking: report['inference']=inference_benchmark(args.fast,args.thinking)
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(report,indent=2),encoding='utf-8'); print(json.dumps(report,indent=2))


if __name__=='__main__':main()
