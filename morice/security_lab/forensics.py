"""Bounded signature inspection; entropy and script ranges are observations."""
from __future__ import annotations
import base64, binascii, collections, csv, gzip, hashlib, html, io, json, math, re, sqlite3, struct, tarfile, time, unicodedata, urllib.parse, wave, zipfile, zlib
from pathlib import Path
from .contracts import Budget, IntegrityFailure, LimitReached, Limits, Unsupported, member_name, sha256

MAGIC=b'MORICE-LAB-AEAD-1\n'
SIGNATURES=((b'PK\x03\x04','ZIP'),(b'PK\x05\x06','ZIP'),(b'7z\xbc\xaf\x27\x1c','7Z'),
    (b'\x1f\x8b','GZIP'),(b'%PDF-','PDF'),(b'SQLite format 3\0','SQLITE'),
    (b'\x89PNG\r\n\x1a\n','PNG'),(b'\xff\xd8\xff','JPEG'),(b'GIF8','GIF'),(b'MZ','PE'),
    (b'\x7fELF','ELF'),(b'RIFF','RIFF'),(b'ID3','MP3'),(b'Rar!','RAR'),
    (b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1','OLE_COMPOUND'),(MAGIC,'MORICE_AEAD'))

def signature(data):
    for magic,name in SIGNATURES:
        if data.startswith(magic):return name
    if len(data)>262 and data[257:262]==b'ustar':return 'TAR'
    return 'UNKNOWN'

def text_info(data):
    encodings=['utf-8-sig']
    if data.startswith((b'\xff\xfe\0\0',b'\0\0\xfe\xff')):encodings=['utf-32']
    elif data.startswith((b'\xff\xfe',b'\xfe\xff')):encodings=['utf-16']
    for encoding in encodings:
        try:
            text=data.decode(encoding)
            if not text or sum(c.isprintable() or c in '\r\n\t' for c in text)/len(text)<.9:continue
            scripts=collections.Counter()
            for c in text:
                if not c.isalpha():continue
                name=unicodedata.name(c,'')
                script=next((s for s in ('TAMIL','DEVANAGARI','ARABIC','HIRAGANA','KATAKANA','HANGUL','CYRILLIC','GREEK','HEBREW','LATIN') if s in name),'HAN' if 'CJK' in name else 'OTHER')
                scripts[script]+=1
            return {'encoding':encoding,'scripts':dict(scripts),'preview':text[:1200],
                'language_note':'Unicode scripts observed; script alone does not establish a language.'}
        except UnicodeError:pass
    return {'encoding':None,'scripts':{},'preview':'','language_note':'No validated Unicode text; arbitrary bytes are not an unknown language.'}

def zip_metadata(path,limits):
    # Reject a huge classic central directory before zipfile materializes it.
    with Path(path).open('rb') as stream:
        stream.seek(max(0,Path(path).stat().st_size-65557));tail=stream.read()
    pos=tail.rfind(b'PK\x05\x06')
    if pos<0 or len(tail)-pos<22:raise IntegrityFailure('ZIP central directory missing')
    entries=struct.unpack_from('<H',tail,pos+10)[0]
    if entries==65535:raise UnsupportedZip64()
    if entries>limits.members:raise LimitReached()
    with zipfile.ZipFile(path) as archive:
        infos=archive.infolist()
        if len(infos)>limits.members:raise LimitReached()
        rows=[];seen=set();total=0
        for info in infos:
            name=member_name(info.filename)
            if name.casefold() in seen:raise IntegrityFailure('Aliased archive paths')
            seen.add(name.casefold());total+=info.file_size
            if total>limits.output_bytes or info.file_size>max(1,info.compress_size)*limits.expansion_ratio:raise LimitReached()
            mode=(info.external_attr>>16)&0o170000
            if mode==0o120000:raise IntegrityFailure('Archive symbolic link')
            scheme='ZipCrypto' if info.flag_bits&1 else 'none';strength=None
            offset=0
            while offset+4<=len(info.extra):
                kind,size=struct.unpack_from('<HH',info.extra,offset);extra=info.extra[offset+4:offset+4+size];offset+=4+size
                if kind==0x9901 and len(extra)>=7:
                    strength={1:128,2:192,3:256}.get(extra[4]);scheme='WinZip AES-'+str(strength)
            row={'name':name,'bytes':info.file_size,'compressed_bytes':info.compress_size,'scheme':scheme,
                'password_based':scheme!='none','kdf':'PBKDF2-HMAC-SHA1, 1000 iterations' if 'AES' in scheme else None,
                'salt':'Per-entry prefix; '+str({128:8,192:12,256:16}.get(strength,0))+' bytes' if strength else None,
                'integrity':'HMAC-SHA1-80' if strength else 'CRC32 (not cryptographic authentication)',
                'crc32_hex':format(info.CRC,'08x'),'offline_verification':bool(info.flag_bits&1)}
            if strength:
                salt_length={128:8,192:12,256:16}[strength]
                with Path(path).open('rb') as source:
                    source.seek(info.header_offset);local=source.read(30)
                    if len(local)!=30 or local[:4]!=b'PK\x03\x04':raise IntegrityFailure()
                    name_length,extra_length=struct.unpack_from('<HH',local,26)
                    data_offset=info.header_offset+30+name_length+extra_length
                    if info.compress_size<salt_length+12 or data_offset+info.compress_size>Path(path).stat().st_size:raise IntegrityFailure()
                    source.seek(data_offset);row['salt_hex']=source.read(salt_length).hex()
                    source.seek(data_offset+info.compress_size-10);row['authentication_tag_hex']=source.read(10).hex()
            rows.append(row)
        return rows

class UnsupportedZip64(Unsupported):pass

def inspect(path,limits=None):
    limits=limits or Limits();path=Path(path)
    if path.stat().st_size>limits.input_bytes:raise LimitReached()
    with path.open('rb') as stream:data=stream.read(min(1024**2,limits.input_bytes))
    kind=signature(data);counts=collections.Counter(data)
    entropy=-sum((n/len(data))*math.log2(n/len(data)) for n in counts.values()) if data else 0
    result={'format':kind,'claimed_extension':path.suffix,'bytes':path.stat().st_size,'sha256':sha256(path),
        'signature_confidence':'signature match' if kind!='UNKNOWN' else 'unknown',
        'entropy_bits_per_sample_byte':entropy,'entropy_note':'Entropy alone is not proof of encryption.',
        'hex_preview':data[:128].hex(' '),'text':text_info(data[:65536]),'encryption':{'scheme':'unknown','offline_verification':False}}
    if kind=='ZIP':
        try:
            rows=zip_metadata(path,limits);encrypted=[r for r in rows if r['password_based']]
            result['members']=rows;result['encryption']={'scheme':', '.join(sorted({r['scheme'] for r in encrypted})) or 'none',
                'password_based':bool(encrypted),'offline_verification':bool(encrypted)}
            names={r['name'] for r in rows}
            if '[Content_Types].xml' in names:result['format']='OOXML_ZIP'
        except UnsupportedZip64:result['parser_limitation']='ZIP64 central-directory inspection is not implemented.'
        except (zipfile.BadZipFile,IntegrityFailure):result['integrity_error']='Invalid ZIP structure or unsafe member path.'
    elif kind=='MORICE_AEAD':
        try:
            from .recovery import read_envelope
            header,cipher=read_envelope(path,limits)
            result['encryption']={**header,'offline_verification':True,'integrity':'AEAD 128-bit authentication tag',
                'scheme':header['algorithm'],'authentication_tag_hex':cipher[-16:].hex(),'password_based':header['kdf']['name']!='direct-key'}
        except (ValueError,IntegrityFailure):result['integrity_error']='Malformed AEAD envelope.'
    elif kind=='7Z':result['encryption']={'scheme':'7z container; encryption not established from signature alone','offline_verification':False}
    elif kind=='PDF':
        # The reader runs in an owned bounded worker, never in the UI process.
        from pypdf import PdfReader
        reader=PdfReader(path,strict=True)
        encrypted=bool(reader.is_encrypted)
        result['encryption']={'scheme':'PDF standard security handler' if encrypted else 'none',
            'password_based':encrypted,'offline_verification':encrypted}
        if encrypted:
            enc=reader.trailer.get('/Encrypt').get_object()
            result['encryption'].update({key:str(enc.get(key,''))[:100] for key in ('/Filter','/V','/R','/Length','/CF')})
        else:result['page_count']=len(reader.pages)
    elif kind=='SQLITE':
        with sqlite3.connect(path.resolve().as_uri()+'?mode=ro&immutable=1',uri=True) as database:
            budget=Budget(limits);database.set_progress_handler(lambda:int(time.monotonic()-budget.started>min(5,limits.seconds)),1000)
            result['tables']=[{'name':row[0],'type':row[1]} for row in database.execute("SELECT name,type FROM sqlite_master WHERE type IN ('table','view') ORDER BY name LIMIT 64")]
            result['parser_validation']='SQLite schema opened read-only; arbitrary stored SQL and extensions were not executed.'
    elif kind=='TAR':
        budget=Budget(limits);rows=[]
        with tarfile.open(path,'r:') as archive:
            for item in archive:
                budget.check()
                if len(rows)>=limits.members:raise LimitReached()
                rows.append({'name':member_name(item.name),'bytes':item.size,'regular_file':item.isfile(),'link':item.issym() or item.islnk()})
        result['members']=rows;result['compression']='TAR container; no extraction performed.'
    elif kind=='GZIP':result['compression']='GZIP; use Decode for bounded decompression and checksum validation.'
    elif kind in {'PNG','JPEG','GIF'}:
        from PIL import Image
        with Image.open(path) as image:
            result['image']={'format':image.format,'width':image.width,'height':image.height,'mode':image.mode}
            image.verify()
        result['parser_validation']='Image parser structural verification; original not rendered or executed.'
    elif kind=='RIFF' and data[8:12]==b'WAVE':
        with wave.open(str(path),'rb') as audio:
            result['audio']={'format':'WAV','channels':audio.getnchannels(),'sample_rate':audio.getframerate(),'frames':audio.getnframes(),'sample_width':audio.getsampwidth()}
    elif kind=='PE':
        if len(data)>=64:
            offset=struct.unpack_from('<I',data,60)[0]
            with path.open('rb') as stream:stream.seek(offset);header=stream.read(24)
            if len(header)==24 and header[:4]==b'PE\0\0':
                machine,sections=struct.unpack_from('<HH',header,4);result['executable']={'machine':hex(machine),'sections':sections,'executed':False}
            else:result['parser_limitation']='MZ signature present but a valid bounded PE header was not found.'
    elif kind=='UNKNOWN' and result['text']['encoding']:
        result['format']='TEXT';result['signature_confidence']='Validated Unicode sample; full-file structure not yet established.'
        if len(data)==path.stat().st_size:
            text=data.decode(result['text']['encoding'])
            try:
                value=json.loads(text)
                result.update(format='JSON',json_type=type(value).__name__,parser_validation='Complete JSON parsed as data.')
            except (ValueError,RecursionError):
                if text.lstrip().startswith('<') and '<!DOCTYPE' not in text.upper() and '<!ENTITY' not in text.upper():
                    try:
                        from xml.etree import ElementTree
                        root=ElementTree.fromstring(text);result.update(format='XML',root_tag=root.tag,parser_validation='Complete bounded XML parsed; DTD/entity input is not accepted.')
                    except ElementTree.ParseError:pass
                elif '\n' in text and any(c in text for c in ',\t;'):
                    try:
                        dialect=csv.Sniffer().sniff(text[:8192],delimiters=',\t;');rows=list(csv.reader(io.StringIO(text[:65536]),dialect))[:20]
                        if len(rows)>1 and len(rows[0])>1 and all(len(r)==len(rows[0]) for r in rows):result.update(format='CSV',rows_sampled=len(rows),columns=len(rows[0]),parser_validation='Consistent delimited-text sample; not a full dataset validation.')
                    except csv.Error:pass
    return result

def decode(path,destination,limits=None):
    limits=limits or Limits();budget=Budget(limits)
    if Path(path).stat().st_size>limits.input_bytes:raise LimitReached()
    data=Path(path).read_bytes();original=len(data);chain=[]
    for _ in range(limits.layers):
        budget.check();output=None;kind=signature(data)
        if kind=='GZIP':
            with gzip.GzipFile(fileobj=io.BytesIO(data)) as stream:
                blocks=[];size=0
                while block:=stream.read(65536):
                    size+=len(block);budget.check(len(block));blocks.append(block)
                    if size>max(1,original)*limits.expansion_ratio:raise LimitReached()
                output=b''.join(blocks)
            label='GZIP'
        else:
            try:text=data.decode('ascii').strip()
            except UnicodeError:break
            compact=''.join(text.split())
            try:
                if len(compact)>=8 and len(compact)%2==0 and re.fullmatch('[0-9a-fA-F]+',compact):output=bytes.fromhex(compact);label='HEX'
                elif len(compact)>=8 and len(compact)%4==0 and re.fullmatch('[A-Za-z0-9+/]+=*',compact):
                    try:
                        candidate=base64.b64decode(compact,validate=True)
                        if signature(candidate)!='UNKNOWN' or text_info(candidate)['encoding']:output=candidate;label='BASE64'
                    except binascii.Error:pass
                if output is None and len(compact)>=8 and len(compact)%8==0 and re.fullmatch('[A-Z2-7]+=*',compact):
                    candidate=base64.b32decode(compact)
                    if signature(candidate)!='UNKNOWN' or text_info(candidate)['encoding']:output=candidate;label='BASE32'
                if output is None and '%' in text:
                    candidate=urllib.parse.unquote_to_bytes(text)
                    if candidate!=data and text_info(candidate)['encoding']:output=candidate;label='URL'
                if output is None and '&' in text:
                    candidate=html.unescape(text).encode()
                    if candidate!=data:output=candidate;label='HTML_ENTITIES'
            except (ValueError,binascii.Error):break
        if output is None or output==data:break
        if len(output)>limits.output_bytes or len(output)>max(1,original)*limits.expansion_ratio:raise LimitReached()
        chain.append(label);data=output
    if not chain:return {'status':'UNSUPPORTED_FORMAT','message':'No validated supported reversible encoding chain found.'}
    path=Path(destination)/'decoded.bin'
    with path.open('xb') as stream:stream.write(data)
    return {'status':'RECOVERED','chain':chain,'artifacts':[{'path':str(path),'sha256':sha256(path),'bytes':len(data)}],
        'verification':'Reversible decoding and exact output readback hash; decoding is not decryption.'}
