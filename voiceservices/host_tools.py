"""Core Linux maintenance controls and authenticated user PTY terminal."""
import hashlib,html,json,time
E=lambda v:html.escape(str(v),quote=True)
TASKS={'package-cache':('Clean package cache','Remove unused cached Linux packages; keep installed packages.'),'portal-temp':('Clean old temporary files','Remove regular files older than seven days from the portal temporary directory.'),'portal-logs':('Trim portal logs','Keep only the latest 1 MiB of each portal log; older log content is removed.')}
def audit(app,user,action):
    with app.store.connect() as db:db.execute('INSERT INTO audit(at,user_id,action) VALUES(?,?,?)',(int(time.time()),user['id'],action))
def admin_change(app,data,services):
    # Maintenance is handled by page(), where the authenticated actor is available.
    raise ValueError('Use the host maintenance task form.')
def admin_render(app,user,services):
    csrf='<input type="hidden" name="csrf" value="'+E(user['csrf'])+'">'
    if not app.store.accounts:return '<p class="notice">No Linux host provider is connected. Host cleanup and terminal access are unavailable on this development deployment.</p>'
    text='<p>Run individual cleanup tasks on the connected Linux host. Updates remain available on Overview.</p>'
    try:
        state=app.store.accounts.call('maintenance-status','','')
        text+='<p class="notice">'+E(state.get('state','idle'))+': '+E(state.get('message',''))+'</p>'
    except ValueError as exc:text+='<p class="notice error">'+E(exc)+'</p>'
    for key,(title,detail) in TASKS.items():text+='<div class="panel"><h3>'+title+'</h3><p>'+detail+'</p><form method="post">'+csrf+'<input type="hidden" name="task" value="'+key+'"><label>Your local administrator password</label><input type="password" name="current_password" autocomplete="current-password" required><label><input type="checkbox" name="confirm" value="yes" required> Confirm this cleanup task</label><button>Run task</button></form></div>'
    text+='<div class="panel"><h3>Host power</h3><p>Restart or shut down this VM. All hosted services will disconnect. After shutdown, start the VM from your hypervisor.</p>'
    for operation,label in [('restart','Restart VM'),('shutdown','Shut down VM')]:
        text+='<form method="post">'+csrf+'<input type="hidden" name="task" value="power"><input type="hidden" name="operation" value="'+operation+'"><label>Local administrator password</label><input type="password" name="current_password" autocomplete="current-password" required><label>Type '+operation+' to confirm</label><input name="confirm" required autocomplete="off"><button>'+label+'</button></form>'
    text+='</div>'
    return text+'<p><a href="/admin/terminal">Open host terminal</a></p>'
def terminal_render(app,user):
    if not app.store.accounts:return '<p class="notice">The browser terminal requires the Linux host account broker. It is unavailable on this development deployment.</p>'
    return '<p>Open an interactive shell as <strong>'+E(user['username'])+'</strong>. Your existing OS permissions apply; this is not a root shell. Sessions close after 60 seconds without a browser heartbeat or 30 minutes total.</p><div class="panel" id="host-terminal" data-csrf="'+E(user['csrf'])+'"><form data-terminal-open><label>Confirm your local Linux password</label><input name="password" type="password" autocomplete="current-password" required><button>Open terminal</button></form><p data-terminal-status>Disconnected</p><button type="button" data-terminal-close disabled>Close terminal</button><div data-terminal-screen></div></div>'
def page(app,path,method,data,user,env,send):
    if user['role']!='admin':return send('403 Forbidden','Administrator access required.')
    if method=='POST' and app.store.accounts and (not app.base.startswith('https://') or not app.secure):return send('400 Bad Request',json.dumps({'error':'Configure HTTPS and secure cookies before using host tools.'}),'application/json')
    if path=='/admin/host' and method=='POST':
        if not app.store.accounts:return send('400 Bad Request','No supported host provider is connected.')
        from voiceservices.twofactor import password
        try:
            task=data.get('task')
            if task=='power':
                from . import host_configuration
                note=host_configuration.change(app,user,dict(data,kind='power'))
                return send('200 OK',app.page('Host power', '<div class="panel"><h2>Host power request accepted</h2><p>The VM will '+E(data.get('operation',''))+' shortly. The portal will disconnect. After a restart, return to the home page once the VM is available.</p><a href="/">Home</a></div>',user))
            if task not in TASKS or data.get('confirm')!='yes':raise ValueError('Choose and confirm a maintenance task.')
            password(app,user,data.get('current_password',''))
            app.store.accounts.call('maintenance-start',task,'');audit(app,user,'Started host maintenance '+task)
        except ValueError as exc:return send('400 Bad Request',app.page('Host maintenance',E(exc),user))
        return send('303 See Other','',extra=[('Location','/admin/host')])
    if path=='/admin/terminal/io':
        if method!='POST':return send('405 Method Not Allowed',json.dumps({'error':'POST required'}),'application/json')
        if not app.store.accounts:return send('400 Bad Request',json.dumps({'error':'Linux host provider unavailable'}),'application/json')
        from voiceservices import external_auth
        if external_auth.identity(app,user):return send('403 Forbidden',json.dumps({'error':'Local administrator required'}),'application/json')
        action=data.get('action','')
        if action not in ('open','read','write','resize','close'):return send('400 Bad Request',json.dumps({'error':'Invalid operation'}),'application/json')
        payload={'session':hashlib.sha256(env.get('HTTP_COOKIE','').encode()).hexdigest(),'token':data.get('token','')}
        # Bind to the actual authenticated session token; unrelated cookie changes cannot attach a terminal.
        from http.cookies import SimpleCookie
        cookies=SimpleCookie();cookies.load(env.get('HTTP_COOKIE',''))
        payload['session']=hashlib.sha256(cookies['vs_session'].value.encode()).hexdigest()
        if action=='write':payload['data']=data.get('input','')
        if action=='resize':payload.update(rows=data.get('rows','24'),cols=data.get('cols','80'))
        try:
            result=app.store.accounts.call('terminal-'+action,user['username'],data.get('password','') if action=='open' else '',json.dumps(payload))
            if action in ('open','close'):audit(app,user,'Host terminal '+action)
        except ValueError as exc:return send('400 Bad Request',json.dumps({'error':str(exc)}),'application/json')
        return send('200 OK',json.dumps(result),'application/json')
