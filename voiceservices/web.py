"""Dependency-free WSGI portal. Run behind a TLS reverse proxy in deployment."""
import html
import hashlib
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
from .version import __version__, __codename__, __github_revision__, __display_version__
from .accounts import LinuxAccounts
from .updates import Updates
from .modules import Modules
from .library import Library
from . import administration,branding,account,login_protection,security,external_auth

E = lambda value: html.escape(str(value), quote=True)


class App:
    def __init__(self, config):
        self.config = config
        self.started_at = time.time()
        from .network_address import Addresses
        self.addresses = Addresses()
        accounts=LinuxAccounts(config.get('account_socket','/run/serviceready-accounts/socket')) if config.get('auth_backend') in ('alpine','system') else None
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
        login_protection.initialize(self)
        branding.initialize(self)
        external_auth.initialize(self)
        account.initialize(self)
        account.initialize_extras(self)
        from . import twofactor
        twofactor.initialize(self)
        from . import recovery
        recovery.initialize(self)

    @property
    def host_label(self):
        hostname=socket.gethostname().rstrip('.')
        fqdn=socket.getfqdn().rstrip('.')
        _,separator,domain=fqdn.partition('.')
        return domain+'/'+hostname.split('.')[0] if separator else hostname

    def __call__(self, env, start_response):
        def send(status, body, mime='text/html; charset=utf-8', extra=()):
            if mime.startswith('text/html') and status[0] in '45' and isinstance(body,str) and not body.lstrip().lower().startswith('<!doctype'):
                title={'400':'Check your request','403':'Access denied','404':'Page not found','405':'Action unavailable','429':'Please wait'}.get(status[:3],'Unable to complete your request')
                body=self.page(title,'<p class="notice error">'+E(body)+'</p><p><a href="/">Return home</a> &nbsp; | &nbsp; <a href="/login">Sign in again</a></p>',None)
            if isinstance(body, str): body = body.encode()
            headers = [('Content-Type',mime),('Content-Length',str(len(body))),('Cache-Control','no-store'),
                       ('X-Content-Type-Options','nosniff'),('Referrer-Policy','no-referrer'),
                       ('Content-Security-Policy',"default-src 'none'; script-src 'self'; connect-src 'self'; style-src 'self'"+(" 'unsafe-inline'" if env.get('PATH_INFO') in ('/admin/terminal','/admin/host') else "")+"; img-src 'self'; form-action 'self'; frame-ancestors 'none'")]
            if mime.startswith(('image/','text/css','text/javascript')):
                etag='"'+hashlib.sha256(body).hexdigest()+'"'
                headers=[h for h in headers if h[0] not in ('Cache-Control','Content-Length')]
                headers+=[('Cache-Control','private, max-age=0, must-revalidate'),('ETag',etag)]
                if env.get('HTTP_IF_NONE_MATCH')==etag and status=='200 OK': status='304 Not Modified';body=b''
                headers.append(('Content-Length',str(len(body))))
            start_response(status, headers+list(extra))
            return [body]
        with self.store.connect() as db:
            for row in db.execute('SELECT key,value FROM portal_settings'): self.config[row['key']]=json.loads(row['value'])
        if self.config.get('automatic_public_url'):
            from .network_address import origin
            _,address=self.addresses.current()
            if address:self.base=origin(self.config,address);self.config['public_url']=self.base
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
        if path in ('/branding/logo','/branding/masthead','/branding/header-fill'):
            asset=branding.logo(self,path.rsplit('/',1)[-1])
            if path.endswith('/masthead') and not asset: asset=(Path(__file__).with_name('static').joinpath('masthead.png').read_bytes(),'image/png')
            return send('200 OK',asset[0],asset[1]) if asset else send('404 Not Found','Logo unavailable.')
        if path in ('/static/casualnetworks-arrow.svg','/static/provider-virtualbox.svg','/static/provider-vmware.svg'):
            return send('200 OK',Path(__file__).with_name('static').joinpath(path.rsplit('/',1)[1]).read_bytes(),'image/svg+xml')
        if path == '/static/brand-arrow.svg':
            return send('200 OK',Path(__file__).with_name('static').joinpath('brand-arrow.svg').read_bytes(),'image/svg+xml')
        if path == '/static/masthead.png':
            return send('200 OK',Path(__file__).with_name('static').joinpath('masthead.png').read_bytes(),'image/png')
        if path == '/host/distro-logo':
            from . import distro
            return send('200 OK',distro.logo(self),'image/svg+xml')
        if path=='/static/xterm.css':return send('200 OK',(Path(__file__).with_name('static')/'xterm.css').read_bytes(),'text/css; charset=utf-8')
        if path in ('/static/portal.js','/static/host-terminal.js','/static/xterm.js'):
            return send('200 OK',Path(__file__).with_name('static').joinpath(path.rsplit('/',1)[1]).read_bytes(),'text/javascript')
        if path=='/branding/style.css':
            brand=branding.defaults(self)
            masthead=brand.get('masthead',__version__);fill=brand.get('header-fill','none')
            return send('200 OK','.masthead-compact .masthead-image{background-image:url("/branding/masthead?v='+masthead+'")}.masthead-wide .brand{background-image:url("/branding/header-fill?v='+fill+'")}', 'text/css')
        if path == '/static/style.css':
            return send('200 OK',Path(__file__).with_name('static').joinpath('style.css').read_bytes(),'text/css')
        if path in ('/admin/addons/upload','/admin/branding/upload','/admin/branding/masthead/upload','/admin/branding/header-fill/upload','/account/photo/upload'):
            cookie=SimpleCookie()
            try: cookie.load(env.get('HTTP_COOKIE',''))
            except Exception: pass
            user=self.store.session(cookie['vs_session'].value if 'vs_session' in cookie else '')
            if not user: return send('303 See Other','',extra=[('Location','/login')])
            if path!='/account/photo/upload' and user['role']!='admin': return send('403 Forbidden','Administrator access required.')
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
                if path=='/account/photo/upload': account.upload_photo(self,user,fields['file'])
                elif path.startswith('/admin/branding/'): branding.upload_logo(self,fields['file'],'header-fill' if '/header-fill/' in path else 'masthead' if '/masthead/' in path else 'logo')
                else: self.modules.install(fields['file'])
            except (ValueError,OSError) as exc: return send('400 Bad Request',self.page('Package installation failed',E(exc),user))
            return send('303 See Other','',extra=[('Location','/account' if path=='/account/photo/upload' else '/admin/branding' if path.startswith('/admin/branding/') else '/admin/addons')])
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
            if not security.settings(self)['registration_enabled']: return send('403 Forbidden','Account registration is disabled. Contact your administrator.')
            box_title,box_subtitle=branding.box_text(self,'create')
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
                    from . import onboarding
                    details=onboarding.profile(data,self)
                    self.store.create_user(username,data.get('password',''),'user',invitation=data.get('invitation',''),profile=details)
                    session = self.store.login(username,data['password'])
                    duration=security.duration(self)
                    with self.store.connect() as db: db.execute('UPDATE sessions SET expires=? WHERE token=?',(int(time.time())+duration,session))
                    suffix = '; Secure' if self.secure else ''
                    return send('303 See Other','',extra=[('Location','/welcome'),('Set-Cookie',f'vs_session={session}; HttpOnly; SameSite=Lax; Path=/; Max-Age={duration}'+suffix),('Set-Cookie','vs_signup=; HttpOnly; SameSite=Lax; Path=/create-account; Max-Age=0'+suffix)])
                except (ValueError,sqlite3.IntegrityError) as exc:
                    message = 'That username is already in use.' if isinstance(exc,sqlite3.IntegrityError) else str(exc)
                    error = '<p class="notice error">'+E(message)+'</p>'
            nonce = nonce if re.fullmatch(r'[A-Za-z0-9_-]{43}',nonce) else secrets.token_urlsafe(32)
            suffix = '; Secure' if self.secure else ''
            from . import onboarding
            form = error+'<div class="signin-card"><div class="signin-banner"><strong>'+E(box_title)+'</strong><small>'+E(box_subtitle)+'</small></div><div class="panel login">'+onboarding.form(self,nonce,data)+'</div><p class="signin-help">Already registered? <a href="/login">Sign in</a>.</p></div>'
            return send('200 OK',self.page('Create an account',form,None),extra=[('Set-Cookie',f'vs_signup={nonce}; HttpOnly; SameSite=Lax; Path=/create-account; Max-Age=900'+suffix)])
        if path == '/welcome':
            if not user or user['role']=='guest':return send('303 See Other','',extra=[('Location','/login')])
            return send('200 OK',self.page('Welcome','<div class="signin-card"><div class="signin-banner"><strong>Your account is ready</strong><small>Welcome to your network services portal.</small></div><div class="panel"><p>You are signed in. Choose your next step:</p><p><a class="button" href="/account">Finish your profile</a></p><p><a href="/account/security">Set up two-factor authentication</a></p><p><a href="/">Explore your services</a></p></div></div>',user))
        if path == '/logged-out':
            session_text=branding.defaults(self)
            return send('200 OK',self.page('You have been logged out','<div class="signin-card"><div class="signin-banner"><strong>'+E(session_text['logged_out_title'])+'</strong><small>'+E(session_text['logged_out_subtitle'])+'</small></div><div class="panel"><p>'+E(session_text['logged_out_message'])+'</p><p class="signin-help"><a href="/login">'+E(session_text['logged_out_link'])+'</a></p></div></div>',None),extra=[('Refresh','5; url=/login')])
        if path == '/recover':
            from . import recovery
            return recovery.public(self,env,data,cookie,method,send)
        if path in ('/login','/login/verify') and method=='POST':
            wait=login_protection.reserve(self,env,'mfa' if path.endswith('/verify') else 'login')
            if wait: return send('429 Too Many Requests','Too many sign-in attempts. Please wait before trying again.',extra=[('Retry-After',str(wait))])
        if path == '/login/verify':
            from . import twofactor
            pending=cookie['vs_factor'].value if 'vs_factor' in cookie else ''
            result=twofactor.finish(self,pending,data.get('csrf',''),data.get('code','')) if method=='POST' else None
            suffix='; Secure' if self.secure else ''
            if result:
                with self.store.connect() as db: duration=max(1,db.execute('SELECT expires FROM sessions WHERE token=?',(result,)).fetchone()[0]-int(time.time()))
                return send('303 See Other','',extra=[('Location','/'),('Set-Cookie',f'vs_session={result}; HttpOnly; SameSite=Lax; Path=/; Max-Age={duration}'+suffix),('Set-Cookie','vs_factor=; HttpOnly; SameSite=Lax; Path=/login; Max-Age=0')])
            if method=='POST': login_protection.failed(env,'mfa',self)
            return send('200 OK',self.page('Verify your sign-in',twofactor.login_page(self,pending,'Code incorrect or already used.' if method=='POST' else ''),None))
        if path == '/login/kerberos':
            return external_auth.sso(self,env,cookie,send)
        if path == '/login':
            box_title,box_subtitle=branding.box_text(self,'login')
            error = '<p class="notice error">Your sign-in form expired. Please enter your credentials again.</p>' if env.get('voiceservices.login_expired') else ''
            nonce = cookie['vs_login'].value if 'vs_login' in cookie else ''
            if method == 'POST':
                if not nonce or not secrets.compare_digest(nonce,data.get('csrf','')):
                    retry_env = dict(env, REQUEST_METHOD='GET', **{'voiceservices.login_expired':True})
                    def retry_start(status, headers): start_response('403 Forbidden', headers)
                    response = self(retry_env, retry_start)
                    return response
                result = external_auth.login(self,data.get('provider','local'),data.get('username',''),data.get('password',''))
                if result:
                    from . import twofactor
                    person=self.store.session(result)
                    if twofactor.state(self,person).get('secret'):
                        self.store.logout(result);pending=twofactor.challenge(self,person,data.get('remember')=='yes')
                        suffix='; Secure' if self.secure else ''
                        return send('303 See Other','',extra=[('Location','/login/verify'),('Set-Cookie',f'vs_factor={pending}; HttpOnly; SameSite=Lax; Path=/login; Max-Age=300'+suffix)])
                    duration=security.duration(self,data.get('remember')=='yes')
                    with self.store.connect() as db: db.execute('UPDATE sessions SET expires=? WHERE token=?',(int(time.time())+duration,result))
                    suffix = '; Secure' if self.secure else ''
                    return send('303 See Other','',extra=[('Location','/'),('Set-Cookie',f'vs_session={result}; HttpOnly; SameSite=Lax; Path=/; Max-Age={duration}'+suffix)])
                login_protection.failed(env,'login',self)
                error = '<p class="notice error">Invalid username or password.</p>'
            nonce = nonce if re.fullmatch(r'[A-Za-z0-9_-]{43}',nonce) else secrets.token_urlsafe(32)
            suffix = '; Secure' if self.secure else ''
            form = error+'<div class="signin-card"><div class="signin-banner"><strong>'+E(box_title)+'</strong><small>'+E(box_subtitle)+'</small></div><div class="panel login"><form method="post"><input type="hidden" name="csrf" value="'+E(nonce)+'"><label>Username</label><input name="username" autocomplete="username" required><label>Password</label><input name="password" type="password" autocomplete="current-password" required><label class="remember-login"><input type="checkbox" name="remember" value="yes"> Stay signed in for 30 days</label><br><button>Sign in</button></form><p class="signin-help"><a href="/recover">Recover your account</a></p></div><p class="signin-help">New here? <a href="/create-account">Create an account</a>.</p></div>'
            providers=[(key,label) for key,label in external_auth.KINDS.items() if external_auth.settings(self,key)['enabled']]
            if providers:
                picker='<label>Sign in with</label><select name="provider"><option value="local">Local account</option>'+''.join('<option value="'+key+'">'+label+'</option>' for key,label in providers)+'</select>'
                form=form.replace('<label>Username</label>',picker+'<label>Username</label>')
            if external_auth.settings(self,'kerberos')['enabled']: form+='<p class="signin-help"><a href="/login/kerberos" data-full-navigation="yes">Sign in with Kerberos browser SSO</a></p>'
            policy=security.settings(self)
            if policy['remember_enabled']: form=form.replace('Stay signed in for 30 days','Stay signed in for '+str(policy['remember_days'])+' days')
            else: form=re.sub(r'<label class="remember-login">.*?</label>','',form)
            if not policy['registration_enabled']: form=re.sub(r'<p class="signin-help">New here\?.*?</p>','',form)
            look=branding.defaults(self)
            if look['login_disclaimer_enabled']:
                form+='<div class="login-disclaimer panel"><h2>Notice</h2><p>'+E(look['login_disclaimer'])+'</p></div>'
            return send('200 OK',self.page('Sign in',form,None),extra=[('Set-Cookie',f'vs_login={nonce}; HttpOnly; SameSite=Lax; Path=/login; Max-Age=900'+suffix)])

        if not user and (method == 'POST' or path not in ('/', '/downloads')):
            return send('303 See Other','',extra=[('Location','/login')])
        if not user:
            user = {'id': -1, 'username': '', 'role': 'guest', 'preferences': '{}', 'csrf': ''}
        if path=='/admin/update-status':
            if user['role']!='admin':return send('403 Forbidden',json.dumps({'error':'Administrator access required.'}),'application/json')
            if method!='GET':return send('405 Method Not Allowed',json.dumps({'error':'GET required.'}),'application/json')
            if not self.store.accounts:return send('503 Service Unavailable',json.dumps({'error':'Host update provider unavailable.'}),'application/json')
            try:state=self.store.accounts.call('maintenance-status','','')
            except ValueError as exc:return send('503 Service Unavailable',json.dumps({'error':str(exc)}),'application/json')
            return send('200 OK',json.dumps({'status':state,'version':__version__}),'application/json')
        if path=='/admin/overview-stats':
            if user['role']!='admin': return send('403 Forbidden',json.dumps({'error':'Administrator access required.'}),'application/json')
            if method!='GET': return send('405 Method Not Allowed',json.dumps({'error':'GET required.'}),'application/json')
            from . import overview
            return send('200 OK',json.dumps({'html':overview.render(self,user)}),'application/json')
        if path=='/admin/recovery' and method=='GET':
            return send('303 See Other','',extra=[('Location','/admin/users#recovery')])
        if method == 'POST' and not secrets.compare_digest(data.get('csrf',''),user['csrf']):
            return send('403 Forbidden','Invalid or expired form token.')
        if path == '/logout' and method == 'POST':
            if data.get('confirm')!='yes':
                session_text=branding.defaults(self)
                form='<div class="signin-card session-card"><div class="signin-banner"><strong>'+E(session_text['logout_title'])+'</strong><small>'+E(session_text['logout_subtitle'])+'</small></div><div class="panel"><p>'+E(session_text['logout_message'])+'</p><p class="muted">'+E(session_text['logout_detail'])+'</p><form method="post"><input type="hidden" name="csrf" value="'+E(user['csrf'])+'"><input type="hidden" name="confirm" value="yes"><div class="session-actions"><a class="session-cancel" href="/">'+E(session_text['logout_cancel'])+'</a><button class="end-session">'+E(session_text['logout_confirm'])+'</button></div></form></div></div>'
                return send('200 OK',self.page('End your session?',form,user))
            self.store.logout(token)
            return send('303 See Other','',extra=[('Location','/logged-out'),('Set-Cookie','vs_session=; HttpOnly; SameSite=Lax; Path=/; Max-Age=0')])
        if path == '/account/twofactor/qr':
            from . import twofactor
            image=twofactor.qr(self,user,token)
            return send('200 OK',image,'image/png') if image else send('404 Not Found','Authenticator setup expired.')
        if path == '/account/photo':
            asset=account.photo(self,user)
            if asset: return send('200 OK',asset[0],asset[1])
            return send('200 OK','<svg xmlns="http://www.w3.org/2000/svg" width="96" height="96"><rect width="96" height="96" fill="#829da9"/><circle cx="48" cy="32" r="17" fill="white"/><path d="M16 90v-12a32 32 0 0 1 64 0v12" fill="white"/></svg>','image/svg+xml')
        if path in ('/account','/account/inbox','/account/security','/account/services'):
            section=path.rsplit('/',1)[-1] if path!='/account' else 'profile'
            if method=='POST' and data.get('action','password')!='password':
                try: note=account.change(self,user,data,token)
                except ValueError as exc: return send('400 Bad Request',self.page('My Account',account.render(self,user,token,str(exc),section),user))
                user=self.store.session(token)
                return send('200 OK',self.page('My Account',account.render(self,user,token,note,section),user))
            if method=='POST':
                try:
                    if data.get('new_password')!=data.get('confirm_password'): raise ValueError('Passwords do not match.')
                    self.store.change_password(user,data.get('current_password',''),data.get('new_password',''))
                except ValueError as exc: return send('400 Bad Request',self.page('My Account',account.render(self,user,token,str(exc),section),user))
                return send('303 See Other','',extra=[('Location','/login'),('Set-Cookie','vs_session=; HttpOnly; SameSite=Lax; Path=/; Max-Age=0')])
            return send('200 OK',self.page('My Account',account.render(self,user,token,section=section),user))
        if path in ('/admin/terminal/io','/admin/host') and (path.endswith('/io') or (method=='POST' and bool(data.get('task')))):
            from . import host_tools
            return host_tools.page(self,path,method,data,user,env,send)
        if path=='/admin' or path.startswith('/admin/'):
            try: content=administration.render(self,path,user,data,method,self.modules.services())
            except PermissionError as exc: return send('403 Forbidden',self.page('Access denied',E(exc),user))
            except ValueError as exc: return send('400 Bad Request',self.page('Check your input',E(exc),user))
            return send('200 OK',self.page('Administration',content,user))
        result=self.modules.dispatch(self,path,method,data,user,env,send)
        if result is not None: return result
        if path == '/':
            title = 'Welcome to '+branding.defaults(self)['title']
            content = branding.home(self,user)
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
        logo='/branding/logo?v='+brand['logo'] if brand.get('logo') else '/static/brand-arrow.svg'
        brand_style='/branding/style.css?v='+brand.get('masthead',__version__)+'-'+brand.get('header-fill','none')
        masthead_url='/branding/masthead?v='+brand.get('masthead',__version__)
        avatar_url='/account/photo'
        if user and user['role']!='guest':
            from .account import photo as account_photo
            photo=account_photo(self,user)
            avatar_url+='?v='+str(user['id'])+'-'+(hashlib.sha256(photo[0]).hexdigest()[:16] if photo else 'default')
        account = '<a class="guest-signin" href="/login">Sign in</a>';logout='';account_actions=''
        if user and user['role'] != 'guest':
            identity=('<div><span>Current user:</span> '+E(user['username'])+'</div><div><span>Access:</span> Administrator</div>') if user['role']=='admin' else '<div>Hello, '+E(user['display_name'] or user['username'])+'.</div>'
            account=identity;indicator=''
            with self.store.connect() as db:
                unread=db.execute("SELECT priority,COUNT(*) AS total FROM notifications WHERE user_id=? AND is_read=0 GROUP BY priority",(user['id'],)).fetchall()
            count=sum(row['total'] for row in unread)
            if count:
                level=next((level for level in ('urgent','caution','info') if any(row['priority']==level for row in unread)),'info')
                indicator='<a class="notification-indicator priority-'+level+'" href="/account/inbox" aria-label="'+str(count)+' unread notifications; highest priority '+level+'">'+str(count)+' unread</a>'
            logout='<form class="inline" action="/logout" method="post"><input type="hidden" name="csrf" value="'+E(user['csrf'])+'"><button>Log out</button></form>'
            account_actions='<div class="account-actions"><a class="profile-link" href="/account">My Account</a><a href="/account/inbox">Inbox</a>'+indicator+logout+'</div>'
        links = [('/','Home'),('/my-phone','My Phone'),('/directory','Directory'),('/applications','Applications'),('/recordings','Recordings'),('/downloads','Downloads')]
        if not self.modules.installed('voice'): links = [('/', 'Home'),('/downloads','Downloads')]
        if not self.modules.installed('downloads'): links=[item for item in links if item[0]!='/downloads']
        if user and user['role']=='admin':
            if self.modules.installed('esxi'): links.append(('/esxi','ESXi'))
            links.append(('/admin','Administration'))
        if not user or user['role'] == 'guest': links = [('/', 'Home')]+([('/downloads','Downloads')] if self.modules.installed('downloads') else [])
        content = re.sub(r'<label>([^<]*)</label><(input|select) name="([^"]+)"', lambda m: '<label for="field-'+m[3]+'">'+m[1]+'</label><'+m[2]+' id="field-'+m[3]+'" name="'+m[3]+'"', content)
        nav = ''.join('<a href="'+url+'">'+label+'</a>' for url,label in links)
        return '<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>'+E(title)+' - '+E(brand['title'])+'</title><link rel="stylesheet" href="/static/style.css"><link data-brand-style rel="stylesheet" href="'+E(brand_style)+'"><script defer src="/static/portal.js?v='+E(__version__)+'"></script><script defer src="/static/host-terminal.js?v='+E(__version__)+'"></script></head><body><header class="masthead-'+('compact' if brand.get('masthead_layout')=='compact' else 'wide')+'"><div class="brand">'+('<img class="wide-photo" src="'+E(masthead_url)+'" alt="">' if brand.get('masthead_layout')!='compact' else '')+'<img class="brand-arrow" src="'+E(logo)+'" alt=""><div><strong>'+E(brand['title'])+'</strong><small>'+E(brand['subtitle'])+'</small></div></div>'+('<div class="masthead-image" aria-hidden="true"></div>' if brand.get('masthead_layout')=='compact' else '')+'<div class="account">'+('<div class="account-picture"><img class="account-avatar" src="'+E(avatar_url)+'" alt=""></div>' if user and user['role']!='guest' else '')+'<div class="account-details"><div><span>System:</span> '+E(self.host_label)+'</div>'+account+'</div>'+account_actions+'</div></header><nav>'+nav+'</nav><div class="layout"><main><div class="crumb">'+E(brand['title'])+' &gt; '+E(title)+'</div><h1>'+E(title)+'</h1>'+content+'</main></div><footer><span>'+E(footer)+' &nbsp; | &nbsp; Version '+E(__display_version__)+' '+E(__codename__)+'</span><span class="footer-copyright">Copyright &copy; '+str(time.localtime().tm_year)+' CasualNetworks.</span></footer></body></html>'
