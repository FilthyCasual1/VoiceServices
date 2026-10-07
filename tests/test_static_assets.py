import tempfile, unittest
from pathlib import Path
from unittest.mock import patch
from voiceservices import static_assets
from voiceservices.web import App

class StaticAssetTests(unittest.TestCase):
    def tearDown(self):static_assets._read.cache_clear()

    def test_reuses_read_and_invalidates_when_asset_changes(self):
        with tempfile.TemporaryDirectory() as root:
            root=Path(root);file=root/'style.css';file.write_text('first')
            with patch.object(static_assets,'ROOT',root):
                first=static_assets.get('/static/style.css')
                with patch.object(Path,'read_bytes',side_effect=AssertionError('Unexpected reread')):
                    self.assertEqual(static_assets.get('/static/style.css'),first)
                file.write_text('replacement')
                second=static_assets.get('/static/style.css')
                self.assertEqual(second[0],b'replacement');self.assertNotEqual(first[2],second[2])
                self.assertIsNone(static_assets.get('/static/../config.json'))

    def test_static_requests_skip_settings_database_and_keep_conditional_cache(self):
        with tempfile.TemporaryDirectory() as root:
            app=App({'database':root+'/db.sqlite','secure_cookies':False})
            def request(etag=''):
                result={}
                def start(status,headers):result.update(status=status,headers=dict(headers))
                result['body']=b''.join(app({'PATH_INFO':'/static/style.css','REQUEST_METHOD':'GET','HTTP_IF_NONE_MATCH':etag},start))
                return result
            with patch.object(app.store,'connect',side_effect=AssertionError('Static asset queried database')):
                first=request();self.assertEqual(first['status'],'200 OK')
                second=request(first['headers']['ETag']);self.assertEqual(second['status'],'304 Not Modified');self.assertEqual(second['body'],b'')
