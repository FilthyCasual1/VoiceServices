import io,unittest
from unittest.mock import patch
import test_app
from voiceservices import distro
class DistroTests(unittest.TestCase):
    setUp=test_app.PortalTests.setUp
    tearDown=test_app.PortalTests.tearDown
    def test_detect_fetch_sanitize_and_cache(self):
        raw=b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script><path d="M0 0h24v24H0z"/></svg>'
        with patch.object(distro,'detected',return_value={'ID':'alpine','PRETTY_NAME':'Alpine Linux'}),patch.object(distro,'urlopen',return_value=io.BytesIO(raw)) as fetch:
            first=distro.logo(self.app);second=distro.logo(self.app)
            self.assertEqual(first,second);self.assertNotIn(b'script',first);self.assertIn(b'Alpine Linux',first)
            fetch.assert_called_once_with('https://cdn.simpleicons.org/alpinelinux',timeout=2)
    def test_unknown_distribution_offline_fallback(self):
        with patch.object(distro,'detected',return_value={'ID':'unknown','PRETTY_NAME':'Example Linux'}),patch.object(distro,'urlopen') as fetch:
            self.assertIn(b'Example Linux',distro.logo(self.app));fetch.assert_not_called()
