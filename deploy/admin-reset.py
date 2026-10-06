#!/usr/bin/python3
"""Root-only console recovery; no dependency on a working portal or its venv."""
import argparse,getpass,grp,hashlib,json,os,pathlib,pwd,secrets,sqlite3,subprocess,time
from contextlib import closing

def reset(config,username,password,reset_factor=False):
    if os.geteuid()!=0:raise PermissionError('Root console access is required.')
    if not 12<=len(password)<=1024 or any(c in password for c in '\r\n\x00'):raise ValueError('Use 12–1024 characters without line breaks.')
    database=pathlib.Path(config['database'])
    if not database.is_file():raise ValueError('Portal account database is unavailable.')
    with closing(sqlite3.connect(database,timeout=15)) as db, db:
        db.row_factory=sqlite3.Row;db.execute('BEGIN IMMEDIATE')
        user=db.execute('SELECT id,username,password,role FROM users WHERE username=?',(username,)).fetchone()
        if not user or user['role']!='admin':raise ValueError('Choose an existing portal administrator account.')
        if user['password']=='external':raise ValueError('External passwords must be recovered through the identity provider.')
        if user['password']=='system' or config.get('auth_backend') in ('alpine','system'):
            entry=pwd.getpwnam(username);group=grp.getgrnam('serviceready-users')
            if entry.pw_uid<1000 or not (entry.pw_gid==group.gr_gid or username in group.gr_mem):raise ValueError('Only enrolled, non-system administrator accounts can be recovered.')
            subprocess.run(['/usr/sbin/chpasswd','-c','SHA512'],input=username+':'+password+'\n',text=True,check=True,timeout=15,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        else:
            salt=secrets.token_hex(16);digest=hashlib.pbkdf2_hmac('sha256',password.encode(),salt.encode(),310000).hex()
            db.execute('UPDATE users SET password=? WHERE id=?',(salt+':'+digest,user['id']))
        tables={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        for table in ('sessions','phones','factor_challenges','recovery_tokens'):
            if table in tables:db.execute('DELETE FROM '+table+' WHERE user_id=?',(user['id'],))
        if reset_factor and 'twofactor' in tables:db.execute('DELETE FROM twofactor WHERE user_id=?',(user['id'],))
        if 'audit' in tables:db.execute('INSERT INTO audit(at,user_id,action) VALUES(?,?,?)',(int(time.time()),user['id'],'Root console administrator password reset'+('; two-factor enrollment cleared' if reset_factor else '')))

def main():
    parser=argparse.ArgumentParser(description='Recover a portal administrator from the root Linux console.')
    parser.add_argument('username',nargs='?');parser.add_argument('--config',default='/etc/serviceready/config.json');parser.add_argument('--reset-twofactor',action='store_true')
    args=parser.parse_args()
    if os.geteuid()!=0:parser.exit(1,'Root console access is required. Use sudo serviceready-admin-reset.\n')
    try:
        config=json.loads(pathlib.Path(args.config).read_text())
        username=args.username
        if not username:
            with closing(sqlite3.connect(config['database'])) as db:names=[r[0] for r in db.execute("SELECT username FROM users WHERE role='admin' ORDER BY username")]
            print('Portal administrators: '+', '.join(names));username=input('Administrator username: ').strip()
        clear=args.reset_twofactor or input('Clear authenticator enrollment too? [y/N] ').strip().lower()=='y'
        print('This resets '+username+' and signs out all its portal sessions.'+(' Two-factor authentication will be cleared.' if clear else ''))
        if input('Type RESET to continue: ').strip()!='RESET':parser.exit(1,'Cancelled.\n')
        password=getpass.getpass('New password (12+ characters): ')
        if password!=getpass.getpass('Confirm new password: '):raise ValueError('Passwords differ.')
        reset(config,username,password,clear)
        print('Administrator password reset. Portal sessions revoked.'+(' Enroll an authenticator again after signing in.' if clear else ''))
    except (ValueError,OSError,KeyError,sqlite3.Error,subprocess.SubprocessError) as exc:parser.exit(1,'Recovery failed: '+str(exc)+'\n')
if __name__=='__main__':main()
