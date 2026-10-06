import subprocess,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
class InstallerPreflightTests(unittest.TestCase):
    def repository(self,contents,version='3.23.1'):
        with tempfile.TemporaryDirectory() as temporary:
            file=Path(temporary)/'repositories';file.write_text(contents)
            result=subprocess.run(['sh','-c','. "$1"; ensure_community "$2" "$3"','test',str(ROOT/'deploy/alpine-repositories.sh'),str(file),version],text=True,capture_output=True)
            return result,file.read_text(),(file.with_name('repositories.serviceready-backup').read_text() if file.with_name('repositories.serviceready-backup').exists() else None)
    def test_enable_matching_community_and_back_up(self):
        original='https://mirror.local/alpine/v3.23/main\n#https://mirror.local/alpine/v3.23/community\n'
        result,text,backup=self.repository(original)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertTrue(text.endswith('\nhttps://mirror.local/alpine/v3.23/community\n'))
        self.assertEqual(backup,original)
    def test_repository_retry_is_idempotent(self):
        original='https://mirror.local/alpine/v3.23/main\nhttps://mirror.local/alpine/v3.23/community\n'
        result,text,backup=self.repository(original)
        self.assertEqual(result.returncode,0);self.assertEqual(text,original);self.assertIsNone(backup)
    def test_wrong_release_or_edge_is_not_used(self):
        for original in ['https://mirror.local/alpine/edge/main\n','https://mirror.local/alpine/v3.22/main\n','#https://mirror.local/alpine/v3.23/main\n','https://mirror.local/alpine/v3.23/main\nhttps://mirror.local/alpine/edge/community\n']:
            with self.subTest(original=original):
                result,text,backup=self.repository(original)
                self.assertNotEqual(result.returncode,0);self.assertEqual(text,original);self.assertIsNone(backup)
    def test_failed_command_reports_stage_and_log_without_success(self):
        shell=(ROOT/'install-alpine.sh').read_text();functions=shell[shell.index('stage="preflight"'):shell.index('[ "$(id -u)"')]
        with tempfile.TemporaryDirectory() as temporary:
            log=Path(temporary)/'install.log'
            result=subprocess.run(['sh','-c',functions+'\ninstall_log="$1"\nstep "Package check"\nrun sh -c "echo missing-package; exit 7"\necho Installation-complete','test',str(log)],capture_output=True,text=True)
            self.assertNotEqual(result.returncode,0)
            self.assertIn('Package check',result.stderr);self.assertIn('missing-package',log.read_text())
            self.assertNotIn('Installation-complete',result.stdout)
