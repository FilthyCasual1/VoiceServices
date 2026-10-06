#!/usr/bin/env python3
"""Fixed, root-only Rocky host operations. Never accepts shell commands."""
import sqlite3,base64,hashlib,ipaddress,json,os,pathlib,pwd,subprocess,sys,time,fcntl,shutil
CONFIG=pathlib.Path('/etc/serviceready/config.json')
STATE=pathlib.Path('/run/serviceready-accounts/host-job.json')
MOUNT=pathlib.Path('/srv/serviceready-data')
def run(args):return subprocess.check_output(args,text=True,stderr=subprocess.STDOUT).strip()
def disks():
 rows=json.loads(run(['lsblk','--json','--bytes','-o','PATH,TYPE,SIZE,MODEL,SERIAL,RO,FSTYPE,UUID,MOUNTPOINTS,PTTYPE']))['blockdevices']
 def system_disk(node):
  mounts=node.get('mountpoints') or []
  if any(m in ('/', '/boot', '/boot/efi', '/usr', '/var') for m in mounts):return True
  return any(system_disk(child) for child in node.get('children') or [])
 result=[]
 for d in rows:
  if d['type']!='disk' or system_disk(d):continue
  d['eligible']=d['type']=='disk' and not d.get('ro') and not any(d.get(k) for k in ('children','fstype','pttype')) and not any(d.get('mountpoints') or [])
  d['fingerprint']=hashlib.sha256(json.dumps(d,sort_keys=True).encode()).hexdigest()
  result.append(d)
 return result

def snapshot(section='storage'):
 cfg=json.loads(CONFIG.read_text())
 try:state=json.loads(STATE.read_text())
 except FileNotFoundError:state={'state':'idle','message':'No host configuration task started.'}
 if state.get('state') in ('running','pending') and state.get('pid') and not pathlib.Path('/proc/'+str(state['pid'])).exists():state={'state':'failed','message':'The host operation was interrupted. Inspect the host before retrying.'}
 result={'storage_available':bool(cfg.get('data_mount') and os.path.ismount(cfg['data_mount'])),'job':state,'storage':cfg.get('data_mount','Not configured'),'errors':[],'disks':[]}
 if section=='storage':
  try:result['disks']=disks()
  except (OSError,ValueError,subprocess.SubprocessError) as exc:result['errors'].append('Disk discovery unavailable: '+str(exc)[-400:])
 else:
  for key,args in [('timezone',['timedatectl','show','--property=Timezone','--value']),('hostname',['hostname']),('connections',['nmcli','-t','-f','NAME,UUID,DEVICE','connection','show','--active']),('time',['timedatectl','status'])]:
   try:
    result[key]=subprocess.check_output(args,text=True,stderr=subprocess.STDOUT,timeout=3).strip()
    if key=='connections':result[key]='\n'.join(line for line in result[key].splitlines() if line.rsplit(':',1)[-1]!='lo')
   except (OSError,subprocess.SubprocessError) as exc:
    result[key]='Unavailable';result['errors'].append(key+': '+str(exc)[-400:])
 return result
