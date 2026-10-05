import io,tempfile,unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
from voiceservices.web import App
from voiceservices import login_protection
class LoginProtectionTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.config={'database':self.tmp.name+'/db','secure_cookies':False};self.app=App(self.config)
    def tearDown(self): self.tmp.cleanup()
    def test_atomic_persistent_budgets_and_expiry(self):
        env={'REMOTE_ADDR':'192.0.2.1','HTTP_X_FORWARDED_FOR':'198.51.100.1'}
        with patch.object(login_protection.time,'time',return_value=1000):
            with ThreadPoolExecutor(max_workers=8) as pool: results=list(pool.map(lambda _:login_protection.reserve(self.app,env,'login'),range(20)))
            self.assertEqual(results.count(0),10)
            self.assertEqual(login_protection.reserve(App(self.config),env,'login'),300)
            self.assertEqual(login_protection.reserve(self.app,{'REMOTE_ADDR':'192.0.2.2'},'login'),0)
            self.assertEqual(login_protection.reserve(self.app,env,'mfa'),0)
        with patch.object(login_protection.time,'time',return_value=1300): self.assertEqual(login_protection.reserve(self.app,env,'login'),0)
    def test_password_and_mfa_endpoints_throttle_before_work(self):
        for path in ('/login','/login/verify'):
            for _ in range(10):
                self.app({'PATH_INFO':path,'REQUEST_METHOD':'POST','REMOTE_ADDR':'192.0.2.9','CONTENT_LENGTH':'0','wsgi.input':io.BytesIO()},lambda s,h:None)
            response={}
            def start(s,h): response.update(status=s,headers=dict(h))
            body=b''.join(self.app({'PATH_INFO':path,'REQUEST_METHOD':'POST','REMOTE_ADDR':'192.0.2.9','CONTENT_LENGTH':'0','wsgi.input':io.BytesIO()},start))
            self.assertEqual(response['status'],'429 Too Many Requests');self.assertGreater(int(response['headers']['Retry-After']),0);self.assertIn(b'/static/style.css',body)
    def test_failure_log_cannot_be_injected(self):
        with self.assertLogs('serviceready.auth',level='WARNING') as logs:
            login_protection.failed({'REMOTE_ADDR':'192.0.2.3','HTTP_X_FORWARDED_FOR':'203.0.113.5','username':'bad\nlogin_failed ip=203.0.113.5'},'login')
        self.assertIn('login_failed ip=192.0.2.3',logs.output[0]);self.assertNotIn('203.0.113.5',logs.output[0])
    def test_configurable_security_and_source_block(self):
        from voiceservices import security
        user={'role':'admin','csrf':'test'};env={'REMOTE_ADDR':'192.0.2.4'}
        security.change(self.app,user,{'login_limit':'2','window':'120','automatic_blocks':'yes','failure_limit':'2','block_seconds':'600','remember_enabled':'no','registration_enabled':'no','session_hours':'2'})
        self.assertEqual(security.duration(self.app,True),7200)
        self.assertEqual(login_protection.reserve(self.app,env,'login'),0)
        self.assertEqual(login_protection.reserve(self.app,env,'login'),0)
        self.assertGreater(login_protection.reserve(self.app,env,'login'),0)
        login_protection.failed(env,'login',self.app);login_protection.failed(env,'mfa',self.app)
        self.assertGreater(login_protection.reserve(self.app,env,'mfa'),500)
        self.assertIn('192.0.2.4',security.render(self.app,user))
        security.change(self.app,user,{'action':'unblock','source':'192.0.2.4'})
        self.assertEqual(login_protection.reserve(self.app,env,'login'),0)
        reloaded=App(self.config)
        with reloaded.store.connect() as db:
            import json
            reloaded.config['security']=json.loads(db.execute("SELECT value FROM portal_settings WHERE key='security'").fetchone()[0])
        self.assertEqual(security.settings(reloaded)['login_limit'],2)
        with self.assertRaises(PermissionError): security.change(self.app,{'role':'user'},{})
        with self.assertRaises(ValueError): security.change(self.app,user,{'window':'0'})
        response={}
        body=b''.join(self.app({'PATH_INFO':'/create-account','REQUEST_METHOD':'GET'},lambda s,h:response.update(status=s)))
        self.assertEqual(response['status'],'403 Forbidden')
        body=b''.join(self.app({'PATH_INFO':'/login','REQUEST_METHOD':'GET'},lambda s,h:None))
        self.assertNotIn(b'name="remember"',body);self.assertNotIn(b'New here?',body)
