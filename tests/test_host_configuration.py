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
