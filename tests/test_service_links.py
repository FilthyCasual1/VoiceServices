import unittest
from unittest.mock import patch
import test_app
from voiceservices import service_links
class ServiceLinksTests(unittest.TestCase):
 setUp=test_app.PortalTests.setUp
 tearDown=test_app.PortalTests.tearDown
 user=test_app.PortalTests.user
 request=test_app.PortalTests.request
 def test_request_approval_links_voice_identity_and_does_not_auto_verify(self):
  token,user=self.user('alice');admin_token,admin=self.user('admin')
  response=self.request('/account/services','POST',{'csrf':user['csrf'],'action':'request-service-link','module':'voice','identity':'alice-phone'},token)
  self.assertEqual(response['status'],'200 OK');self.assertIn('Pending',response['body'])
  with self.app.store.connect() as db:
   row=db.execute('SELECT * FROM service_link_requests').fetchone()
   self.assertIsNone(db.execute('SELECT * FROM voice_user_links WHERE user_id=?',(user['id'],)).fetchone())
  result=self.request('/admin/users','POST',{'csrf':admin['csrf'],'action':'approve-service-link','request':str(row['id'])},admin_token)
  self.assertEqual(result['status'],'200 OK')
  with self.app.store.connect() as db:
   self.assertEqual(db.execute('SELECT userid FROM voice_user_links WHERE user_id=?',(user['id'],)).fetchone()[0],'alice-phone')
  self.assertIn('Approved',self.request('/account/services',token=token)['body'])
 def test_no_cross_user_approval_and_no_uninstalled_service(self):
  token,user=self.user('alice')
  with self.assertRaises(PermissionError):service_links.review(self.app,user,{'action':'approve-service-link','request':'1'})
  with self.assertRaises(ValueError):service_links.request(self.app,user,{'module':'esxi','identity':'alice'})
  service_links.request(self.app,user,{'module':'voice','identity':'alice'})
  self.app.modules.change('voice',False)
  token,admin=self.user('admin')
  with self.assertRaises(ValueError):service_links.review(self.app,admin,{'action':'approve-service-link','request':'1'})
 def test_build_display_and_combined_overview_repository(self):
  from voiceservices.version import __build__,__display_version__
  token,user=self.user('admin');body=self.request('/admin',token=token)['body']
  self.assertIn(__display_version__,body);self.assertIn('Overview and addons',body);self.assertIn('Addon repository',body);self.assertIn('Manual installation',body);self.assertIn('Available to install',body)
  self.assertIn('Addon repository',self.request('/admin/addons',token=token)['body'])
  self.assertIn('build '+str(__build__),self.request()['body'])
 def test_addon_settings_wizard_and_separate_phone_links(self):
  token,user=self.user('admin');body=self.request('/admin',token=token)['body']
  sidebar=body.split('<aside class="admin-nav"')[1].split('</aside>')[0]
  self.assertNotIn('/admin/voice',sidebar);self.assertNotIn('/admin/downloads',sidebar)
  self.assertIn('Configure addon',body)
  wizard=self.request('/admin/downloads',token=token)['body']
  self.assertIn('data-addon-active',wizard);self.assertIn('data-addon-step="0"',wizard);self.assertIn('action="/admin/downloads"',wizard)
  users=self.request('/admin/users',token=token)['body']
  self.assertIn('Phone account links',users);self.assertIn('action="/admin/voice"',users)
  voice=self.request('/admin/voice',token=token)['body']
  self.assertIn('Save AXL settings',voice);self.assertNotIn('Create and link CUCM user',voice)
 def test_build_counter_increments_with_each_release(self):
  import tempfile,subprocess
  from pathlib import Path
  with tempfile.TemporaryDirectory() as root:
   root=Path(root);(root/'tools').mkdir();(root/'voiceservices').mkdir()
   script=root/'tools/bump_version.py';script.write_text(Path('tools/bump_version.py').read_text())
   version=root/'voiceservices/version.py';version.write_text("__version__ = '1.0.0'\n__build__ = 8\n")
   subprocess.run(['python3',str(script),'patch','Test'],check=True,capture_output=True)
   self.assertIn("__version__ = '1.0.1'",version.read_text());self.assertIn('__build__ = 9',version.read_text())
 def test_smart_alerts_are_deduplicated(self):
  from voiceservices import disk_health
  state={'smart':[{'disk':'/dev/sdb','identity':'disk-serial','state':'Failed','message':'Health check failed'}]}
  disk_health.render(self.app,state);disk_health.render(self.app,state)
  with self.app.store.connect() as db:count=db.execute("SELECT COUNT(*) FROM notifications WHERE priority='urgent' AND title='Upload disk failed'").fetchone()[0]
  self.assertEqual(count,1)
