"""Exercise the actual installer configuration generator without touching the OS."""
import json,os,re,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch

class AlpineInstallerTests(unittest.TestCase):
    def generate(self,url,tls):
        root=Path(__file__).resolve().parents[1]
        shell=(root/'install-alpine.sh').read_text()
        script=re.search(r"<<'PY'\n(.*?)\nPY",shell,re.S).group(1)
        with tempfile.TemporaryDirectory() as temporary:
            output=Path(temporary)/'config.json'
            script=script.replace('/etc/serviceready/config.json',str(output))
            with patch('voiceservices.network_address.Addresses.current',return_value=(['192.168.56.20'],'192.168.56.20')),patch.object(sys,'argv',['installer',str(root/'config.bare.json'),url]),patch.dict(os.environ,{'SERVICEREADY_LOCAL_TLS':str(tls)}):
                exec(compile(script,'installer-config','exec'),{})
            return json.loads(output.read_text())
    def test_tls_bare_loopback_and_alpine_accounts(self):
        config=self.generate('https://192.168.56.20',1)
        self.assertEqual(config['initial_modules'],[])
        self.assertEqual(config['listen_host'],'127.0.0.1')
        self.assertTrue(config['secure_cookies'])
        self.assertEqual(config['auth_backend'],'alpine')
    def test_http_testbed(self):
        config=self.generate('http://192.168.56.20:8080',0)
        self.assertEqual(config['listen_host'],'0.0.0.0')
        self.assertFalse(config['secure_cookies'])
    def test_local_tls_rejects_http_and_other_ports(self):
        for url in ['http://192.168.56.20:8080','https://192.168.56.20:8443','https://user:secret@host','https://host/path']:
            with self.subTest(url=url),self.assertRaises(SystemExit):self.generate(url,1)
    def test_proxy_config_matches_loopback_port(self):
        root=Path(__file__).resolve().parents[1]
        script=re.search(r"<<'PYTLS'\n(.*?)\nPYTLS",(root/'install-alpine.sh').read_text(),re.S).group(1)
        with tempfile.TemporaryDirectory() as temporary:
            config=Path(temporary)/'config.json';caddy=Path(temporary)/'Caddyfile'
            config.write_text(json.dumps({'public_url':'https://192.168.56.20','listen_port':8080}))
            script=script.replace('/etc/serviceready/config.json',str(config)).replace('/etc/caddy/Caddyfile',str(caddy))
            exec(compile(script,'installer-tls','exec'),{})
            self.assertEqual(caddy.read_text(),'https://192.168.56.20 {\n    tls internal\n    reverse_proxy 127.0.0.1:8080\n}\n')
            self.assertEqual(json.loads(config.read_text())['listen_host'],'127.0.0.1')
    def test_blank_url_follows_address_by_default(self):
        for tls,expected in [(0,'http://192.168.56.20:8080'),(1,'https://192.168.56.20')]:
            with self.subTest(tls=tls):
                config=self.generate('',tls)
                self.assertEqual(config['public_url'],expected)
                self.assertTrue(config['automatic_public_url'])
                self.assertEqual(config['automatic_local_tls'],bool(tls))
