"""Explicit educational transforms, never a strong-encryption recovery claim."""
import codecs,string
from pathlib import Path
from .contracts import Limits,LimitReached,sha256

def transform(text,method,key='',inverse=False):
    if method=='ROT13':return codecs.encode(text,'rot13')
    if method=='ATBASH':
        return text.translate(str.maketrans(string.ascii_lowercase+string.ascii_uppercase,string.ascii_lowercase[::-1]+string.ascii_uppercase[::-1]))
    if method=='CAESAR':
        shift=int(key)%26
        if inverse:shift=-shift
        letters=string.ascii_lowercase;upper=string.ascii_uppercase
        return text.translate(str.maketrans(letters+upper,letters[shift:]+letters[:shift]+upper[shift:]+upper[:shift]))
    if method=='VIGENERE':
        if not key or any(c not in string.ascii_letters for c in key) or len(key)>256:raise ValueError('Use an explicit ASCII-letter Vigenere key.')
        result=[];index=0
        for char in text:
            if char in string.ascii_letters:
                offset=ord('A' if char.isupper() else 'a');amount=ord(key[index%len(key)].lower())-97
                result.append(chr((ord(char)-offset+(-amount if inverse else amount))%26+offset));index+=1
            else:result.append(char)
        return ''.join(result)
    raise ValueError('Choose a supported educational cipher.')

def decode_cipher(path,destination,method,key='',limits=None):
    limits=limits or Limits()
    if Path(path).stat().st_size>min(limits.input_bytes,1024**2):raise LimitReached()
    original=Path(path).read_text(encoding='utf-8-sig');decoded=transform(original,method,key,inverse=True)
    if transform(decoded,method,key)!=original:raise ValueError('Educational round-trip verification failed.')
    output=Path(destination)/'cipher-candidate.txt';raw=decoded.encode('utf-8')
    if len(raw)>limits.output_bytes:raise LimitReached()
    with output.open('xb') as stream:stream.write(raw)
    return {'status':'DECODED_CANDIDATE','cipher':method,'artifacts':[{'path':str(output),'sha256':sha256(output),'bytes':len(raw)}],
        'verification':'Explicit toy transform round-tripped to the original text and output readback hashed.',
        'limitation':'A reversible candidate is not proof of intended plaintext. This is not a modern-encryption attack.'}
