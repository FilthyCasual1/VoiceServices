"""Explicit external identity namespaces; local administrators never use remote auth."""
import base64,html,importlib.util,io,json,re,secrets,ssl,threading,time
from pathlib import Path
E=lambda value:html.escape(str(value),quote=True)
KINDS={'ldap':'LDAP','kerberos':'Kerberos','radius':'RADIUS'}
DEFAULT={'enabled':False,'allowed_users':'','host':'','port':636,'bind_template':'uid={username},ou=People,dc=example,dc=org','ca_file':'','realm':'','principal':'','keytab':'','secret':''}
def initialize(app):
    app.sso_pending={};app.sso_lock=threading.RLock()
    with app.store.connect() as db:
        db.execute('CREATE TABLE IF NOT EXISTS external_identities(user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,provider TEXT NOT NULL,subject TEXT NOT NULL,active INTEGER NOT NULL DEFAULT 1,UNIQUE(provider,subject))')
    app.store.external_session_check=lambda user: session_valid(app,user)
    app.store.external_check=lambda user,password: verify_existing(app,user,password)
def settings(app,kind):
    with app.store.connect() as db: row=db.execute('SELECT value FROM portal_settings WHERE key=?',('auth-'+kind,)).fetchone()
    return dict(DEFAULT,port=1812 if kind=='radius' else 636,**(json.loads(row[0]) if row else {})) if not row else dict(DEFAULT,**json.loads(row[0]))
def identity(app,user):
    with app.store.connect() as db: row=db.execute('SELECT * FROM external_identities WHERE user_id=?',(user['id'],)).fetchone()
    return dict(row) if row else None
def session_valid(app,user):
    row=identity(app,user)
    if not row:return True
    s=settings(app,row['provider'])
    return bool(row['active'] and user['role']=='user' and s['enabled'] and allowed(s,row['subject']))
def allowed(s,subject): return subject in s['allowed_users'].splitlines()
def change(app,user,data):
    if user['role']!='admin': raise PermissionError('Administrator access required.')
    kind=data.get('provider')
    if kind not in KINDS: raise ValueError('Choose an authentication provider.')
    from .twofactor import password
    password(app,user,data.get('current_password',''))
    s=settings(app,kind)
    for key in ('host','bind_template','ca_file','realm','principal','keytab','allowed_users'):
        s[key]=data.get(key,s[key]).strip()
        if len(s[key])>5000 or '\x00' in s[key]: raise ValueError('Check provider settings.')
    s['allowed_users']='\n'.join(dict.fromkeys(x.strip() for x in s['allowed_users'].splitlines() if x.strip()))
    if data.get('secret'):s['secret']=data['secret']
    s['enabled']=data.get('enabled')=='yes'
    try:s['port']=int(data.get('port',s['port']))
    except ValueError:raise ValueError('Enter a valid port.')
    if not 1<=s['port']<=65535:raise ValueError('Enter a valid port.')
    if s['host'] and not re.fullmatch(r'[A-Za-z0-9_.:-]+',s['host']):raise ValueError('Use a hostname or IP without a URL scheme.')
    if s['enabled']:
        if not app.base.startswith('https://') or not app.secure:raise ValueError('Configure an HTTPS public URL and secure cookies before enabling remote authentication.')
        if not s['allowed_users']:raise ValueError('List permitted external usernames, one per line.')
        library={'ldap':'ldap3','kerberos':'gssapi','radius':'pyrad'}[kind]
        if importlib.util.find_spec(library) is None:raise ValueError('Install the '+library+' host dependency before enabling this provider.')
        if kind=='ldap' and (not s['host'] or s['bind_template'].count('{username}')!=1):raise ValueError('Set an LDAP host and bind identity template with one {username}.')
        if kind=='radius' and (not s['host'] or not s['secret']):raise ValueError('Set the RADIUS server and shared secret.')
        if kind=='kerberos' and (not re.fullmatch(r'[A-Za-z0-9_.-]+',s['realm']) or not s['principal'].startswith('HTTP/') or not s['principal'].endswith('@'+s['realm']) or not Path(s['keytab']).is_file()):raise ValueError('Set the realm, service principal and readable service keytab.')
    with app.store.connect() as db:
        db.execute('INSERT OR REPLACE INTO portal_settings VALUES(?,?)',('auth-'+kind,json.dumps(s)))
        db.execute('DELETE FROM sessions WHERE user_id IN (SELECT user_id FROM external_identities WHERE provider=?)',(kind,))
    with app.sso_lock:app.sso_pending.clear()
    return KINDS[kind]+' settings saved; existing provider sessions revoked.'
