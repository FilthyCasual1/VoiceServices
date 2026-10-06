#!/usr/bin/env python3
"""Fixed Alpine update operations; invoked only by the peer-restricted root broker."""
import fcntl,json,os,pathlib,shutil,sqlite3,subprocess,sys,tempfile,time
ROOT=pathlib.Path('/opt/serviceready');STATE=pathlib.Path('/run/serviceready-accounts/maintenance.json')
def status(kind,state,message):
    temporary=STATE.with_suffix('.tmp');temporary.write_text(json.dumps({'kind':kind,'state':state,'message':message,'at':int(time.time())}));os.chmod(temporary,0o600);temporary.replace(STATE)
def run(args): subprocess.run(args,check=True,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=1800)
def clean_temp(folder):
    removed=0
    if folder.is_symlink():raise ValueError('Temporary directory must not be a symlink.')
    if folder.exists():
        for path in folder.iterdir():
            if not path.is_symlink() and path.is_file() and path.stat().st_mtime<time.time()-7*86400:
                fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW)
                try:
                    metadata=os.fstat(fd)
                    if metadata.st_mtime<time.time()-7*86400 and metadata.st_ino==path.lstat().st_ino:path.unlink();removed+=1
                finally:os.close(fd)
    return removed
def trim_logs(folder):
    trimmed=0
    if folder.is_symlink():raise ValueError('Log directory must not be a symlink.')
    for path in folder.glob('*.log'):
        if path.is_symlink() or not path.is_file():continue
        fd=os.open(path,os.O_RDWR|os.O_NOFOLLOW)
        with os.fdopen(fd,'r+b') as log:
            fcntl.flock(log,fcntl.LOCK_EX);size=os.fstat(log.fileno()).st_size
            if size>1024*1024:
                log.seek(-1024*1024,2);tail=log.read();log.seek(0);log.write(tail);log.truncate();trimmed+=1
    return trimmed
def main(kind):
    if kind not in ('os','insap','package-cache','portal-temp','portal-logs') or os.geteuid()!=0 or not pathlib.Path('/etc/alpine-release').is_file(): raise ValueError('Alpine root update worker required.')
    with open('/run/serviceready-accounts/maintenance.lock','w') as lock:
        try: fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError: return
        try:
            status(kind,'running','Preparing update')
            if kind=='os':
                status(kind,'running','Refreshing Alpine package indexes');run(['/sbin/apk','update'])
                status(kind,'running','Upgrading installed Alpine packages');run(['/sbin/apk','upgrade'])
                status(kind,'complete','Alpine packages updated. A restart may be needed for kernel or service changes; no reboot was performed.')
                return
            if kind=='package-cache':
                status(kind,'running','Cleaning unused Alpine package cache');run(['/sbin/apk','cache','clean'])
                status(kind,'complete','Unused package cache cleaned. Installed packages retained.');return
            if kind=='portal-temp':
                removed=clean_temp(pathlib.Path('/var/lib/serviceready/tmp'))
                status(kind,'complete',str(removed)+' portal temporary files older than seven days removed.');return
            if kind=='portal-logs':
                trimmed=trim_logs(pathlib.Path('/var/log/serviceready'))
                status(kind,'complete',str(trimmed)+' portal logs trimmed to their latest 1 MiB.');return
            source=ROOT/'source'
            for path in (ROOT,source,source/'.git'):
                meta=path.stat()
                if meta.st_uid!=0 or meta.st_mode&0o022 or path.is_symlink(): raise ValueError('Update checkout must be root-owned and not group/world writable.')
            if subprocess.check_output(['git','-C',str(source),'status','--porcelain'],text=True).strip(): raise ValueError('Update checkout has local edits; resolve them before updating.')
            remote=subprocess.check_output(['git','-C',str(source),'remote','get-url','origin'],text=True).strip()
            if remote!='https://github.com/FilthyCasual1/VoiceServices.git': raise ValueError('Update source is not the approved repository.')
            backup=pathlib.Path('/var/backups/serviceready')/str(int(time.time()));backup.mkdir(parents=True,mode=0o700);os.chmod(backup.parent,0o700)
            config=json.loads(pathlib.Path('/etc/serviceready/config.json').read_text());shutil.copy2('/etc/serviceready/config.json',backup/'config.json')
            with sqlite3.connect(config['database']) as original,sqlite3.connect(backup/'portal.sqlite') as copy: original.backup(copy)
            status(kind,'running','Fetching INSAP from the approved main branch');run(['git','-C',str(source),'fetch','origin','main'])
            run(['git','-C',str(source),'merge','--ff-only','origin/main'])
            run(['/sbin/apk','add','--no-cache','krb5','krb5-dev','build-base','python3-dev','libffi-dev','iproute2']);status(kind,'running','Installing INSAP and its dependencies');run([str(ROOT/'venv/bin/pip'),'install','--disable-pip-version-check',str(source)+'[identity]','aiosmtpd==1.4.6'])
            # Refresh installed official addons only; absent addons remain absent.
            script="""import json\nfrom pathlib import Path\nfrom voiceservices.web import App\napp=App(json.loads(Path('/etc/serviceready/config.json').read_text()))\nfor key in app.modules.approved:\n if (app.modules.root/key).exists():\n  from voiceservices.version import __version__\n  package=Path('/opt/serviceready/source/packages/addons')/__version__/(key+'-'+__version__+'.sraddon')\n  if not package.is_file(): raise RuntimeError('Matching addon package missing')\n  app.modules.change(key,False);app.modules.install(package.read_bytes())\n"""
            run([str(ROOT/'venv/bin/python'),'-c',script])
            for name in ('account-broker.py','maintenance-worker.py'): shutil.copy2(source/'deploy'/name,ROOT/name);os.chmod(ROOT/name,0o700)
            shutil.copy2(source/'deploy/serviceready-smtp.initd','/etc/init.d/serviceready-smtp');os.chmod('/etc/init.d/serviceready-smtp',0o755)
            run(['/sbin/rc-update','add','serviceready-smtp','default'])
            shutil.copy2(source/'deploy/serviceready-snmp.initd','/etc/init.d/serviceready-snmp');os.chmod('/etc/init.d/serviceready-snmp',0o755)
            run(['/sbin/rc-update','add','serviceready-snmp','default'])
            shutil.copy2(source/'deploy/serviceready-scheduler.initd','/etc/init.d/serviceready-scheduler');os.chmod('/etc/init.d/serviceready-scheduler',0o755)
            run(['/sbin/rc-update','add','serviceready-scheduler','default'])
            shutil.copy2(source/'deploy/serviceready-addresses.initd','/etc/init.d/serviceready-addresses');os.chmod('/etc/init.d/serviceready-addresses',0o755)
            run(['/sbin/rc-update','add','serviceready-addresses','default'])
            status(kind,'running','Restarting portal services')
            for service in ('serviceready','serviceready-ftp','serviceready-pxe','serviceready-smtp','serviceready-snmp','serviceready-scheduler','serviceready-addresses'): run(['/sbin/rc-service',service,'restart'])
            status(kind,'complete','INSAP updated. Database/configuration backup saved in '+str(backup)+'.')
            # Reload the broker last, after publishing the completion status.
            subprocess.Popen(['/sbin/rc-service','serviceready-accounts','restart'],stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)
        except Exception as exc:
            status(kind,'failed',str(exc) if isinstance(exc,ValueError) else 'Update failed. Inspect the host and retry; database/configuration backups are retained if created. No automatic rollback was performed.')
if __name__=='__main__': main(sys.argv[1])
