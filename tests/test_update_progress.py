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

 def test_schedules_share_update_page_without_triggering_update(self):
  from voiceservices import update_schedule
  token,user=self.user('admin')
  body=self.request('/admin/system-updates',token=token)['body']
  self.assertIn('Automatic update schedules',body);self.assertIn('name="os_timezone"',body)
  self.assertNotIn('href="/admin/schedules"',body)
  with patch('voiceservices.maintenance.change') as manual:
   response=self.request('/admin/system-updates','POST',{'csrf':user['csrf'],'action':'save-update-schedules','os_enabled':'yes','os_frequency':'daily','os_time':'04:30'},token)
  self.assertEqual(response['status'],'200 OK');manual.assert_not_called()
  self.assertTrue(update_schedule.settings(self.app)['os']['enabled'])
  self.assertIn('id="update-schedules" open',response['body'])

 def test_failed_guest_tools_show_escaped_installer_output(self):
  token,user=self.user('admin');self.app.store.accounts=Mock()
  self.app.store.accounts.call.return_value={'state':'failed','kind':'vmtools-cd','message':'Installation failed','tools_log':'actual error <script>bad</script>'}
  body=self.request('/admin/host',token=token)['body']
  self.assertIn('Installer output',body);self.assertIn('actual error &lt;script&gt;',body);self.assertNotIn('actual error <script>',body)

 def test_live_tools_status_does_not_erase_previous_failure(self):
  token,user=self.user('admin');self.app.store.accounts=Mock()
  self.app.store.accounts.call.return_value={'state':'failed','message':'Previous failure','tools_live':{'provider':'virtualbox','version':'7.2.18','state':'Running'}}
  body=self.request('/admin/host',token=token)['body']
  self.assertIn('Guest tools now:',body);self.assertIn('VirtualBox 7.2.18',body)
  self.assertIn('Last host operation',body);self.assertIn('Previous failure',body)

 def test_cd_button_version_only_comes_from_detected_virtualbox_cd(self):
  token,user=self.user('admin');self.app.store.accounts=Mock()
  for cd,label in [({'provider':'virtualbox','version':'7.2.18'},'Install tools CD 7.2.18'),({'provider':'vmware','version':'VMware Tools'},'Install tools CD'),({'provider':'virtualbox','version':'not detected'},'Install tools CD')]:
   self.app.store.accounts.call.return_value={'state':'idle','tools_cd':cd}
   body=self.request('/admin/host',token=token)['body']
   self.assertIn('value="vmtools-cd">'+label+'</option>',body)

 def test_wizard_checks_hypervisor_before_starting_worker(self):
  from voiceservices import maintenance
  token,user=self.user('admin');self.app.store.accounts=Mock()
  self.app.store.accounts.call.return_value={'tools_provider':'vmware'}
  with self.assertRaisesRegex(ValueError,'does not match'):
   maintenance.change(self.app,user,{'update':'vmtools','tools_provider':'virtualbox'})
  self.assertEqual(self.app.store.accounts.call.call_count,1)
 def test_wizard_replaces_raw_tools_buttons(self):
  token,user=self.user('admin');self.app.store.accounts=Mock()
  self.app.store.accounts.call.return_value={'state':'idle','tools_provider':'vmware'}
  body=self.request('/admin/host',token=token)['body']
  self.assertIn('1. Hypervisor',body);self.assertIn('2. Installation method',body);self.assertIn('3. Review and install',body)
  self.assertNotIn('>Update VM tools</button>',body);self.assertIn('Start tools setup',body)
