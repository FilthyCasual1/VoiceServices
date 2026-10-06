#!/usr/bin/env python3
"""Fixed Linux update operations; invoked only by the peer-restricted root broker."""
import fcntl,json,re,os,pathlib,shutil,sqlite3,subprocess,sys,tempfile,time
ROOT=pathlib.Path('/opt/serviceready');STATE=pathlib.Path('/run/serviceready-accounts/maintenance.json')
def status(kind,state,message):
    temporary=STATE.with_suffix('.tmp');temporary.write_text(json.dumps({'kind':kind,'state':state,'message':message,'at':time.time()}));os.chmod(temporary,0o600);temporary.replace(STATE)
UPDATE_LOG=pathlib.Path('/run/serviceready-accounts/update.log')
def run(args):
    fd=os.open(UPDATE_LOG,os.O_WRONLY|os.O_CREAT|os.O_APPEND|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'ab') as log:
        os.fchmod(log.fileno(),0o600);log.write(('\nRunning: '+' '.join(args)+'\n').encode());log.flush()
        subprocess.run(args,check=True,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,timeout=1800)
def restart_portal(rocky):
    command=lambda service: ['/usr/bin/systemctl','restart',service] if rocky else ['/sbin/rc-service',service,'restart']
    run(command('serviceready'))
    from urllib.request import build_opener,ProxyHandler
    from urllib.error import URLError
    config=json.loads(pathlib.Path('/etc/serviceready/config.json').read_text())
    host=config.get('listen_host','127.0.0.1')
    if host=='0.0.0.0':host='127.0.0.1'
    if host=='::':host='::1'
    if ':' in host:host='['+host+']'
    health_url='http://'+host+':'+str(int(config.get('listen_port',8080)))+'/healthz'
    opener=build_opener(ProxyHandler({}))
    for attempt in range(30):
        try:
            with opener.open(health_url,timeout=2) as response:
                if response.status==200:break
        except (OSError,URLError):pass
        time.sleep(1)
    else:raise ValueError('Updated portal did not respond to its health check. Expand Installer output for details.')
    warnings=[]
    for service in ('serviceready-ftp','serviceready-pxe','serviceready-smtp','serviceready-snmp','serviceready-scheduler','serviceready-addresses'):
        try:run(command(service))
        except (OSError,subprocess.SubprocessError):warnings.append(service)
    return warnings
TOOLS_LOG=pathlib.Path('/run/serviceready-accounts/vm-tools.log')
def tools_run(args):
    fd=os.open(TOOLS_LOG,os.O_WRONLY|os.O_CREAT|os.O_APPEND|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'ab') as log:
        os.fchmod(log.fileno(),0o600)
        log.write(('\nRunning: '+' '.join(args)+'\n').encode());log.flush()
        subprocess.run(args,check=True,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,timeout=1800)
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
REVIEW=pathlib.Path('/etc/serviceready/update-review.json')
def read_review():
    try:return json.loads(REVIEW.read_text())
    except FileNotFoundError:return {}
def write_review(value):
    temporary=REVIEW.with_suffix('.new');temporary.write_text(json.dumps(value));os.chmod(temporary,0o600);temporary.replace(REVIEW)
def stage_review(source):
    commit=subprocess.check_output(['git','-C',str(source),'rev-parse','origin/main'],text=True).strip()
    raw=subprocess.check_output(['git','-C',str(source),'show',commit+':voiceservices/version.py'],text=True)
    match=re.search(r"__version__ = '([0-9]+\.[0-9]+\.[0-9]+)'",raw)
    if not match:raise ValueError('The available release has invalid version metadata.')
    version=match[1];previous=read_review();declined=previous.get('declined_versions',[])
    current=subprocess.check_output([str(ROOT/'venv/bin/python'),'-I','-c',"from voiceservices.version import __version__; print(\"__version__ = '\"+__version__+\"'\")"],text=True)
    installed=re.search(r"__version__ = '([0-9]+\.[0-9]+\.[0-9]+)'",current)
    changelog=subprocess.check_output(['git','-C',str(source),'show',commit+':CHANGELOG.md'],text=True)
    if len(changelog)>262144:raise ValueError('Release changelog exceeds the review size limit.')
    state='declined' if version in declined else 'ready'
    if installed and tuple(map(int,version.split('.')))<=tuple(map(int,installed[1].split('.'))):state='current'
    value={'commit':commit,'version':version,'changelog':changelog,'state':state,'declined_versions':declined,'at':int(time.time())}
    write_review(value);return value

