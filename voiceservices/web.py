"""Dependency-free WSGI portal. Run behind a TLS reverse proxy in deployment."""
import html
import json
import re
import secrets
import socket
import sqlite3
import time
from http.cookies import SimpleCookie
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlsplit
from .core import Store, calculate
from .version import __version__, __codename__
from .accounts import LinuxAccounts
from .updates import Updates
from .modules import Modules
from .library import Library
from . import administration,branding,account

E = lambda value: html.escape(str(value), quote=True)


class App:
    def __init__(self, config):
        self.config = config
        self.started_at = time.time()
        accounts=LinuxAccounts(config.get('account_socket','/run/serviceready-accounts/socket')) if config.get('auth_backend')=='alpine' else None
        self.store = Store(config.get('database','data/voiceservices.sqlite3'),accounts)
        self.updates = Updates(self.store,config)
        self.modules = Modules(self.store,config=config)
        with self.store.connect() as db: db.execute('CREATE TABLE IF NOT EXISTS portal_settings(key TEXT PRIMARY KEY,value TEXT NOT NULL)')
        self.base = config.get('public_url','http://127.0.0.1:8080').rstrip('/')
        parsed = urlsplit(self.base)
        if parsed.scheme not in ('http','https') or not parsed.netloc or parsed.query or parsed.fragment:
            raise ValueError('public_url must be an absolute HTTP(S) URL without a query or fragment.')
        self.secure = config.get('secure_cookies', True)
        self.attempts = {}
        branding.initialize(self)
        account.initialize(self)

    def __call__(self, env, start_response):
        def send(status, body, mime='text/html; charset=utf-8', extra=()):
            if mime.startswith('text/html') and status[0] in '45' and isinstance(body,str) and not body.lstrip().lower().startswith('<!doctype'):
                title={'400':'Check your request','403':'Access denied','404':'Page not found','405':'Action unavailable','429':'Please wait'}.get(status[:3],'Unable to complete your request')
                body=self.page(title,'<p class="notice error">'+E(body)+'</p><p><a href="/">Return home</a> &nbsp; | &nbsp; <a href="/login">Sign in again</a></p>',None)
            if isinstance(body, str): body = body.encode()
            headers = [('Content-Type',mime),('Content-Length',str(len(body))),('Cache-Control','no-store'),
                       ('X-Content-Type-Options','nosniff'),('Referrer-Policy','no-referrer'),
                       ('Content-Security-Policy',"default-src 'none'; style-src 'self'; img-src 'self'; form-action 'self'; frame-ancestors 'none'")]
            start_response(status, headers+list(extra))
            return [body]
        with self.store.connect() as db:
            for row in db.execute('SELECT key,value FROM portal_settings'): self.config[row['key']]=json.loads(row['value'])
        path = env.get('PATH_INFO','/')
        method = env.get('REQUEST_METHOD','GET')
        missing=self.modules.unavailable_for(path)
        if missing: return send('404 Not Found',self.page('Service unavailable','<p class="notice error">This service is not installed.</p><p><a href="/">Return home</a></p>',None))
        if path.startswith('/files/downloads/') or path.startswith('/pxe/files/'):
            if method not in ('GET','HEAD'): return send('405 Method Not Allowed','GET or HEAD required.')
            library=self.downloads if path.startswith('/files/downloads/') else self.boot_files
            name=path.split('/',3)[-1]
            return library.serve(env,start_response,name,library is self.downloads)
        if path=='/pxe/boot.ipxe':
            if method!='GET': return send('405 Method Not Allowed','GET required.')
            return send('200 OK',self.pxe.script(),'text/plain; charset=utf-8')
        aliases = {'/register-phone':'setup', '/self-care':'customization', '/preferences':'settings'}
        if method == 'GET' and path in aliases and not env.get('voiceservices.section'):
            return send('303 See Other','',extra=[('Location','/my-phone#'+aliases[path])])
        if method not in ('GET','POST'):
            return send('405 Method Not Allowed','Method not allowed.')
        if path == '/healthz':
            return send('200 OK',json.dumps({'service':'ServiceReady','status':'running','integrations':'not probed'}),'application/json')
        if path in ('/branding/logo','/branding/masthead'):
            asset=branding.logo(self,'masthead' if path.endswith('/masthead') else 'logo')
            if path.endswith('/masthead') and not asset: asset=(Path(__file__).with_name('static').joinpath('masthead.png').read_bytes(),'image/png')
            return send('200 OK',asset[0],asset[1]) if asset else send('404 Not Found','Logo unavailable.')
        if path == '/static/brand-arrow.svg':
            return send('200 OK',Path(__file__).with_name('static').joinpath('brand-arrow.svg').read_bytes(),'image/svg+xml')
        if path == '/static/masthead.png':
            return send('200 OK',Path(__file__).with_name('static').joinpath('masthead.png').read_bytes(),'image/png')
        if path == '/static/style.css':
            return send('200 OK',Path(__file__).with_name('static').joinpath('style.css').read_bytes(),'text/css')
        if path in ('/admin/addons/upload','/admin/branding/upload','/admin/branding/masthead/upload'):
            cookie=SimpleCookie()
            try: cookie.load(env.get('HTTP_COOKIE',''))
            except Exception: pass
            user=self.store.session(cookie['vs_session'].value if 'vs_session' in cookie else '')
            if not user: return send('303 See Other','',extra=[('Location','/login')])
            if user['role']!='admin': return send('403 Forbidden','Administrator access required.')
            if method!='POST': return send('405 Method Not Allowed','POST required.')
            try:
                from email.parser import BytesParser
                from email.policy import default
                size=int(env.get('CONTENT_LENGTH') or 0)
                if not 0<size<2*1024**2+16384: raise ValueError('Package size limit is 2 MiB.')
                mime=env.get('CONTENT_TYPE','')
                if not mime.startswith('multipart/form-data') or '\r' in mime or '\n' in mime: raise ValueError('Use the package upload form.')
                message=BytesParser(policy=default).parsebytes(('Content-Type: '+mime+'\r\nMIME-Version: 1.0\r\n\r\n').encode()+env['wsgi.input'].read(size))
                parts=list(message.iter_parts());fields={}
                for part in parts:
                    name=part.get_param('name',header='content-disposition')
                    if name in fields: raise ValueError('Duplicate package field.')
                    fields[name]=part.get_payload(decode=True)
                if set(fields)!={'csrf','file'} or any(not isinstance(v,bytes) for v in fields.values()): raise ValueError('Invalid package fields.')
                if not secrets.compare_digest(fields.get('csrf',b''),user['csrf'].encode()): return send('403 Forbidden','Invalid form token.')
                if path.startswith('/admin/branding/'): branding.upload_logo(self,fields['file'],'masthead' if '/masthead/' in path else 'logo')
                else: self.modules.install(fields['file'])
            except (ValueError,OSError) as exc: return send('400 Bad Request',self.page('Package installation failed',E(exc),user))
            return send('303 See Other','',extra=[('Location','/admin/branding' if path.startswith('/admin/branding/') else '/admin/addons')])
        if path in ('/admin/updates/upload','/admin/downloads/upload','/admin/pxe/upload'):
            cookie=SimpleCookie()
            try: cookie.load(env.get('HTTP_COOKIE',''))
            except Exception: pass
            user=self.store.session(cookie['vs_session'].value if 'vs_session' in cookie else '')
            if not user: return send('303 See Other','',extra=[('Location','/login')])
            if method!='POST': return send('405 Method Not Allowed','POST required.')
            repository=self.updates if path=='/admin/updates/upload' else self.downloads if path=='/admin/downloads/upload' else self.boot_files
            try: repository.upload(env,user)
            except PermissionError as exc: return send('403 Forbidden',self.page('Access denied',E(exc),user))
            except (ValueError,OSError) as exc: return send('400 Bad Request',self.page('Upload failed',E(exc),user))
            return send('303 See Other','',extra=[('Location',path.removesuffix('/upload'))])
        try:
            size = int(env.get('CONTENT_LENGTH') or 0)
        except ValueError:
            return send('400 Bad Request','Invalid request length.')
        if size < 0 or size > 65536:
            return send('413 Content Too Large','Request too large.')
        try:
            raw = env['wsgi.input'].read(size).decode() if method == 'POST' else env.get('QUERY_STRING','')
            data = {k:v[0] for k,v in parse_qs(raw, max_num_fields=30).items()}
        except (ValueError, UnicodeError):
            return send('400 Bad Request','Invalid request.')
        if path.startswith('/phone/'):
            return self.modules.load('voice').phone_request(self,path,method,data,send)
        cookie = SimpleCookie()
        try: cookie.load(env.get('HTTP_COOKIE',''))
        except Exception: pass
        token = cookie['vs_session'].value if 'vs_session' in cookie else ''
        user = self.store.session(token)
        if path == '/create-account':
            error = ''
            nonce = cookie['vs_signup'].value if 'vs_signup' in cookie else ''
            if method == 'POST':
                if not nonce or not secrets.compare_digest(nonce,data.get('csrf','')):
                    return send('403 Forbidden','Reload the account form and try again.')
                key = 'signup:'+env.get('REMOTE_ADDR','unknown')
                now = time.time()
                count, at = self.attempts.get(key,(0,now))
                if at < now-300: count = 0
                if count >= 10: return send('429 Too Many Requests','Try again in five minutes.')
                self.attempts[key] = (count+1,now)
                username = data.get('username','').strip()
                try:
                    if not re.fullmatch(r'[A-Za-z0-9_.-]{3,64}',username): raise ValueError('Use 3–64 letters, numbers, dots, underscores or hyphens for your username.')
                    if data.get('password') != data.get('confirm_password'): raise ValueError('Passwords do not match.')
                    self.store.create_user(username,data.get('password',''),'user')
                    session = self.store.login(username,data['password'])
                    suffix = '; Secure' if self.secure else ''
                    return send('303 See Other','',extra=[('Location','/'),('Set-Cookie',f'vs_session={session}; HttpOnly; SameSite=Lax; Path=/; Max-Age=28800'+suffix),('Set-Cookie','vs_signup=; HttpOnly; SameSite=Lax; Path=/create-account; Max-Age=0'+suffix)])
                except (ValueError,sqlite3.IntegrityError) as exc:
                    message = 'That username is already in use.' if isinstance(exc,sqlite3.IntegrityError) else str(exc)
                    error = '<p class="notice error">'+E(message)+'</p>'
            nonce = secrets.token_urlsafe(32)
            suffix = '; Secure' if self.secure else ''
            form = error+'<p>Create your ServiceReady account to set up the network services available in your deployment. Your administrator assigns the services and permissions you need.</p><div class="panel login"><form method="post"><input type="hidden" name="csrf" value="'+E(nonce)+'"><label>Username</label><input name="username" autocomplete="username" minlength="3" maxlength="64" required><label>Password</label><input name="password" type="password" autocomplete="new-password" minlength="12" required><label>Confirm password</label><input name="confirm_password" type="password" autocomplete="new-password" minlength="12" required><br><button>Create account</button></form></div><p>Already registered? <a href="/login">Sign in</a>.</p>'
            return send('200 OK',self.page('Create an account',form,None),extra=[('Set-Cookie',f'vs_signup={nonce}; HttpOnly; SameSite=Lax; Path=/create-account; Max-Age=900'+suffix)])
        if path == '/login':
            error = ''
            nonce = cookie['vs_login'].value if 'vs_login' in cookie else ''
            if method == 'POST':
                if not nonce or not secrets.compare_digest(nonce,data.get('csrf','')):
                    return send('403 Forbidden','Reload the sign-in form and try again.')
                key = env.get('REMOTE_ADDR','unknown')
                now = time.time()
                self.attempts = {k:v for k,v in self.attempts.items() if v[1]>now-300}
                count, _ = self.attempts.get(key,(0,now))
                if count >= 10: return send('429 Too Many Requests','Try again in five minutes.')
                result = self.store.login(data.get('username',''),data.get('password',''))
                if result:
                    self.attempts.pop(key,None)
                    suffix = '; Secure' if self.secure else ''
                    return send('303 See Other','',extra=[('Location','/'),('Set-Cookie',f'vs_session={result}; HttpOnly; SameSite=Lax; Path=/; Max-Age=28800'+suffix)])
                self.attempts[key] = (count+1,now)
                error = '<p class="notice error">Invalid username or password.</p>'
            nonce = secrets.token_urlsafe(32)
            suffix = '; Secure' if self.secure else ''
            form = error+'<div class="panel login"><form method="post"><input type="hidden" name="csrf" value="'+E(nonce)+'"><label>Username</label><input name="username" autocomplete="username" required><label>Password</label><input name="password" type="password" autocomplete="current-password" required><br><button>Sign in</button></form></div><p>New to ServiceReady? <a href="/create-account">Create an account</a>.</p>'
            return send('200 OK',self.page('Sign in',form,None),extra=[('Set-Cookie',f'vs_login={nonce}; HttpOnly; SameSite=Lax; Path=/login; Max-Age=900'+suffix)])

        if not user and (method == 'POST' or path not in ('/', '/downloads')):
            return send('303 See Other','',extra=[('Location','/login')])
        if not user:
            user = {'id': -1, 'username': '', 'role': 'guest', 'preferences': '{}', 'csrf': ''}
        if method == 'POST' and not secrets.compare_digest(data.get('csrf',''),user['csrf']):
            return send('403 Forbidden','Invalid or expired form token.')
        if path == '/logout' and method == 'POST':
            self.store.logout(token)
            return send('303 See Other','',extra=[('Location','/login'),('Set-Cookie','vs_session=; HttpOnly; SameSite=Lax; Path=/; Max-Age=0')])
        if path == '/account':
            if method=='POST' and data.get('action','password')!='password':
                try: note=account.change(self,user,data,token)
                except ValueError as exc: return send('400 Bad Request',self.page('My Account',account.render(self,user,token,str(exc)),user))
                user=self.store.session(token)
                return send('200 OK',self.page('My Account',account.render(self,user,token,note),user))
            if method=='POST':
                try:
                    if data.get('new_password')!=data.get('confirm_password'): raise ValueError('Passwords do not match.')
                    self.store.change_password(user,data.get('current_password',''),data.get('new_password',''))
                except ValueError as exc: return send('400 Bad Request',self.page('My Account',account.render(self,user,token,str(exc)),user))
                return send('303 See Other','',extra=[('Location','/login'),('Set-Cookie','vs_session=; HttpOnly; SameSite=Lax; Path=/; Max-Age=0')])
            return send('200 OK',self.page('My Account',account.render(self,user,token),user))
        if path=='/admin' or path.startswith('/admin/'):
            try: content=administration.render(self,path,user,data,method,self.modules.services())
            except PermissionError as exc: return send('403 Forbidden',self.page('Access denied',E(exc),user))
            except ValueError as exc: return send('400 Bad Request',self.page('Check your input',E(exc),user))
            return send('200 OK',self.page('Administration',content,user))
        result=self.modules.dispatch(self,path,method,data,user,env,send)
        if result is not None: return result
        if path == '/':
            title = 'Welcome to '+branding.defaults(self)['title']
            content = branding.home(self)
        else:
            return send('404 Not Found',self.page('Page not found','<p class="notice error">The page you requested could not be found. It may have moved or its service may have been removed.</p><p><a href="/">Return home</a></p>',user))
        return send('200 OK',self.page(title,content,user))

    @property
    def downloads(self): return self.modules.resource(self,'downloads','library')
    @property
    def boot_files(self): return Library(self.store,self.config,self.modules,'pxe')
    @property
    def pxe(self): return self.modules.resource(self,'pxe','pxe')
    @property
    def plugins(self): return self.modules.resource(self,'voice','plugins')

    @staticmethod
    def valid_link(url):
        parsed = urlsplit(url)
        return parsed.scheme in ('http','https') and bool(parsed.netloc) and not parsed.username and not parsed.password and not any(ord(c)<32 for c in url)

    def page(self, title, content, user):
        brand=branding.defaults(self)
        footer='CasualNetworks Service Ready' if brand['title']=='CasualNetworks' else brand['title']+' | Powered By CasualNetworks ServiceReady'
        logo='/branding/logo' if brand.get('logo') else '/static/brand-arrow.svg'
        account = '<a href="/login">Sign in</a>'
        if user and user['role'] != 'guest':
            identity=('<div><span>Current user:</span> '+E(user['username'])+'</div><div><span>Access:</span> Administrator</div>') if user['role']=='admin' else '<div>Hello, '+E(user['display_name'] or user['username'])+'.</div>'
            account = identity+'<a href="/account">Change password</a><form class="inline" action="/logout" method="post"><input type="hidden" name="csrf" value="'+E(user['csrf'])+'"><button>Log out</button></form>'
        links = [('/','Home'),('/my-phone','My Phone'),('/directory','Directory'),('/applications','Applications'),('/recordings','Recordings'),('/downloads','Downloads')]
        if not self.modules.installed('voice'): links = [('/', 'Home'),('/downloads','Downloads')]
        if not self.modules.installed('downloads'): links=[item for item in links if item[0]!='/downloads']
        if user and user['role']!='guest': links.append(('/account','My Account'))
        if user and user['role']=='admin':
            if self.modules.installed('esxi'): links.append(('/esxi','ESXi'))
            links.append(('/admin','Administration'))
        if not user or user['role'] == 'guest': links = [('/', 'Home')]+([('/downloads','Downloads')] if self.modules.installed('downloads') else [])
        content = re.sub(r'<label>(.*?)</label><(input|select) name="([^"]+)"', lambda m: '<label for="field-'+m[3]+'">'+m[1]+'</label><'+m[2]+' id="field-'+m[3]+'" name="'+m[3]+'"', content)
        nav = ''.join('<a href="'+url+'">'+label+'</a>' for url,label in links)
        return '<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>'+E(title)+' - '+E(brand['title'])+'</title><link rel="stylesheet" href="/static/style.css"></head><body><header class="masthead-'+('compact' if brand.get('masthead_layout')=='compact' else 'wide')+'"><div class="brand">'+('<img class="wide-photo" src="/branding/masthead" alt="">' if brand.get('masthead_layout')!='compact' else '')+'<img class="brand-arrow" src="'+E(logo)+'" alt=""><div><strong>'+E(brand['title'])+'</strong><small>'+E(brand['subtitle'])+'</small></div></div>'+('<div class="masthead-image" aria-hidden="true"></div>' if brand.get('masthead_layout')=='compact' else '')+'<div class="account"><div><span>System:</span> '+E(socket.gethostname())+'</div>'+account+'</div></header><nav>'+nav+'</nav><div class="layout"><main><div class="crumb">'+E(brand['title'])+' &gt; '+E(title)+'</div><h1>'+E(title)+'</h1>'+content+'</main></div><footer>'+E(footer)+' &nbsp; | &nbsp; Version '+E(__version__)+' '+E(__codename__)+'</footer></body></html>'