def principal(s,username):
    if '@' in username:
        if username.rsplit('@',1)[1]!=s['realm']:raise ValueError('Wrong realm')
        return username
    return username+'@'+s['realm']
def accept_credentials(s):
    import gssapi
    return gssapi.Credentials(name=gssapi.Name(s['principal'],name_type=gssapi.NameType.kerberos_principal),usage='accept',store={'keytab':s['keytab']})
def check(kind,s,username,password):
    if not password or len(password)>1024 or not re.fullmatch(r'[A-Za-z0-9_.@-]{1,128}',username):return False
    if kind=='ldap':
        from ldap3 import Server,Connection,Tls
        from ldap3.utils.dn import escape_rdn
        server=Server(s['host'],port=s['port'],use_ssl=True,connect_timeout=3,tls=Tls(validate=ssl.CERT_REQUIRED,ca_certs_file=s['ca_file'] or None))
        conn=Connection(server,user=s['bind_template'].replace('{username}',escape_rdn(username)),password=password,read_only=True,receive_timeout=3,raise_exceptions=True)
        try:return conn.bind()
        finally:conn.unbind()
    if kind=='radius':
        from pyrad.client import Client
        from pyrad.dictionary import Dictionary
        from pyrad import packet
        dictionary=Dictionary(io.StringIO('ATTRIBUTE User-Name 1 string\nATTRIBUTE User-Password 2 octets\nATTRIBUTE NAS-Identifier 32 string\nATTRIBUTE Message-Authenticator 80 octets\n'))
        client=Client(server=s['host'],authport=s['port'],secret=s['secret'].encode(),dict=dictionary,retries=1,timeout=3)
        try:
            request=client.CreateAuthPacket(code=packet.AccessRequest,User_Name=username,NAS_Identifier='ServiceReady')
            request['User-Password']=request.PwCrypt(password);request.add_message_authenticator()
            reply=client.SendPacket(request)
            return reply.code==packet.AccessAccept and reply.verify_message_authenticator(secret=s['secret'].encode(),original_authenticator=request.authenticator)
        finally:
            if client._socket:client._socket.close()
    import gssapi
    name=gssapi.Name(principal(s,username),name_type=gssapi.NameType.kerberos_principal)
    acquired=gssapi.raw.acquire_cred_with_password(name,password.encode(),usage='initiate',mechs=[gssapi.MechType.kerberos])
    initiator=gssapi.SecurityContext(name=gssapi.Name(s['principal'],name_type=gssapi.NameType.kerberos_principal),creds=gssapi.Credentials(base=acquired.creds),mech=gssapi.MechType.kerberos,usage='initiate')
    acceptor=gssapi.SecurityContext(creds=accept_credentials(s),usage='accept')
    token=initiator.step()
    for _ in range(4):
        token=acceptor.step(token)
        if acceptor.complete:return str(acceptor.initiator_name)==principal(s,username)
        token=initiator.step(token)
    return False

