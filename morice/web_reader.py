"""Read explicitly supplied web pages as bounded, untrusted context."""
from __future__ import annotations

from dataclasses import dataclass
from html.parser import HTMLParser
import re
import urllib.parse
import urllib.request


MAX_BYTES=2_000_000


def supplied_urls(text):
    # Code examples are context, not instructions to contact their example URLs.
    text=re.sub(r'```.*?```','',str(text),flags=re.S)
    urls=[]
    for value in re.findall(r'https?://[^\s<>"\x00-\x1f]+',text):
        value=value.rstrip('.,;!?)]}')
        if value not in urls:urls.append(value)
    return urls[:3]


def checked_url(url):
    parts=urllib.parse.urlsplit(url)
    if parts.scheme not in {'http','https'} or not parts.hostname or parts.username or parts.password:
        raise ValueError('Use an HTTP or HTTPS page without embedded credentials.')
    return urllib.parse.urlunsplit(parts._replace(fragment=''))


class PageText(HTMLParser):
    def __init__(self):super().__init__(convert_charrefs=True);self.hidden=0;self.title_depth=0;self.title=[];self.parts=[]
    def handle_starttag(self,tag,attrs):
        if tag in {'script','style','noscript','template'}:self.hidden+=1
        if tag=='title':self.title_depth+=1
        if tag in {'p','br','div','h1','h2','h3','li','tr'}:self.parts.append('\n')
    def handle_endtag(self,tag):
        if tag in {'script','style','noscript','template'}:self.hidden=max(0,self.hidden-1)
        if tag=='title':self.title_depth=max(0,self.title_depth-1)
    def handle_data(self,data):
        if self.hidden:return
        if self.title_depth:self.title.append(data)
        self.parts.append(data+' ')


class CheckedRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        return super().redirect_request(req,fp,code,msg,headers,checked_url(newurl))


@dataclass(frozen=True)
class ReadPage:
    url: str
    title: str
    text: str


def read_page(url,*,timeout=12,cancel_event=None,progress=None,opener=None):
    url=checked_url(url)
    if cancel_event is not None and cancel_event.is_set():raise InterruptedError('Page reading cancelled.')
    if progress:progress('Opening link: '+url)
    client=opener or urllib.request.build_opener(CheckedRedirect())
    request=urllib.request.Request(url,headers={'User-Agent':'MORICE/0.11 (+read-only page context)','Accept':'text/html,text/plain,application/json,application/xhtml+xml'})
    with client.open(request,timeout=timeout) as response:
        resolved=checked_url(response.geturl());mime=response.headers.get_content_type()
        if mime not in {'text/html','text/plain','text/markdown','application/json','application/xhtml+xml'}:
            raise ValueError('This link is not a readable text/HTML page. PDF, video and JavaScript-only pages need their corresponding tools.')
        if progress:progress('Reading page: '+resolved)
        raw=bytearray()
        while len(raw)<=MAX_BYTES:
            if cancel_event is not None and cancel_event.is_set():raise InterruptedError('Page reading cancelled.')
            chunk=response.read(min(65536,MAX_BYTES+1-len(raw)))
            if not chunk:break
            raw.extend(chunk)
        if len(raw)>MAX_BYTES:raise ValueError('The page exceeds the 2 MB reading limit.')
        content=raw.decode(response.headers.get_content_charset() or 'utf-8',errors='replace')
    parser=PageText()
    if mime in {'text/html','application/xhtml+xml'}:
        parser.feed(content);title=' '.join(' '.join(parser.title).split())[:200]
        content='\n'.join(' '.join(line.split()) for line in ''.join(parser.parts).splitlines() if line.strip())
    else:title=urllib.parse.urlsplit(resolved).hostname or 'Web page'
    content=content.strip()[:18000]
    if not content:raise ValueError('The page did not expose readable text.')
    if progress:progress('Page read: '+(title or resolved))
    return ReadPage(resolved,title or 'Web page',content)
