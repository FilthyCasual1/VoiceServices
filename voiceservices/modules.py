"""Verified file-package installation and runtime dispatch for optional addons."""
import hashlib
import io
import json
from pathlib import Path
import shutil
import sys
import tempfile
import threading
import types
import zipfile
ROUTES={'smtp-notifications':{'exact':('/admin/smtp',),'prefix':()},'downloads':{'exact':('/downloads','/admin/downloads'),'prefix':('/files/downloads/','/admin/downloads/')},
        'pxe':{'exact':('/admin/pxe',),'prefix':('/pxe/','/admin/pxe/')},
        'voice':{'exact':('/admin/voice','/my-phone','/register-phone','/self-care','/preferences','/directory','/applications','/recordings'),'prefix':('/phone/',)},
        'server-management':{'exact':('/admin/settings','/network'),'prefix':()},
        'ftp-updates':{'exact':('/admin/updates',),'prefix':('/admin/updates/',)},
        'esxi':{'exact':('/esxi','/admin/esxi'),'prefix':()}}
CATALOG={'smtp-notifications':('SMTP Notifications','Receive application email as portal inbox notifications.'),'downloads':('Downloads','Internal tool and application distribution.'),'pxe':('PXE and Image Deployment','ISO boot and interactive image restoration.'),'voice':('Voice Services','Phone setup, XML services and directories.'),'server-management':('Server Management','Service configuration and administration links.'),'ftp-updates':('FTP Update Repository','Upload updates for read-only FTP retrieval.'),'esxi':('ESXi Management','Host inventory and virtual machine power controls.')}
_lock=threading.RLock()
class Modules:
    def __init__(self,store,initial_modules=None,config=None):
        self.store=store;self.config=config or {}
        self.root=Path(self.config.get('addon_directory',str(Path(str(store.path)+'.addons'))))
        self.root.mkdir(parents=True,exist_ok=True)
        self.approved=json.loads(Path(__file__).with_name('addon_catalog.json').read_text())
        self.cache={};self.resources={}
        with store.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS platform_modules(id TEXT PRIMARY KEY)')
            db.execute('CREATE TABLE IF NOT EXISTS module_metadata(key TEXT PRIMARY KEY)')
            db.execute('CREATE TABLE IF NOT EXISTS addons(id TEXT PRIMARY KEY,settings TEXT NOT NULL)')
    def installed(self,module):
        if module not in self.approved: return False
        try: return hashlib.sha256((self.root/module/'module.py').read_bytes()).hexdigest()==self.approved[module]['sha256']
        except OSError: return False
    def install(self,raw):
        if len(raw)>2*1024**2: raise ValueError('Addon package exceeds 2 MiB.')
        with _lock:
            try:
                with zipfile.ZipFile(io.BytesIO(raw)) as archive:
                    if set(archive.namelist())!={'manifest.json','module.py'} or len(archive.infolist())!=2: raise ValueError('Invalid package layout.')
                    if any(item.file_size>2*1024**2 for item in archive.infolist()): raise ValueError('Package is too large.')
                    manifest=json.loads(archive.read('manifest.json'));code=archive.read('module.py')
                key=manifest['id']
                if key not in self.approved or manifest!=dict(self.approved[key],id=key): raise ValueError('Package is not compatible with this core release.')
                if hashlib.sha256(code).hexdigest()!=manifest['sha256']: raise ValueError('Package checksum is not approved.')
                compile(code,'module.py','exec')
            except (KeyError,TypeError,SyntaxError,zipfile.BadZipFile,json.JSONDecodeError,UnicodeError,RuntimeError,EOFError) as exc: raise ValueError('Invalid addon package.') from exc
            if (self.root/key).exists(): raise ValueError('Uninstall the existing package before installing a replacement.')
            temporary=Path(tempfile.mkdtemp(prefix='.install-',dir=self.root))
            try:
                (temporary/'module.py').write_bytes(code)
                (temporary/'manifest.json').write_text(json.dumps(manifest))
                temporary.rename(self.root/key)
            finally:
                if temporary.exists(): shutil.rmtree(temporary)
            with self.store.connect() as db: db.execute('INSERT OR IGNORE INTO platform_modules VALUES(?)',(key,))
            if key=='ftp-updates':
                with self.store.connect() as db: db.execute("INSERT OR IGNORE INTO addons VALUES('ftp-updates',?)",(json.dumps({'enabled':False,'username':'updates','port':21,'passive_start':30000,'passive_end':30009,'address':''}),))
            return key
    def change(self,module,install):
        if module not in CATALOG: raise ValueError('Unknown addon.')
        if install: raise ValueError('Upload an addon file to install it.')
        with _lock:
            path=self.root/module
            if path.exists(): shutil.rmtree(path)
            self.cache.pop(module,None)
            self.resources={k:v for k,v in self.resources.items() if k[0]!=module}
            with self.store.connect() as db: db.execute('DELETE FROM platform_modules WHERE id=?',(module,))
    def load(self,module):
        with _lock:
            if not self.installed(module): raise ValueError('Install the '+module+' addon package first.')
            if module not in self.cache:
                # Compile verified bytes, never import writable addon files as privileged code.
                code=(self.root/module/'module.py').read_bytes()
                if hashlib.sha256(code).hexdigest()!=self.approved[module]['sha256']: raise ValueError('Addon checksum changed.')
                loaded=types.ModuleType('serviceready_addon_'+module.replace('-','_'));loaded.__package__='voiceservices'
                exec(compile(code,str(self.root/module/'module.py'),'exec'),loaded.__dict__)
                self.cache[module]=loaded
            return self.cache[module]
    def resource(self,app,module,name):
        loaded=self.load(module);key=(module,name,id(app))
        if key not in self.resources: self.resources[key]=loaded.resource(app,name)
        return self.resources[key]
    def unavailable_for(self,path):
        for module,routes in ROUTES.items():
            if (path in routes['exact'] or any(path.startswith(prefix) for prefix in routes['prefix'])) and not self.installed(module): return module
        return None
    def dispatch(self,app,path,method,data,user,env,send):
        for key,routes in ROUTES.items():
            if (path in routes['exact'] or any(path.startswith(p) for p in routes['prefix'])) and self.installed(key):
                handler=getattr(self.load(key),'page',None)
                if handler: return handler(app,path,method,data,user,env,send)
        return None
    def services(self):
        if self.installed('server-management'):
            return [item for item in self.load('server-management').SERVICES if self.installed('voice') or item[0]=='openwrt']
        return []
