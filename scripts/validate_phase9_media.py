"""Real, approved SD-Turbo validation through the existing MORICE runtime."""
from __future__ import annotations
import argparse, json, os, sys, time
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', default='build/phase9-real-image.json')
    parser.add_argument('--resolution', type=int, default=512)
    parser.add_argument('--mode', choices=['direct','low_vram','offload'], default='direct')
    parser.add_argument('--intent', default='TEXT_TO_IMAGE')
    parser.add_argument('--reference', default='')
    parser.add_argument('--mask', default='')
    parser.add_argument('--seed', type=int, default=91001)
    parser.add_argument('--count', type=int, default=1)
    parser.add_argument('--benchmark', action='store_true')
    parser.add_argument('--suite', action='store_true')
    parser.add_argument('--ui', action='store_true')
    parser.add_argument('--oom', action='store_true')
    parser.add_argument('--cancel-after', type=float, default=0)
    args = parser.parse_args()
    import faulthandler
    trace=(ROOT/(args.output+'.trace')).open('w',encoding='utf-8')
    faulthandler.enable(file=trace,all_threads=True)
    faulthandler.dump_traceback_later(60,repeat=True,file=trace)
    from morice.config import local_data_dir
    from morice.runtime_services import RuntimeServices
    from morice.media_lab.contracts import ImageModelDescriptor, ImageRequest
    from morice.media_lab.storage import atomic_json
    from morice.kernel import ExecutionContext
    from PySide6.QtCore import QCoreApplication
    if args.ui:
        os.environ.update(QT_QPA_PLATFORM='offscreen',MORICE_PRELOAD='0',MORICE_DISABLE_SESSION='1',MORICE_DISABLE_RECOVERY='1',MORICE_NODE_NETWORK='0')
        from PySide6.QtWidgets import QApplication
    import psutil
    app = QCoreApplication.instance() or (QApplication([]) if args.ui else QCoreApplication([]))
    data = local_data_dir()
    runtime = RuntimeServices(data/'runtime'/'phase9-validation', project_root=ROOT)
    import morice.runtime_services as runtime_module
    runtime_module._RUNTIME_SERVICES=runtime
    report = {'schema':1,'scope':'ACTUAL local approved SD-Turbo, existing Kernel/AgentCoordinator/ResourceManager', 'cases':[]}
    output = ROOT / args.output
    before = psutil.Process().memory_info().rss; window=None;settings_patch=None;normal_model=None;media=None
    try:
        if args.ui:
            from unittest.mock import patch
            from morice import settings
            settings_patch=patch('morice.settings._settings_dir',return_value=str(data/'media'/'validation-settings'));settings_patch.start()
            settings.save_settings({**settings.DEFAULT_SETTINGS,'tts_enabled':'false','stt_enabled':'false','desktop_pet_enabled':'false'})
            from morice.pyside_app import MoriceWindow
            window=MoriceWindow(runtime,runtime.start());window.show();app.processEvents()
            report['ui_scope']='Actual MoriceWindow and Qt event loop, offscreen platform, isolated test settings'
        media = runtime.media
        model = ImageModelDescriptor('sd-turbo-fp16','SD-Turbo fp16','stable-diffusion','diffusers',str(data/'models'/'image'/'sd-turbo'),
            source='https://huggingface.co/stabilityai/sd-turbo/tree/b261bac6fd2cf515557d5d0707481eafa0485ec2',
            license='Stability AI Community License (2024-07-05); see pinned local LICENSE.md',
            version='b261bac6fd2cf515557d5d0707481eafa0485ec2', estimated_vram_mb=4096,estimated_ram_mb=3584,minimum_vram_mb=2304,
            default_steps=1,maximum_steps=4,default_guidance=0, pipeline_class='StableDiffusionPipeline',
            capabilities=('TEXT_TO_IMAGE','IMAGE_TO_IMAGE','IMAGE_VARIATION','INPAINT','OUTPAINT'))
        normal_model=model
        if args.oom:model=replace(model,estimated_vram_mb=512)
        media.models.register(model)
        inspected = media.inspect_model(model.model_id)
        report['model'] = inspected.to_dict()
        report['hardware_before'] = media.hardware(refresh=True).to_dict()
        report['backend'] = media.providers['diffusers'].health(inspected)
        atomic_json(output, report)
        if args.benchmark:
            ticket=runtime.kernel.dispatch('media.model.benchmark',{'model_ids':[model.model_id],'resolutions':[512,640,768],'modes':['direct','low_vram','offload']})
            if not ticket.success:raise RuntimeError(str(ticket.to_dict()))
            started=time.perf_counter();ticks=0;polls=[];last=0
            while getattr(media,'_benchmark_active',None):
                stamp=time.perf_counter();app.processEvents();ticks+=1
                assert runtime.kernel.dispatch('kernel.echo',{'value':ticks}).success
                polls.append((time.perf_counter()-stamp)*1000)
                if time.perf_counter()-last>15:
                    print(json.dumps({'benchmark':ticket.output['benchmark_id'],'completed':len(media._benchmark_active.rows),'elapsed_s':round(time.perf_counter()-started,2)}),flush=True);last=time.perf_counter()
                if time.perf_counter()-started>1200:
                    media._benchmark_active.cancel();raise TimeoutError('Bounded real benchmark timed out.')
                time.sleep(.03)
            report['benchmark']=json.loads(Path(ticket.output['json_path']).read_text(encoding='utf-8'))
            report['event_loop_ticks']=ticks;report['active_poll_p95_ms']=sorted(polls)[int(.95*(len(polls)-1))]
            report['hardware_after']=media.hardware(refresh=True).to_dict();report['owned_processes_after']=media.providers['diffusers'].processes.snapshot()
            report['leases_after']={k:[str(c) for c in v] for k,v in runtime.kernel.resources.snapshot().items()}
            report['storage']=media.storage_stats();atomic_json(output,report)
            return 0 if any(r['status']=='SUCCEEDED' for r in report['benchmark']['rows']) else 1
        request = ImageRequest('A small copper robot watering a lush fern on a wooden desk, soft window light, detailed illustration',
            model_id=model.model_id, intent=args.intent, width=args.resolution,height=args.resolution,seed=args.seed,count=args.count,
            reference_images=(args.reference,) if args.reference else (),mask=args.mask)
        context = ExecutionContext(active_files=tuple(p for p in (args.reference,args.mask) if p))
        def execute_case(request,context,mode=None,cancel_after=0):
            rss_before=psutil.Process().memory_info().rss
            identifier,future=media.submit(request,context,benchmark_mode=mode)
            started=time.perf_counter();ticks=0;samples=[];last=0;cancelled=False
            while not future.done():
                stamp=time.perf_counter();app.processEvents();ticks+=1
                assert runtime.kernel.dispatch('kernel.echo',{'value':ticks}).success
                samples.append((time.perf_counter()-stamp)*1000)
                if cancel_after and not cancelled and time.perf_counter()-started>=cancel_after:
                    report['cancel_requested_at_s']=time.perf_counter()-started;media.cancel(identifier);cancelled=True
                if time.perf_counter()-last>15:
                    state=media.result(identifier);print(json.dumps({'generation_id':identifier,'intent':request.intent,'stage':state.get('status'),'elapsed_s':round(time.perf_counter()-started,2)}),flush=True);last=time.perf_counter()
                if time.perf_counter()-started>300:
                    media.cancel(identifier);raise TimeoutError('Real image validation exceeded bounded five-minute budget.')
                time.sleep(.03)
            result=future.result()
            case={'generation_id':identifier,'success':result.success,'result':result.to_dict(),'history':media.result(identifier),
                'wall_ms':(time.perf_counter()-started)*1000,'event_loop_ticks':ticks,'active_poll_p95_ms':sorted(samples)[int(.95*(len(samples)-1))] if samples else 0,
                'parent_rss_before':rss_before,'parent_rss_after':psutil.Process().memory_info().rss,
                'owned_processes_after':media.providers['diffusers'].processes.snapshot(),'resource_leases_after':{k:[str(c) for c in v] for k,v in runtime.kernel.resources.snapshot().items()}}
            report['cases'].append(case);report['hardware_after']=media.hardware(refresh=True).to_dict();atomic_json(output,report)
            print(json.dumps({'success':result.success,'generation_id':identifier,'errors':result.to_dict()['errors'],'output':str(output)},default=str),flush=True)
            return case
        first=execute_case(request,context,args.mode,args.cancel_after)
        if args.oom:
            assert not first['success'] and any('out of memory' in e['detail'].lower() for e in first['result']['errors']),first
            report['oom_scope']='ACTUAL Torch allocator OutOfMemoryError using a deliberately bounded 512 MiB worker budget; no host-wide exhaustion'
            media.models.register(normal_model);media.inspect_model(model.model_id)
            recovery=execute_case(request,context,'direct');assert recovery['success']
            return 0
        if args.cancel_after:
            assert first['result']['status']=='cancelled' and not first['owned_processes_after'] and not first['resource_leases_after']
            return 0
        if not first['success']:return 1
        if args.suite:
            from PIL import Image
            from morice.media_lab.contracts import Quality
            inputs=data/'media'/'validation-inputs';inputs.mkdir(exist_ok=True)
            reference=first['history']['artifacts'][0]['path']
            mask=inputs/'mask.png';im=Image.new('L',(512,512),0);im.paste(255,(256,0,512,512));im.save(mask)
            small=inputs/'small-reference.png'
            with Image.open(reference) as image:image.resize((384,384)).save(small)
            cases=[replace(request,seed=91002,count=2,output_format='WEBP'),
                replace(request,intent='IMAGE_TO_IMAGE',reference_images=(reference,),seed=91003,output_format='JPEG'),
                replace(request,intent='INPAINT',reference_images=(reference,),mask=str(mask),seed=91004),
                replace(request,intent='OUTPAINT',reference_images=(str(small),),seed=91005),
                replace(request,quality=Quality.MAXIMUM_THAT_FITS,seed=91006)]
            for item in cases:
                ctx=ExecutionContext(active_files=tuple(p for p in (*item.reference_images,item.mask) if p))
                assert execute_case(item,ctx)['success']
            report['contact_sheet']=media.contact_sheet([c['generation_id'] for c in report['cases']]).to_dict()
            assert report['contact_sheet']['success']
            report['soak_scope']='Six sequential actual model loads in one runtime, including edits and benchmark-selected maximum'
            report['storage']=media.storage_stats();report['parent_rss_before_suite']=before;report['parent_rss_after_suite']=psutil.Process().memory_info().rss
            atomic_json(output,report)
        return 0
    except Exception as exc:
        report['error']=type(exc).__name__+': '+str(exc);atomic_json(output,report);raise
    finally:
        if args.oom and normal_model is not None and media is not None:
            # Never persist the deliberately reduced allocator-test descriptor.
            media.models.register(normal_model)
            report['test_model_descriptor_restored']=True
        if window is not None:window.close();app.processEvents()
        runtime.shutdown();report['shutdown']=runtime.shutdown_report;atomic_json(output,report)
        if settings_patch is not None:settings_patch.stop()
        faulthandler.cancel_dump_traceback_later();trace.close()


if __name__=='__main__':raise SystemExit(main())