def main(kind,approved_commit=''):
    checking=kind=='insap-check'
    if checking:kind='insap'
    rocky=pathlib.Path('/etc/rocky-release').is_file()
    if kind not in ('os','insap','vmtools','vmtools-cd','cleanup','package-cache','portal-temp','portal-logs') or os.geteuid()!=0 or not (rocky or pathlib.Path('/etc/alpine-release').is_file()): raise ValueError('Supported Linux root update worker required.')
    with open('/run/serviceready-accounts/maintenance.lock','w') as lock:
        try: fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:
            status(kind,'failed','Another host operation is running. Wait for it to finish before starting an update.');return
        try:
            fd=os.open(UPDATE_LOG,os.O_WRONLY|os.O_CREAT|os.O_TRUNC|os.O_NOFOLLOW,0o600);os.fchmod(fd,0o600);os.close(fd)
            status(kind,'running','Preparing update')
            if kind=='cleanup':
                selected=json.loads(approved_commit)
                if not isinstance(selected,list) or not selected or len(selected)>3 or any(task not in ('package-cache','portal-temp','portal-logs') for task in selected):raise ValueError('Select valid cleanup tasks.')
                messages=[]
                for task in dict.fromkeys(selected):
                    status(kind,'running','Cleaning '+task)
                    if task=='package-cache':run(['/usr/bin/dnf','clean','packages'] if rocky else ['/sbin/apk','cache','clean']);messages.append('Package cache cleaned')
                    elif task=='portal-temp':
                        config=json.loads(pathlib.Path('/etc/serviceready/config.json').read_text())
                        removed=clean_temp(pathlib.Path(config.get('data_mount','/var/lib/serviceready'))/'tmp');messages.append(str(removed)+' old temporary files removed')
                    else:messages.append(str(trim_logs(pathlib.Path('/var/log/serviceready')))+' logs trimmed')
                status(kind,'complete','; '.join(messages)+'.');return
            if kind in ('vmtools','vmtools-cd'):
                fd=os.open(TOOLS_LOG,os.O_WRONLY|os.O_CREAT|os.O_TRUNC|os.O_NOFOLLOW,0o600);os.close(fd)
                import importlib.util
                file=ROOT/'vm-tools.py'
                if file.is_symlink() or file.stat().st_uid!=0 or file.stat().st_mode&0o022:raise ValueError('Guest-tools worker must be root-owned and not writable by other users.')
                spec=importlib.util.spec_from_file_location('vm_tools',file);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
                message=(module.install_cd if kind=='vmtools-cd' else module.update)(tools_run,lambda message:status(kind,'running',message))
                status(kind,'complete',message);return
            if kind=='os':
                status(kind,'running','Refreshing host package indexes');run(['/usr/bin/dnf','makecache'] if rocky else ['/sbin/apk','update'])
                status(kind,'running','Upgrading installed host packages');run(['/usr/bin/dnf','-y','upgrade'] if rocky else ['/sbin/apk','upgrade'])
                status(kind,'complete','Host packages updated. A restart may be needed for kernel or service changes; no reboot was performed.')
                return
            if kind=='package-cache':
                status(kind,'running','Cleaning host package cache');run(['/usr/bin/dnf','clean','packages'] if rocky else ['/sbin/apk','cache','clean'])
                status(kind,'complete','Unused package cache cleaned. Installed packages retained.');return
            if kind=='portal-temp':
                config=json.loads(pathlib.Path('/etc/serviceready/config.json').read_text())
                removed=clean_temp(pathlib.Path(config.get('data_mount','/var/lib/serviceready'))/'tmp')
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
            if checking:
                status(kind,'running','Fetching release metadata and changelog; installed version is unchanged')
                run(['git','-C',str(source),'fetch','origin','main'])
                review=stage_review(source)
                message={'ready':'Release '+review['version']+' is ready for review. Read the changelog and proceed or decline.', 'declined':'Release '+review['version']+' was declined; it will not install.', 'current':'INSAP is up to date.'}[review['state']]
                status(kind,'complete',message);return
            review=read_review()
            current=stage_review(source)
            if current['state']=='current':
                status(kind,'complete','INSAP is already up to date. No changes were needed.');return
            if not re.fullmatch('[a-f0-9]{40}',approved_commit) or review.get('commit')!=approved_commit or review.get('state')!='ready':raise ValueError('Fetch and approve the available INSAP release before installing.')
            backup=pathlib.Path('/var/backups/serviceready')/str(int(time.time()));backup.mkdir(parents=True,mode=0o700);os.chmod(backup.parent,0o700)
            config=json.loads(pathlib.Path('/etc/serviceready/config.json').read_text());shutil.copy2('/etc/serviceready/config.json',backup/'config.json')
            with sqlite3.connect(config['database']) as original,sqlite3.connect(backup/'portal.sqlite') as copy: original.backup(copy)
            review['state']='installing';write_review(review)
            status(kind,'running','Installing approved INSAP release '+review['version'])
            run(['git','-C',str(source),'merge','--ff-only',approved_commit])
            run(['/usr/bin/dnf','-y','install','krb5-devel','gcc','make','python3-devel','libffi-devel','iproute','chrony','smartmontools','mdadm','e2fsprogs','util-linux','NetworkManager'] if rocky else ['/sbin/apk','add','--no-cache','krb5','krb5-dev','build-base','python3-dev','libffi-dev','iproute2']);status(kind,'running','Installing INSAP and its dependencies');run([str(ROOT/'venv/bin/pip'),'install','--disable-pip-version-check',str(source)+'[identity]','aiosmtpd==1.4.6'])
            status(kind,'running','Restoring service-account runtime access and verifying imports')
            run(['/usr/bin/python3',str(source/'deploy/runtime-access.py')])
            # Stop the portal before repairing old root-private addon files.
            status(kind,'running','Refreshing installed addons; portal will reconnect shortly')
            run(['/usr/bin/systemctl','stop','serviceready'] if rocky else ['/sbin/rc-service','serviceready','stop'])
            import importlib.util,pwd
            spec=importlib.util.spec_from_file_location('runtime_access',source/'deploy/runtime-access.py');access=importlib.util.module_from_spec(spec);spec.loader.exec_module(access)
            access.normalise_addons(config)
            # Refresh installed official addons only; absent addons remain absent.
            script="""import json\nfrom pathlib import Path\nfrom voiceservices.web import App\napp=App(json.loads(Path('/etc/serviceready/config.json').read_text()))\nfor key in app.modules.approved:\n if (app.modules.root/key).exists():\n  from voiceservices.version import __version__\n  package=Path('/opt/serviceready/source/packages/addons')/__version__/(key+'-'+__version__+'.sraddon')\n  if not package.is_file(): raise RuntimeError('Matching addon package missing')\n  app.modules.install(package.read_bytes(),replace=True)\n"""
            actor=pwd.getpwnam('serviceready')
            subprocess.run([str(ROOT/'venv/bin/python'),'-I','-c',script],check=True,timeout=1800,cwd='/var/lib/serviceready',user=actor.pw_uid,group=actor.pw_gid,extra_groups=[actor.pw_gid])
            for name in ('account-broker.py','maintenance-worker.py','host-control.py','runtime-access.py','vm-tools.py'): shutil.copy2(source/'deploy'/name,ROOT/name);os.chmod(ROOT/name,0o700)
            shutil.copy2(source/'deploy/admin-reset.py','/usr/local/sbin/serviceready-admin-reset');os.chmod('/usr/local/sbin/serviceready-admin-reset',0o700)
            if rocky:
                for unit in (source/'deploy/systemd').glob('*.service'):
                    shutil.copy2(unit,pathlib.Path('/etc/systemd/system')/unit.name)
                    os.chmod(pathlib.Path('/etc/systemd/system')/unit.name,0o644)
                run(['/usr/bin/systemctl','daemon-reload'])
            else:
                for service in ('serviceready-smtp','serviceready-snmp','serviceready-scheduler','serviceready-addresses'):
                    shutil.copy2(source/'deploy'/(service+'.initd'),'/etc/init.d/'+service);os.chmod('/etc/init.d/'+service,0o755)
                    run(['/sbin/rc-update','add',service,'default'])
            status(kind,'running','Restarting portal services')
            warnings=restart_portal(rocky)
            review['state']='installed';write_review(review)
            status(kind,'complete','INSAP and installed addons updated successfully. Database/configuration backup saved in '+str(backup)+'.'+(' Auxiliary services need attention: '+', '.join(warnings)+'. See Installer output.' if warnings else ''))
            # Reload the broker last, after publishing the completion status.
            subprocess.Popen(['/usr/bin/systemctl','restart','serviceready-accounts'] if rocky else ['/sbin/rc-service','serviceready-accounts','restart'],stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)
        except Exception as exc:
            if kind=='insap':
                if not checking:
                    review=read_review()
                    if review.get('state')=='installing':review['state']='failed';write_review(review)
                subprocess.run(['/usr/bin/systemctl','start','serviceready'] if rocky else ['/sbin/rc-service','serviceready','start'],check=False,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            if kind in ('vmtools','vmtools-cd') and isinstance(exc,subprocess.CalledProcessError):
                status(kind,'failed','Guest tools installation failed. Expand Installer output below for the actual error. Kernel dependencies must match the running kernel. No reboot was performed.');return
            if kind in ('vmtools','vmtools-cd'):
                status(kind,'failed','Guest tools operation failed: '+str(exc)+'. No reboot was performed.');return
            status(kind,'failed',str(exc) if isinstance(exc,ValueError) else 'Update failed: '+str(exc)+'. Expand Installer output for details; backups are retained if created. No automatic rollback was performed.')
if __name__=='__main__': main(sys.argv[1],sys.argv[2] if len(sys.argv)>2 else '')
