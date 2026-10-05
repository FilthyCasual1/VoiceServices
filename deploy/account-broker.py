#!/usr/bin/env python3
"""Root broker: peer-restricted, group-restricted Alpine account operations."""
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

def handle(request):
    username=request.get('username','');password=request.get('password','')
    if not re.fullmatch('[a-z_][a-z0-9_-]{2,31}',username): raise ValueError('System usernames use 3–32 lowercase letters, numbers, underscores or hyphens.')
    if not isinstance(password,str) or len(password)>1024 or '\x00' in password: raise ValueError('Invalid password.')
    action=request.get('action')
    if action=='create':
        try: pwd.getpwnam(username)
        except KeyError: pass
        else: raise ValueError('System username already exists. Ask your administrator to enroll it.')
        if len(password)<12 or any(c in password for c in '\r\n'): raise ValueError('Use a password of at least 12 characters without line breaks.')
        subprocess.run(['/usr/sbin/adduser','-D','-H','-s','/sbin/nologin','-G',GROUP,username],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        try: set_password(username,password)
        except Exception:
            subprocess.run(['/usr/sbin/deluser',username],check=False,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            raise
    elif action=='delete':
        try: allowed=eligible(username)
        except KeyError: allowed=False
        if not allowed: raise ValueError('Only enrolled non-system accounts can be deleted.')
        subprocess.run(['/usr/sbin/deluser',username],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
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
        server.listen(8)
        while True:
            connection,_=server.accept()
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