def session_for(app,kind,subject):
    s=settings(app,kind)
    if not s['enabled'] or not allowed(s,subject):return None
    namespace=kind+':'+subject
    with app.store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        row=db.execute('SELECT users.*,external_identities.active FROM external_identities JOIN users ON users.id=user_id WHERE provider=? AND subject=?',(kind,subject)).fetchone()
        if not row:
            if db.execute('SELECT 1 FROM users WHERE username=?',(namespace,)).fetchone():return None
            db.execute("INSERT INTO users(username,password,role,display_name) VALUES(?,'external','user',?)",(namespace,subject))
            uid=db.execute('SELECT id FROM users WHERE username=?',(namespace,)).fetchone()[0]
            db.execute('INSERT INTO external_identities(user_id,provider,subject) VALUES(?,?,?)',(uid,kind,subject))
        else:
            if not row['active'] or row['role']!='user':return None
            uid=row['id']
        token=secrets.token_urlsafe(32)
        db.execute('INSERT INTO sessions VALUES(?,?,?,?)',(token,uid,secrets.token_urlsafe(24),int(time.time())+28800))
    return token

def login(app,kind,username,password):
    if kind=='local':return app.store.login(username,password)
    if kind not in KINDS:return None
    s=settings(app,kind);username=username.strip()
    if kind=='kerberos':
        try: username=principal(s,username)
        except ValueError:return None
    if not s['enabled'] or not allowed(s,username):return None
    try:
        if not check(kind,s,username,password):return None
    except Exception:return None # Provider exceptions may include secrets; never expose or log them.
    return session_for(app,kind,username)
def verify_existing(app,user,password):
    row=identity(app,user)
    if not row or not row['active'] or user['role']!='user':return False
    s=settings(app,row['provider'])
    if not s['enabled'] or not allowed(s,row['subject']):return False
    try:return check(row['provider'],s,row['subject'],password)
    except Exception:return False

def sso(app,env,cookie,send):
    from . import login_protection,security
    if env.get('REQUEST_METHOD')!='GET':return send('405 Method Not Allowed','Use GET for browser sign-in.')
    wait=login_protection.reserve(app,env,'login')
    if wait:return send('429 Too Many Requests','Too many sign-in attempts.',extra=[('Retry-After',str(wait))])
    s=settings(app,'kerberos')
    if not s['enabled']:return send('404 Not Found','Kerberos sign-in is not enabled.')
    if env.get('HTTP_SEC_FETCH_SITE') not in (None,'same-origin','none'):return send('403 Forbidden','Open Kerberos sign-in from this portal.')
    authorization=env.get('HTTP_AUTHORIZATION','');identifier=cookie['vs_sso'].value if 'vs_sso' in cookie else ''
    with app.sso_lock:
        now=time.time();app.sso_pending={k:v for k,v in app.sso_pending.items() if v[0]>now}
        record=app.sso_pending.pop(identifier,None)
        if not record:
            if len(app.sso_pending)>=64:return send('429 Too Many Requests','Too many Kerberos negotiations. Try again shortly.')
            identifier=secrets.token_urlsafe(32)
            try:
                import gssapi
                context=gssapi.SecurityContext(creds=accept_credentials(s),usage='accept')
            except Exception:return send('503 Service Unavailable','Kerberos service credentials are unavailable. Use local sign-in or contact your administrator.')
            app.sso_pending[identifier]=(now+60,context,env.get('REMOTE_ADDR'))
            return send('401 Unauthorized',app.page('Kerberos sign-in','<p>Your browser must be configured for Kerberos. <a href="/login">Use password sign-in</a>.</p>',None),extra=[('WWW-Authenticate','Negotiate'),('Set-Cookie','vs_sso='+identifier+'; HttpOnly; Secure; SameSite=Lax; Path=/login; Max-Age=60')])
        _,context,source=record
        try:
            if source!=env.get('REMOTE_ADDR') or not authorization.startswith('Negotiate ') or len(authorization)>65536:raise ValueError()
            outgoing=context.step(base64.b64decode(authorization[10:],validate=True))
            if not context.complete:
                app.sso_pending[identifier]=(now+60,context,source)
                return send('401 Unauthorized',app.page('Kerberos sign-in','<p>Completing browser authentication.</p>',None),extra=[('WWW-Authenticate','Negotiate '+base64.b64encode(outgoing or b'').decode())])
            import gssapi
            if context.mech!=gssapi.MechType.kerberos:raise ValueError()
            subject=str(context.initiator_name)
            if subject.rsplit('@',1)[-1]!=s['realm']:raise ValueError()
            # SSO allowlist uses full principal names, avoiding cross-realm name collisions.
            token=session_for(app,'kerberos',subject)
            if not token:raise ValueError()
        except Exception:
            login_protection.failed(env,'login',app)
            return send('403 Forbidden',app.page('Sign-in unavailable','<p>Kerberos sign-in failed or your principal is not permitted. <a href="/login">Return to sign in</a>.</p>',None))
    from . import twofactor
    person=app.store.session(token)
    if twofactor.state(app,person).get('secret'):
        app.store.logout(token);pending=twofactor.challenge(app,person,False)
        extra=[('Location','/login/verify'),('Set-Cookie','vs_factor='+pending+'; HttpOnly; Secure; SameSite=Lax; Path=/login; Max-Age=300')]
    else:
        duration=security.duration(app)
        with app.store.connect() as db:db.execute('UPDATE sessions SET expires=? WHERE token=?',(int(time.time())+duration,token))
        extra=[('Location','/'),('Set-Cookie','vs_session='+token+'; HttpOnly; Secure; SameSite=Lax; Path=/; Max-Age='+str(duration))]
    if outgoing:extra.append(('WWW-Authenticate','Negotiate '+base64.b64encode(outgoing).decode()))
    extra.append(('Set-Cookie','vs_sso=; HttpOnly; Secure; SameSite=Lax; Path=/login; Max-Age=0'))
    return send('303 See Other','',extra=extra)

