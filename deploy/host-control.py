#!/usr/bin/env python3
"""Fixed, root-only Rocky host operations. Never accepts shell commands."""
import sqlite3,base64,hashlib,ipaddress,json,os,pathlib,pwd,subprocess,sys,time,fcntl,shutil
CONFIG=pathlib.Path('/etc/serviceready/config.json')
STATE=pathlib.Path('/run/serviceready-accounts/host-job.json')
MOUNT=pathlib.Path('/srv/serviceready-data')
FSTAB=pathlib.Path('/etc/fstab')
MDADM=pathlib.Path('/etc/mdadm.conf')
ARRAY='/dev/md/serviceready-data'
SMART_CACHE=pathlib.Path('/run/serviceready-accounts/smart.json')
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
  d['raid_eligible']=not d.get('ro') and not d.get('children') and not any(d.get('mountpoints') or [])
  d['fingerprint']=hashlib.sha256(json.dumps(d,sort_keys=True).encode()).hexdigest()
  result.append(d)
 return result

def virtual_machine():
 try:
  provider=subprocess.check_output(['systemd-detect-virt','--vm'],text=True,stderr=subprocess.DEVNULL,timeout=2).strip()
  if provider and provider!='none':return provider
 except (OSError,subprocess.SubprocessError):pass
 try:
  description=' '.join(pathlib.Path('/sys/class/dmi/id/'+name).read_text().lower() for name in ('product_name','sys_vendor'))
  for provider,words in [('virtualbox',('virtualbox','innotek')),('vmware',('vmware',)),('kvm',('kvm','qemu')),('hyper-v',('virtual machine',)),('xen',('xen',))]:
   if any(word in description for word in words):return provider
 except OSError:pass
 return ''

def smart_health(disk):
 result={'disk':disk['path'],'identity':disk.get('serial') or disk['path'],'state':'Unavailable','message':'SMART data is not exposed by this disk or hypervisor.'}
 if not shutil.which('smartctl'):result['message']='SMART tools are not installed. Update INSAP host integration.';return result
 try:
  process=subprocess.run(['smartctl','--json','--health','--attributes','--info',disk['path']],capture_output=True,text=True,timeout=3)
  data=json.loads(process.stdout)
  result['identity']=data.get('serial_number') or result['identity']
  health=data.get('smart_status',{}).get('passed')
  if health is not None:
   result.update(state='Healthy' if health else 'Failed',message='SMART overall health passed.' if health else 'SMART reports a disk failure. Back up data and replace the disk.')
  result['temperature']=data.get('temperature',{}).get('current');result['hours']=data.get('power_on_time',{}).get('hours')
  warnings=[]
  for attribute in data.get('ata_smart_attributes',{}).get('table',[]):
   if attribute.get('id') in (5,197,198) and attribute.get('raw',{}).get('value',0)>0:warnings.append(attribute.get('name','Sector errors')+': '+str(attribute['raw']['value']))
  nvme=data.get('nvme_smart_health_information_log',{})
  if nvme.get('critical_warning',0):result.update(state='Failed',message='NVMe reports a critical health warning.')
  if nvme.get('media_errors',0):warnings.append('NVMe media errors: '+str(nvme['media_errors']))
  if warnings:
   if result['state']=='Healthy':result['state']='Caution'
   result['message']+=' '+'; '.join(warnings)
 except (OSError,ValueError,subprocess.SubprocessError):result['message']='Unable to read SMART data from this device.'
 return result
def smart_disks(devices):
 fingerprint=hashlib.sha256(json.dumps(devices,sort_keys=True).encode()).hexdigest()
 try:
  cached=json.loads(SMART_CACHE.read_text())
  if cached.get('fingerprint')==fingerprint and time.time()-cached.get('at',0)<60:return cached['disks']
 except (OSError,ValueError):pass
 results=[smart_health(disk) for disk in devices[:8]]
 try:
  temporary=SMART_CACHE.with_suffix('.new');temporary.write_text(json.dumps({'at':time.time(),'fingerprint':fingerprint,'disks':results}));os.chmod(temporary,0o600);temporary.replace(SMART_CACHE)
 except OSError:pass
 return results

