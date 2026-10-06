import io,json,unittest
from unittest.mock import patch,Mock
import test_app
from voiceservices import external_auth as auth,user_management
class IdentityTests(unittest.TestCase):
    setUp=test_app.PortalTests.setUp
    tearDown=test_app.PortalTests.tearDown
    request=test_app.PortalTests.request
    user=test_app.PortalTests.user
    def enable(self,kind='ldap',**values):
        s=dict(auth.settings(self.app,kind),enabled=True,allowed_users='alice\nadmin',**values)
        with self.app.store.connect() as db:db.execute('INSERT OR REPLACE INTO portal_settings VALUES(?,?)',('auth-'+kind,json.dumps(s)))
    def test_isolation_local_admin_and_deactivation(self):
        self.enable()
        with patch.object(auth,'check',return_value=True) as check:
            token=auth.login(self.app,'ldap','alice','remote-password')
            person=self.app.store.session(token)
            self.assertEqual(person['username'],'ldap:alice');self.assertEqual(person['role'],'user')
            self.assertIsNotNone(auth.login(self.app,'local','admin','a-long-password'))
            remote_admin=auth.login(self.app,'ldap','admin','remote-password')
            self.assertEqual(self.app.store.session(remote_admin)['role'],'user')
            check.reset_mock();self.assertIsNone(auth.login(self.app,'ldap','unknown','x'));check.assert_not_called()
            local,admin=self.user('admin')
            with self.assertRaises(ValueError):user_management.change(self.app,admin,{'action':'role','user':str(person['id']),'role':'admin'})
            user_management.change(self.app,admin,{'action':'delete','user':str(person['id']),'confirm':'yes'})
            self.assertIsNone(auth.login(self.app,'ldap','alice','remote-password'))
    def test_external_password_changes_and_reauthentication(self):
        self.enable()
        with patch.object(auth,'check',return_value=True):
            token=auth.login(self.app,'ldap','alice','pw');person=self.app.store.session(token)
            self.assertIsNotNone(self.app.store.login(person['username'],'pw'))
            with self.assertRaises(ValueError):self.app.store.change_password(person,'pw','new-long-password')
            page=self.request('/account/security',token=token)['body']
            self.assertIn('identity provider',page)
    def test_tls_and_portal_admin_requirements(self):
        token,admin=self.user('admin')
        with self.assertRaises(ValueError):auth.change(self.app,admin,{'provider':'ldap','current_password':'a-long-password','enabled':'yes','allowed_users':'alice','host':'ldap.local'})
        user=self.app.store.session(self.user('alice')[0])
        self.assertEqual(self.request('/admin/authentication',token=self.user('alice')[0])['status'],'403 Forbidden')
        page=self.request('/admin/authentication',token=token)['body']
        self.assertIn('LDAP',page);self.assertIn('Kerberos',page);self.assertIn('RADIUS',page)
    def test_radius_message_authenticator_required(self):
        from pyrad.client import Client
        reply=Mock(code=2);reply.verify_message_authenticator.return_value=False
        with patch.object(Client,'SendPacket',return_value=reply):
            self.assertFalse(auth.check('radius',{'host':'127.0.0.1','port':1812,'secret':'shared'},'alice','password'))
        reply.verify_message_authenticator.return_value=True
        with patch.object(Client,'SendPacket',return_value=reply):
            self.assertTrue(auth.check('radius',{'host':'127.0.0.1','port':1812,'secret':'shared'},'alice','password'))

    def test_kerberos_sso_namespace_and_mfa(self):
        import base64,types
        self.enable('kerberos',realm='EXAMPLE.TEST')
        s=auth.settings(self.app,'kerberos');s['allowed_users']='alice@EXAMPLE.TEST'
        with self.app.store.connect() as db:db.execute("UPDATE portal_settings SET value=? WHERE key='auth-kerberos'",(json.dumps(s),))
        context=Mock(complete=True,initiator_name='alice@EXAMPLE.TEST',mech='krb5');context.step.return_value=b'server-token'
        self.app.sso_pending['nonce']=(9999999999,context,'127.0.0.1')
        import http.cookies
        cookie=http.cookies.SimpleCookie('vs_sso=nonce');response={}
        def send(status,body,extra=()):response.update(status=status,headers=dict(extra));return body
        fake=types.SimpleNamespace(MechType=types.SimpleNamespace(kerberos='krb5'))
        with patch.dict('sys.modules',{'gssapi':fake}):
            auth.sso(self.app,{'REQUEST_METHOD':'GET','REMOTE_ADDR':'127.0.0.1','HTTP_AUTHORIZATION':'Negotiate '+base64.b64encode(b'ticket').decode()},cookie,send)
        self.assertEqual(response['status'],'303 See Other')
        self.assertIn('Secure',response['headers']['Set-Cookie'])
        with self.app.store.connect() as db:
            row=db.execute("SELECT role FROM users WHERE username='kerberos:alice@EXAMPLE.TEST'").fetchone()
            self.assertEqual(row['role'],'user')
    def test_provider_disable_invalidates_pending_session(self):
        self.enable()
        with patch.object(auth,'check',return_value=True):token=auth.login(self.app,'ldap','alice','pw')
        s=auth.settings(self.app,'ldap');s['enabled']=False
        with self.app.store.connect() as db:db.execute("UPDATE portal_settings SET value=? WHERE key='auth-ldap'",(json.dumps(s),))
        self.assertIsNone(self.app.store.session(token))
