import json,unittest
from unittest.mock import Mock,patch
import test_app
class UpdateProgressTests(unittest.TestCase):
 setUp=test_app.PortalTests.setUp
 tearDown=test_app.PortalTests.tearDown
 request=test_app.PortalTests.request
 user=test_app.PortalTests.user
 def test_status_requires_administrator_and_get(self):
  self.assertEqual(self.request('/admin/update-status',token=self.user('alice')[0])['status'],'403 Forbidden')
  token,user=self.user('admin')
  self.assertEqual(self.request('/admin/update-status','POST',{'csrf':user['csrf']},token)['status'],'405 Method Not Allowed')
  self.assertEqual(self.request('/admin/update-status',token=token)['status'],'503 Service Unavailable')
 def test_progress_is_json_and_no_manual_refresh_link(self):
  token,user=self.user('admin');self.app.store.accounts=Mock()
  self.app.store.accounts.call.return_value={'state':'running','message':'Installing packages','kind':'os'}
  response=self.request('/admin/update-status',token=token)
  self.assertEqual(response['status'],'200 OK');self.assertEqual(json.loads(response['body'])['status']['message'],'Installing packages')
  body=self.request('/admin/system-updates',token=token)['body']
  self.assertIn('data-update-state="running"',body);self.assertIn('aria-live="polite"',body);self.assertNotIn('Refresh update status',body)
 def test_submitted_update_starts_watching_even_before_worker_reports(self):
  token,user=self.user('admin');self.app.store.accounts=Mock()
  self.app.store.accounts.call.return_value={'state':'idle','message':'No updates started.'}
  body=self.request('/admin/system-updates','POST',{'csrf':user['csrf'],'update':'insap'},token)['body']
  self.assertIn('data-update-state="starting"',body);self.assertIn('Progress updates automatically',body)

 def test_versions_are_below_logo_and_heading_is_not_duplicated(self):
  token,user=self.user('admin')
  with patch('voiceservices.distro.detected',return_value={'NAME':'Rocky Linux','VERSION_ID':'10.2'}):
   body=self.request('/admin/system-updates',token=token)['body']
  self.assertNotIn('Installed INSAP version:',body)
  self.assertEqual(body.count('<h2>Portal and host updates</h2>'),1)
  self.assertLess(body.index('alt="Host distribution logo"'),body.index('Rocky Linux 10.2'))
  self.assertIn('class="update-version">INSAP ',body);self.assertIn('class="update-actions"',body)
