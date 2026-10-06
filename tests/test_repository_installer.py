import io,json,unittest,zipfile
from pathlib import Path
from unittest.mock import patch
import test_app
from voiceservices import addon_updates
class RepositoryInstallerTests(unittest.TestCase):
 setUp=test_app.PortalTests.setUp
 tearDown=test_app.PortalTests.tearDown
 request=test_app.PortalTests.request
 user=test_app.PortalTests.user
 def package(self,key='snmp'):
  version=self.app.modules.approved[key]['version']
  return Path(__file__).parents[1].joinpath('packages','addons',version,key+'-'+version+'.sraddon').read_bytes()
 def test_installs_pinned_compatible_package_and_keeps_manual_upload(self):
  token,user=self.user('admin');version=self.app.modules.approved['snmp']['version'];commit='a'*40
  with patch.object(addon_updates,'fetch',side_effect=[json.dumps({'sha':commit}).encode(),self.package()]) as fetch:
   body=self.request('/admin/addons','POST',{'csrf':user['csrf'],'module':'snmp','action':'install-repository-addon'},token)['body']
  self.assertTrue(self.app.modules.installed('snmp'))
  self.assertIn('/'+commit+'/packages/addons/'+version+'/snmp-'+version+'.sraddon',fetch.call_args_list[1].args[0])
  self.assertIn('Manual installation',body);self.assertIn('/admin/addons/upload',body)
  self.assertIn('SNMP Monitoring installed from the repository',body)
 def test_network_error_retains_manual_fallback_and_changes_nothing(self):
  token,user=self.user('admin')
  with patch.object(addon_updates,'fetch',side_effect=OSError('offline')):
   with self.assertRaisesRegex(ValueError,'upload a compatible package manually'):addon_updates.install_from_repository(self.app,user,{'module':'snmp'})
  self.assertFalse((self.app.modules.root/'snmp').exists())
 def test_mismatched_or_unapproved_package_is_not_installed(self):
  token,user=self.user('admin')
  for raw in (self.package('esxi'),b'not a zip'):
   with patch.object(addon_updates,'fetch',side_effect=[json.dumps({'sha':'a'*40}).encode(),raw]):
    with self.assertRaises(ValueError):addon_updates.install_from_repository(self.app,user,{'module':'snmp'})
   self.assertFalse((self.app.modules.root/'snmp').exists())
  source=self.package();out=io.BytesIO()
  with zipfile.ZipFile(io.BytesIO(source)) as src,zipfile.ZipFile(out,'w') as dst:
   for name in src.namelist():dst.writestr(name,b'print("unapproved")' if name=='module.py' else src.read(name))
  with patch.object(addon_updates,'fetch',side_effect=[json.dumps({'sha':'a'*40}).encode(),out.getvalue()]):
   with self.assertRaises(ValueError):addon_updates.install_from_repository(self.app,user,{'module':'snmp'})
  self.assertFalse((self.app.modules.root/'snmp').exists())
 def test_rejects_nonadmin_unknown_and_already_present_before_download(self):
  token,user=self.user('admin')
  with patch.object(addon_updates,'fetch') as fetch:
   for key in ('downloads','../../other'):
    with self.assertRaises(ValueError):addon_updates.install_from_repository(self.app,user,{'module':key})
   with self.assertRaises(PermissionError):addon_updates.install_from_repository(self.app,{'role':'user'},{'module':'snmp'})
   fetch.assert_not_called()
 def test_release_notes_permission_error_never_breaks_admin(self):
  token,user=self.user('admin')
  original=Path.read_text
  def read(path,*args,**kwargs):
   if path.name=='addon_notes.json':raise PermissionError('Protected notes')
   return original(path,*args,**kwargs)
  with patch.object(Path,'read_text',read):body=self.request('/admin',token=token)
  self.assertEqual(body['status'],'200 OK');self.assertIn('Release notes are unavailable',body['body']);self.assertIn('Download and install',body['body'])
 def test_release_notes_are_bundled_with_portal(self):
  token,user=self.user('admin');body=addon_updates.repository_installer(self.app,user)
  self.assertIn('Release notes</summary>',body)
 def test_batch_installs_multiple_addons_from_one_pinned_revision(self):
  token,user=self.user('admin');commit='a'*40
  def fetch(url,limit=0):
   if '/commits/main' in url:return json.dumps({'sha':commit}).encode()
   return self.package('snmp' if '/snmp-' in url else 'esxi')
  with patch.object(addon_updates,'fetch',side_effect=fetch) as download:
   result=self.request('/admin','POST',{'csrf':user['csrf'],'action':'install-repository-addons','install_module_snmp':'yes','install_module_esxi':'yes'},token)
  self.assertEqual(result['status'],'200 OK');self.assertTrue(self.app.modules.installed('snmp'));self.assertTrue(self.app.modules.installed('esxi'))
  self.assertIn('Installation results',result['body']);self.assertEqual(sum('/commits/main' in call.args[0] for call in download.call_args_list),1)
 def test_batch_retains_successes_and_reports_individual_failure(self):
  token,user=self.user('admin')
  with patch.object(addon_updates,'fetch',side_effect=[json.dumps({'sha':'a'*40}).encode(),self.package('snmp'),OSError('offline')]):
   result=addon_updates.install_batch(self.app,user,{'install_module_snmp':'yes','install_module_esxi':'yes'})
  self.assertTrue(self.app.modules.installed('snmp'));self.assertFalse(self.app.modules.installed('esxi'));self.assertIn('SNMP Monitoring: installed',result);self.assertIn('ESXi Management: failed',result)
