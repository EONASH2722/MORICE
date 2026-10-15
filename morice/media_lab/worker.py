"""Standalone isolated worker. Heavy optional imports exist ONLY in this file.

Invoke with an explicitly configured external Python, including from frozen apps.
No network/model download, custom pipeline, remote code or package installation.
"""
from __future__ import annotations

import argparse
import gc
import hashlib
import importlib.metadata
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path


def emit(**value):print(json.dumps(value,allow_nan=False),flush=True)


def probe():
    packages=('torch','diffusers','transformers','accelerate','safetensors','PIL')
    missing=[name for name in packages if importlib.util.find_spec(name) is None]
    versions={name:importlib.metadata.version('Pillow' if name=='PIL' else name) for name in packages if name not in missing}
    if missing:return {'available':False,'reason':'Missing optional worker packages: '+', '.join(missing),'version':json.dumps(versions,sort_keys=True),'versions':versions}
    import torch
    available=torch.cuda.is_available()
    return {'available':available,'reason':'CUDA Diffusers packages available; model still requires actual load.' if available else 'CUDA runtime is unavailable to the external worker.',
        'version':json.dumps(versions,sort_keys=True),'versions':versions,'cuda':torch.version.cuda}


def verify_bundle(model):
    root=Path(model['model_path']).resolve()
    for entry in model.get('files',[]):
        path=root/entry['path']
        if path.is_symlink() or not path.resolve().is_relative_to(root):raise ValueError('Model file path escape.')
        if path.stat().st_size!=entry['bytes']:raise ValueError('Model file changed before loading.')
        digest=hashlib.sha256()
        with path.open('rb') as stream:
            while chunk:=stream.read(1024*1024):digest.update(chunk)
        if digest.hexdigest()!=entry['sha256']:raise ValueError('Model hash changed before loading.')
    if not model.get('files') or not model.get('sha256'):raise ValueError('Inspected model manifest required.')
    index=json.loads((root/'model_index.json').read_text(encoding='utf-8'))
    allowed={'StableDiffusionPipeline','StableDiffusionInpaintPipeline','StableDiffusionXLPipeline','StableDiffusionXLInpaintPipeline','StableVideoDiffusionPipeline'}
    if index.get('_class_name') not in allowed or index['_class_name']!=model['pipeline_class']:raise ValueError('Unreviewed model pipeline.')
    # Model metadata is data. Component imports are restricted to the bundled
    # upstream implementations, with no custom module or auto_map dispatch.
    components={'UNet2DConditionModel','UNetSpatioTemporalConditionModel','AutoencoderKL','AutoencoderKLTemporalDecoder',
        'CLIPTextModel','CLIPTextModelWithProjection','CLIPTokenizer','CLIPImageProcessor','CLIPVisionModelWithProjection',
        'EulerDiscreteScheduler','EulerAncestralDiscreteScheduler','DDIMScheduler','PNDMScheduler','LMSDiscreteScheduler','DPMSolverMultistepScheduler','StableDiffusionSafetyChecker'}
    for key,value in index.items():
        if key=='requires_safety_checker' and type(value) is bool:continue
        if key.startswith('_') or value in (None,[None,None]):continue
        if not isinstance(value,list) or len(value)!=2 or value[0] not in {'diffusers','transformers','stable_diffusion'} or value[1] not in components:raise ValueError('Unreviewed executable model component.')
    for path in root.glob('*/config.json'):
        value=json.loads(path.read_text(encoding='utf-8'))
        if 'auto_map' in value or value.get('trust_remote_code'):raise ValueError('Remote model code is not trusted.')
    return root


