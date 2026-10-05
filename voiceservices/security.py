"""Core sign-in policy and application-level source blocking."""
import html,ipaddress,json,time
E=lambda v:html.escape(str(v),quote=True)
DEFAULT={'login_limit':10,'mfa_limit':10,'window':300,'automatic_blocks':False,'failure_limit':5,'block_seconds':900,'session_hours':8,'remember_enabled':True,'remember_days':30,'registration_enabled':True}
NUMBERS={'login_limit':('Password attempts per IP',1,100),'mfa_limit':('Two-factor attempts per IP',1,100),'window':('Attempt window (seconds)',60,3600),'failure_limit':('Failures before automatic block',1,100),'block_seconds':('Automatic block duration (seconds)',60,86400),'session_hours':('Standard session duration (hours)',1,24),'remember_days':('Stay signed in duration (days)',1,90)}
def settings(app): return dict(DEFAULT,**app.config.get('security',{}))
def duration(app,remember=False):
    s=settings(app);return s['remember_days']*86400 if remember and s['remember_enabled'] else s['session_hours']*3600
def change(app,user,data):
    if user['role']!='admin': raise PermissionError('Administrator access required.')
    if data.get('action')=='unblock':
        try: ip=str(ipaddress.ip_address(data.get('source','')))
        except ValueError: raise ValueError('Choose a valid IP address.')
        with app.store.connect() as db:
            db.execute('DELETE FROM login_failures WHERE source=?',(ip,));db.execute('DELETE FROM login_limits WHERE source=?',(ip,))
        return 'Source block and attempt counters cleared.'
    s=settings(app)
    for key,(_,low,high) in NUMBERS.items():
        try: value=int(data.get(key,s[key]))
        except (ValueError,TypeError): raise ValueError('Enter numeric security limits.')
        if not low<=value<=high: raise ValueError(NUMBERS[key][0]+' must be between '+str(low)+' and '+str(high)+'.')
        s[key]=value
    for key in ('automatic_blocks','remember_enabled','registration_enabled'):
        value=data.get(key,'yes' if s[key] else 'no')
        if value not in ('yes','no'): raise ValueError('Choose On or Off.')
        s[key]=value=='yes'
    with app.store.connect() as db: db.execute("INSERT OR REPLACE INTO portal_settings VALUES('security',?)",(json.dumps(s),))
    app.config['security']=s
    return 'Security policy saved. Session duration changes apply to new sign-ins.'
def render(app,user):
    s=settings(app);csrf='<input type="hidden" name="csrf" value="'+E(user['csrf'])+'">'
    text='<p>Manage portal sign-in protection and account policy. These controls are part of the core.</p><div class="panel"><form method="post">'+csrf
    for key,(label,low,high) in NUMBERS.items(): text+='<label>'+label+'</label><input type="number" name="'+key+'" min="'+str(low)+'" max="'+str(high)+'" value="'+str(s[key])+'" required>'
    for key,label in [('automatic_blocks','Automatically block repeated authentication failures'),('remember_enabled','Allow Stay Signed In'),('registration_enabled','Allow account self-registration')]:
        text+='<label>'+label+'</label><select name="'+key+'"><option value="no">Off</option><option value="yes"'+(' selected' if s[key] else '')+'>On</option></select>'
    text+='<br><button>Save security policy</button></form></div><h2>Active source blocks</h2><p>Blocks apply to new password and two-factor sign-ins. They do not terminate existing sessions. IPs sharing a NAT also share limits.</p>'
    with app.store.connect() as db: rows=list(db.execute('SELECT source,blocked_until FROM login_failures WHERE blocked_until>?',(int(time.time()),)))
    if not rows: text+='<p>No active blocks.</p>'
    for row in rows:
        text+='<div class="panel">'+E(row['source'])+' — '+str(max(0,row['blocked_until']-int(time.time())))+' seconds remaining'+(' (automatic blocking is currently off)' if not s['automatic_blocks'] else '')+'<form class="inline" method="post">'+csrf+'<input type="hidden" name="source" value="'+E(row['source'])+'"><button name="action" value="unblock">Unblock</button></form></div>'
    return text+'<h2>Connection and host security</h2><p>Secure session cookies: '+('On' if app.secure else 'Off')+'. Public portal URL: '+E(app.base)+'. TLS and trusted proxy handling are configured on the host. Two-factor enrollment is available under My Account → Security.</p><p>Authentication failure logging is always enabled. Optional host Fail2ban can additionally block traffic at the firewall; its service and firewall action are managed on the host. The portal’s automatic IP blocking works without Fail2ban.</p>'
