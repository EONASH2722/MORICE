"""Artifact observations plugged into the existing Kernel verification contract."""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from .storage import file_hash


def verify_image(path,width=None,height=None,*,allow_constant=False,token=None):
    from PIL import Image,ImageStat
    path=Path(path)
    if not path.is_file() or not 0<path.stat().st_size<=64*1024*1024:raise ValueError('Image file missing or outside byte budget.')
    with Image.open(path) as image:
        image.verify()
    with Image.open(path) as image:
        if image.width*image.height>16*1024*1024:raise ValueError('Image exceeds decode pixel budget.')
        image.load()
        if width is not None and image.size!=(width,height):raise ValueError('Decoded image dimensions differ from requested output.')
        if image.mode not in {'RGB','RGBA','L','P'}:raise ValueError('Unsupported decoded image channels.')
        variation=max(ImageStat.Stat(image.convert('RGB').resize((64,64))).stddev)
        if variation<.1 and not allow_constant:raise ValueError('Generated image is nearly constant; explicit minimalism allowance required.')
        data={'width':image.width,'height':image.height,'channels':len(image.getbands()),'format':image.format,'pixel_variation':variation,'decoded':True}
    return {**data,'path':str(path.resolve()),'bytes':path.stat().st_size,'sha256':file_hash(path,token)}


def verify_video(path,width,height,frames,fps,*,motion_required=False,token=None):
    from PIL import Image
    path=Path(path)
    if not path.is_file() or not 0<path.stat().st_size<=512*1024*1024:raise ValueError('Video missing or exceeds byte budget.')
    if path.suffix.lower()=='.gif':
        hashes=[];duration=0
        with Image.open(path) as image:
            actual=getattr(image,'n_frames',1)
            if actual!=frames or image.size!=(width,height):raise ValueError('GIF frame count/dimensions mismatch.')
            for i in range(actual):
                if token:token.raise_if_cancelled()
                image.seek(i);image.load();duration+=image.info.get('duration',0)
                hashes.append(__import__('hashlib').sha256(image.convert('RGB').tobytes()).hexdigest())
        if abs(duration/1000-frames/fps)>max(.2,frames*.01):raise ValueError('GIF duration mismatch.')
        if motion_required and len(set(hashes))==1:raise ValueError('Requested motion produced identical frames.')
        metadata={'container':'GIF','codec':'GIF','frames':actual,'width':width,'height':height,'duration':duration/1000,'decoded':True,'motion_detected':len(set(hashes))>1}
    else:
        ffmpeg=shutil.which('ffmpeg');ffprobe=shutil.which('ffprobe')
        if not ffmpeg or not ffprobe:raise ValueError('ffmpeg/ffprobe are required to verify encoded video.')
        import json
        response=subprocess.run([ffprobe,'-v','error','-count_frames','-select_streams','v:0','-show_entries','stream=codec_name,width,height,nb_read_frames:format=duration,format_name','-of','json',str(path)],capture_output=True,text=True,timeout=10,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        if response.returncode:raise ValueError('Video container could not be decoded.')
        info=json.loads(response.stdout);stream=info['streams'][0];duration=float(info['format']['duration'])
        if int(stream['nb_read_frames'])!=frames or (stream['width'],stream['height'])!=(width,height) or abs(duration-frames/fps)>max(.2,1/fps):raise ValueError('Decoded video dimensions/frame count/duration mismatch.')
        # Decode ALL frames to prove codec usability. The max dimensions/count
        # bound this output, avoiding a pipe or memory allocation per pixel.
        response=subprocess.run([ffmpeg,'-nostdin','-v','error','-i',str(path),'-vf','scale=32:32','-f','framemd5','-'],capture_output=True,text=True,timeout=20,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        if response.returncode:raise ValueError('Video frame decode failed.')
        hashes=[line.rsplit(',',1)[-1].strip() for line in response.stdout.splitlines() if line and not line.startswith('#')]
        if len(hashes)!=frames:raise ValueError('Full video decode frame count mismatch.')
        if motion_required and len(set(hashes))==1:raise ValueError('Requested video motion produced identical frames.')
        metadata={'container':info['format']['format_name'],'codec':stream['codec_name'],'frames':frames,'width':width,'height':height,'duration':duration,'decoded':True,'motion_detected':len(set(hashes))>1}
    return {**metadata,'path':str(path.resolve()),'bytes':path.stat().st_size,'sha256':file_hash(path,token)}


def atomic_export(source,destination,expected_hash):
    source=Path(source);destination=Path(destination).resolve()
    if file_hash(source)!=expected_hash:raise ValueError('Artifact changed before export.')
    if destination.exists():raise FileExistsError('Export never silently overwrites an existing file.')
    destination.parent.mkdir(parents=True,exist_ok=True)
    handle,temporary=tempfile.mkstemp(prefix='.media-export-',suffix='.tmp',dir=destination.parent)
    os.close(handle)
    try:
        shutil.copyfile(source,temporary)
        if file_hash(temporary)!=expected_hash:raise ValueError('Export hash verification failed.')
        # Atomic hard-link publication gives create-if-absent semantics; unlike
        # os.replace it cannot clobber a concurrently created destination.
        os.link(temporary,destination)
    finally:
        if os.path.exists(temporary):os.unlink(temporary)
    return {'path':str(destination),'sha256':expected_hash,'verified':True}
