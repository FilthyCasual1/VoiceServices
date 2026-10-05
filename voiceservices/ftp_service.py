"""Optional addon worker. No anonymous, upload, delete, or shell permissions."""
import argparse
import hashlib
import hmac
import json
import logging
import os
import pwd
import grp
import time
from .core import Store
from .updates import Updates

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--config',required=True)
    args=parser.parse_args()
    with open(args.config) as source: config=json.load(source)
    updates=Updates(Store(config['database']),config)
    from pyftpdlib.authorizers import DummyAuthorizer,AuthenticationFailed
    from pyftpdlib.handlers import FTPHandler
    from pyftpdlib.servers import FTPServer
    logging.getLogger('pyftpdlib').setLevel(logging.CRITICAL)
    server=None;previous=None;dropped=False;heartbeat=0
    while True:
        settings=updates.settings()
        if settings!=previous:
            if dropped: return  # OpenRC restarts the worker to rebind under root, then drop again.
            if server: server.close_all();server=None
            previous=settings
            if settings and settings.get('enabled'):
                current=dict(settings)
                class Authorizer(DummyAuthorizer):
                    def validate_authentication(self,username,password,handler):
                        salt,expected=current['password'].split(':')
                        actual=hashlib.pbkdf2_hmac('sha256',password.encode(),salt.encode(),310000).hex()
                        if username!=current['username'] or not hmac.compare_digest(actual,expected): raise AuthenticationFailed('Authentication failed.')
                auth=Authorizer();auth.add_user(current['username'],'unused',str(updates.root),perm='elr')
                class Handler(FTPHandler): pass
                Handler.authorizer=auth;Handler.passive_ports=range(current['passive_start'],current['passive_end']+1)
                if current.get('address'): Handler.masquerade_address=current['address']
                try:
                    server=FTPServer((config.get('ftp_listen_host','0.0.0.0'),current['port']),Handler)
                    if os.getuid()==0:
                        uid=pwd.getpwnam('serviceready').pw_uid
                        gid=grp.getgrnam('serviceready').gr_gid
                        os.setgroups([]);os.setgid(gid);os.setuid(uid);dropped=True
                    status='running'
                except OSError: status='Port unavailable; change the port or restart the addon worker.'
                with updates.store.connect() as db:
                    db.execute('CREATE TABLE IF NOT EXISTS addon_status(id TEXT PRIMARY KEY,status TEXT,at INTEGER)')
                    db.execute("INSERT OR REPLACE INTO addon_status VALUES('ftp-updates',?,?)",(status,int(time.time())))
        if settings and settings.get('enabled') and time.time()-heartbeat>3:
            with updates.store.connect() as db: db.execute("UPDATE addon_status SET at=? WHERE id='ftp-updates'",(int(time.time()),))
            heartbeat=time.time()
        if server: server.serve_forever(timeout=.5,blocking=False,handle_exit=False)
        else: time.sleep(.5)

if __name__=='__main__': main()
