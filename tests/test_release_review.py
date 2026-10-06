import importlib.util,json,tempfile,unittest
from pathlib import Path
from unittest.mock import Mock,patch
import test_app
from voiceservices import addon_updates,maintenance
spec=importlib.util.spec_from_file_location('review_worker',Path(__file__).parents[1]/'deploy/maintenance-worker.py');worker=importlib.util.module_from_spec(spec);spec.loader.exec_module(worker)
class ReleaseReviewTests(unittest.TestCase):
 setUp=test_app.PortalTests.setUp
 tearDown=test_app.PortalTests.tearDown
 request=test_app.PortalTests.request
 user=test_app.PortalTests.user
 def test_review_html_escaped_and_exact_release_submitted(self):
  token,user=self.user('admin');self.app.store.accounts=Mock()
  commit='a'*40
  self.app.store.accounts.call.return_value={'state':'complete','review':{'state':'ready','commit':commit,'version':'1.19.0','changelog':'<script>unsafe</script>'}}
  body=self.request('/admin/host',token=token)['body']
  self.assertIn('&lt;script&gt;unsafe',body);self.assertIn('Proceed with update',body);self.assertIn('Decline this version',body)
  self.request('/admin/host','POST',{'csrf':user['csrf'],'update':'insap-install','release':commit},token)
  self.assertIn(unittest.mock.call('maintenance-start','insap-install',commit),self.app.store.accounts.call.call_args_list)
  self.request('/admin/host','POST',{'csrf':user['csrf'],'update':'insap-decline','release':commit},token)
  self.assertIn(unittest.mock.call('maintenance-decline','',commit),self.app.store.accounts.call.call_args_list)
 def test_staging_remembers_declined_version_without_changing_checkout(self):
  with tempfile.TemporaryDirectory() as root:
   review=Path(root)/'review.json';review.write_text(json.dumps({'declined_versions':['1.19.0']}))
   with patch.object(worker,'REVIEW',review),patch.object(worker.subprocess,'check_output',side_effect=['a'*40,"__version__ = '1.19.0'","__version__ = '1.18.3'",'# changes']) as git:
    result=worker.stage_review(Path(root))
   self.assertEqual(result['state'],'declined');self.assertEqual(result['commit'],'a'*40)
   self.assertFalse(any('merge' in call.args[0] for call in git.call_args_list))
 def addon_fixture(self):
  path=self.app.modules.root/'downloads'/'manifest.json';manifest=json.loads(path.read_text());manifest['version']='1.18.3';path.write_text(json.dumps(manifest))
  catalog={'downloads':dict(self.app.modules.approved['downloads'],version='1.19.0')}
  def fetch(url,limit=0):
   if '/commits/main' in url:return json.dumps({'sha':'a'*40}).encode()
   if url.endswith('addon_catalog.json'):return json.dumps(catalog).encode()
   if url.endswith('.sraddon'):return (Path(__file__).parents[1]/'packages/addons/1.19.0/downloads-1.19.0.sraddon').read_bytes()
   return b'# Downloads changes\nSettings retained.'
  return fetch,catalog
 def test_individual_addon_review_replace_and_settings_retained(self):
  token,user=self.user('admin');fetch,catalog=self.addon_fixture()
  with self.app.store.connect() as db:db.execute("INSERT OR REPLACE INTO addons VALUES('downloads','{\"example\":true}')")
  with patch.object(addon_updates,'fetch',side_effect=fetch):
   addon_updates.change(self.app,user,{'action':'check-addon-update','module':'downloads'})
   self.assertEqual(addon_updates.settings(self.app)['downloads']['state'],'ready')
   with self.assertRaises(ValueError):addon_updates.change(self.app,user,{'action':'install-addon-update','module':'downloads','release':'b'*40})
   addon_updates.change(self.app,user,{'action':'install-addon-update','module':'downloads','release':'a'*40})
  self.assertTrue(self.app.modules.installed('downloads'));self.assertTrue((self.app.modules.root/'downloads'/'CHANGELOG.md').exists())
  with self.app.store.connect() as db:self.assertIn('example',db.execute("SELECT settings FROM addons WHERE id='downloads'").fetchone()[0])
 def test_addon_decline_persists_and_uninstalled_addon_not_updated(self):
  token,user=self.user('admin');fetch,catalog=self.addon_fixture()
  with patch.object(addon_updates,'fetch',side_effect=fetch):
   addon_updates.change(self.app,user,{'action':'check-addon-update','module':'downloads'})
   addon_updates.change(self.app,user,{'action':'decline-addon-update','module':'downloads','release':'a'*40})
   addon_updates.change(self.app,user,{'action':'check-addon-update','module':'downloads'})
  self.assertEqual(addon_updates.settings(self.app)['downloads']['state'],'declined')
  self.app.modules.change('downloads',False)
  with self.assertRaises(ValueError):addon_updates.change(self.app,user,{'action':'check-addon-update','module':'downloads'})
 def test_addon_changed_code_requires_core_update(self):
  token,user=self.user('admin');fetch,catalog=self.addon_fixture();catalog['downloads']['sha256']='b'*64
  with patch.object(addon_updates,'fetch',side_effect=fetch):addon_updates.change(self.app,user,{'action':'check-addon-update','module':'downloads'})
  self.assertEqual(addon_updates.settings(self.app)['downloads']['state'],'core-required')

 def test_tools_runner_captures_output_in_private_log(self):
  with tempfile.TemporaryDirectory() as root:
   log=Path(root)/'tools.log'
   with patch.object(worker,'TOOLS_LOG',log),patch.object(worker.subprocess,'run') as run:
    worker.tools_run(['/usr/bin/dnf','install','gcc'])
   self.assertIn('Running: /usr/bin/dnf install gcc',log.read_text());self.assertEqual(log.stat().st_mode&0o777,0o600)
   self.assertEqual(run.call_args.kwargs['stderr'],worker.subprocess.STDOUT)
   target=Path(root)/'target';target.write_text('retain');log.unlink();log.symlink_to(target)
   with patch.object(worker,'TOOLS_LOG',log):
    with self.assertRaises(OSError):worker.tools_run(['/usr/bin/dnf','install','gcc'])
   self.assertEqual(target.read_text(),'retain')
