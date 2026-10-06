import io,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import test_app
class UploadStagingTests(unittest.TestCase):
 setUp=test_app.PortalTests.setUp
 tearDown=test_app.PortalTests.tearDown
 user=test_app.PortalTests.user
 def body(self,user):
  raw=(b'--B\r\nContent-Disposition: form-data; name="csrf"\r\n\r\n'+user['csrf'].encode()+b'\r\n--B\r\nContent-Disposition: form-data; name="file"; filename="tool.exe"\r\nContent-Type: application/octet-stream\r\n\r\ninternal-tool\r\n--B--\r\n')
  return {'CONTENT_LENGTH':str(len(raw)),'CONTENT_TYPE':'multipart/form-data; boundary=B','wsgi.input':io.BytesIO(raw)}
 def setup_volume(self,root):
  volume=Path(root)/'disk';volume.mkdir();staging=volume/'tmp';staging.mkdir(mode=0o700);repository=volume/'downloads';repository.mkdir()
  library=self.app.downloads;library.root=repository;library.volume_config={'data_mount':str(volume),'data_disk_uuid':'test'}
  volume.chmod(0o555)
  return library,volume,staging
 def test_upload_succeeds_without_writing_volume_root(self):
  token,user=self.user('admin')
  with tempfile.TemporaryDirectory() as root:
   library,volume,staging=self.setup_volume(root)
   try:
    with patch.object(library,'require_volume'),patch('voiceservices.updates.tempfile.mkstemp',wraps=tempfile.mkstemp) as temporary:
     self.assertEqual(library.upload(self.body(user),user),'tool.exe')
    self.assertEqual(Path(temporary.call_args.kwargs['dir']),staging)
    self.assertEqual((library.root/'tool.exe').read_bytes(),b'internal-tool');self.assertEqual(list(staging.iterdir()),[])
    self.assertEqual(volume.stat().st_mode&0o777,0o555)
   finally:volume.chmod(0o755)
 def test_missing_disk_never_creates_temporary_upload_on_boot_disk(self):
  token,user=self.user('admin')
  with patch.object(self.app.downloads,'require_volume',side_effect=ValueError('Upload disk is unavailable')),patch('voiceservices.updates.tempfile.mkstemp') as temporary:
   with self.assertRaisesRegex(ValueError,'disk is unavailable'):self.app.downloads.upload(self.body(user),user)
   temporary.assert_not_called()
 def test_staging_failure_has_actionable_error_and_no_published_file(self):
  token,user=self.user('admin')
  with patch.object(self.app.downloads,'require_volume'),patch('voiceservices.updates.tempfile.mkstemp',side_effect=PermissionError('Permission denied')):
   with self.assertRaisesRegex(ValueError,'Upload staging is unavailable'):self.app.downloads.upload(self.body(user),user)
  self.assertFalse((self.app.downloads.root/'tool.exe').exists())