def snapshot(section='storage'):
 cfg=json.loads(CONFIG.read_text())
 try:state=json.loads(STATE.read_text())
 except FileNotFoundError:state={'state':'idle','message':'No host configuration task started.'}
 if state.get('state') in ('running','pending') and state.get('pid') and not pathlib.Path('/proc/'+str(state['pid'])).exists():state={'state':'failed','message':'The host operation was interrupted. Inspect the host before retrying.'}
 result={'storage_available':bool(cfg.get('data_mount') and os.path.ismount(cfg['data_mount'])),'job':state,'storage':cfg.get('data_mount','Not configured'),'errors':[],'disks':[]}
 if section=='storage':
  result['vm_provider']=virtual_machine()
  result['raid']=cfg.get('data_raid','')
  if cfg.get('data_raid'):
   try:result['raid_status']=run(['mdadm','--detail',cfg.get('data_array',ARRAY)])
   except (OSError,subprocess.SubprocessError):result['errors'].append('Upload RAID array is unavailable or degraded. Check the member disks.')
  try:
   result['disks']=disks()
   result['smart']=smart_disks([disk for disk in result['disks'] if disk['path'] in cfg.get('data_members',[]) or (cfg.get('data_disk_uuid') and disk.get('uuid')==cfg['data_disk_uuid'])])
   for disk in result['disks']:disk['reformat']=bool(cfg.get('data_disk_uuid') and disk.get('uuid')==cfg['data_disk_uuid'] and disk.get('fstype')=='ext4' and not disk.get('children') and disk.get('mountpoints')==[str(MOUNT)] and cfg.get('data_mount')==str(MOUNT) and not disk.get('ro'))
  except (OSError,ValueError,subprocess.SubprocessError) as exc:result['errors'].append('Disk discovery unavailable: '+str(exc)[-400:])
 else:
  for key,args in [('timezone',['timedatectl','show','--property=Timezone','--value']),('hostname',['hostname']),('connections',['nmcli','-t','-f','NAME,UUID,DEVICE','connection','show','--active']),('time',['timedatectl','status'])]:
   try:
    result[key]=subprocess.check_output(args,text=True,stderr=subprocess.STDOUT,timeout=3).strip()
    if key=='connections':result[key]='\n'.join(line for line in result[key].splitlines() if line.rsplit(':',1)[-1]!='lo')
   except (OSError,subprocess.SubprocessError) as exc:
    result[key]='Unavailable';result['errors'].append(key+': '+str(exc)[-400:])
 return result
