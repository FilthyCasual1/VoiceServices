"""General artifact repositories and byte-range HTTP delivery for network boot."""
import html
import re
from urllib.parse import urlsplit
from .updates import Updates
E=lambda value:html.escape(str(value),quote=True)

class Library(Updates):
    def __init__(self,store,config,modules,namespace):
        super().__init__(store,config,namespace)
        self.modules=modules;self.namespace=namespace
    def settings(self): return {} if self.modules.installed(self.namespace) else None
    def serve(self,env,start_response,name,attachment=False):
        if not re.fullmatch('[A-Za-z0-9][A-Za-z0-9_.-]{0,199}',name): return self.error(start_response,'404 Not Found')
        row=next((row for row in self.files() if row['name']==name),None)
        try:self.require_volume()
        except ValueError:return self.error(start_response,'503 Service Unavailable')
        path=self.root/name
        if not row or not path.is_file() or path.is_symlink(): return self.error(start_response,'404 Not Found')
        size=path.stat().st_size;start=0;end=size-1;status='200 OK'
        headers=[('Content-Type','application/octet-stream'),('Accept-Ranges','bytes'),('ETag','"'+row['sha256']+'"'),('X-Content-Type-Options','nosniff')]
        if attachment: headers.append(('Content-Disposition','attachment; filename="'+name+'"'))
        value=env.get('HTTP_RANGE')
        if value:
            match=re.fullmatch(r'bytes=(\d*)-(\d*)',value)
            try:
                if not match or not any(match.groups()): raise ValueError()
                if not match[1]: start=max(0,size-int(match[2]));end=size-1
                else: start=int(match[1]);end=min(size-1,int(match[2])) if match[2] else size-1
                if not 0<=start<=end<size: raise ValueError()
            except ValueError: return self.error(start_response,'416 Range Not Satisfiable',[('Content-Range',f'bytes */{size}')])
            status='206 Partial Content';headers.append(('Content-Range',f'bytes {start}-{end}/{size}'))
        headers.append(('Content-Length',str(end-start+1)));start_response(status,headers)
        if env.get('REQUEST_METHOD')=='HEAD': return [b'']
        def stream():
            with path.open('rb') as source:
                source.seek(start);left=end-start+1
                while left:
                    value=source.read(min(left,1024**2))
                    if not value: break
                    left-=len(value);yield value
        return stream()
    @staticmethod
    def error(start_response,status,extra=()):
        start_response(status,[('Content-Type','text/plain'),('Content-Length','0')]+list(extra));return [b'']
