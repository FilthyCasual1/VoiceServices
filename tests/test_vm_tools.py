import importlib.util,unittest
from pathlib import Path
from unittest.mock import Mock,patch
spec=importlib.util.spec_from_file_location('vm_tools',Path(__file__).parents[1]/'deploy/vm-tools.py');tools=importlib.util.module_from_spec(spec);spec.loader.exec_module(tools)
class VMToolsTests(unittest.TestCase):
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