def validate(p,raid_member=False):
 kind=p.get('kind')
 if kind=='storage-raid':
  if p.get('raid_mode') not in ('mirror','stripe'):raise ValueError('Choose mirrored or combined storage.')
  members=p.get('members')
  if not isinstance(members,list) or not 2<=len(members)<=8 or any(not isinstance(d,dict) for d in members) or len({d.get('disk') for d in members})!=len(members):raise ValueError('Select two to eight distinct blank disks for software RAID.')
  if p.get('confirm')!='CREATE ARRAY' or p.get('erase_confirm')!='yes':raise ValueError('Confirm erasing all selected disks and type CREATE ARRAY.')
  if pathlib.Path(ARRAY).exists():raise ValueError('An upload RAID array already exists.')
  if not shutil.which('mdadm'):raise ValueError('Update host integration to install software RAID support first.')
  for member in members:validate(dict(member,kind='storage',confirm='FORMAT '+member.get('disk','')),raid_member=True)
 elif kind=='storage':
  d=next((d for d in disks() if d['path']==p.get('disk')),None)
  if not d or not (d.get('raid_eligible',d['eligible']) if raid_member or p.get('erase_confirm')=='yes' else d['eligible']) or d['fingerprint']!=p.get('fingerprint'):raise ValueError('Disk is in use, contains data, or has changed. Reload the disk list.')
  if p.get('confirm')!='FORMAT '+d['path']:raise ValueError('Type FORMAT followed by the exact disk path.')
  if not raid_member and p.get('erase_confirm')!='yes' and json.loads(run(['wipefs','--no-act','--json',d['path']])).get('signatures'):raise ValueError('Disk has existing signatures. Only blank disks are accepted.')
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
 elif kind=='storage-reset':
  cfg=json.loads(CONFIG.read_text());d=next((d for d in disks() if d['path']==p.get('disk')),None)
  if not d or d['fingerprint']!=p.get('fingerprint') or d.get('ro') or d.get('children') or d.get('fstype')!='ext4' or d.get('uuid')!=cfg.get('data_disk_uuid') or not cfg.get('data_disk_uuid') or cfg.get('data_mount')!=str(MOUNT) or d.get('mountpoints')!=[str(MOUNT)]:raise ValueError('Only the current, unchanged upload data disk can be reformatted. Reload storage.')
  if p.get('confirm')!='ERASE '+d['path'] or p.get('erase_confirm')!='yes':raise ValueError('Confirm permanent data loss and type ERASE followed by the exact disk path.')
  if run(['findmnt','-n','-o','UUID','--target',str(MOUNT)])!=cfg['data_disk_uuid']:raise ValueError('Upload disk identity changed. Reload storage.')
 elif kind=='storage-maintenance':
  if virtual_machine():raise ValueError('TRIM and defragmentation are disabled on virtual machines.')
  cfg=json.loads(CONFIG.read_text())
  if p.get('operation') not in ('trim','defrag'):raise ValueError('Choose TRIM or fragmentation check.')
  if cfg.get('data_mount')!=str(MOUNT) or not cfg.get('data_disk_uuid') or not os.path.ismount(MOUNT) or run(['findmnt','-n','-o','UUID','--target',str(MOUNT)])!=cfg['data_disk_uuid']:raise ValueError('The configured upload disk is unavailable or changed.')
  if p.get('operation')=='defrag' and run(['findmnt','-n','-o','FSTYPE','--target',str(MOUNT)])!='ext4':raise ValueError('Fragmentation checks currently support ext4 upload volumes only.')
 elif kind=='network':
  import re
  if not re.fullmatch(r'[a-fA-F0-9-]{36}',p.get('connection','')):raise ValueError('Select an active connection UUID.')
  if p.get('mode') not in ('keep','auto','manual','disabled'):raise ValueError('Choose DHCP or static IPv4.')
  if p['mode']=='manual':
   ipaddress.IPv4Interface(p['address'])
   if p.get('gateway'):ipaddress.IPv4Address(p['gateway'])
  for value in p.get('dns','').split():ipaddress.IPv4Address(value)
  if p.get('mode')=='disabled' and p.get('ipv6_mode')=='disabled':raise ValueError('Keep at least one IP protocol enabled.')
  if p.get('ipv6_mode'):
   if p['ipv6_mode'] not in ('auto','dhcp','manual','disabled'):raise ValueError('Choose an IPv6 address method.')
   if p['ipv6_mode']=='manual':
    ipaddress.IPv6Interface(p.get('ipv6_address',''))
    if p.get('ipv6_gateway'):ipaddress.IPv6Address(p['ipv6_gateway'])
   for value in p.get('ipv6_dns','').split():ipaddress.IPv6Address(value)
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
def reset_storage(p):
 cfg=json.loads(CONFIG.read_text());old_uuid=cfg['data_disk_uuid']
 services=['serviceready','serviceready-ftp','serviceready-pxe','serviceready-smtp','serviceready-snmp','serviceready-scheduler']
 stopped=[]
 try:
  status('running','Stopping upload services before reformatting the data disk')
  for service in services:
   run(['systemctl','stop',service]);stopped.append(service)
  validate(p)
  run(['umount',str(MOUNT)])
  # Never use force/lazy unmount: a busy volume must remain intact.
  run(['mkfs.ext4','-F','-L','ServiceReadyData',p['disk']])
  uuid=run(['blkid','-s','UUID','-o','value',p['disk']])
  run(['mount','-t','ext4',p['disk'],str(MOUNT)])
  account=pwd.getpwnam('serviceready')
  for name in ('downloads','updates','pxe','branding','photos','tmp'):
   folder=MOUNT/name;folder.mkdir();os.chown(folder,account.pw_uid,account.pw_gid);os.chmod(folder,0o700 if name=='tmp' else 0o755)
  for name in ('downloads','updates','pxe'):cfg[name+'_directory']=str(MOUNT/name)
  cfg['data_disk_uuid']=uuid
  # Replace the old mount entry rather than accumulating stale UUID entries.
  lines=[line for line in FSTAB.read_text().splitlines() if not (len(line.split())>1 and (line.split()[0]=='UUID='+old_uuid or line.split()[1]==str(MOUNT)))]
  FSTAB.write_text('\n'.join(lines)+'\nUUID='+uuid+' '+str(MOUNT)+' ext4 defaults,nofail,x-systemd.device-timeout=15s 0 2\n')
  meta=CONFIG.stat();replacement=CONFIG.with_suffix('.new');replacement.write_text(json.dumps(cfg,indent=2)+'\n');os.chown(replacement,meta.st_uid,meta.st_gid);os.chmod(replacement,meta.st_mode&0o777);replacement.replace(CONFIG)
  with sqlite3.connect(cfg['database']) as db:
   for table in ('downloads_files','updates_files','pxe_files','account_photos'):
    if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(table,)).fetchone():db.execute('DELETE FROM '+table)
   if db.execute("SELECT 1 FROM sqlite_master WHERE name='downloads_details'").fetchone():db.execute("DELETE FROM downloads_details WHERE kind='file'")
  status('complete','Upload disk reformatted. Uploaded files, images and profile photos were erased; accounts, settings, download links and categories were retained.')
 finally:
  for service in stopped:run(['systemctl','start',service])

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
   elif p['kind']=='storage-maintenance':
    if p['operation']=='trim':
     if not shutil.which('fstrim'):raise ValueError('TRIM tools are unavailable. Update host integration.')
     try:message=run(['fstrim','--verbose',str(MOUNT)])
     except subprocess.CalledProcessError:raise ValueError('TRIM is unavailable for this upload volume or is not passed through by the disk, RAID layer or hypervisor.') from None
     status('complete','Upload volume TRIM completed. '+message)
    else:
     import re
     if not shutil.which('e4defrag'):raise ValueError('ext4 defragmentation tools are unavailable on this host.')
     message=run(['e4defrag','-c',str(MOUNT)]);score=re.search(r'Fragmentation score\s+(\d+)',message)
     if not score:raise ValueError('The fragmentation score could not be determined; no defragmentation was performed.')
     if int(score[1])<55:status('complete','Upload fragmentation score '+score[1]+': no defragmentation needed.')
     else:
      status('running','Defragmenting the upload volume (score '+score[1]+')');run(['e4defrag',str(MOUNT)]);status('complete','Upload volume defragmentation completed.')
   elif p['kind']=='storage-reset':
    reset_storage(p)
   elif p['kind'] in ('storage','storage-raid'):
    if p['kind']=='storage-raid':
     status('running','Creating upload disk array')
     for member in p['members']:run(['wipefs','--all',member['disk']])
     run(['mdadm','--create',ARRAY,'--run','--metadata=1.2','--level='+('1' if p['raid_mode']=='mirror' else '0'),'--raid-devices='+str(len(p['members']))]+[member['disk'] for member in p['members']])
     disk=ARRAY
     detail=run(['mdadm','--detail','--scan',ARRAY]);lines=[line for line in detail.splitlines() if line.startswith('ARRAY '+ARRAY+' ')]
     if len(lines)!=1:raise ValueError('Unable to verify persistent RAID array configuration.')
     MDADM.write_text((MDADM.read_text() if MDADM.exists() else '')+'\n'+lines[0]+'\n')
    else:
     disk=p['disk']
     if p.get('erase_confirm')=='yes':run(['wipefs','--all',disk])
    run(['mkfs.ext4','-F','-L','ServiceReadyData',disk]);uuid=run(['blkid','-s','UUID','-o','value',disk]);MOUNT.mkdir(parents=True,exist_ok=True)
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
     if p['kind']=='storage-raid':cfg.update(data_raid='RAID 1 mirror' if p['raid_mode']=='mirror' else 'RAID 0 combined capacity',data_array=ARRAY,data_members=[member['disk'] for member in p['members']])
     else:
      for key in ('data_raid','data_array','data_members'):cfg.pop(key,None)
     with FSTAB.open('a') as f:f.write('\n# ServiceReady uploaded data\nUUID='+uuid+' '+str(MOUNT)+' ext4 defaults,nofail,x-systemd.device-timeout=15s 0 2\n')
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
    args=['nmcli','connection','modify',original]
    if p['mode']!='keep':args+=['ipv4.method',p['mode'],'ipv4.addresses',p.get('address','') if p['mode']=='manual' else '', 'ipv4.gateway',p.get('gateway','') if p['mode']=='manual' else '', 'ipv4.dns',','.join(p.get('dns','').split()),'ipv4.ignore-auto-dns','yes' if p.get('dns') else 'no']
    if p.get('ipv6_mode'):args+=['ipv6.method',p['ipv6_mode'],'ipv6.addresses',p.get('ipv6_address','') if p['ipv6_mode']=='manual' else '', 'ipv6.gateway',p.get('ipv6_gateway','') if p['ipv6_mode']=='manual' else '', 'ipv6.dns',','.join(p.get('ipv6_dns','').split()),'ipv6.ignore-auto-dns','yes' if p.get('ipv6_dns') else 'no']
    oldhost=run(['hostname']);marker=STATE.with_suffix('.confirmed');marker.unlink(missing_ok=True)
    try:
     if len(args)>4:run(args)
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
