import base64,io,json,os,pwd,time,unittest
from unittest.mock import patch,Mock
from types import SimpleNamespace
import test_app,test_account_broker
from addon_support import install
broker=test_account_broker.broker
class HostToolTests(unittest.TestCase):
    setUp=test_app.PortalTests.setUp
    tearDown=test_app.PortalTests.tearDown
    request=test_app.PortalTests.request
    user=test_app.PortalTests.user
    def test_optional_routes_and_admin_only(self):
        install(self.app,'host-tools');token,user=self.user('admin')
        page=self.request('/admin/terminal',token=token)['body'];self.assertIn('Alpine host account broker',page)
        self.assertEqual(self.request('/admin/host',token=self.user('alice')[0])['status'],'403 Forbidden')
        self.app.modules.change('host-tools',False)
        self.assertEqual(self.request('/admin/terminal',token=token)['status'],'404 Not Found')
    def test_terminal_api_and_binding(self):
        install(self.app,'host-tools');token,user=self.user('admin')
        self.app.base='https://portal.example';self.app.secure=True
        self.app.store.accounts=Mock();self.app.store.accounts.call.return_value={'token':'test'}
        response=self.request('/admin/terminal/io','POST',{'csrf':user['csrf'],'action':'open','password':'secret'},token)
        self.assertEqual(response['status'],'200 OK')
        args=self.app.store.accounts.call.call_args.args
        self.assertEqual(args[:3],('terminal-open','admin','secret'));self.assertEqual(len(json.loads(args[3])['session']),64)
        self.assertEqual(self.request('/admin/terminal/io','POST',{'csrf':'bad','action':'read'},token)['status'],'403 Forbidden')
    def test_terminal_rejects_cross_session_and_wrong_password(self):
        with patch.object(broker,'authenticate',return_value=False):
            with self.assertRaises(ValueError):broker.handle({'action':'terminal-open','username':'admin','password':'wrong','new_password':json.dumps({'session':'a'*64})})
        broker.TERMINALS['fake']={'username':'admin','binding':'a'*64,'touched':time.monotonic(),'created':time.monotonic(),'process':Mock(poll=lambda:None)}
        try:
            with self.assertRaises(ValueError):broker.handle({'action':'terminal-read','username':'admin','password':'','new_password':json.dumps({'token':'fake','session':'b'*64})})
        finally:broker.TERMINALS.pop('fake',None)
    def test_actual_unprivileged_pty(self):
        if os.geteuid()==0:self.skipTest('Never start a real root shell in this test')
        entry=pwd.getpwuid(os.getuid());name=entry.pw_name
        request={'action':'terminal-open','username':name,'password':'test','new_password':json.dumps({'session':'a'*64})}
        with patch.object(broker,'authenticate',return_value=True),patch.object(broker.os,'initgroups'),patch.object(broker.os,'setuid'),patch.object(broker.os,'setgid'):
            opened=broker.terminal_handle(request)
        key=opened['status']['token']
        def action(kind,**extra):return broker.terminal_handle({'action':'terminal-'+kind,'username':name,'password':'','new_password':json.dumps(dict(session='a'*64,token=key,**extra))})
        try:
            command=b'printf "HOST_"; printf "PTY_OK\\n"\r'
            action('write',data=base64.b64encode(command).decode());output=b''
            for _ in range(20):
                output+=base64.b64decode(action('read')['status'].get('data',''))
                if b'HOST_PTY_OK' in output:break
                time.sleep(.05)
            self.assertIn(b'HOST_PTY_OK',output)
        finally:action('close')

    def test_cleanup_preserves_recent_files_and_symlink_targets(self):
        import importlib.util
        from pathlib import Path
        spec=importlib.util.spec_from_file_location('maintenance_worker',Path(__file__).parents[1]/'deploy/maintenance-worker.py')
        worker=importlib.util.module_from_spec(spec);spec.loader.exec_module(worker)
        folder=Path(self.tmp.name)/'cleanup';folder.mkdir()
        old=folder/'old';old.write_text('old');os.utime(old,(time.time()-8*86400,)*2)
        recent=folder/'recent';recent.write_text('recent')
        outside=Path(self.tmp.name)/'outside';outside.write_text('keep');(folder/'link').symlink_to(outside)
        self.assertEqual(worker.clean_temp(folder),1);self.assertTrue(recent.exists());self.assertEqual(outside.read_text(),'keep')
        log=folder/'test.log';log.write_bytes(b'old'+b'x'*1024**2)
        (folder/'linked.log').symlink_to(outside)
        self.assertEqual(worker.trim_logs(folder),1);self.assertEqual(log.stat().st_size,1024**2);self.assertEqual(outside.read_text(),'keep')
