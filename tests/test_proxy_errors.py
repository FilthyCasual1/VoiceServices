import json,sqlite3,tempfile,unittest
from pathlib import Path
from voiceservices.proxy_errors import publish
class ProxyErrorTests(unittest.TestCase):
 def test_pages_work_offline_and_escape_branding(self):
  with tempfile.TemporaryDirectory() as temporary:
   root=Path(temporary);database=root/'portal.sqlite'
   with sqlite3.connect(database) as db:
    db.execute('CREATE TABLE portal_settings(key TEXT,value TEXT)');db.execute('INSERT INTO portal_settings VALUES(?,?)',('branding',json.dumps({'title':'Example <script>','subtitle':'Network & services'})))
   folder=publish({'database':str(database)},root)
   html=(folder/'unavailable.html').read_text()
   self.assertIn('Example &lt;script&gt;',html);self.assertNotIn('<script>Example',html)
   self.assertIn('check for its return automatically',html);self.assertIn('Any submitted change may already have completed',html)
   self.assertTrue((folder/'style.css').is_file());self.assertTrue((folder/'masthead.png').is_file())
   self.assertNotIn('proxy-reconnect.js',(folder/'request.html').read_text())
   script=(folder/'proxy-reconnect.js').read_text();self.assertIn("fetch('/healthz'",script);self.assertNotIn("method: 'POST'",script)
 def test_managed_nginx_uses_internal_pages_preserving_app_responses(self):
  import voiceservices.rocky_tls as tls
  from unittest.mock import Mock
  with tempfile.TemporaryDirectory() as temporary:
   root=Path(temporary);addresses=Mock();addresses.current.return_value=(['10.0.2.3'],'10.0.2.3')
   tls.configure({'public_url':'https://10.0.2.3'},addresses,False,root)
   text=(root/'etc/nginx/conf.d/serviceready.conf').read_text()
   self.assertIn('error_page 500 502 503 504',text);self.assertIn('error_page 400 403 404 405 413 414 429',text);self.assertIn('internal;',text);self.assertIn('proxy_intercept_errors off;',text);self.assertNotIn('=200',text)
