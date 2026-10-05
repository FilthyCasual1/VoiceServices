import html,json,time
from urllib.parse import urlencode,urlsplit
E=lambda value:html.escape(str(value),quote=True)
def admin_render(app,user,services):
    csrf='<input type="hidden" name="csrf" value="'+E(user["csrf"])+'">'
    content=""
    settings=app.updates.settings()
    if settings is None: content+='<p><a href="/admin/addons">Install the FTP update addon</a> to use this page.</p>'
    else:
        status='Disabled'
        if settings.get('enabled'):
            status='Enabled; worker not yet verified'
            with app.store.connect() as db:
                exists=db.execute("SELECT 1 FROM sqlite_master WHERE name='addon_status'").fetchone()
                if exists:
                    row=db.execute("SELECT status,at FROM addon_status WHERE id='ftp-updates'").fetchone()
                    if row and row['at']>time.time()-10: status=row['status']
        content+='<p class="notice">'+E(status)+'. Applications pull files from this repository; installation and reboot remain in their native upgrade screen. FTP is unencrypted; restrict it to your testbed network.</p><div class="panel"><form method="post">'+csrf
        for key,label,kind in [('username','FTP username','text'),('port','Control port','number'),('passive_start','First passive port','number'),('passive_end','Last passive port','number'),('address','Advertised address (optional)','text')]:
            content+='<label>'+label+'</label><input name="'+key+'" type="'+kind+'" value="'+E(settings.get(key,''))+'">'
        content+='<label>FTP password (leave blank to retain)</label><input name="ftp_password" type="password" autocomplete="new-password"><label>FTP server</label><select name="enabled"><option value="no">Disabled</option><option value="yes"'+(' selected' if settings.get('enabled') else '')+'>Enabled</option></select><br><button>Save FTP settings</button></form></div>'
        host=settings.get('address') or urlsplit(app.base).hostname
        content+='<h2>Upgrade source details</h2><div class="panel">Server: '+E(host)+'<br>Port: '+E(settings['port'])+'<br>Directory: /<br>Username: '+E(settings['username'])+'<p>Use Remote Filesystem with FTP in your application upgrade workflow. Supply the password configured above. Use the uploaded filename listed below.</p></div>'
        content+='<h2>Upload an update file</h2><div class="panel"><form action="/admin/updates/upload" method="post" enctype="multipart/form-data">'+csrf+'<label for="update-file">Package file</label><input id="update-file" name="file" type="file" required><br><button>Upload file</button></form><p>Maximum file size: '+E(app.updates.limit//1024**2)+' MiB. Existing filenames are never overwritten.</p></div><table><tr><th>Filename</th><th>Bytes</th><th>SHA-256</th></tr>'
        for row in app.updates.files(): content+='<tr><td>'+E(row['name'])+'</td><td>'+str(row['size'])+'</td><td><code>'+E(row['sha256'])+'</code></td></tr>'
        content+='</table>'
    return content

def admin_change(app,data,services):
    app.updates.configure(data);note='FTP settings saved. The installed worker applies changes automatically.'
    return locals().get("note","Settings saved.")

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
from voiceservices.core import Store
from voiceservices.updates import Updates

def worker_main():
    parser=argparse.ArgumentParser();parser.add_argument('--config',required=True)
    args=parser.parse_args()
    with open(args.config) as source: config=json.load(source)
    updates=Updates(Store(config['database']),config)
    from pyftpdlib.authorizers import DummyAuthorizer,AuthenticationFailed
    from pyftpdlib.handlers import FTPHandler
    from pyftpdlib.servers import FTPServer
    logging.getLogger('pyftpdlib').setLevel(logging.CRITICAL)
    server=None;previous=None;dropped=False;heartbeat=0
    while updates.modules.installed('ftp-updates'):
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



    if server: server.close_all()
