#!/usr/bin/env python3
"""Root broker: peer-restricted, group-restricted Linux account operations."""
import ctypes
import ctypes.util
import grp
import hmac
import json
import os
import pwd
import re
import socket
import struct
import subprocess
import time

SOCKET='/run/serviceready-accounts/socket'
GROUP='serviceready-users'

def account_command(action,username):
    rocky=os.path.isfile('/etc/rocky-release')
    if action=='create':
        return ['/usr/sbin/useradd','-M','-s','/sbin/nologin','-g',GROUP,username] if rocky else ['/usr/sbin/adduser','-D','-H','-s','/sbin/nologin','-G',GROUP,username]
    return ['/usr/sbin/userdel',username] if rocky else ['/usr/sbin/deluser',username]

def eligible(username):
    entry=pwd.getpwnam(username)
    group=grp.getgrnam(GROUP)
    return entry.pw_uid >= 1000 and (username in group.gr_mem or entry.pw_gid==group.gr_gid)

def authenticate(username,password):
    if not eligible(username): return False
    with open('/etc/shadow') as source:
        row=next((line.strip().split(':') for line in source if line.startswith(username+':')),None)
    if not row or row[1].startswith(('!','*')): return False
    today=int(time.time()//86400)
    if row[7] and today>=int(row[7]): return False
    if row[2] and row[4] and int(row[4])>=0 and today>int(row[2])+int(row[4]): return False
    library=ctypes.CDLL(ctypes.util.find_library('crypt') or ctypes.util.find_library('c'))
    library.crypt.argtypes=[ctypes.c_char_p,ctypes.c_char_p]
    library.crypt.restype=ctypes.c_char_p
    value=library.crypt(password.encode(),row[1].encode())
    return bool(value) and hmac.compare_digest(value.decode(),row[1])

def set_password(username,password):
    if len(password)<12 or len(password)>1024 or any(c in password for c in '\r\n\x00'):
        raise ValueError('Password must contain 12–1024 characters and no line breaks.')
    subprocess.run(['/usr/sbin/chpasswd','-c','SHA512'],input=f'{username}:{password}\n',text=True,check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)

# In-memory PTY sessions: never run the user's shell as the root broker.
TERMINALS={}
def terminal_close(key):
    import signal
    session=TERMINALS.pop(key,None)
    if not session:return
    try:os.killpg(session['process'].pid,signal.SIGHUP)
    except ProcessLookupError:pass
    try:session['process'].wait(timeout=1)
    except subprocess.TimeoutExpired:
        try:os.killpg(session['process'].pid,signal.SIGKILL)
        except ProcessLookupError:pass
        session['process'].wait(timeout=1)
    os.close(session['fd'])
def terminal_expire():
    now=time.monotonic()
    for key,s in list(TERMINALS.items()):
        if now-s['touched']>60 or now-s['created']>1800 or s['process'].poll() is not None:terminal_close(key)
def terminal_handle(request):
    import base64,fcntl,pty,secrets,termios
    terminal_expire()
    username=request.get('username','');action=request['action']
    try:payload=json.loads(request.get('new_password','{}'))
    except (TypeError,ValueError):raise ValueError('Invalid terminal request.')
    if not isinstance(payload,dict) or not re.fullmatch(r'[a-f0-9]{64}',payload.get('session','')):raise ValueError('Invalid terminal session binding.')
    binding=payload['session']
    if action=='terminal-open':
        if not authenticate(username,request.get('password','')):raise ValueError('Confirm your local Linux password.')
        if len(TERMINALS)>=4:raise ValueError('Maximum four host terminals. Close another session first.')
        entry=pwd.getpwnam(username)
        master,slave=pty.openpty()
        fcntl.ioctl(slave,termios.TIOCSWINSZ,struct.pack('HHHH',24,80,0,0))
        def child():
            os.setsid();fcntl.ioctl(slave,termios.TIOCSCTTY,0)
            os.initgroups(username,entry.pw_gid);os.setgid(entry.pw_gid);os.setuid(entry.pw_uid)
        environment={'HOME':entry.pw_dir,'USER':username,'LOGNAME':username,'TERM':'xterm-256color','PATH':'/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin','LANG':'C.UTF-8'}
        try:process=subprocess.Popen(['/bin/sh','-l'],stdin=slave,stdout=slave,stderr=slave,env=environment,cwd=entry.pw_dir if os.path.isdir(entry.pw_dir) else '/',preexec_fn=child,close_fds=True)
        except Exception:os.close(master);raise
        finally:os.close(slave)
        os.set_blocking(master,False);key=secrets.token_urlsafe(32)
        TERMINALS[key]={'process':process,'fd':master,'username':username,'binding':binding,'created':time.monotonic(),'touched':time.monotonic()}
        return {'ok':True,'status':{'token':key}}
    key=payload.get('token','');session=TERMINALS.get(key)
    if not session or session['username']!=username or session['binding']!=binding:raise ValueError('Terminal expired or belongs to another session.')
    session['touched']=time.monotonic()
    if action=='terminal-close':terminal_close(key);return {'ok':True,'status':{'closed':True}}
    if action=='terminal-write':
        try:raw=base64.b64decode(payload.get('data',''),validate=True)
        except ValueError:raise ValueError('Invalid terminal input.')
        if len(raw)>2048:raise ValueError('Terminal input exceeds 2048 bytes.')
        try:written=os.write(session['fd'],raw)
        except BlockingIOError:raise ValueError('Terminal input buffer full. Try again.')
        return {'ok':True,'status':{'written':written}}
    if action=='terminal-resize':
        rows=int(payload.get('rows',24));cols=int(payload.get('cols',80))
        if not 10<=rows<=100 or not 20<=cols<=240:raise ValueError('Invalid terminal dimensions.')
        fcntl.ioctl(session['fd'],termios.TIOCSWINSZ,struct.pack('HHHH',rows,cols,0,0))
        return {'ok':True,'status':{}}
    if action!='terminal-read':raise ValueError('Unknown terminal operation.')
    try:raw=os.read(session['fd'],4096)
    except BlockingIOError:raw=b''
    except OSError:terminal_close(key);return {'ok':True,'status':{'closed':True}}
    return {'ok':True,'status':{'data':base64.b64encode(raw).decode()}}

def handle(request):
    if request.get('action') in ('host-status','host-start','host-confirm'):
        import importlib.util,base64
        from pathlib import Path
        worker=Path('/opt/serviceready/host-control.py')
        if not worker.exists():
            # Older GUI update workers copied only the broker and updater.
            # Bootstrap solely from the root-controlled approved checkout.
            source=Path('/opt/serviceready/source/deploy/host-control.py')
            chain=[Path('/opt/serviceready'),source.parents[1],source.parent,source]
            if all(path.exists() and not path.is_symlink() and path.stat().st_uid==0 and not path.stat().st_mode&0o022 for path in chain):
                import shutil
                shutil.copyfile(source,worker);os.chmod(worker,0o700)

        if not worker.is_file() or worker.is_symlink() or worker.stat().st_uid!=0 or worker.stat().st_mode&0o022:raise ValueError('Host controls are not installed safely.')
        spec=importlib.util.spec_from_file_location('host_control',worker);control=importlib.util.module_from_spec(spec);spec.loader.exec_module(control)
        if request['action']=='host-status':return {'ok':True,'status':control.snapshot(request.get('new_password','storage'))}
        if not authenticate(request.get('username',''),request.get('password','')):raise ValueError('Confirm your local administrator password.')
        if request['action']=='host-confirm':
            if control.snapshot()['job']['state']!='pending':raise ValueError('No network change awaiting confirmation.')
            control.STATE.with_suffix('.confirmed').touch();return {'ok':True}
        state=control.snapshot()['job']
        if state['state'] in ('running','pending'):raise ValueError('A host operation is already running.')
        payload=json.loads(request.get('new_password','{}'));control.validate(payload)
        control.status('running','Starting host operation')
        subprocess.Popen(['/usr/bin/python3',str(worker),base64.b64encode(json.dumps(payload).encode()).decode()],stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)
        return {'ok':True}
    if request.get('action') in ('maintenance-start','maintenance-status'):
        from pathlib import Path
        state_path=Path('/run/serviceready-accounts/maintenance.json')
        state=json.loads(state_path.read_text()) if state_path.exists() else {'state':'idle','message':'No updates started.'}
        if request['action']=='maintenance-status': return {'ok':True,'status':state}
        kind=request.get('username')
        if kind not in ('os','insap','package-cache','portal-temp','portal-logs'): raise ValueError('Unknown update operation.')
        if state.get('state')=='running': raise ValueError('An update is already running.')
        worker=Path('/opt/serviceready/maintenance-worker.py')
        if not worker.is_file() or worker.is_symlink() or worker.stat().st_uid!=0 or worker.stat().st_mode&0o022: raise ValueError('Update worker not installed safely.')
        starting={'kind':kind,'state':'running','message':'Starting host update worker','at':int(time.time())}
        temporary=state_path.with_suffix('.starting');temporary.write_text(json.dumps(starting));os.chmod(temporary,0o600);temporary.replace(state_path)
        try:
            subprocess.Popen(['/usr/bin/python3',str(worker),kind],stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)
        except OSError:
            starting.update(state='failed',message='The host update worker could not start.');temporary.write_text(json.dumps(starting));temporary.replace(state_path)
            raise ValueError(starting['message']) from None
        return {'ok':True}
    username=request.get('username','');password=request.get('password','')
    if not re.fullmatch('[a-z_][a-z0-9_-]{2,31}',username): raise ValueError('System usernames use 3–32 lowercase letters, numbers, underscores or hyphens.')
    if not isinstance(password,str) or len(password)>1024 or '\x00' in password: raise ValueError('Invalid password.')
    action=request.get('action')
    if action.startswith('terminal-'):return terminal_handle(request)
    if action=='create':
        try: pwd.getpwnam(username)
        except KeyError: pass
        else: raise ValueError('System username already exists. Ask your administrator to enroll it.')
        if len(password)<12 or any(c in password for c in '\r\n'): raise ValueError('Use a password of at least 12 characters without line breaks.')
        subprocess.run(account_command('create',username),check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        try: set_password(username,password)
        except Exception:
            subprocess.run(account_command('delete',username),check=False,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            raise
    elif action=='reset':
        try: allowed=eligible(username)
        except KeyError: allowed=False
        if not allowed: raise ValueError('Only enrolled non-system accounts can be reset.')
        set_password(username,request.get('new_password',''))
    elif action=='delete':
        try: allowed=eligible(username)
        except KeyError: allowed=False
        if not allowed: raise ValueError('Only enrolled non-system accounts can be deleted.')
        subprocess.run(account_command('delete',username),check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    elif action in ('authenticate','change'):
        try: valid=authenticate(username,password)
        except KeyError: valid=False
        if not valid: raise ValueError('Invalid username or password.')
        if action=='change': set_password(username,request.get('new_password',''))
    else: raise ValueError('Unknown account operation.')
    return {'ok':True}

def main():
    os.umask(0o077)
    if os.path.exists(SOCKET): os.unlink(SOCKET)
    allowed_uid=pwd.getpwnam('serviceready').pw_uid
    with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as server:
        server.bind(SOCKET)
        os.chown(SOCKET,0,grp.getgrnam('serviceready').gr_gid);os.chmod(SOCKET,0o660)
        server.listen(8);server.settimeout(1)
        while True:
            terminal_expire()
            try:connection,_=server.accept()
            except socket.timeout:continue
            with connection:
                connection.settimeout(15)
                _,uid,_=struct.unpack('3i',connection.getsockopt(socket.SOL_SOCKET,socket.SO_PEERCRED,12))
                if uid not in (0,allowed_uid): continue
                try:
                    raw=connection.makefile('rb').readline(8193)
                    if len(raw)>8192: raise ValueError('Request too large.')
                    result=handle(json.loads(raw))
                except Exception as exc:
                    result={'ok':False,'error':str(exc) if isinstance(exc,ValueError) else 'System account operation failed.'}
                connection.sendall(json.dumps(result).encode()+b'\n')

if __name__=='__main__': main()
