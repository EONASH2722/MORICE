"""ACTUAL CUDA allocator OOM fixture; does not load a diffusion model."""
import gc,json,sys
import torch

try:
    if not torch.cuda.is_available():raise RuntimeError('CUDA unavailable')
    total=torch.cuda.get_device_properties(0).total_memory
    torch.cuda.set_per_process_memory_fraction(64*2**20/total)
    # Deliberately exceed only this worker's 64 MiB allocator budget. This
    # allocates no large host tensor and never exhausts host-wide VRAM.
    tensor=torch.empty((128*2**20,),dtype=torch.uint8,device='cuda')
    raise RuntimeError('The bounded CUDA allocation unexpectedly succeeded.')
except torch.OutOfMemoryError as exc:
    gc.collect();torch.cuda.empty_cache()
    print(json.dumps({'type':'error','oom':True,'message':'ACTUAL bounded CUDA OutOfMemoryError: '+str(exc)[:1000]}),flush=True)
    sys.exit(2)