def validate(p):
 kind=p.get('kind')
 if kind=='storage':
  d=next((d for d in disks() if d['path']==p.get('disk')),None)
  if not d or not d['eligible'] or d['fingerprint']!=p.get('fingerprint'):raise ValueError('Disk is in use, contains data, or has changed. Reload the disk list.')
  if p.get('confirm')!='FORMAT '+d['path']:raise ValueError('Type FORMAT followed by the exact disk path.')
  if json.loads(run(['wipefs','--no-act','--json',d['path']])).get('signatures'):raise ValueError('Disk has existing signatures. Only blank disks are accepted.')
  cfg=json.loads(CONFIG.read_text())
  if cfg.get('data_mount') and os.path.ismount(cfg['data_mount']):raise ValueError('An upload disk is already mounted. Detach it before configuring a replacement.')
  if MOUNT.exists() and any(MOUNT.iterdir()):raise ValueError('The upload mount directory is not empty.')
  needed=0
  for name in ('downloads','updates','pxe','branding'):
   source=pathlib.Path(cfg.get(name+'_directory',str(pathlib.Path(cfg['database']).parent/name)))
   if source.exists():
    if not source.resolve().is_relative_to(pathlib.Path('/var/lib/serviceready')) or source.is_symlink() or any(f.is_symlink() for f in source.rglob('*')):raise ValueError('Repository requires manual migration: unexpected path or symlink.')
    needed+=sum(f.stat().st_size for f in source.rglob('*') if f.is_file())
  if needed+1024**3>int(d['size'])*.9:raise ValueError('This disk is too small for existing uploads and migration headroom.')
 elif kind=='network':
  import re
  if not re.fullmatch(r'[a-fA-F0-9-]{36}',p.get('connection','')):raise ValueError('Select an active connection UUID.')
  if p.get('mode') not in ('auto','manual'):raise ValueError('Choose DHCP or static IPv4.')
  if p['mode']=='manual':ipaddress.IPv4Interface(p['address']);ipaddress.IPv4Address(p['gateway'])
  for value in p.get('dns','').split():ipaddress.ip_address(value)
  if p.get('hostname') and not re.fullmatch(r'(?=.{1,253}$)[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?',p['hostname']):raise ValueError('Invalid hostname.')
 elif kind=='power':
  if p.get('operation') not in ('restart','shutdown') or p.get('confirm')!=p.get('operation'):raise ValueError('Choose and confirm restart or shutdown.')
 elif kind=='timezone':
  from zoneinfo import ZoneInfo,ZoneInfoNotFoundError
  try:ZoneInfo(p.get('timezone',''))
  except (ValueError,ZoneInfoNotFoundError):raise ValueError('Choose a valid IANA time zone.')
 elif kind=='ntp':
  import re
  servers=p.get('servers','').split()
  if not servers or len(servers)>8 or any(not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9.:-]{0,252}',s) for s in servers):raise ValueError('Enter up to eight NTP hostnames or addresses.')
 else:raise ValueError('Unknown host operation.')
def status(state,message):
 temporary=STATE.with_suffix('.new');temporary.write_text(json.dumps({'state':state,'message':message,'at':int(time.time()),'pid':os.getpid()}));os.chmod(temporary,0o600);temporary.replace(STATE)
