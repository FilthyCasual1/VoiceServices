import os,subprocess,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
class ProgressTests(unittest.TestCase):
    def test_failure_propagates_and_never_reports_completion(self):
        with tempfile.TemporaryDirectory() as temporary:
            log=Path(temporary)/'log'
            command='set -e; source "$1"; log="$2"; step "Install dependencies"; run sh -c "echo missing-package; exit 7"; progress_complete'
            result=subprocess.run(['bash','-c',command,'test',str(ROOT/'deploy/rocky-progress.sh'),str(log)],capture_output=True,text=True)
            self.assertEqual(result.returncode,7)
            self.assertIn('missing-package',result.stderr);self.assertIn('[2/9]',result.stdout)
            self.assertNotIn('[100%]',result.stdout)
    def test_gauge_reports_stage_activity_and_elapsed_time(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);fake=root/'whiptail';gauge=root/'gauge'
            fake.write_text('#!/bin/sh\ncat > "$GAUGE"\n');fake.chmod(0o755)
            command='source "$1"; log="$2"; progress_ui=1; step "Verify HTTP and HTTPS"; run sh -c "echo checking; sleep .2"; progress_complete'
            result=subprocess.run(['bash','-c',command,'test',str(ROOT/'deploy/rocky-progress.sh'),str(root/'log')],env=dict(os.environ,PATH=str(root)+':'+os.environ['PATH'],GAUGE=str(gauge)),capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertIn('88',gauge.read_text());self.assertIn('Elapsed:',gauge.read_text())
            self.assertIn('Running: sh -c',gauge.read_text());self.assertIn('[100%]',result.stdout)
