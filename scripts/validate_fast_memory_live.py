"""Ground-truth acceptance probes against explicitly supplied installed GGUF weights."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import time

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--model',type=Path,required=True);parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    from morice.config import load_environment
    load_environment()
    from morice.desktop_environment import MemoryManager
    from morice.memory_policy import memory_context
    from morice.research.history import ChatHistory
    from morice.realtime_intelligence import SemanticChunker,TieredModelRouter
    from morice import llm_client
    from morice.llama_server import stop_server
    report={'scope':'Actual inference plus controlled local history/preferences; no physical microphone or paid TTS request.'}
    with tempfile.TemporaryDirectory(prefix='morice-live-memory-') as directory:
        root=Path(directory);history=ChatHistory(root/'knowledge.db');memory=MemoryManager(root/'memory')
        memory.set_personal_enabled(True)
        messages=[{'role':'user','content':'Use the name Project Orion. Use orange for the interface.'},
            *[{'role':'assistant','content':f'Routine unrelated synthetic update {i}'} for i in range(10000)],
            {'role':'user','content':'Actually change the interface to blue.'}]
        history.save('a',messages,merge=True)
        preferences={'personal_memory_enabled':'true','chat_memory_enabled':'true'}
        cases=[('first_message','What name did I choose at the beginning? Answer only the project name.'),
            ('latest_correction','What color is the latest interface decision? Answer only the color.'),
            ('missing_fact','What did I say earlier about nonexistentbeacon? Do not invent anything.'),
            ('current_override','Explain how to implement a file manager in one sentence.')]
        memory.save_preference('For coding tasks, give detailed implementation steps.')
        results=[]
        try:
            for label,query in cases:
                context,sources=memory_context(history,memory,'a',query,settings=preferences)
                started=time.perf_counter();output=''.join(llm_client.stream_chat([],query,gguf_path=str(args.model),extra_system=context,max_tokens=256,precision_mode=True))
                checks={'first_message':lambda:'project orion' in output.casefold() and any(s['sequence']==1 for s in sources),
                    'latest_correction':lambda:'blue' in output.casefold() and 'orange' not in output.casefold() and any(s['sequence']==10002 for s in sources),
                    'missing_fact':lambda:any(t in output.casefold() for t in ('could not','couldn\'t','cannot','can\'t','no supporting','not found','no record','no mention','no information','unable','not verify')),
                    'current_override':lambda:len([s for s in re.split(r'[.!?](?:\s|$)',output) if s.strip()])==1}
                results.append({'case':label,'output':output,'passed':checks[label](),'source_sequences':[s['sequence'] for s in sources],
                    'prompt_context_chars':len(context),'duration_ms':(time.perf_counter()-started)*1000})
            chunker=SemanticChunker();first_speakable=None;started=time.perf_counter();deltas=0
            for delta in llm_client.stream_chat([],'Explain gravity naturally in about 100 words with several sentences.',gguf_path=str(args.model),max_tokens=180):
                deltas+=1
                if chunker.feed(delta) and first_speakable is None:first_speakable=time.perf_counter()-started
            duration=time.perf_counter()-started
            report['speech_chunking']={'first_speakable_ms':first_speakable*1000 if first_speakable else None,'generation_ms':duration*1000,
                'ready_before_generation_complete':first_speakable is not None and first_speakable<duration,'deltas':deltas,
                'physical_audio':'not validated in this probe'}
            long=[{'role':'system','content':'Keep answers short.'},{'role':'user','content':'漢字 '*5000}, {'role':'user','content':'Reply only Ready.'}]
            backend=llm_client.ensure_server(str(args.model),llm_client.DEFAULT_CTX,llm_client.DEFAULT_GPU_LAYERS,llm_client.DEFAULT_THREADS,llm_client.DEFAULT_BATCH)
            events=[];fitted=llm_client._fit_backend_context(backend,long,256,telemetry=lambda e,m:events.append((e,m)))
            report['token_budget']={'messages_after':len(fitted),'telemetry':events}
        finally:stop_server()
        report['cases']=results;report['passed']=all(r['passed'] for r in results) and report['speech_chunking']['ready_before_generation_complete']
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(report,indent=2))
    return 0 if report['passed'] else 1


if __name__=='__main__':raise SystemExit(main())
