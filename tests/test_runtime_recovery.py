import importlib.util,json,os,sqlite3,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock,patch
ROOT=Path(__file__).parents[1]
def load(name,file):
 spec=importlib.util.spec_from_file_location(name,ROOT/'deploy'/file);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
runtime=load('runtime_access','runtime-access.py');recovery=load('admin_reset','admin-reset.py')
class RuntimeRecoveryTests(unittest.TestCase):
 def test_private_pip_files_become_group_readable_without_writable_code(self):
  with tempfile.TemporaryDirectory() as temporary:
   root=Path(temporary)/'venv';package=root/'lib/voiceservices';package.mkdir(parents=True)
   file=package/'server.py';file.write_text('value=1');file.chmod(0o600);package.chmod(0o700)
   outside=Path(temporary)/'system-python';outside.write_text('interpreter');outside.chmod(0o600);(root/'python').symlink_to(outside)
   runtime.normalise_runtime(root,os.getgid(),os.getuid())
   self.assertEqual(file.stat().st_mode&0o777,0o640);self.assertEqual(package.stat().st_mode&0o777,0o750)
   self.assertEqual(outside.stat().st_mode&0o777,0o600)
   file.chmod(0o666);runtime.normalise_runtime(root,os.getgid(),os.getuid());self.assertEqual(file.stat().st_mode&0o022,0)
 def test_verify_imports_as_service_account_in_isolated_python(self):
  with patch.object(runtime.pwd,'getpwnam',return_value=SimpleNamespace(pw_uid=991,pw_gid=992)),patch.object(runtime.subprocess,'run') as run:
   runtime.verify_runtime();args=run.call_args
   self.assertEqual(args.kwargs['user'],991);self.assertEqual(args.kwargs['group'],992);self.assertIn('-I',args.args[0])
 def database(self,root):
  from voiceservices.web import App
  app=App({'database':str(root/'portal.sqlite'),'secure_cookies':False});app.store.create_user('admin','original-password','admin');app.store.create_user('alice','original-password')
  token=app.store.login('admin','original-password')
  return app,token,{'database':str(app.store.path)}
 def test_local_admin_reset_revokes_sessions_and_optional_factor(self):
  with tempfile.TemporaryDirectory() as temporary:
   app,token,config=self.database(Path(temporary))
   with app.store.connect() as db:
    user=db.execute("SELECT id FROM users WHERE username='admin'").fetchone()[0];db.execute('INSERT INTO twofactor(user_id,secret) VALUES(?,?)',(user,'fake-secret'))
   with patch.object(recovery.os,'geteuid',return_value=0):recovery.reset(config,'admin','replacement-password',True)
   self.assertIsNone(app.store.session(token));self.assertIsNotNone(app.store.login('admin','replacement-password'))
   with app.store.connect() as db:self.assertIsNone(db.execute('SELECT * FROM twofactor WHERE user_id=?',(user,)).fetchone())
 def test_nonroot_and_nonadministrator_resets_are_rejected(self):
  with tempfile.TemporaryDirectory() as temporary:
   app,token,config=self.database(Path(temporary))
   with patch.object(recovery.os,'geteuid',return_value=1000):
    with self.assertRaises(PermissionError):recovery.reset(config,'admin','replacement-password')
   with patch.object(recovery.os,'geteuid',return_value=0):
    with self.assertRaises(ValueError):recovery.reset(config,'alice','replacement-password')
   self.assertIsNotNone(app.store.session(token))
 def test_system_password_uses_enrolled_account_and_secret_stdin(self):
  with tempfile.TemporaryDirectory() as temporary:
   app,token,config=self.database(Path(temporary));config['auth_backend']='system'
   with patch.object(recovery.os,'geteuid',return_value=0),patch.object(recovery.pwd,'getpwnam',return_value=SimpleNamespace(pw_uid=1001,pw_gid=1001)),patch.object(recovery.grp,'getgrnam',return_value=SimpleNamespace(gr_gid=999,gr_mem=['admin'])),patch.object(recovery.subprocess,'run') as run:
    recovery.reset(config,'admin','replacement-password')
    self.assertEqual(run.call_args.kwargs['input'],'admin:replacement-password\n');self.assertNotIn('replacement-password',str(run.call_args.args[0]))
   with patch.object(recovery.os,'geteuid',return_value=0),patch.object(recovery.pwd,'getpwnam',return_value=SimpleNamespace(pw_uid=0,pw_gid=0)),patch.object(recovery.grp,'getgrnam',return_value=SimpleNamespace(gr_gid=999,gr_mem=['admin'])):
    with self.assertRaises(ValueError):recovery.reset(config,'admin','replacement-password')
 def test_old_private_addons_become_manageable_by_service_account(self):
  with tempfile.TemporaryDirectory() as temporary:
   root=Path(temporary);addon=root/'addons/downloads';addon.mkdir(parents=True);file=addon/'module.py';file.write_text('approved code');file.chmod(0o600);addon.chmod(0o700)
   runtime.normalise_addons({'database':str(root/'portal.sqlite'),'addon_directory':str(root/'addons')},os.getuid(),os.getgid())
   self.assertEqual(file.stat().st_mode&0o777,0o640);self.assertEqual(addon.stat().st_mode&0o777,0o750)
