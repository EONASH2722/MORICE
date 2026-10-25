"""Bounded stable-ID selection from actual domain records, never from salience alone."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import math
import re


def label(record):
    return str(record.get('title') or record.get('name') or record.get('objective') or record.get('id',''))[:240]


def timestamp(record):
    value=record.get('updated',record.get('last_used',record.get('created',None)))
    if type(value) in (int,float):return float(value) if math.isfinite(value) else None
    if isinstance(value,str):
        try:
            parsed=datetime.fromisoformat(value.replace('Z','+00:00'))
            return parsed.timestamp() if parsed.tzinfo is not None else None
        except (ValueError,OverflowError):return None
    return None


@dataclass(frozen=True)
class TargetSelection:
    record: dict|None
    question: str=''
    choices: tuple[dict,...]=()


def select_target(reference,records,*,active_id='',kind='item'):
    candidates=[dict(r) for r in records if r.get('id')][:1000]
    clean=' '.join(str(reference or '').casefold().strip(' "').split())
    for prefix in ('my ','the '):
        if clean.startswith(prefix):clean=clean[len(prefix):]
    if not candidates:return TargetSelection(None,f'No saved {kind}s are available.')
    temporal=re.fullmatch(r'(latest|newest|first|oldest|earliest|original|most recent) (.+)',clean)
    if temporal:
        matching=[r for r in candidates if temporal[2] in label(r).casefold()]
        return select_target(temporal[1],matching,active_id=active_id,kind=kind)
    exact=[r for r in candidates if clean and clean in {str(r['id']).casefold(),label(r).casefold()}]
    if len(exact)==1:return TargetSelection(exact[0])
    if clean in {'this','that','it','current','selected','active',''} and active_id:
        active=[r for r in candidates if str(r['id'])==active_id]
        if len(active)==1:return TargetSelection(active[0])
    if clean=='previous' and active_id:
        active=next((r for r in candidates if str(r['id'])==active_id),None)
        stamp=timestamp(active) if active else None
        dated=[r for r in candidates if timestamp(r) is not None and stamp is not None and timestamp(r)<stamp]
        if dated:
            previous=max(timestamp(r) for r in dated)
            matches=[r for r in dated if timestamp(r)==previous]
            if len(matches)==1:return TargetSelection(matches[0])
            candidates=matches
    if clean in {'latest','last','newest','most recent','most recently modified','first','oldest','original','earliest'}:
        dated=[(timestamp(r),r) for r in candidates]
        if all(stamp is not None for stamp,_ in dated):
            wanted=(min if clean in {'first','oldest','original','earliest'} else max)(stamp for stamp,_ in dated)
            exact=[r for stamp,r in dated if stamp==wanted]
            if len(exact)==1:return TargetSelection(exact[0])
            candidates=exact
        question=f'The {kind} timestamps are missing or tied. Which one should I use?'
    else:
        if exact:candidates=exact
        elif clean and clean not in {'this','that','it','current','selected','active','', 'previous'}:
            matching=[r for r in candidates if clean in label(r).casefold()]
            if not matching:return TargetSelection(None,f'No saved {kind} matches “{reference}”.')
            candidates=matching
        if len(candidates)==1 and clean not in {'previous'}:return TargetSelection(candidates[0])
        question=f'Which {kind} should I use?'
    return TargetSelection(None,question,tuple({'id':str(r['id']),'label':label(r),
        'updated':r.get('updated',r.get('last_used',r.get('created')))} for r in candidates[:20]))
