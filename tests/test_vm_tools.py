import importlib.util,unittest
from pathlib import Path
from unittest.mock import Mock,patch
spec=importlib.util.spec_from_file_location('vm_tools',Path(__file__).parents[1]/'deploy/vm-tools.py');tools=importlib.util.module_from_spec(spec);spec.loader.exec_module(tools)
real_tools_cd=tools.tools_cd
class VMToolsTests(unittest.TestCase):
 def setUp(self):
  self.provider_patch=patch.object(tools,'hypervisor',return_value='virtualbox');self.provider_patch.start();self.addCleanup(self.provider_patch.stop)
  self.cd_patch=patch.object(tools,'tools_cd',return_value={});self.cd_patch.start();self.addCleanup(self.cd_patch.stop)
  self.running_patch=patch.object(tools,'virtualbox_running',return_value=False);self.running_patch.start();self.addCleanup(self.running_patch.stop)
 def test_vmware_updates_repository_package_and_service(self):
  run=Mock()
  with patch.object(tools.pathlib.Path,'is_file',return_value=True),patch.object(tools,'hypervisor',return_value='vmware'):
   message=tools.update(run,Mock())
  self.assertIn('No reboot',message);self.assertIn(['/usr/bin/dnf','-y','upgrade','open-vm-tools'],[c.args[0] for c in run.call_args_list])
  self.assertNotIn('reboot',str(run.call_args_list))
 def test_unknown_hypervisor_and_initial_virtualbox_install_fail_clearly(self):
  with patch.object(tools.pathlib.Path,'is_file',return_value=True),patch.object(tools,'hypervisor',return_value='unsupported'):
   with self.assertRaises(ValueError):tools.update(Mock(),Mock())
  with patch.object(tools.pathlib.Path,'is_file',return_value=True),patch.object(tools,'hypervisor',return_value='virtualbox'),patch.object(tools.shutil,'which',return_value=None):
   with self.assertRaisesRegex(ValueError,'initial VirtualBox'):tools.update(Mock(),Mock())
 def test_checksums_require_exact_name_and_hash(self):
  name='VBoxGuestAdditions_7.2.0.iso';digest='a'*64
  self.assertEqual(tools.checksum(digest+' *'+name,name),digest)
  with self.assertRaises(ValueError):tools.checksum(digest+' other.iso',name)
 def test_virtualbox_matching_version_does_not_reinstall(self):
  import subprocess
  run=Mock()
  with patch.object(tools.pathlib.Path,'is_file',return_value=True),patch.object(tools,'hypervisor',return_value='virtualbox'),patch.object(tools.shutil,'which',return_value='/usr/bin/VBoxControl'),patch.object(tools,'output',side_effect=[subprocess.CalledProcessError(1,'rpm'),'Value: 7.2.0','7.2.0r12345']):
   self.assertIn('already match',tools.update(run,Mock()))
  run.assert_not_called()
 def test_virtualbox_checksum_failure_never_runs_installer(self):
  import subprocess
  run=Mock()
  def download(url,path,limit):
   if url.endswith('SHA256SUMS'):path.write_text('a'*64+' VBoxGuestAdditions_7.2.0.iso')
   return 'b'*64
  with patch.object(tools.pathlib.Path,'is_file',return_value=True),patch.object(tools,'hypervisor',return_value='virtualbox'),patch.object(tools.shutil,'which',return_value='/usr/bin/VBoxControl'),patch.object(tools,'output',side_effect=[subprocess.CalledProcessError(1,'rpm'),'Value: 7.2.0','7.1.0r12345']),patch.object(tools,'download',side_effect=download):
   with self.assertRaisesRegex(ValueError,'checksum mismatch'):tools.update(run,Mock())
  self.assertFalse(any(c.args[0][0] in ('/bin/sh','/usr/bin/mount') for c in run.call_args_list))
 def test_guest_tools_schedule_is_core_and_saves(self):
  import tempfile
  from voiceservices.web import App
  from voiceservices import update_schedule
  with tempfile.TemporaryDirectory() as root:
   app=App({'database':root+'/db.sqlite','secure_cookies':False})
   update_schedule.change(app,{'role':'admin'},{'vmtools_enabled':'yes','vmtools_frequency':'daily','vmtools_time':'03:30'})
   self.assertTrue(update_schedule.settings(app)['vmtools']['enabled'])
   self.assertIn('vmtools_timezone',update_schedule.render(app,{'csrf':'test'}))

 def test_verified_virtualbox_installer_always_unmounts_on_failure(self):
  import subprocess
  run=Mock()
  def command(args):
   if args[0]=='/bin/sh':raise subprocess.CalledProcessError(1,args)
  run.side_effect=command
  def download(url,path,limit):
   if url.endswith('SHA256SUMS'):path.write_text('a'*64+' VBoxGuestAdditions_7.2.0.iso')
   return 'a'*64
  with patch.object(tools.pathlib.Path,'is_file',return_value=True),patch.object(tools,'hypervisor',return_value='virtualbox'),patch.object(tools.shutil,'which',return_value='/usr/bin/VBoxControl'),patch.object(tools,'output',side_effect=[subprocess.CalledProcessError(1,'rpm'),'Value: 7.2.0','7.1.0r12345']),patch.object(tools,'download',side_effect=download):
   with self.assertRaises(subprocess.CalledProcessError):tools.update(run,Mock())
  self.assertEqual(run.call_args.args[0][0],'/usr/bin/umount')
 def test_optical_media_detection_and_attempt_tracking(self):
  import json,tempfile
  with tempfile.TemporaryDirectory() as root:
   marker=Path(root)/'cd.json'
   rows={'blockdevices':[{'path':'/dev/sr0','type':'rom','label':'VBox_GAs_7.2.0','size':4096},{'path':'/dev/sda','type':'disk','label':'VBox_GAs_7.2.0','size':4096}]}
   with patch.object(tools,'output',return_value=json.dumps(rows)),patch.object(tools,'CD_STATE',marker):
    cd=real_tools_cd();self.assertEqual(cd['version'],'7.2.0');self.assertFalse(cd['attempted'])
    marker.write_text(json.dumps({'fingerprint':cd['fingerprint']}));self.assertTrue(real_tools_cd()['attempted'])
 def test_cd_dependencies_verified_copy_and_unmount(self):
  import io,hashlib,tempfile
  data=b'official tools iso fixture';digest=hashlib.sha256(data).hexdigest();run=Mock();original_open=open
  def source(path,*args,**kwargs):
   return io.BytesIO(data) if str(path)=='/dev/sr0' else original_open(path,*args,**kwargs)
  def download(url,path,limit):path.write_text(digest+' VBoxGuestAdditions_7.2.0.iso');return digest
  with tempfile.TemporaryDirectory() as root,patch.object(tools,'CD_STATE',Path(root)/'cd.json'),patch.object(tools,'tools_cd',return_value={'device':'/dev/sr0','version':'7.2.0','provider':'virtualbox','fingerprint':'fixture'}),patch.object(tools,'hypervisor',return_value='virtualbox'),patch.object(tools,'output',return_value=str(len(data))) as probe,patch.object(tools,'download',side_effect=download),patch('builtins.open',side_effect=source):
   self.assertIn('installed from CD',tools.install_cd(run,Mock()))
  probe.assert_called_once_with(['/usr/bin/lsblk','--bytes','--nodeps','--noheadings','--output','SIZE','/dev/sr0'])
  commands=[call.args[0] for call in run.call_args_list]
  dependencies=next(command for command in commands if command[0]=='/usr/bin/dnf')
  for package in ('gcc','make','perl','bzip2','tar','xz','kernel-headers'):self.assertIn(package,dependencies)
  self.assertTrue(any(p.startswith('kernel-devel-') for p in dependencies))
  mount=next(command for command in commands if command[0]=='/usr/bin/mount');self.assertIn('verified-tools.iso',mount[-2]);self.assertEqual(commands[-1][0],'/usr/bin/umount')
 def test_scheduler_installs_inserted_media_once_and_setting_can_disable(self):
  import tempfile
  from voiceservices.web import App
  from voiceservices import update_schedule
  with tempfile.TemporaryDirectory() as root:
   app=App({'database':root+'/db.sqlite','secure_cookies':False});app.store.accounts=Mock()
   app.store.accounts.call.return_value={'state':'idle','tools_cd':{'version':'7.2.0','attempted':False}}
   update_schedule.tick(app);self.assertIn(unittest.mock.call('maintenance-start','vmtools-cd',''),app.store.accounts.call.call_args_list)
   app.store.accounts.call.reset_mock()
   with app.store.connect() as db:db.execute("INSERT OR REPLACE INTO portal_settings VALUES('tools_cd_auto','no')")
   update_schedule.tick(app);self.assertFalse(any(call.args[0]=='maintenance-start' for call in app.store.accounts.call.call_args_list))

 def test_installer_nonzero_only_succeeds_with_verified_running_tools(self):
  import subprocess
  run=Mock(side_effect=subprocess.CalledProcessError(1,'installer'))
  with patch.object(tools,'virtualbox_running',return_value=True):
   warning=tools.run_installer(run,Path('/media/VBoxLinuxAdditions.run'),'7.2.0',Mock())
  self.assertIn('exit 1',warning);self.assertIn('verified',warning)
  with patch.object(tools,'virtualbox_running',return_value=False):
   with self.assertRaises(subprocess.CalledProcessError):tools.run_installer(run,Path('/media/VBoxLinuxAdditions.run'),'7.2.0',Mock())

 def test_live_status_requires_driver_service_and_host_communication(self):
  with patch.object(tools.shutil,'which',return_value='/usr/bin/VBoxControl'),patch.object(tools,'output',side_effect=['7.2.18r175117','Value: 7.2.18']),patch.object(tools,'virtualbox_service',return_value=True),patch.object(tools.pathlib.Path,'is_dir',return_value=True):
   self.assertEqual(tools.live_status()['state'],'Running')
  with patch.object(tools.shutil,'which',return_value='/usr/bin/VBoxControl'),patch.object(tools,'output',side_effect=['7.2.18r175117','Value: 7.2.18']),patch.object(tools,'virtualbox_service',return_value=False),patch.object(tools.pathlib.Path,'is_dir',return_value=True):
   self.assertNotEqual(tools.live_status()['state'],'Running')
 def test_oracle_process_is_recognized_without_matching_systemd_unit(self):
  import subprocess
  with patch.object(tools,'output',side_effect=subprocess.CalledProcessError(3,'systemctl')),patch.object(tools.pathlib.Path,'iterdir',return_value=iter([Path('/proc/123')])),patch.object(tools.os,'readlink',return_value='/opt/VBoxGuestAdditions-7.2.18/sbin/VBoxService'):
   self.assertTrue(tools.virtualbox_service('7.2.18'))

 def test_missing_host_property_does_not_fail_running_headless_tools(self):
  import subprocess
  with patch.object(tools.shutil,'which',return_value='/usr/bin/VBoxControl'),patch.object(tools,'output',side_effect=['7.2.18r175117',subprocess.CalledProcessError(1,'guestproperty')]),patch.object(tools,'virtualbox_service',return_value=True),patch.object(tools.pathlib.Path,'is_dir',return_value=True):
   status=tools.live_status();self.assertEqual(status['state'],'Running');self.assertFalse(status['communication'])

 def test_vmware_live_tools_version_is_not_virtualbox(self):
  with patch.object(tools,'hypervisor',return_value='vmware'),patch.object(tools.shutil,'which',return_value='/usr/bin/vmware-toolbox-cmd'),patch.object(tools,'output',side_effect=['13.0.5.0 (build-12345)','active']):
   status=tools.live_status();self.assertEqual(status['provider'],'vmware');self.assertEqual(status['version'],'13.0.5');self.assertEqual(status['state'],'Running');self.assertEqual(status['host_version'],'')
