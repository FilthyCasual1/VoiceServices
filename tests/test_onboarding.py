import hashlib,time,unittest
from unittest.mock import Mock
import test_app
from voiceservices import onboarding
class OnboardingTests(unittest.TestCase):
 setUp=test_app.PortalTests.setUp
 tearDown=test_app.PortalTests.tearDown
 request=test_app.PortalTests.request
 user=test_app.PortalTests.user
 def code(self,expires=None,revoked=0):
  code='test-invitation-'+str(time.time_ns())
  with self.app.store.connect() as db:db.execute('INSERT INTO invitations(digest,created,expires,revoked) VALUES(?,?,?,?)',(hashlib.sha256(code.encode()).hexdigest(),int(time.time()),expires or int(time.time())+3600,revoked))
  return code
 def signup(self,code,username='new-person',**extra):
  import re
  body=self.request('/create-account')['body'];nonce=re.search('name="csrf" value="([^"]+)"',body)[1]
  return self.request('/create-account','POST',dict(csrf=nonce,invitation=code,username=username,password='a-long-new-password',confirm_password='a-long-new-password',**extra),'unused; vs_signup='+nonce)
 def test_valid_code_creates_profile_and_is_single_use(self):
  code=self.code();result=self.signup(code,display_name='Alex',email='alex@example.net',timezone='America/Chicago')
  self.assertEqual(result['headers']['Location'],'/welcome')
  token=self.app.store.login('new-person','a-long-new-password');user=self.app.store.session(token)
  self.assertEqual(user['display_name'],'Alex');self.assertEqual(user['role'],'user')
  self.assertIn('Your account is ready',self.request('/welcome',token=token)['body'])
  self.assertIn('already used',self.signup(code,'second-person')['body'])
  with self.app.store.connect() as db:
   self.assertEqual(db.execute('SELECT email FROM account_profiles WHERE user_id=?',(user['id'],)).fetchone()[0],'alex@example.net')
   self.assertFalse(db.execute("SELECT 1 FROM users WHERE username='second-person'").fetchone())
 def test_missing_expired_revoked_codes_do_not_create_users(self):
  for code in ('',self.code(int(time.time())-1),self.code(revoked=1)):
   self.assertIn('Invitation code is invalid',self.signup(code)['body'])
  with self.app.store.connect() as db:self.assertFalse(db.execute("SELECT 1 FROM users WHERE username='new-person'").fetchone())
 def test_invalid_profile_does_not_consume_invitation(self):
  code=self.code();self.assertIn('email address',self.signup(code,email='bad')['body'])
  self.assertEqual(self.signup(code)['status'],'303 See Other')
 def test_invalid_invitation_never_creates_os_account(self):
  self.app.store.accounts=Mock()
  with self.assertRaises(ValueError):self.app.store.create_user('new-person','long-enough-password',invitation='invalid')
  self.app.store.accounts.call.assert_not_called()
 def test_admin_issue_and_revoke(self):
  token,actor=self.user('admin');note=onboarding.invitation_action(self.app,actor,{'action':'invite-create','days':'7'})
  self.assertIn('shown once',note)
  with self.app.store.connect() as db:row=db.execute('SELECT * FROM invitations').fetchone();digest=row['digest']
  self.assertNotIn(digest,note)
  onboarding.invitation_action(self.app,actor,{'action':'invite-revoke','invitation':digest})
  with self.app.store.connect() as db:self.assertEqual(db.execute('SELECT revoked FROM invitations WHERE digest=?',(digest,)).fetchone()[0],1)
  with self.assertRaises(PermissionError):onboarding.invitation_action(self.app,{'role':'user'},{'action':'invite-create'})
