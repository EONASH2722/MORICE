"""CONTROLLED TEST PROVIDER, not a real diffusion model or product backend."""
import argparse,json,sys,time
from pathlib import Path
from PIL import Image

parser=argparse.ArgumentParser();parser.add_argument('--job');args=parser.parse_args()
job=json.loads(Path(args.job).read_text());request=job['request'];directory=Path(job['output_directory'])
emit=lambda **value:print(json.dumps(value),flush=True)
prompt=request['prompt']
emit(type='progress',stage='GENERATING',step=1,total_steps=2)
if prompt=='crash':sys.exit(17)
if prompt=='oom':emit(type='error',message='Controlled CUDA out of memory fixture',oom=True);sys.exit(2)
if prompt=='oom-fallback' and request['width']>=128:emit(type='error',message='Controlled CUDA out of memory fixture',oom=True);sys.exit(2)
if prompt=='slow':time.sleep(30)
if prompt=='ram':
    bounded_fixture_buffer=bytearray(64*1024*1024)
    time.sleep(5)
time.sleep(.03)
files=[]
width=request['width']+(8 if prompt=='wrong-size' else 0);height=request['height']
def frame(offset):
    image=Image.new('RGB',(width,height))
    image.putdata([((x+request['seed']+offset)%256,(y*3+offset)%256,(x+y+offset)%256) for y in range(height) for x in range(width)])
    return image
if request['intent']=='IMAGE_TO_VIDEO':
    frames=[frame(i*8) for i in range(request['frames'])];path=directory/'fixture.gif'
    frames[0].save(path,save_all=True,append_images=frames[1:],duration=round(1000/request['fps']),loop=0,optimize=False);files.append(str(path))
else:
    for i in range(request['count']):
        path=directory/f'fixture_{i}.png'
        if prompt=='corrupt':path.write_bytes(b'not an image')
        else:frame(i*8).save(path)
        files.append(str(path))
emit(type='progress',stage='GENERATING',step=2,total_steps=2)
emit(type='result',files=files,backend_version='controlled-fixture-v1',metrics={'model_load_ms':0,'generation_ms':30,'peak_vram_mb':0})
