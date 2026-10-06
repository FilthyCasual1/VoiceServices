import importlib.util,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
spec=importlib.util.spec_from_file_location('control',Path(__file__).parents[1]/'deploy/host-control.py');control=importlib.util.module_from_spec(spec);spec.loader.exec_module(control)
class HostConfigurationTests(unittest.TestCase):
 def test_disk_refuses_in_use_changed_and_signed(self):
  d={'path':'/dev/sdb','eligible':False,'fingerprint':'one'}
  with patch.object(control,'disks',return_value=[d]):
   with self.assertRaises(ValueError):control.validate({'kind':'storage','disk':'/dev/sdb','fingerprint':'one','confirm':'FORMAT /dev/sdb'})
   d['eligible']=True
   with self.assertRaises(ValueError):control.validate({'kind':'storage','disk':'/dev/sdb','fingerprint':'two','confirm':'FORMAT /dev/sdb'})
   with patch.object(control,'run',return_value='{"signatures":[{}]}'):
    with self.assertRaises(ValueError):control.validate({'kind':'storage','disk':'/dev/sdb','fingerprint':'one','confirm':'FORMAT /dev/sdb'})
 def test_network_and_ntp_reject_shell_and_invalid_address(self):
  for p in [{'kind':'ntp','servers':'host;reboot'},{'kind':'network','connection':'x;reboot','mode':'auto'},{'kind':'network','connection':'a'*36,'mode':'manual','address':'invalid','gateway':'10.0.0.1'}]:
   with self.assertRaises(ValueError):control.validate(p)
 def test_missing_and_wrong_volume_block_content(self):
  from voiceservices.data_volume import require
  with patch('voiceservices.data_volume.os.path.ismount',return_value=False):
   with self.assertRaises(ValueError):require({'data_mount':'/srv/data','data_disk_uuid':'expected'})
  with patch('voiceservices.data_volume.os.path.ismount',return_value=True),patch('voiceservices.data_volume.subprocess.check_output',return_value='wrong'):
   with self.assertRaises(ValueError):require({'data_mount':'/srv/data','data_disk_uuid':'expected'})
 def test_rocky_logo_is_available_offline(self):
  from voiceservices import distro
  with patch.object(distro,'detected',return_value={'ID':'rocky'}),patch.object(distro,'urlopen',side_effect=OSError):
   self.assertIn(b'<path',distro.logo(None));self.assertNotIn(b'<text',distro.logo(None))
 def test_profile_contacts_persist_and_invalid_numbers_fail(self):
  from voiceservices.web import App
  from voiceservices import account
  with tempfile.TemporaryDirectory() as root:
   app=App({'database':root+'/portal.sqlite','secure_cookies':False})
   app.store.create_user('alice','a-password-long-enough')
   with app.store.connect() as db:user=dict(db.execute("SELECT * FROM users WHERE username='alice'").fetchone())
   values={'action':'profile','display_name':'Alice','email':'alice@example.net','phone':'+1 555 0100','timezone':'UTC','location':'Main office','address':'1 Example Street\nRoom 2','mobile_phone':'+1 555 0101','work_phone':'555-0102','other_phone':'555-0103'}
   account.change(app,user,values,'unused');saved=account.profile(app,user)
   self.assertEqual(saved['address'],values['address']);self.assertEqual(saved['mobile_phone'],values['mobile_phone'])
   with self.assertRaises(ValueError):account.change(app,user,dict(values,work_phone='<script>'),'unused')

 def test_unconfirmed_network_restores_boot_persistent_profile(self):
  with tempfile.TemporaryDirectory() as root:
   state=Path(root)/'job.json';calls=[]
   def command(args):
    calls.append(args)
    if args[0]=='hostname':return 'old-host'
    if args[:3]==['nmcli','-g','connection.uuid']:return '22222222-2222-2222-2222-222222222222'
    return ''
   original='11111111-1111-1111-1111-111111111111'
   with patch.object(control,'STATE',state),patch.object(control,'run',side_effect=command),patch.object(control.os,'geteuid',return_value=0),patch.object(control.time,'monotonic',side_effect=[0,91]):
    control.main({'kind':'network','connection':original,'mode':'auto','dns':'','hostname':'new-host'})
   self.assertEqual(json.loads(state.read_text())['state'],'rolled-back')
   self.assertIn(['nmcli','connection','modify',original,'connection.autoconnect','no'],calls)
   self.assertIn(['nmcli','connection','modify','22222222-2222-2222-2222-222222222222','connection.autoconnect','yes'],calls)
   self.assertIn(['hostnamectl','set-hostname','old-host'],calls)
 def test_storage_status_does_not_require_network_or_time_tools(self):
  with tempfile.TemporaryDirectory() as root:
   cfg=Path(root)/'config.json';cfg.write_text('{}')
   with patch.object(control,'CONFIG',cfg),patch.object(control,'STATE',Path(root)/'job.json'),patch.object(control,'disks',return_value=[]),patch.object(control.subprocess,'check_output',side_effect=FileNotFoundError):
    storage=control.snapshot('storage');network=control.snapshot('network-host')
   self.assertEqual(storage['errors'],[])
   self.assertEqual(network['connections'],'Unavailable');self.assertEqual(len(network['errors']),4)

 def test_system_disks_and_their_partition_trees_are_hidden(self):
  blank={'path':'/dev/sdb','type':'disk','size':10000000000,'ro':False,'mountpoints':[None]}
  rows=[{'path':'/dev/sda','type':'disk','children':[{'path':'/dev/sda2','type':'part','children':[{'path':'/dev/mapper/root','type':'lvm','mountpoints':['/']}]}]},
        {'path':'/dev/nvme0n1','type':'disk','children':[{'path':'/dev/nvme0n1p1','type':'part','mountpoints':['/boot/efi']}]},
        {'path':'/dev/sdc','type':'disk','children':[{'mountpoints':['/boot']}]},
        {'path':'/dev/mapper/root','type':'lvm','mountpoints':['/']},blank]
  with patch.object(control,'run',return_value=json.dumps({'blockdevices':rows})):
   found=control.disks()
  self.assertEqual([d['path'] for d in found],['/dev/sdb']);self.assertTrue(found[0]['eligible'])

 def test_power_requires_exact_confirmation_and_uses_fixed_delayed_commands(self):
  for operation in ('restart','shutdown'):
   with self.assertRaises(ValueError):control.validate({'kind':'power','operation':operation,'confirm':'yes'})
  with self.assertRaises(ValueError):control.validate({'kind':'power','operation':'shutdown;reboot','confirm':'shutdown;reboot'})
  with tempfile.TemporaryDirectory() as root:
   for operation,command in [('restart','reboot'),('shutdown','poweroff')]:
    with patch.object(control,'STATE',Path(root)/'job.json'),patch.object(control.os,'geteuid',return_value=0),patch.object(control,'run') as run:
     control.main({'kind':'power','operation':operation,'confirm':operation})
    run.assert_called_once_with(['systemd-run','--unit=serviceready-power','--on-active=10s','/usr/bin/systemctl',command])
    self.assertEqual(json.loads((Path(root)/'job.json').read_text())['state'],'complete')
 def test_power_rejects_nonadmins_and_external_accounts(self):
  from types import SimpleNamespace
  from voiceservices import host_configuration
  app=SimpleNamespace(store=SimpleNamespace(accounts=object()),base='https://portal.example',secure=True)
  with self.assertRaises(PermissionError):host_configuration.change(app,{'role':'user'}, {'kind':'power'})
  with patch('voiceservices.external_auth.identity',return_value=True):
   with self.assertRaises(ValueError):host_configuration.change(app,{'role':'admin'},{'kind':'power'})

 def test_timezone_validated_and_loopback_hidden(self):
  control.validate({'kind':'timezone','timezone':'America/Chicago'})
  with self.assertRaises(ValueError):control.validate({'kind':'timezone','timezone':'bad/timezone'})
  with tempfile.TemporaryDirectory() as root:
   config=Path(root)/'config.json';config.write_text('{}')
   def output(args,**kwargs):
    return 'Loopback:uuid:lo\nEthernet:uuid:eth0' if args[0]=='nmcli' else 'UTC'
   with patch.object(control,'CONFIG',config),patch.object(control,'STATE',Path(root)/'state.json'),patch.object(control.subprocess,'check_output',side_effect=output):
    state=control.snapshot('network')
   self.assertEqual(state['connections'],'Ethernet:uuid:eth0');self.assertEqual(state['timezone'],'UTC')

 def test_ipv6_static_and_dhcp_configuration_validation(self):
  valid={'kind':'network','connection':'a'*36,'mode':'auto','ipv6_mode':'manual','ipv6_address':'2001:db8::20/64','ipv6_gateway':'fe80::1','ipv6_dns':'2001:db8::53'}
  control.validate(valid)
  for key,value in [('ipv6_address','192.0.2.1/24'),('ipv6_gateway','host;reboot'),('ipv6_dns','192.0.2.1'),('ipv6_mode','invalid')]:
   with self.assertRaises(ValueError):control.validate(dict(valid,**{key:value}))
  control.validate(dict(valid,mode='disabled',ipv6_mode='dhcp'))
  control.validate(dict(valid,mode='keep'))
  with self.assertRaises(ValueError):control.validate(dict(valid,mode='disabled',ipv6_mode='disabled'))

 def test_ipv6_only_change_keeps_ipv4_and_retains_rollback(self):
  with tempfile.TemporaryDirectory() as root:
   state=Path(root)/'job.json';calls=[]
   def command(args):
    calls.append(args)
    if args[0]=='hostname':return 'old-host'
    if args[:3]==['nmcli','-g','connection.uuid']:return '22222222-2222-2222-2222-222222222222'
    return ''
   original='11111111-1111-1111-1111-111111111111'
   with patch.object(control,'STATE',state),patch.object(control,'run',side_effect=command),patch.object(control.os,'geteuid',return_value=0),patch.object(control.time,'monotonic',side_effect=[0,91]):
    control.main({'kind':'network','connection':original,'mode':'keep','ipv6_mode':'manual','ipv6_address':'2001:db8::20/64','ipv6_gateway':'fe80::1','ipv6_dns':'2001:db8::53'})
   update=next(c for c in calls if 'ipv6.method' in c)
   self.assertNotIn('ipv4.method',update);self.assertIn('2001:db8::20/64',update)
   self.assertEqual(json.loads(state.read_text())['state'],'rolled-back')
 def test_reformat_requires_current_disk_identity_and_exact_confirmation(self):
  with tempfile.TemporaryDirectory() as root:
   cfg=Path(root)/'config';cfg.write_text(json.dumps({'data_mount':str(control.MOUNT),'data_disk_uuid':'expected'}))
   disk={'path':'/dev/sdb','fingerprint':'same','ro':False,'fstype':'ext4','uuid':'expected','mountpoints':[str(control.MOUNT)]}
   payload={'kind':'storage-reset','disk':'/dev/sdb','fingerprint':'same','confirm':'ERASE /dev/sdb','erase_confirm':'yes'}
   with patch.object(control,'CONFIG',cfg),patch.object(control,'disks',return_value=[disk]),patch.object(control,'run',return_value='expected'):
    control.validate(payload)
    for change in ({'confirm':'FORMAT /dev/sdb'},{'erase_confirm':''},{'disk':'/dev/sda'},{'fingerprint':'changed'}):
     with self.assertRaises(ValueError):control.validate(dict(payload,**change))
    for change in ({'uuid':'other'},{'ro':True},{'mountpoints':['/']},{'children':[{'path':'/dev/sdb1'}]}):
     with patch.object(control,'disks',return_value=[dict(disk,**change)]):
      with self.assertRaises(ValueError):control.validate(payload)
 def test_reformat_busy_disk_never_formats_and_restarts_services(self):
  import subprocess
  with tempfile.TemporaryDirectory() as root:
   cfg=Path(root)/'config';cfg.write_text(json.dumps({'data_disk_uuid':'old'}));calls=[]
   def command(args):
    calls.append(args)
    if args[0]=='umount':raise subprocess.CalledProcessError(1,args)
    return ''
   with patch.object(control,'CONFIG',cfg),patch.object(control,'validate'),patch.object(control,'status'),patch.object(control,'run',side_effect=command):
    with self.assertRaises(subprocess.CalledProcessError):control.reset_storage({'disk':'/dev/sdb'})
   self.assertFalse(any(c[0]=='mkfs.ext4' for c in calls))
   self.assertEqual(len([c for c in calls if c[:2]==['systemctl','stop']]),len([c for c in calls if c[:2]==['systemctl','start']]))
 def test_reformat_rebuilds_disk_and_preserves_core_and_links(self):
  import sqlite3
  from types import SimpleNamespace
  with tempfile.TemporaryDirectory() as root:
   root=Path(root);mount=root/'data';mount.mkdir();cfg=root/'config';database=root/'db';fstab=root/'fstab'
   cfg.write_text(json.dumps({'data_disk_uuid':'old','data_mount':str(mount),'database':str(database)}));fstab.write_text('UUID=boot / ext4 defaults 0 1\nUUID=old '+str(mount)+' ext4 defaults 0 2\n')
   with sqlite3.connect(database) as db:
    for table in ('downloads_files','updates_files','pxe_files','account_photos','users','downloads_categories','downloads_catalog'):db.execute('CREATE TABLE '+table+'(name TEXT)');db.execute('INSERT INTO '+table+" VALUES('keep-or-delete')")
    db.execute('CREATE TABLE downloads_details(kind TEXT)');db.executemany('INSERT INTO downloads_details VALUES(?)',[('file',),('link',)])
   calls=[]
   def command(args):calls.append(args);return 'new' if args[0]=='blkid' else ''
   with patch.object(control,'CONFIG',cfg),patch.object(control,'MOUNT',mount),patch.object(control,'FSTAB',fstab),patch.object(control,'validate'),patch.object(control,'status'),patch.object(control,'run',side_effect=command),patch.object(control.os,'chown'),patch.object(control.pwd,'getpwnam',return_value=SimpleNamespace(pw_uid=1000,pw_gid=1000)):
    control.reset_storage({'disk':'/dev/sdb'})
   self.assertEqual(json.loads(cfg.read_text())['data_disk_uuid'],'new');self.assertIn('UUID=boot /',fstab.read_text());self.assertNotIn('UUID=old',fstab.read_text());self.assertEqual((mount/'tmp').stat().st_mode&0o777,0o700)
   with sqlite3.connect(database) as db:
    for table in ('downloads_files','updates_files','pxe_files','account_photos'):self.assertEqual(db.execute('SELECT COUNT(*) FROM '+table).fetchone()[0],0)
    for table in ('users','downloads_categories','downloads_catalog'):self.assertEqual(db.execute('SELECT COUNT(*) FROM '+table).fetchone()[0],1)
    self.assertEqual(db.execute('SELECT kind FROM downloads_details').fetchall(),[('link',)])
