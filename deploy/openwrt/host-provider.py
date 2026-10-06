"""OpenWrt preparation provider: native accounts/PTY, cleanup and address tracking.
Rocky disk/network/update commands must never be executed on OpenWrt.
"""
import json,os,time
from pathlib import Path
CONFIG=Path('/etc/serviceready/config.json')
SETUP_LOCK=Path('/run/serviceready-accounts/setup.lock')
SHADOW=Path('/etc/shadow')
NOTICE='OpenWrt host integration is in preparation. Use LuCI/UCI for network, time and disks; use attended sysupgrade for firmware. Install INSAP from its OpenWrt release bundle. Guest drivers must match the OpenWrt kernel.'
LAST_REFRESH=0
STATE={'state':'idle','message':'No maintenance started.','kind':'','at':0}
def refresh():
    global LAST_REFRESH
    if time.monotonic()-LAST_REFRESH<15:return
    LAST_REFRESH=time.monotonic()
    from voiceservices.network_address import Addresses
    from voiceservices.openwrt_tls import refresh as tls_refresh
    config=json.loads(CONFIG.read_text());url=tls_refresh(config,Addresses())
    if config.get('public_url')!=url:
        config['public_url']=url;temporary=CONFIG.with_suffix('.new');temporary.write_text(json.dumps(config,indent=2));os.chown(temporary,CONFIG.stat().st_uid,CONFIG.stat().st_gid);temporary.chmod(0o640);temporary.replace(CONFIG)
def complete_setup(request,account_command,set_password):
    import fcntl,hmac,pwd,re,subprocess
    from zoneinfo import ZoneInfo
    from voiceservices.core import Store
    config=json.loads(CONFIG.read_text())
    if not config.get('first_boot_setup'):raise ValueError('First-boot setup is disabled.')
    username=request.get('username','');code=request.get('password','')
    payload=json.loads(request.get('new_password','{}'))
    if not isinstance(payload,dict):raise ValueError('Invalid setup fields.')
    password=payload.get('password','')
    if not re.fullmatch('[a-z_][a-z0-9_-]{2,31}',username):raise ValueError('Use 3–32 lowercase letters, digits, underscores or hyphens.')
    if not isinstance(password,str) or not 12<=len(password)<=1024 or any(c in password for c in '\r\n\x00'):raise ValueError('Use a password of 12–1024 characters without line breaks.')
    title=payload.get('title','').strip()
    if not title or len(title)>100:raise ValueError('Enter a portal title of 1–100 characters.')
    zone=payload.get('timezone','UTC')
    try:ZoneInfo(zone)
    except (ValueError,KeyError):raise ValueError('Choose a supported time zone.')
    store=Store(config['database']);token=CONFIG.parent/'setup-token'
    with open(SETUP_LOCK,'w') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        with store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if db.execute("SELECT 1 FROM users WHERE role='admin'").fetchone():raise ValueError('Setup has already been completed.')
            if not token.is_file() or not hmac.compare_digest(token.read_text().strip(),str(code)):raise ValueError('Setup code is incorrect. Check the VM console.')
            try:pwd.getpwnam(username)
            except KeyError:pass
            else:raise ValueError('Choose a new OS username; existing accounts cannot be claimed.')
            subprocess.run(account_command('create',username),check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            try:
                set_password(username,password)
                # A fresh image must not retain OpenWrt's blank root-console password.
                root=next((line.split(':') for line in SHADOW.read_text().splitlines() if line.startswith('root:')),None)
                if root and root[1]=='':set_password('root',password)
                db.execute("INSERT INTO users(username,password,role) VALUES(?,'system','admin')",(username,))
                row=db.execute("SELECT value FROM portal_settings WHERE key='branding'").fetchone()
                look=json.loads(row[0]) if row else {};look.update(title=title,global_timezone=zone)
                db.execute("INSERT OR REPLACE INTO portal_settings VALUES('branding',?)",(json.dumps(look),))
                db.execute('INSERT INTO audit(at,user_id,action) VALUES(?,(SELECT id FROM users WHERE username=?),?)',(int(time.time()),username,'Completed appliance first-boot setup'))
                db.commit()
            except Exception:
                subprocess.run(account_command('delete',username),check=False,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL);raise
        token.unlink(missing_ok=True)
    return {'ok':True}

def handle(request,authenticate,account_command=None,set_password=None):
    action=request.get('action')
    if action=='setup-complete':return complete_setup(request,account_command,set_password)
    if action=='maintenance-status':return {'ok':True,'status':dict(STATE,provider='openwrt',provider_message=NOTICE)}
    if action=='host-status':return {'ok':True,'status':{'provider':'openwrt','provider_message':NOTICE,'job':dict(STATE)}}
    if action in ('host-start','host-confirm'):
        if not authenticate(request.get('username',''),request.get('password','')):raise ValueError('Confirm your local administrator password.')
        raise ValueError(NOTICE)
    if action=='maintenance-start':
        kind=request.get('username','')
        selected=json.loads(request.get('password','[]')) if kind=='cleanup' else [kind]
        if not isinstance(selected,list) or not selected or len(selected)>3 or any(v not in ('package-cache','portal-temp','portal-logs') for v in selected):raise ValueError(NOTICE)
        messages=[]
        for task in dict.fromkeys(selected):
            if task=='package-cache':messages.append('No persistent package cache is managed by this profile')
            elif task=='portal-temp':
                now=time.time();count=0
                for path in Path('/tmp/serviceready').iterdir():
                    if path.is_file() and not path.is_symlink() and path.stat().st_mtime<now-7*86400:path.unlink();count+=1
                messages.append(str(count)+' old temporary files removed')
            else:messages.append('Portal logs use OpenWrt logd; no persistent portal log files')
        STATE.update(kind=kind,state='complete',message='; '.join(messages)+'.',at=time.time());return {'ok':True}
    if action=='maintenance-decline':raise ValueError(NOTICE)
    return None
