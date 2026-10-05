import tempfile
import unittest
from pathlib import Path
from xml.etree import ElementTree
from voiceservices.core import Store
from voiceservices.web import App
from addon_support import install
def implementation(directory):
    app=App({"database":str(Path(directory)/"modules-db")})
    install(app,"voice")
    return app.modules.load("voice")

class PluginTests(unittest.TestCase):
    def test_install_configure_phone_menu_disable_remove_and_persist(self):
        with tempfile.TemporaryDirectory() as temp:
            store = Store(Path(temp)/'db')
            module=implementation(temp);Plugins=module.Plugins;phone=module.phone
            plugins = Plugins(store)
            plugins.install(Path('plugins/site-information/plugin.json').read_text())
            plugins.change('site-information',{'enabled':'yes','config_site':'A & B','config_helpdesk':'1234','config_message':'Welcome'})
            plugins = Plugins(Store(Path(temp)/'db'))
            screen = ElementTree.fromstring(plugins.render('site-information','http://localhost','token'))
            self.assertIn('A & B',screen.findtext('Text'))
            self.assertIn('plugin/site-information',phone.menu('http://localhost','token',plugins.list()).decode())
            plugins.change('site-information',{'enabled':'no'})
            self.assertIsNone(plugins.render('site-information','http://localhost','token'))
            plugins.change('site-information',{'action':'remove'})
            self.assertEqual(['calculator'],[p['id'] for p in plugins.list()])

    def test_invalid_packages(self):
        with tempfile.TemporaryDirectory() as temp:
            Plugins=implementation(temp).Plugins
            plugins = Plugins(Store(Path(temp)/'db'))
            for raw in ['[]','{}','{"id":"bad","name":"Bad","version":"1","kind":"python"}', '{"id":"bad","name":"Bad","version":"1","kind":"text","text":"{unknown}"}']:
                with self.assertRaises(ValueError): plugins.install(raw)
