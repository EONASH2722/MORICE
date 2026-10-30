"""Readable, bounded text from an actual response source; no invented results."""
import json

def source_text(snapshot,component):
    if snapshot is None:
        config=component.config
        if component.kind=='math':return 'Formula: '+str(config.get('formula','No formula supplied.'))
        return 'Supplied diagram description:\n'+json.dumps(config,ensure_ascii=False,indent=2)[:16000]
    lines=[snapshot.title,'Source: '+snapshot.provenance]
    if snapshot.limitation:lines.append(snapshot.limitation)
    if not snapshot.verified:lines.append('Source verification is unavailable; these values are not verified results.')
    for key,value in snapshot.data.items():
        if key in {'rows','attempts','findings','artifacts'} or value is None:continue
        label=str(key).replace('_',' ').capitalize()
        text=json.dumps(value,ensure_ascii=False,default=str) if isinstance(value,(dict,list)) else str(value)
        unit=snapshot.units.get(key,'')
        lines.append(label+': '+text[:2000]+(' '+str(unit) if unit else ''))
    if snapshot.rows:
        lines.append('\nAvailable source records:')
        for index,row in enumerate(snapshot.rows[:30],1):
            text='; '.join(str(key).replace('_',' ')+': '+str(value) for key,value in row.items()) if isinstance(row,dict) else str(row)
            lines.append(str(index)+'. '+text[:1500])
        if len(snapshot.rows)>30:lines.append('Showing 30 of '+str(len(snapshot.rows))+' records in this source snapshot.')
    for artifact in snapshot.artifacts[:20]:
        lines.append(('Available file: ' if artifact.available else 'Unavailable file: ')+artifact.name+'; SHA-256 '+artifact.sha256)
    result='\n'.join(lines)
    return result if len(result)<=20000 else result[:19800]+'\n[Text preview truncated; the original source remains available.]'
