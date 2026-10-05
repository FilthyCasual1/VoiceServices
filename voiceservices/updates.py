"""Optional read-only FTP repository with bounded streaming browser uploads."""
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import tempfile

class Updates:
    def __init__(self,store,config,namespace='updates'):
        if namespace not in ('updates','downloads','pxe'): raise ValueError('Unknown repository.')
        self.table=namespace+'_files'
        self.store=store
        from .modules import Modules
        self.modules=Modules(store,config=config)
        self.root=Path(config.get(namespace+'_directory',str(Path(store.path).parent/namespace)))
        self.limit=int(config.get('update_upload_limit',8*1024**3))
        with store.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS addons(id TEXT PRIMARY KEY, settings TEXT NOT NULL)')
            db.execute(f'CREATE TABLE IF NOT EXISTS {self.table}(name TEXT PRIMARY KEY, size INTEGER, sha256 TEXT)')
    def settings(self):
        if not self.modules.installed('ftp-updates'): return None
        with self.store.connect() as db:
            row=db.execute("SELECT settings FROM addons WHERE id='ftp-updates'").fetchone()
            return json.loads(row[0]) if row else None
    def install(self):
        if not self.modules.installed('ftp-updates'): raise ValueError('Upload the FTP addon package first.')
        with self.store.connect() as db: db.execute("INSERT OR IGNORE INTO addons VALUES('ftp-updates',?)",(json.dumps({'enabled':False,'username':'updates','port':21,'passive_start':30000,'passive_end':30009,'address':''}),))
    def remove(self):
        self.modules.change('ftp-updates',False)
    def configure(self,data):
        settings=self.settings()
        if settings is None: raise ValueError('Install the FTP update addon first.')
        try: port,start,end=[int(data.get(k,'')) for k in ('port','passive_start','passive_end')]
        except ValueError: raise ValueError('Enter valid port numbers.')
        if not ((port==21 or 1024<=port<=65535) and 1024<=start<=end<=65535 and end-start<100 and not start<=port<=end): raise ValueError('Use control port 21 or an unprivileged port, distinct ports and a passive range of at most 100 ports.')
        username=data.get('username','')
        if not re.fullmatch('[a-zA-Z0-9_-]{1,32}',username): raise ValueError('Invalid FTP username.')
        address=data.get('address','')
        if address and not re.fullmatch('[a-zA-Z0-9.:-]{1,253}',address): raise ValueError('Invalid advertised server address.')
        password=data.get('ftp_password','')
        if password:
            if len(password)<12: raise ValueError('FTP password must contain at least 12 characters.')
            salt=secrets.token_hex(16)
            settings['password']=salt+':'+hashlib.pbkdf2_hmac('sha256',password.encode(),salt.encode(),310000).hex()
        enabled=data.get('enabled')=='yes'
        if enabled and not settings.get('password'): raise ValueError('Set an FTP password before enabling the server.')
        settings.update(enabled=enabled,username=username,port=port,passive_start=start,passive_end=end,address=address)
        self.root.mkdir(parents=True,exist_ok=True)
        with self.store.connect() as db: db.execute("UPDATE addons SET settings=? WHERE id='ftp-updates'",(json.dumps(settings),))
    def files(self):
        with self.store.connect() as db: return db.execute(f'SELECT * FROM {self.table} ORDER BY name').fetchall()
    def upload(self,env,user):
        if user['role']!='admin': raise PermissionError('Administrator access required.')
        if self.settings() is None: raise ValueError('FTP update addon is not installed.')
        size=int(env.get('CONTENT_LENGTH') or 0)
        if not 0<size<=self.limit+16384: raise ValueError('Upload exceeds the configured size limit.')
        content_type=env.get('CONTENT_TYPE','')
        match=re.fullmatch(r'multipart/form-data; boundary="?([A-Za-z0-9\x27()+_,./:=? -]{1,70})"?',content_type)
        if not match: raise ValueError('Multipart upload required.')
        boundary=match[1].rstrip('"').encode()
        stream=env['wsgi.input'];consumed=0
        def line():
            nonlocal consumed
            value=stream.readline(8193);consumed+=len(value)
            if len(value)>8192 or not value.endswith(b'\r\n'): raise ValueError('Invalid upload headers.')
            return value
        def headers():
            result=b''
            for _ in range(20):
                value=line()
                if value==b'\r\n': return result
                result+=value
            raise ValueError('Too many headers.')
        if line()!=b'--'+boundary+b'\r\n' or b'name="csrf"' not in headers(): raise ValueError('Form token must precede the file.')
        nonce=line().rstrip(b'\r\n').decode()
        if not hmac.compare_digest(nonce,user['csrf']): raise PermissionError('Invalid form token.')
        if line()!=b'--'+boundary+b'\r\n': raise ValueError('Invalid multipart separator.')
        header=headers()
        match=re.search(rb'name="file"; filename="([^"]+)"',header)
        if not match: raise ValueError('Choose an update file.')
        name=match[1].decode()
        if not re.fullmatch('[A-Za-z0-9][A-Za-z0-9_.-]{0,199}',name): raise ValueError('Use a plain filename without paths or special characters.')
        suffix=b'\r\n--'+boundary+b'--\r\n'
        remaining=size-consumed-len(suffix)
        if not 0<remaining<=self.limit: raise ValueError('Empty file or file too large.')
        self.root.mkdir(parents=True,exist_ok=True)
        if shutil.disk_usage(self.root).free<remaining+1024**2: raise ValueError('Insufficient repository disk space.')
        target=self.root/name
        digest=hashlib.sha256();length=remaining
        # Temporary files live outside the FTP root so clients cannot retrieve partial uploads.
        fd,temp=tempfile.mkstemp(prefix='.upload-',dir=self.root.parent)
        try:
            with os.fdopen(fd,'wb') as output:
                while remaining:
                    chunk=stream.read(min(1024**2,remaining))
                    if not chunk: raise ValueError('Upload was interrupted.')
                    output.write(chunk);digest.update(chunk);remaining-=len(chunk)
            if stream.read(len(suffix))!=suffix: raise ValueError('Invalid multipart ending.')
            os.chmod(temp,0o640)
            try: os.link(temp,target)
            except FileExistsError: raise ValueError('A file with this name already exists.')
            with self.store.connect() as db: db.execute(f'INSERT INTO {self.table} VALUES(?,?,?)',(name,length,digest.hexdigest()))
        finally: os.unlink(temp)
        return name
