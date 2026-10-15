"""Small deterministic media intent router; user's words remain the prompt."""
from __future__ import annotations

import re
from .contracts import ImageRequest,VideoRequest


def route_media_intent(text,reference_images=(),model_id=''):
    text=str(text).strip();lower=text.casefold()
    if not 1<=len(text)<=4000:return None
    video=bool(re.search(r'\b(?:animate|image[ -]to[ -]video)\b',lower)) or bool(re.search(r'\b(?:create|generate|make)\b.*\b(?:video|clip)\b',lower))
    image=bool(re.search(r'\b(?:create|generate|draw|make|edit|restyle|inpaint|outpaint|upscale)\b',lower)) and bool(re.search(r'\b(?:image|photo|picture|art|illustration|wallpaper|texture)\b',lower))
    if not video and not image:return None
    dimensions=re.search(r'\b(\d{2,4})\s*[x×]\s*(\d{2,4})\b',text)
    width,height=(int(dimensions[1]),int(dimensions[2])) if dimensions else (768,432) if '16:9' in lower else (512,512)
    references=tuple(reference_images)
    if video:
        return VideoRequest(text,model_id,intent='IMAGE_TO_VIDEO' if references else 'TEXT_TO_VIDEO',reference_images=references,width=width,height=height)
    intent='OUTPAINT' if 'outpaint' in lower else 'INPAINT' if 'inpaint' in lower else 'UPSCALE' if 'upscale' in lower else 'IMAGE_TO_IMAGE' if references else 'TEXT_TO_IMAGE'
    count=1
    match=re.search(r'\b([1-8]|two|three|four|five|six|seven|eight)\s+(?:variations|images|options)\b',lower)
    if match:count={'two':2,'three':3,'four':4,'five':5,'six':6,'seven':7,'eight':8}.get(match[1],int(match[1]) if match[1].isdigit() else 1)
    return ImageRequest(text,model_id,intent=intent,reference_images=references,width=width,height=height,count=count)
