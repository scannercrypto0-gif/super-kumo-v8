import copy
import pathlib
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

import atlas_runner as runner


class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=runner.ROOT)
        self.root = pathlib.Path(self.temp.name)
        self.addCleanup(self.temp.cleanup)
        self.issue = dict(number=82, state='open', title='repair', body='scope',
                          updated_at='2026-10-24T00:00:00Z',
                          user={'login': runner.OWNER.split('/')[0]},
                          labels=[{'name': x} for x in
                                  ('track:core', 'worker:approved', 'queue:ready')])

    def test_claim_survives_restart_and_keys_all_dimensions(self):
        with patch.object(runner, 'STATE', self.root):
            self.assertTrue(runner.claim_execution(82, 'base', 'revision'))
            code = ('import atlas_runner as r,pathlib,sys; '
                    'r.STATE=pathlib.Path(sys.argv[1]); '
                    'sys.exit(1 if r.claim_execution(82,"base","revision") else 0)')
            result = subprocess.run([sys.executable, '-c', code, str(self.root)],
                                    cwd=runner.ROOT, timeout=20, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(runner.claim_execution(83, 'base', 'revision'))
            self.assertTrue(runner.claim_execution(82, 'base2', 'revision'))
            self.assertTrue(runner.claim_execution(82, 'base', 'revision2'))

    def test_quota_fails_closed(self):
        with patch.object(runner, 'QUOTA_PROVIDER', None):
            with self.assertRaises(RuntimeError): runner.budget_gate(900)
        for telemetry in ({}, {'observed_at': time.time()-120, 'remaining_execution_seconds': 9999},
                          {'observed_at': time.time(), 'remaining_execution_seconds': 899},
                          {'observed_at': float('nan'), 'remaining_execution_seconds': 9999}):
            with self.subTest(telemetry=telemetry), patch.object(runner, 'QUOTA_PROVIDER', lambda: telemetry):
                with self.assertRaises(RuntimeError): runner.budget_gate(900)
        with patch.object(runner, 'QUOTA_PROVIDER', lambda: dict(observed_at=time.time(), remaining_execution_seconds=900)):
            runner.budget_gate(900)

    def test_revision_and_authorization(self):
        self.assertIsNone(runner.eligibility(self.issue))
        changed = copy.deepcopy(self.issue)
        changed['body'] = 'new scope'
        self.assertNotEqual(runner.request_revision(self.issue), runner.request_revision(changed))
        changed['labels'].append({'name': 'do-not-run'})
        self.assertIsNotNone(runner.eligibility(changed))

    def test_bounded_tests_pass_fail_empty_and_timeout(self):
        with self.assertRaises(RuntimeError): runner.run_tests(self.root)
        test_file = self.root / 'test_sample.py'
        test_file.write_text('import unittest\nclass T(unittest.TestCase):\n def test_ok(self): self.assertTrue(True)\n')
        runner.run_tests(self.root)
        test_file.write_text('import unittest\nclass T(unittest.TestCase):\n def test_failure(self): self.fail("expected")\n')
        with self.assertRaises(RuntimeError): runner.run_tests(self.root)
        with patch.object(runner, 'cmd', side_effect=subprocess.TimeoutExpired('tests', 120)):
            with self.assertRaises(subprocess.TimeoutExpired): runner.run_tests(self.root)

    def test_failed_tests_prevent_publication(self):
        (self.root / '.git').mkdir()
        calls = []
        def command(args, **kwargs):
            calls.append(args)
            output = ''
            if args[1:3] == ['branch', '--show-current']: output = 'main'
            if args[1:3] == ['rev-parse', 'origin/main']: output = 'a'*40
            if args[0] == 'codex': output = 'done'
            if args[1:3] == ['status', '--porcelain'] and kwargs.get('cwd') != self.root:
                output = ' M module.py'
            return subprocess.CompletedProcess(args, 0, output, '')
        with patch.object(runner, 'REPO', self.root), patch.object(runner, 'STATE', self.root/'state'), \
             patch.object(runner, 'issue_data', return_value=self.issue), \
             patch.object(runner, 'budget_gate'), patch.object(runner.shutil, 'which', return_value='tool'), \
             patch.object(runner, 'cmd', side_effect=command), patch.object(runner, 'log'), \
             patch.object(runner, 'run_tests', side_effect=RuntimeError('failed tests')), \
             patch.object(sys, 'argv', ['runner', '--issue', '82', '--execute']):
            with self.assertRaisesRegex(RuntimeError, 'failed tests'): runner.main()
        self.assertTrue(any(c[0] == 'codex' for c in calls))
        self.assertFalse(any(c[1] in ('push', 'commit', 'pr') for c in calls))

    def test_execution_disabled_by_default(self):
        with patch.object(sys, 'argv', ['runner', '--issue', '82']), \
             patch.object(runner, 'issue_data', return_value=self.issue), \
             patch.object(runner, 'log'), patch.object(runner, 'cmd') as command:
            self.assertEqual(runner.main(), 0)
            command.assert_not_called()


if __name__ == '__main__':
    unittest.main()
