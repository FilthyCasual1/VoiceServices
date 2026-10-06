import io,time,unittest
from unittest.mock import patch
import pyotp
import test_app
from voiceservices import twofactor,account
class FactorTests(unittest.TestCase):
    setUp=test_app.PortalTests.setUp
    tearDown=test_app.PortalTests.tearDown
    request=test_app.PortalTests.request
    user=test_app.PortalTests.user
    def test_enroll_login_replay_recovery_and_disable(self):
        token,user=self.user('alice')
        # The normal test fixture stores this password.
        twofactor.change(self.app,user,{'action':'factor-start','current_password':'a-long-password'},token)
        row=twofactor.state(self.app,user)
        self.assertTrue(twofactor.qr(self.app,user,token).startswith(b'\x89PNG'))
        self.assertIsNone(twofactor.qr(self.app,user,'wrong-session'))
        code=pyotp.TOTP(row['pending']).now()
        note=twofactor.change(self.app,user,{'action':'factor-confirm','code':code},token)
        recovery=note.split(': ')[-1].split(', ')[0]
        pending=twofactor.challenge(self.app,user)
        with self.app.store.connect() as db: csrf=db.execute('SELECT csrf FROM factor_challenges').fetchone()[0]
        self.assertIsNone(twofactor.finish(self.app,pending,csrf,code))
        self.assertIsNone(twofactor.finish(self.app,pending,'wrong',recovery))
        session=twofactor.finish(self.app,pending,csrf,recovery)
        self.assertIsNotNone(self.app.store.session(session))
        self.assertIsNone(twofactor.finish(self.app,pending,csrf,recovery))
        with self.app.store.connect() as db:
            self.assertNotIn(recovery,db.execute('SELECT recovery FROM twofactor').fetchone()[0])
        result=self.request('/login','POST',{'username':'alice','password':'a-long-password'})
        self.assertEqual(result['headers']['Location'],'/login/verify')
        self.assertNotIn('vs_session=',result['headers']['Set-Cookie'])
        second=note.split(': ')[-1].split(', ')[1]
        twofactor.change(self.app,user,{'action':'factor-disable','current_password':'a-long-password','code':second},session)
        self.assertFalse(twofactor.state(self.app,user).get('secret'))
    def test_admin_notifications_are_authorized_and_targeted(self):
        admin_token,admin=self.user('admin');token,user=self.user('alice')
        payload={'csrf':admin['csrf'],'recipient':str(user['id']),'title':'Maintenance','body':'Service restart tonight.'}
        self.assertEqual(self.request('/admin/notifications','POST',payload,admin_token)['status'],'200 OK')
        self.assertIn('Maintenance',self.request('/account/inbox',token=token)['body'])
        self.assertNotIn('Maintenance',self.request('/account/inbox',token=admin_token)['body'])
        payload['csrf']=user['csrf']
        self.assertEqual(self.request('/admin/notifications','POST',payload,token)['status'],'403 Forbidden')

    def test_failure_limit_and_expired_challenge(self):
        token,user=self.user('alice')
        with self.app.store.connect() as db: db.execute('INSERT INTO twofactor(user_id,secret) VALUES(?,?)',(user['id'],pyotp.random_base32()))
        pending=twofactor.challenge(self.app,user)
        with self.app.store.connect() as db: csrf=db.execute('SELECT csrf FROM factor_challenges').fetchone()[0]
        for _ in range(10): self.assertIsNone(twofactor.finish(self.app,pending,csrf,'invalid'))
        self.assertGreater(twofactor.state(self.app,user)['blocked_until'],time.time())
        with self.app.store.connect() as db: db.execute('UPDATE factor_challenges SET expires=0')
        self.assertIn('expired',twofactor.login_page(self.app,pending))

    def test_recovery_token_is_verified_expiring_and_single_use(self):
        from voiceservices import recovery
        admin_token,admin=self.user('admin');token,user=self.user('alice')
        with self.assertRaises(ValueError): recovery.issue(self.app,admin,{'username':'alice','current_password':'a-long-password'})
        note=recovery.issue(self.app,admin,{'username':'alice','current_password':'a-long-password','verified':'yes'})
        code=note.rsplit(': ',1)[1]
        recovery.reset(self.app,{'recovery_code':code,'new_password':'replacement-password','confirm_password':'replacement-password'})
        self.assertIsNone(self.app.store.session(token))
        self.assertIsNone(self.app.store.login('alice','a-long-password'))
        self.assertIsNotNone(self.app.store.login('alice','replacement-password'))
        with self.assertRaises(ValueError): recovery.reset(self.app,{'recovery_code':code,'new_password':'replacement-password','confirm_password':'replacement-password'})
        page=self.request('/recover')
        self.assertEqual(page['status'],'200 OK');self.assertIn('Request account recovery',page['body'])
        self.assertIn('Recover your account',self.request('/login')['body'])
    def test_maintenance_requires_admin_and_backend(self):
        from voiceservices import maintenance
        token,user=self.user('alice');admin_token,admin=self.user('admin')
        with self.assertRaises(PermissionError): maintenance.change(self.app,user,{'update':'os'})
        with self.assertRaises(ValueError): maintenance.change(self.app,admin,{'update':'os'})
        from unittest.mock import Mock
        self.app.store.accounts=Mock()
        self.app.store.accounts.call.return_value={'state':'idle','message':'Ready'}
        maintenance.change(self.app,admin,{'update':'insap'})
        self.app.store.accounts.call.assert_called_with('maintenance-start','insap','')
        self.assertIn('Grab INSAP update',maintenance.render(self.app,admin))