def encode_frames(frames,request,directory):
    from PIL import Image
    format=request['output_format'].upper();fps=request['fps']
    paths=[]
    for i,frame in enumerate(frames):
        if not isinstance(frame,Image.Image):raise ValueError('Backend did not return decoded image frames.')
        path=directory/f'frame_{i:05d}.png';frame.convert('RGB').save(path);paths.append(str(path))
    emit(type='progress',stage='ENCODING')
    suffix={'MP4':'.mp4','WEBM':'.webm','GIF':'.gif'}[format];target=directory/('video'+suffix)
    if format=='GIF':
        frames[0].save(target,save_all=True,append_images=frames[1:],duration=round(1000/fps),loop=0,optimize=False)
    else:
        ffmpeg=shutil.which('ffmpeg')
        if not ffmpeg:raise ValueError('ffmpeg unavailable; MP4/WebM encoding is degraded.')
        codec=['-c:v','libx264','-pix_fmt','yuv420p'] if format=='MP4' else ['-c:v','libvpx-vp9','-pix_fmt','yuv420p']
        command=[ffmpeg,'-nostdin','-v','error','-n','-framerate',str(fps),'-i',str(directory/'frame_%05d.png'),*codec,str(target)]
        # No shell. Termination of the inference worker cannot leave an encoder
        # child: encode runs with a bounded timeout and an explicit finally reap.
        process=subprocess.Popen(command,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        try:
            _,error=process.communicate(timeout=60)
            if process.returncode:raise ValueError('Video encoding failed: '+error.decode(errors='replace')[:500])
        finally:
            if process.poll() is None:process.kill();process.wait(timeout=3)
    return [str(target)],paths


def generate(job):
    started=time.perf_counter();model=job['model'];request=job['request'];mode=job['plan']['mode']
    directory=Path(job['output_directory']).resolve();root=verify_bundle(model)
    if mode not in {'direct','low_vram','offload'}:raise ValueError('Unsupported execution mode.')
    if request.get('controls') or request.get('loras'):raise ValueError('Control/LoRA adapters have not been validated by this worker.')
    emit(type='progress',stage='LOADING_MODEL')
    import torch
    import diffusers
    from PIL import Image,ImageOps
    dtype={'fp16':torch.float16,'fp32':torch.float32,'bf16':torch.bfloat16}[model['precision']]
    if dtype==torch.bfloat16 and not torch.cuda.is_bf16_supported():raise ValueError('GPU does not support BF16.')
    torch.cuda.reset_peak_memory_stats()
    # PyTorch's allocator limit enforces the admitted VRAM estimate and turns
    # impossible activation spikes into a worker-local OOM before OS thrashing.
    total=torch.cuda.get_device_properties(0).total_memory/2**20
    torch.cuda.set_per_process_memory_fraction(min(1,job['plan']['vram_mb']/total))
    options={'torch_dtype':dtype,'local_files_only':True,'use_safetensors':True}
    if model.get('variant'):options['variant']=model['variant']
    intent=request['intent']
    if intent=='IMAGE_TO_VIDEO':
        pipeline_class=diffusers.StableVideoDiffusionPipeline
    elif intent in {'INPAINT','OUTPAINT'}:pipeline_class=diffusers.AutoPipelineForInpainting
    elif intent in {'IMAGE_TO_IMAGE','IMAGE_VARIATION'}:pipeline_class=diffusers.AutoPipelineForImage2Image
    elif intent=='TEXT_TO_IMAGE':pipeline_class=diffusers.AutoPipelineForText2Image
    else:raise ValueError('Unimplemented diffusion workflow.')
    pipe=pipeline_class.from_pretrained(str(root),**options)
    pipe.set_progress_bar_config(disable=True)
    if mode=='offload':pipe.enable_model_cpu_offload()
    else:
        pipe.to('cuda')
        if mode=='low_vram':
            pipe.enable_attention_slicing()
            if hasattr(pipe,'enable_vae_slicing'):pipe.enable_vae_slicing()
            if hasattr(pipe,'enable_vae_tiling'):pipe.enable_vae_tiling()
    loaded=time.perf_counter();emit(type='progress',stage='GENERATING')
    kwargs={'width':request['width'],'height':request['height'],'num_inference_steps':request['steps']}
    if intent!='IMAGE_TO_VIDEO':kwargs.update(prompt=request['prompt'],guidance_scale=request['guidance'])
    if request.get('negative_prompt') and request.get('guidance',0)>1:kwargs['negative_prompt']=request['negative_prompt']
    generator=torch.Generator(device='cpu').manual_seed(request['seed']);kwargs['generator']=generator
    reference=None;mask=None
    if intent!='TEXT_TO_IMAGE':
        if len(request.get('reference_images',[]))!=1:raise ValueError('Exactly one approved reference image is required.')
        with Image.open(request['reference_images'][0]) as image:
            image.load();reference=ImageOps.exif_transpose(image).convert('RGB')
        if intent=='OUTPAINT':
            if reference.width>request['width'] or reference.height>request['height']:raise ValueError('Outpaint canvas must contain the source image.')
            canvas=Image.new('RGB',(request['width'],request['height']));mask=Image.new('L',canvas.size,255)
            position=((canvas.width-reference.width)//2,(canvas.height-reference.height)//2)
            canvas.paste(reference,position);mask.paste(0,(*position,position[0]+reference.width,position[1]+reference.height));reference=canvas
        else:reference=reference.resize((request['width'],request['height']))
        kwargs['image']=reference
        if intent=='INPAINT':
            with Image.open(request['mask']) as image:image.load();mask=image.convert('L').resize(reference.size)
        if mask is not None:kwargs['mask_image']=mask
        if intent in {'IMAGE_TO_IMAGE','IMAGE_VARIATION','INPAINT','OUTPAINT'}:kwargs['strength']=request['strength']
    completed_steps=0;image_index=0
    def callback(pipeline,step,timestep,callback_kwargs):
        nonlocal completed_steps
        completed_steps+=1
        emit(type='progress',stage='GENERATING',step=step+1,total_steps=int(getattr(pipeline,'num_timesteps',request['steps'])),image_index=image_index,total_images=request['count'])
        return callback_kwargs
    kwargs['callback_on_step_end']=callback
    if intent=='IMAGE_TO_VIDEO':
        kwargs.update(num_frames=request['frames'],decode_chunk_size=1)
        # SVD does not condition on text; preserve the prompt as user intent and
        # disclose this model limitation in metadata rather than fabricate use.
        result=pipe(**kwargs);frames=result.frames[0]
        images=None
    else:
        # Sequential variations avoid batch activation spikes on small GPUs.
        images=[]
        for i in range(request['count']):
            image_index=i
            kwargs['generator']=torch.Generator(device='cpu').manual_seed(request['seed']+i)
            result=pipe(**kwargs)
            if getattr(result,'nsfw_content_detected',None) and any(result.nsfw_content_detected):raise ValueError('Backend safety policy rejected the generated output.')
            image=result.images[0]
            if mask is not None:image=Image.composite(image,reference,mask)
            images.append(image)
    generated=time.perf_counter();peak_vram=torch.cuda.max_memory_allocated()/2**20
    del result;del pipe;gc.collect();torch.cuda.empty_cache();torch.cuda.synchronize()
    emit(type='progress',stage='POSTPROCESSING')
    frame_paths=[];encoding_ms=0
    if images is None:
        encoded=time.perf_counter();files,frame_paths=encode_frames(frames,request,directory);encoding_ms=(time.perf_counter()-encoded)*1000
    else:
        files=[];suffix={'PNG':'.png','JPEG':'.jpg','WEBP':'.webp'}[request['output_format'].upper()]
        for i,image in enumerate(images):
            path=directory/f'image_{i}{suffix}';image.convert('RGB').save(path,format=request['output_format'].upper());files.append(str(path))
    emit(type='result',files=files,frames=frame_paths,backend_version=probe()['version'],metrics={
        'model_load_ms':(loaded-started)*1000,'generation_ms':(generated-loaded)*1000,'encoding_ms':encoding_ms,
        'peak_vram_mb':peak_vram,'vram_allocated_after_unload_mb':torch.cuda.memory_allocated()/2**20,'completed_steps':completed_steps},
        warnings=['This local bundle has no embedded content safety classifier.'] if json.loads((root/'model_index.json').read_text()).get('safety_checker') in (None,[None,None]) else [])


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--probe',action='store_true');parser.add_argument('--job')
    args=parser.parse_args()
    if args.probe:emit(**probe());return 0
    try:
        path=Path(args.job)
        if path.stat().st_size>256*1024:raise ValueError('Job metadata too large.')
        generate(json.loads(path.read_text(encoding='utf-8')));return 0
    except BaseException as exc:
        message=str(exc);oom=type(exc).__name__=='OutOfMemoryError' or 'out of memory' in message.lower()
        try:
            if 'torch' in sys.modules:
                gc.collect();sys.modules['torch'].cuda.empty_cache()
        except Exception:pass
        emit(type='error',message=type(exc).__name__+': '+message[:1500],oom=oom);return 2


if __name__=='__main__':raise SystemExit(main())