def render(app,user):
    csrf='<input type="hidden" name="csrf" value="'+E(user['csrf'])+'">'
    text='<p>Local administrators always use local host authentication. External providers create separate user identities and never grant administrator access. Only explicitly permitted usernames can sign in. Passwords and shared secrets are not displayed.</p>'
    for kind,label in KINDS.items():
        s=settings(app,kind);library={'ldap':'ldap3','kerberos':'gssapi','radius':'pyrad'}[kind]
        text+='<details class="settings-section"><summary>'+label+' — '+('Enabled' if s['enabled'] else 'Disabled')+'</summary><div class="panel"><p>Client dependency: '+('Available' if importlib.util.find_spec(library) else 'Not installed')+'</p><form method="post">'+csrf+'<input type="hidden" name="provider" value="'+kind+'">'
        fields={'ldap':[('host','LDAP hostname'),('port','LDAPS port'),('bind_template','Bind identity template ({username})'),('ca_file','CA file (optional; system trust by default)')],'radius':[('host','RADIUS server'),('port','Authentication port')],'kerberos':[('realm','Kerberos realm'),('principal','HTTP service principal (HTTP/portal.example@REALM)'),('keytab','Service keytab path')]}[kind]
        for key,title in fields:text+='<label>'+title+'</label><input name="'+key+'" value="'+E(s[key])+'">'
        if kind=='radius':text+='<label>Shared secret (blank keeps existing)</label><input type="password" name="secret" autocomplete="new-password">'
        text+='<label>Permitted usernames (one per line; full principals for Kerberos SSO)</label><textarea name="allowed_users" rows="4">'+E(s['allowed_users'])+'</textarea><label>Provider</label><select name="enabled"><option value="no">Disabled</option><option value="yes"'+(' selected' if s['enabled'] else '')+'>Enabled</option></select><label>Your local administrator password</label><input type="password" name="current_password" autocomplete="current-password" required><button>Save '+label+'</button></form></div></details>'
    return text+'<p>LDAP requires certificate-verified LDAPS. RADIUS uses PAP with verified response and Message-Authenticator; Access-Challenge is rejected. Kerberos requires host krb5.conf, DNS, synchronized clocks, a keytab and browser trust configuration. Password and browser sign-in both verify service tickets against the configured keytab.</p>'