def main(p):
 if os.geteuid()!=0:raise ValueError('Root host worker required.')
 with open(STATE.parent/'maintenance.lock','w') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX | (fcntl.LOCK_NB if p.get('kind')=='power' else 0))
  try:
   validate(p);status('running','Preparing '+p['kind'])
   if p['kind']=='power':
    operation=p['operation'];command='reboot' if operation=='restart' else 'poweroff'
    run(['systemd-run','--unit=serviceready-power','--on-active=10s','/usr/bin/systemctl',command])
    status('complete','Host '+operation+' scheduled in 10 seconds. The portal will disconnect.')
   elif p['kind']=='storage':
    disk=p['disk'];run(['mkfs.ext4','-F','-L','ServiceReadyData',disk]);uuid=run(['blkid','-s','UUID','-o','value',disk]);MOUNT.mkdir(parents=True,exist_ok=True)
    run(['mount','-t','ext4',disk,str(MOUNT)])
    cfg=json.loads(CONFIG.read_text());uid=pwd.getpwnam('serviceready').pw_uid;gid=pwd.getpwnam('serviceready').pw_gid
    services=['serviceready','serviceready-ftp','serviceready-pxe','serviceready-smtp','serviceready-snmp','serviceready-scheduler']
    status('running','Moving uploaded repositories onto the new disk')
    for service in services:run(['systemctl','stop',service])
    try:
     old=[]
     replacing=bool(cfg.get('data_mount'))
     for name in ('downloads','updates','pxe'):
      source=pathlib.Path(cfg.get(name+'_directory',str(pathlib.Path(cfg['database']).parent/name)));target=MOUNT/name
      if source.exists() and not replacing:
       if source.is_symlink() or any(f.is_symlink() for f in source.rglob('*')):raise ValueError('Repository contains symlinks; migration stopped.')
       shutil.copytree(source,target);old.append(source)
      else:target.mkdir()
      for folder,dirs,files in os.walk(target):
       os.chown(folder,uid,gid)
       for file in files:os.chown(pathlib.Path(folder)/file,uid,gid)
      cfg[name+'_directory']=str(target)
     source=pathlib.Path(cfg['database']).parent/'branding'
     if source.exists() and not replacing:
      if source.is_symlink() or any(f.is_symlink() for f in source.rglob('*')):raise ValueError('Branding directory contains symlinks.')
      shutil.copytree(source,MOUNT/'branding');old.append(source)
      for f in (MOUNT/'branding').rglob('*'):os.chown(f,uid,gid)
      os.chown(MOUNT/'branding',uid,gid)
     photos=MOUNT/'photos';photos.mkdir();os.chown(photos,uid,gid)
     with sqlite3.connect(cfg['database']) as db:
      if db.execute("SELECT 1 FROM sqlite_master WHERE name='account_photos'").fetchone():
       for user,image in db.execute('SELECT user_id,image FROM account_photos'):
        if not image:continue
        f=photos/str(user);f.write_bytes(image);os.chown(f,uid,gid);os.chmod(f,0o600)
     temp=MOUNT/'tmp';temp.mkdir();os.chown(temp,uid,gid);os.chmod(temp,0o700)
     cfg.update(data_mount=str(MOUNT),data_disk_uuid=uuid)
     with open('/etc/fstab','a') as f:f.write('\n# ServiceReady uploaded data\nUUID='+uuid+' '+str(MOUNT)+' ext4 defaults,nofail,x-systemd.device-timeout=15s 0 2\n')
     meta=CONFIG.stat();replacement=CONFIG.with_suffix('.new');replacement.write_text(json.dumps(cfg,indent=2)+'\n');os.chown(replacement,meta.st_uid,meta.st_gid);os.chmod(replacement,meta.st_mode&0o777);replacement.replace(CONFIG)
     with sqlite3.connect(cfg['database']) as db:
      if db.execute("SELECT 1 FROM sqlite_master WHERE name='account_photos'").fetchone():db.execute("UPDATE account_photos SET image=X''")
     with sqlite3.connect(cfg['database']) as db:db.execute('VACUUM')
     for source in old:shutil.rmtree(source)
    finally:
     for service in services:run(['systemctl','start',service])
    status('complete','Upload repositories moved to '+str(MOUNT)+'. Configuration and account metadata remain on the boot disk.')
   elif p['kind']=='timezone':
    run(['timedatectl','set-timezone',p['timezone']]);status('complete','Host time zone set to '+p['timezone']+'.')
   elif p['kind']=='ntp':
    file=pathlib.Path('/etc/chrony.conf');old=file.read_text();backup=file.with_suffix('.serviceready-backup');backup.write_text(old)
    text='\n'.join(line for line in old.splitlines() if not line.strip().startswith(('server ','pool ')))+'\n'+''.join('server '+s+' iburst\n' for s in p['servers'].split())
    file.write_text(text)
    try:run(['chronyd','-p','-f',str(file)]);run(['systemctl','enable','--now','chronyd']);run(['systemctl','restart','chronyd'])
    except Exception:file.write_text(old);raise
    status('complete','NTP sources saved and chrony restarted.')
   else:
    # Keep the original profile as a timed rollback until explicitly confirmed.
    original=p['connection'];name='serviceready-rollback-'+str(int(time.time()))
    run(['nmcli','connection','clone',original,name]);rollback=run(['nmcli','-g','connection.uuid','connection','show',name])
    run(['nmcli','connection','modify',rollback,'connection.autoconnect','no'])
    args=['nmcli','connection','modify',original,'ipv4.method',p['mode'],'ipv4.addresses',p.get('address','') if p['mode']=='manual' else '', 'ipv4.gateway',p.get('gateway','') if p['mode']=='manual' else '', 'ipv4.dns',','.join(p.get('dns','').split()),'ipv4.ignore-auto-dns','yes' if p.get('dns') else 'no']
    oldhost=run(['hostname']);marker=STATE.with_suffix('.confirmed');marker.unlink(missing_ok=True)
    try:
     run(args)
     if p.get('hostname'):run(['hostnamectl','set-hostname',p['hostname']])
     run(['nmcli','connection','up',original]);status('pending','Network changed. Reconnect at the new address and confirm within 90 seconds or settings will roll back.')
     deadline=time.monotonic()+90
     while time.monotonic()<deadline and not marker.exists():time.sleep(1)
     if marker.exists():run(['nmcli','connection','delete',rollback]);status('complete','Network settings confirmed.')
     else:
      run(['nmcli','connection','modify',original,'connection.autoconnect','no']);run(['nmcli','connection','modify',rollback,'connection.autoconnect','yes']);run(['nmcli','connection','up',rollback]);run(['hostnamectl','set-hostname',oldhost]);status('rolled-back','Network settings restored using '+name+'.')
    except Exception:
     run(['nmcli','connection','modify',original,'connection.autoconnect','no']);run(['nmcli','connection','modify',rollback,'connection.autoconnect','yes'])
     run(['nmcli','connection','up',rollback]);run(['hostnamectl','set-hostname',oldhost]);raise
  except Exception as exc:status('failed',str(exc)[-1000:])
if __name__=='__main__':main(json.loads(base64.b64decode(sys.argv[1])))
