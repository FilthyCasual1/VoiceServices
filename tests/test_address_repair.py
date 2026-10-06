import importlib.util,json,subprocess,tempfile,unittest
from pathlib import Path
from unittest.mock import Mock,patch
spec=importlib.util.spec_from_file_location('address_repair',Path(__file__).resolve().parents[1]/'deploy/repair-address.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
class AddressRepairTests(unittest.TestCase):
    def test_stale_address_repair_and_failed_reload_rollback(self):
        for failure in (False,True):
            with self.subTest(failure=failure),tempfile.TemporaryDirectory() as temporary:
                root=Path(temporary);config=root/'config.json';caddy=root/'Caddyfile'
                original=json.dumps({'public_url':'https://10.0.2.15','database':'keep.sqlite','automatic_public_url':False})
                old='# ServiceReady managed address configuration\nhttps://10.0.2.15 { tls internal }\n'
                config.write_text(original);config.chmod(0o640);caddy.write_text(old)
                addresses=Mock();addresses.current.return_value=(['10.0.2.3'],'10.0.2.3')
                with patch.object(module.subprocess,'run',side_effect=[None,subprocess.CalledProcessError(1,'caddy')] if failure else None):
                    if failure:
                        with self.assertRaises(subprocess.CalledProcessError):module.repair(config,caddy,root/'backups',addresses)
                        self.assertEqual(config.read_text(),original);self.assertEqual(caddy.read_text(),old)
                    else:
                        url,backup=module.repair(config,caddy,root/'backups',addresses)
                        result=json.loads(config.read_text())
                        self.assertEqual(url,'https://10.0.2.3');self.assertEqual(result['database'],'keep.sqlite')
                        self.assertTrue(result['automatic_public_url']);self.assertTrue(result['automatic_local_tls'])
                        self.assertIn('https://10.0.2.3',caddy.read_text());self.assertEqual((backup/'config.json').read_text(),original)
                        self.assertEqual(config.stat().st_mode&0o777,0o640)
    def test_manual_proxy_is_untouched(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);config=root/'config.json';caddy=root/'Caddyfile'
            config.write_text('{}');caddy.write_text('manual proxy')
            with self.assertRaises(ValueError):module.repair(config,caddy,root/'backups',Mock())
            self.assertEqual(caddy.read_text(),'manual proxy');self.assertFalse((root/'backups').exists())
