import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch,Mock
from voiceservices.network_address import Addresses,origin,caddy_config
from voiceservices import address_service

class AddressTests(unittest.TestCase):
    def test_live_lease_change_and_route_preference(self):
        reader=Addresses()
        def output(address):return [json.dumps([{'addr_info':[{'scope':'global','local':address},{'scope':'host','local':'127.0.0.1'}]}]),json.dumps([{'prefsrc':address}])]
        with patch('voiceservices.network_address.subprocess.check_output',side_effect=output('192.168.1.20')+output('192.168.1.30')):
            self.assertEqual(reader.current(),(['192.168.1.20'],'192.168.1.20'))
            reader.expires=0
            self.assertEqual(reader.current(),(['192.168.1.30'],'192.168.1.30'))
        self.assertEqual(origin({'public_url':'https://old'},'192.168.1.30'),'https://192.168.1.30')
        self.assertEqual(origin({'public_url':'http://old:8080'},'2001:db8::1'),'http://[2001:db8::1]:8080')
    def test_caddy_reload_only_for_changed_managed_addresses(self):
        with tempfile.TemporaryDirectory() as temporary:
            config=Path(temporary)/'config.json';caddy=Path(temporary)/'Caddyfile'
            config.write_text(json.dumps({'automatic_public_url':True,'automatic_local_tls':True,'public_url':'https://192.168.1.20'}))
            caddy.write_text(caddy_config(['192.168.1.20'],'192.168.1.20',8080))
            reader=Mock();reader.current.return_value=(['192.168.1.30'],'192.168.1.30')
            with patch.object(address_service,'CONFIG',config),patch.object(address_service,'CADDY',caddy),patch.object(address_service.subprocess,'run') as run:
                self.assertEqual(address_service.refresh(reader),'https://192.168.1.30')
                self.assertEqual(run.call_count,2)
                self.assertIn('https://192.168.1.30',caddy.read_text())
                address_service.refresh(reader);self.assertEqual(run.call_count,2)
                caddy.write_text('# My manual configuration\n')
                with self.assertRaises(ValueError):address_service.refresh(reader)
                self.assertEqual(caddy.read_text(),'# My manual configuration\n')
    def test_explicit_configuration_is_untouched(self):
        with tempfile.TemporaryDirectory() as temporary:
            config=Path(temporary)/'config.json';config.write_text('{"automatic_public_url":false}')
            with patch.object(address_service,'CONFIG',config),patch.object(address_service.subprocess,'run') as run:
                address_service.refresh(Mock());run.assert_not_called()
    def test_portal_uses_host_address_not_browser_host_header(self):
        from voiceservices.web import App
        with tempfile.TemporaryDirectory() as temporary:
            app=App({'database':temporary+'/portal.sqlite','initial_modules':[], 'automatic_public_url':True,'public_url':'http://192.168.1.20:8080','secure_cookies':False})
            app.addresses=Mock();app.addresses.current.return_value=(['192.168.1.30'],'192.168.1.30')
            list(app({'PATH_INFO':'/','REQUEST_METHOD':'GET','HTTP_HOST':'attacker.example'},lambda *args:None))
            self.assertEqual(app.base,'http://192.168.1.30:8080')
            self.assertEqual(app.config['public_url'],app.base)
