"""Dependency-free WSGI portal. Run behind a TLS reverse proxy in deployment."""
import html
import json
import re
import secrets
import sqlite3
import time
from http.cookies import SimpleCookie
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlsplit
from . import phone
from .core import Store, calculate
from .plugins import Plugins
from .version import __version__
from .accounts import LinuxAccounts
from .updates import Updates
from .modules import Modules
from . import administration

E = lambda value: html.escape(str(value), quote=True)
APPS = {'calculator':'Calculator', 'rss':'RSS Reader', 'weather':'Weather', 'flights':'Flight Tracker',
        'network':'Network Management', 'recordings':'Call Recordings'}
SERVICES = [
    ('cucm_admin','Call Management','admin'),
    ('cucm_serviceability','Call Service Tools','admin'),
    ('cucm_os','Call Server Settings','admin'),
    ('cucm_drs','Call Server Backup','admin'),
    ('self_care','Self Care','user'),
    ('cuc_admin','Voicemail Management','admin'),
    ('cuc_serviceability','Voicemail Service Tools','admin'),
    ('imp_admin','Messaging Management','admin'),
    ('imp_serviceability','Messaging Service Tools','admin'),
    ('openwrt','Network Management','admin'),
]


class App:
    def __init__(self, config):
        self.config = config
        accounts=LinuxAccounts(config.get('account_socket','/run/serviceready-accounts/socket')) if config.get('auth_backend')=='alpine' else None
        self.store = Store(config.get('database','data/voiceservices.sqlite3'),accounts)
        self.updates = Updates(self.store,config)
        self.modules = Modules(self.store)
        with self.store.connect() as db: db.execute('CREATE TABLE IF NOT EXISTS portal_settings(key TEXT PRIMARY KEY,value TEXT NOT NULL)')
        self.plugins = Plugins(self.store)
        self.base = config.get('public_url','http://127.0.0.1:8080').rstrip('/')
        parsed = urlsplit(self.base)
        if parsed.scheme not in ('http','https') or not parsed.netloc or parsed.query or parsed.fragment:
            raise ValueError('public_url must be an absolute HTTP(S) URL without a query or fragment.')
        self.secure = config.get('secure_cookies', True)
        self.attempts = {}

    def __call__(self, env, start_response):
        def send(status, body, mime='text/html; charset=utf-8', extra=()):
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
        if missing: return send('404 Not Found',self.page('Module unavailable','<p>This module is not installed.</p>',None))
        aliases = {'/register-phone':'setup', '/self-care':'customization', '/preferences':'settings'}
        if method == 'GET' and path in aliases and not env.get('voiceservices.section'):
            return send('303 See Other','',extra=[('Location','/my-phone#'+aliases[path])])
        if method not in ('GET','POST'):
            return send('405 Method Not Allowed','Method not allowed.')
        if path == '/healthz':
            return send('200 OK',json.dumps({'service':'ServiceReady','status':'running','integrations':'not probed'}),'application/json')
        if path == '/static/brand-arrow.svg':
            return send('200 OK',Path(__file__).with_name('static').joinpath('brand-arrow.svg').read_bytes(),'image/svg+xml')
        if path == '/static/masthead.png':
            return send('200 OK',Path(__file__).with_name('static').joinpath('masthead.png').read_bytes(),'image/png')
        if path == '/static/style.css':
            return send('200 OK',Path(__file__).with_name('static').joinpath('style.css').read_bytes(),'text/css')
        if path == '/admin/updates/upload':
            cookie=SimpleCookie()
            try: cookie.load(env.get('HTTP_COOKIE',''))
            except Exception: pass
            user=self.store.session(cookie['vs_session'].value if 'vs_session' in cookie else '')
            if not user: return send('303 See Other','',extra=[('Location','/login')])
            if method!='POST': return send('405 Method Not Allowed','POST required.')
            try: self.updates.upload(env,user)
            except PermissionError as exc: return send('403 Forbidden',self.page('Access denied',E(exc),user))
            except (ValueError,OSError) as exc: return send('400 Bad Request',self.page('Upload failed',E(exc),user))
            return send('303 See Other','',extra=[('Location','/admin/updates')])
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
            if method != 'GET': return send('405 Method Not Allowed','GET required.')
            token = data.get('token','')
            user = self.store.phone_user(token)
            if not user:
                return send('403 Forbidden',phone.text('Sign in required','Bind this terminal from My Phone. Native phone roaming synchronization is not connected.'),'text/xml; charset=utf-8')
            route = path.removeprefix('/phone/')
            if route == 'services': content = phone.menu(self.base,token, self.plugins.list())
            elif route.startswith('plugin/'):
                content = self.plugins.render(route[7:],self.base,token)
                if content is None: return send('404 Not Found',phone.text('Not found','Plugin unavailable.'),'text/xml; charset=utf-8')
            elif route == 'directory': content = phone.directory(self.store.contacts(user['id'],data.get('q',''))[:32])
            elif route == 'calculator': content = phone.calculator(self.base,token)
            elif route == 'calculate':
                try: result = calculate(data.get('left',''),data.get('operation',''),data.get('right',''))
                except ValueError as exc: result = str(exc)
                content = phone.text('Calculator',result)
            elif route == 'current-number':
                content = phone.text('Save current number','the phone system CTI adapter is not connected. No call number has been captured.')
            elif route in APPS:
                content = phone.text(APPS[route], 'Integration not connected. Configure and implement the provider in the web console.')
            else: return send('404 Not Found',phone.text('Not found','Unknown service.'),'text/xml; charset=utf-8')
            return send('200 OK',content,'text/xml; charset=utf-8')
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
            if method=='POST':
                try:
                    if data.get('new_password')!=data.get('confirm_password'): raise ValueError('Passwords do not match.')
                    self.store.change_password(user,data.get('current_password',''),data.get('new_password',''))
                except ValueError as exc: return send('400 Bad Request',self.page('Change password','<p class="notice error">'+E(exc)+'</p>'+administration.password_form(user),user))
                return send('303 See Other','',extra=[('Location','/login'),('Set-Cookie','vs_session=; HttpOnly; SameSite=Lax; Path=/; Max-Age=0')])
            return send('200 OK',self.page('Change password',administration.password_form(user),user))
        if path=='/admin' or path.startswith('/admin/'):
            try: content=administration.render(self,path,user,data,method,[item for item in SERVICES if self.modules.installed('voice') or item[0]=='openwrt'])
            except PermissionError as exc: return send('403 Forbidden',self.page('Access denied',E(exc),user))
            except ValueError as exc: return send('400 Bad Request',self.page('Check your input',E(exc),user))
            return send('200 OK',self.page('Administration',content,user))
        note = ''
        try:
            if path == '/applications' and method == 'POST':
                if user['role'] != 'admin': raise PermissionError('Administrator access required to manage plugins.')
                if data.get('action') == 'install': self.plugins.install(data.get('manifest',''))
                else: self.plugins.change(data.get('plugin',''),data)
                return send('303 See Other','',extra=[('Location','/applications')])
            if path == '/directory' and method == 'POST':
                self.store.add_contact(user,data.get('name',''),data.get('number',''),data.get('scope')=='shared')
                return send('303 See Other','',extra=[('Location','/directory')])
            if method == 'POST' and (path == '/preferences' or (path == '/my-phone' and data.get('action') == 'preferences')):
                values = {k:data.get(k,'')[:200] for k in ('weather_location','rss_url','flight','widget')}
                if values['widget'] not in ('network','weather','off'): raise ValueError('Invalid widget selection.')
                self.store.preferences(user['id'],values)
                return send('303 See Other','',extra=[('Location','/my-phone#settings')])
            if path == '/my-phone' and method == 'POST':
                if data.get('action') == 'unbind':
                    self.store.unbind_phone(user['id'])
                    note = '<p class="notice">Application terminal signed out. Native phone login is unchanged.</p>'
                else:
                    binding = self.store.bind_phone(user,data.get('device','').upper())
                    url = self.base+'/phone/services?'+urlencode({'token':binding})
                    note = '<p class="notice">Application binding created for eight hours. Previous binding revoked.<br>Private Services URL: <code>'+E(url)+'</code></p>'
        except PermissionError as exc:
            return send('403 Forbidden',self.page('Access denied',E(exc),user))
        except ValueError as exc:
            return send('400 Bad Request',self.page('Check your input','<p class="notice error">'+E(exc)+'</p>',user))
        guest = user['role'] == 'guest'
        csrf = '<input type="hidden" name="csrf" value="'+E(user['csrf'])+'">'
        if path == '/':
            title = 'Welcome to ServiceReady'
            content = '<p class="notice">Your starting point for setting up network services and managing your account.</p><h2>1. Get an account</h2><div class="panel"><p><a href="/create-account">Create a ServiceReady account</a> to get started. Your administrator assigns access to the services available on your network.</p></div><h2>2. Sign in</h2><div class="panel"><p><a href="/login">Sign in to ServiceReady</a> to configure your services and manage your account settings. Use <a href="/account">My Account</a> to change your password.</p></div><h2>3. Set up your services</h2><div class="panel"><p>Available services depend on the modules installed for your deployment.</p><dl><dt><strong>Storage</strong></dt><dd>Configure network shares, map drives, and connect your devices to shared storage.</dd><dt><strong>Voice</strong></dt><dd>Set up your phone, calling account, and messaging client.</dd><dt><strong>Email</strong></dt><dd>Configure your mailbox and email clients.</dd><dt><strong>Domain services</strong></dt><dd>Set up your network identity and enroll devices in your domain.</dd></dl><p>Choose the setup tools provided by your installed modules. Ask your administrator for any required service addresses or enrollment details.</p></div><h2>Downloads and setup</h2><div class="panel"><p>Visit the <a href="/downloads">Download Center</a> for available clients and setup information.</p></div>'
        elif path == '/self-care':
            title = 'Self Care'
            url=self.config.get('services',{}).get('self_care','')
            access='<a href="'+E(url)+'" target="_blank" rel="noopener noreferrer">Open Self Care</a>' if self.valid_link(url) else 'Not configured'
            content='<div class="panel">'+access+'</div><h2>Line keys and speed dials</h2><div class="panel">Use Self Care to edit supported speed-dial numbers and labels. Available buttons depend on the phone model and its assigned button template. Extension and line assignments require managed phone system configuration; the custom editor is not connected yet.</div>'
        elif path == '/directory':
            title = 'Directory'
            rows = ''.join('<tr><td>'+E(c['name'])+'</td><td>'+E(c['number'])+'</td><td>'+('Shared' if c['owner'] is None else 'Personal')+'</td></tr>' for c in self.store.contacts(user['id'],data.get('q','')))
            scope = '<option value="shared">Shared</option>' if user['role']=='admin' else ''
            content = '<form method="get"><input name="q" placeholder="Search contacts" value="'+E(data.get('q',''))+'"><button>Search</button></form><table><tr><th>Name</th><th>Number</th><th>Directory</th></tr>'+rows+'</table><h2>Add contact</h2><div class="panel"><form method="post">'+csrf+'<label>Name</label><input name="name" maxlength="100" required><label>Number / dial string</label><input name="number" maxlength="40" required><label>Directory</label><select name="scope"><option value="personal">Personal</option>'+scope+'</select><br><button>Save contact</button></form></div><p class="muted">Save current call requires the the phone system CTI adapter; manual entry works now.</p>'
        elif path == '/preferences':
            title = 'Application preferences'
            prefs = json.loads(user['preferences'])
            fields = ''.join('<label>'+label+'</label><input name="'+key+'" maxlength="200" value="'+E(prefs.get(key,''))+'">' for key,label in [('weather_location','Weather location'),('rss_url','RSS feed URL'),('flight','Tracked flight')])
            options = ''.join('<option value="'+v+'"'+(' selected' if prefs.get('widget','network')==v else '')+'>'+label+'</option>' for v,label in [('network','Network status'),('weather','Weather'),('off','Disabled')])
            content = '<p class="notice">Preferences belong to your user account and follow application terminal bindings. External providers are not connected.</p><div class="panel"><form method="post" action="/my-phone">'+csrf+'<input type="hidden" name="action" value="preferences">'+fields+'<label>Status widget</label><select name="widget">'+options+'</select><br><button>Save preferences</button></form></div>'
        elif path == '/register-phone':
            title = 'Set up a phone'
            settings = self.config.get('self_provisioning', {})
            rows = [('TFTP server', self.config.get('tftp_host') or 'Not configured'),
                    ('Self-provisioning IVR number', settings.get('ivr_number') or 'Not configured'),
                    ('Phone network / VLAN', settings.get('network') or 'Ask your administrator')]
            content = '<p class="notice">the phone system performs registration using its universal device and line templates. This portal supplies setup details; it does not create a separate registration request.</p><h2>Connection details</h2><table>'+''.join('<tr><th>'+E(k)+'</th><td>'+E(v)+'</td></tr>' for k,v in rows)+'</table>'
            content += '<h2>Register your phone</h2><div class="panel"><ol><li>Connect the phone to the designated phone network.</li><li>Obtain the configured TFTP server through DHCP, or enter the server above if your deployment requires manual setup.</li><li>Wait for the phone system auto-registration and a temporary extension.</li><li>Use the native self-provisioning screen if configured for this handset, or dial the self-provisioning IVR number above.</li><li>Provide the phone system identification and authentication details requested by the native workflow. the phone system applies the assigned templates and extension.</li></ol></div>'
            if guest:
                content += '<p><a href="/login">Sign in to view your personal the phone system setup details.</a></p>'
            else:
                identity = settings.get('users', {}).get(user['username'], {})
                content += '<h2>Your phone identity</h2><table>'+''.join('<tr><th>'+E(k)+'</th><td>'+E(v)+'</td></tr>' for k,v in [('Phone user ID', identity.get('user_id') or 'Not linked'), ('Self-service user ID', identity.get('self_service_id') or 'Not linked'), ('Primary extension', identity.get('extension') or 'Not linked')])+'</table><p class="muted">These details are administrator-configured mappings, not live the phone system verification. Enter your PIN only in the native phone workflow. The portal does not store or display it.</p>'
            content += '<p class="muted">the phone system must have auto-registration, templates, an eligible user profile, and the relevant self-provisioning services configured. Native phone login support must be checked for each handset model. Self-provisioning assigns a phone; phone roaming handles later roaming logins.</p>'
        elif path == '/my-phone':
            title = 'My Phone'
            content = note+'<p class="notice">Manual application binding only. This does not configure the phone system, verify handset ownership, or perform native phone roaming. Anyone possessing the generated URL can read this application directory; protect it like a password. Phone login synchronization will replace this development mechanism.</p><div class="panel"><form method="post">'+csrf+'<label>Device name</label><input name="device" placeholder="SEP001122AABBCC" required><br><button>Bind application terminal</button></form><form method="post">'+csrf+'<input type="hidden" name="action" value="unbind"><button>Sign out application terminal</button></form></div>'
        elif path == '/downloads':
            title = 'Download Center'
            rows = ''
            for key,label in [('jabber','Messaging Client'),('ip_communicator','Desktop Phone')]:
                item = self.config.get('downloads',{}).get(key,{})
                url = item.get('url','')
                link = '<a href="'+E(url)+'">Download</a>' if self.valid_link(url) else 'Installer not configured'
                rows += '<tr><td>'+label+'</td><td>'+E(item.get('version','Unspecified'))+'</td><td>'+link+'</td></tr>'
            content = '<p class="notice">Installers are supplied by the operator. Choose a client compatible with your communications system and desktop OS.</p><table><tr><th>Client</th><th>Version</th><th>Download</th></tr>'+rows+'</table><h2>Setup information</h2><div class="panel">TFTP / provisioning: '+E(self.config.get('tftp_host','Not configured'))+'<br>Messaging service domain: '+E(self.config.get('jabber_domain','Not configured'))+'</div>'
            if not self.modules.installed('voice'): content='<p>No downloadable packages are available for the installed modules.</p>'
        elif path == '/applications':
            title = 'Applications'
            content = '<p class="notice">Install separate phone plugins and configure their settings here. Applications appear on the telephone Services menu; they run on the phone display.</p><h2>Installed plugins</h2><table><tr><th>Application / package</th><th>Version</th><th>Status</th><th>Description</th></tr>'
            for item in self.plugins.list():
                package = item['package']
                content += '<tr><td><a href="#plugin-'+E(item['id'])+'">'+E(package['name'])+'</a><br><small>'+E(item['id'])+'</small></td><td>'+E(package['version'])+'</td><td>'+('Enabled' if item['enabled'] else 'Disabled')+'</td><td>'+E(package.get('description',''))+'</td></tr>'
            content += '</table>'
            if user['role'] == 'admin':
                for item in self.plugins.list():
                    package = item['package']
                    fields = ''.join('<label>'+E(label)+'</label><input name="config_'+E(key)+'" maxlength="500" value="'+E(item['config'].get(key,''))+'">' for key,label in package.get('fields',{}).items())
                    content += '<h2 id="plugin-'+E(item['id'])+'">'+E(package['name'])+' — Configuration</h2><div class="panel"><form method="post">'+csrf+'<input type="hidden" name="plugin" value="'+E(item['id'])+'">'+fields+'<label>Services menu</label><select name="enabled"><option value="yes"'+(' selected' if item['enabled'] else '')+'>Enabled</option><option value="no"'+(' selected' if not item['enabled'] else '')+'>Disabled</option></select><br><button name="action" value="save">Save settings</button><button name="action" value="remove">Remove plugin</button></form></div>'
                content += '<h2>Install a plugin</h2><div class="panel"><form method="post">'+csrf+'<input type="hidden" name="action" value="install"><label for="manifest">Plugin package (.json contents)</label><textarea id="manifest" name="manifest" rows="12" required spellcheck="false" placeholder="Paste a ServiceReady plugin manifest"></textarea><br><button>Install plugin</button></form><p class="muted">Declarative text plugins support configurable phone screens. Packages cannot execute server code. Provider adapters for RSS, weather and flights are still pending.</p></div>'
            else:
                content += '<p><a href="/login">Sign in with an administrator account to install and configure plugins.</a></p>'
            content += '<p><a href="/my-phone#settings">Personal phone preferences</a></p>'
        elif path in ('/network','/recordings'):
            title = 'Network Management' if path=='/network' else 'Call Recordings'
            content = '<p class="notice">Adapter not connected. No external data or recordings are available. See the integration roadmap for the next implementation stage.</p>'
        else:
            return send('404 Not Found',self.page('Page not found','Unknown page.',user))
        if guest and path == '/directory':
            content = content[:content.index('<h2>Add contact</h2>')]+'<p><a href="/login">Sign in to add or edit contacts and view your personal directory.</a></p>'
        if guest and path == '/preferences':
            content = '<p class="notice">Phone application preferences follow your user identity.</p><p><a href="/login">Sign in to edit your preferences.</a></p>'
        if path == '/my-phone':
            binding_content = content if not guest else '<p><a href="/login">Sign in to manage your phone and personal settings.</a></p>'
            sections = []
            for route, anchor, heading in [('/register-phone','setup','Phone setup'),('/self-care','customization','Line keys and customization'),('/preferences','settings','Phone application settings')]:
                section_env = dict(env, PATH_INFO=route, REQUEST_METHOD='GET', QUERY_STRING='', CONTENT_LENGTH='0')
                section_env['voiceservices.section'] = True
                body = b''.join(self(section_env, lambda status, headers: None)).decode()
                fragment = body.split('</h1>', 1)[1].split('</main>', 1)[0]
                sections.append('<section id="'+anchor+'"><h2>'+heading+'</h2>'+fragment+'</section>')
            content = ''.join(sections)+'<h2>Application terminal binding</h2>'+binding_content
        return send('200 OK',self.page(title,content,user))

    @staticmethod
    def valid_link(url):
        parsed = urlsplit(url)
        return parsed.scheme in ('http','https') and bool(parsed.netloc) and not parsed.username and not parsed.password and not any(ord(c)<32 for c in url)

    def page(self, title, content, user):
        account = '<a href="/login">Sign in</a>'
        if user and user['role'] != 'guest':
            account = '<div><span>Current user:</span> '+E(user['username'])+'</div><div><span>Access:</span> '+E(user['role'])+'</div><a href="/account">Change password</a><form class="inline" action="/logout" method="post"><input type="hidden" name="csrf" value="'+E(user['csrf'])+'"><button>Log out</button></form>'
        links = [('/','Home'),('/my-phone','My Phone'),('/directory','Directory'),('/applications','Applications'),('/recordings','Recordings'),('/downloads','Downloads')]
        if not self.modules.installed('voice'): links = [('/', 'Home'),('/downloads','Downloads')]
        if user and user['role']!='guest': links.append(('/account','My Account'))
        if user and user['role']=='admin': links.append(('/admin','Administration'))
        if not user or user['role'] == 'guest': links = [('/', 'Home'), ('/downloads', 'Downloads')]
        content = re.sub(r'<label>(.*?)</label><(input|select) name="([^"]+)"', lambda m: '<label for="field-'+m[3]+'">'+m[1]+'</label><'+m[2]+' id="field-'+m[3]+'" name="'+m[3]+'"', content)
        nav = ''.join('<a href="'+url+'">'+label+'</a>' for url,label in links)
        return '<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>'+E(title)+' - ServiceReady</title><link rel="stylesheet" href="/static/style.css"></head><body><header><div class="brand"><img class="brand-arrow" src="/static/brand-arrow.svg" alt=""><div><strong>ServiceReady</strong><small>Integrated Network Service Access Portal</small></div></div><div class="masthead-image" aria-hidden="true"></div><div class="account"><div><span>System:</span> ServiceReady</div>'+account+'</div></header><nav>'+nav+'</nav><div class="layout"><main><div class="crumb">ServiceReady &gt; '+E(title)+'</div><h1>'+E(title)+'</h1>'+content+'</main></div><footer>ServiceReady &nbsp; | &nbsp; Version '+E(__version__)+'</footer></body></html>'
