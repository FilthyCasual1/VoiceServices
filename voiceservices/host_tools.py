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
    text='<h2>Cleanup</h2><form method="post" class="compact-host-tasks">'+csrf+'<input type="hidden" name="task" value="cleanup">'
    for key,(title,detail) in TASKS.items():
        text+='<label class="host-task-row host-task-choice"><input type="checkbox" name="task_'+key+'" value="yes"><div><strong>'+title+'</strong><small>'+detail+'</small></div></label>'
    text+='<div class="cleanup-actions"><button>Run selected tasks</button></div></form>'
    if app.config.get('tls_proxy')=='openwrt':return text+'<p class="notice">Manage host power from the hypervisor while the OpenWrt host provider is being prepared.</p>'
    text+='<h2>Host power</h2><form method="post" class="compact-host-power">'+csrf+'<input type="hidden" name="task" value="power"><p>All services disconnect. After shutdown, start the VM from your hypervisor.</p><label class="host-password">Local administrator password <input type="password" name="current_password" autocomplete="current-password" required></label><label class="host-check"><input type="checkbox" name="confirm" value="yes" required> Confirm power action</label><div class="update-actions"><button name="operation" value="restart">Restart VM</button><button name="operation" value="shutdown">Shut down VM</button></div></form>'
    return text
def terminal_render(app,user):
    if not app.store.accounts:return '<p class="notice">The browser terminal requires the Linux host account broker. It is unavailable on this development deployment.</p>'
    return '<p>Open an interactive shell as <strong>'+E(user['username'])+'</strong>. Your existing OS permissions apply; this is not a root shell. Sessions close after 60 seconds without a browser heartbeat or 30 minutes total.</p><div class="panel" id="host-terminal" data-csrf="'+E(user['csrf'])+'"><form data-terminal-open><label>Confirm your local Linux password</label><input name="password" type="password" autocomplete="current-password" required><button>Open terminal</button></form><p data-terminal-status>Disconnected</p><button type="button" data-terminal-close disabled>Close terminal</button><div data-terminal-screen></div></div>'
def page(app,path,method,data,user,env,send):
    if user['role']!='admin':return send('403 Forbidden','Administrator access required.')
    if method=='POST' and app.store.accounts and (not app.base.startswith('https://') or not app.secure):return send('400 Bad Request',json.dumps({'error':'Configure HTTPS and secure cookies before using host tools.'}),'application/json')
    if path=='/admin/host' and method=='POST':
        if not app.store.accounts:return send('400 Bad Request','No supported host provider is connected.')
        try:
            task=data.get('task')
            if task=='cleanup':
                selected=[key for key in TASKS if data.get('task_'+key)=='yes']
                if not selected:raise ValueError('Select at least one cleanup task.')
                app.store.accounts.call('maintenance-start','cleanup',json.dumps(selected));audit(app,user,'Started cleanup: '+', '.join(selected))
                return send('303 See Other','',extra=[('Location','/admin/host')])
            if task=='power':
                from . import host_configuration
                if data.get('confirm')!='yes' or data.get('operation') not in ('restart','shutdown'):raise ValueError('Choose and confirm a power action.')
                note=host_configuration.change(app,user,dict(data,kind='power',confirm=data['operation']))
                return send('200 OK',app.page('Host power', '<div class="panel"><h2>Host power request accepted</h2><p>The VM will '+E(data.get('operation',''))+' shortly. The portal will disconnect. After a restart, return to the home page once the VM is available.</p><a href="/">Home</a></div>',user))
            if task not in TASKS or data.get('confirm')!='yes':raise ValueError('Choose and confirm a maintenance task.')
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
