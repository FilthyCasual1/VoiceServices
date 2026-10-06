import unittest
from unittest.mock import patch
from voiceservices import host_branding
import test_app
class HostBrandingTests(unittest.TestCase):
 setUp=test_app.PortalTests.setUp
 tearDown=test_app.PortalTests.tearDown
 request=test_app.PortalTests.request
 user=test_app.PortalTests.user
 def test_detection_and_offline_logos(self):
  for value,identifier in [('oracle','virtualbox'),('vmware','vmware')]:
   host_branding.provider.cache_clear()
   with patch.object(host_branding.subprocess,'check_output',return_value=value):self.assertEqual(host_branding.provider()[0],identifier)
   response=self.request('/static/provider-'+identifier+'.svg')
   self.assertEqual(response['status'],'200 OK');self.assertIn('<path',response['body'])
  host_branding.provider.cache_clear()
 def test_three_marks_on_admin_pages_and_unknown_provider_not_invented(self):
  token,user=self.user('admin')
  with patch.object(host_branding,'provider',return_value=('virtualbox','VirtualBox')):
   for path in ('/admin','/admin/host'):
    body=self.request(path,token=token)['body']
    for image in ('casualnetworks-arrow.svg','/host/distro-logo','provider-virtualbox.svg'):self.assertIn(image,body)
  with patch.object(host_branding,'provider',return_value=(None,'Host')):self.assertNotIn('provider-',host_branding.marks())
