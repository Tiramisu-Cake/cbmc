#!/usr/bin/env python3
"""Only isolated synthetic Python processes; never CBMC or a compiler."""
from pathlib import Path
import hashlib
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import runner as r
from compare import compare


class Oracles(unittest.TestCase):
    def test_prepare_synthetic_diff_and_tree_identities(self):
        # A tiny Git fixture only: no CBMC source preparation or build.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            package = root / 'package'
            package.mkdir()

            def git(*args):
                return subprocess.check_output(
                    ['git', '-C', str(package), *args]).decode().strip()

            git('init', '-q')
            git('config', 'user.name', 'Synthetic fixture')
            git('config', 'user.email', 'fixture@example.invalid')
            files = {
                'src/util/simplify_utils.cpp': 'baseline\n',
                '.github/workflows/cbmc-zst-bits2expr.yml': 'synthetic\n',
                'scripts/zst-bits2expr/runner.py': 'synthetic\n',
                'scripts/zst-bits2expr/fixtures/input.c': 'synthetic\n'}
            for name, content in files.items():
                path = package / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content)
            git('add', '.')
            git('commit', '-qm', 'Synthetic baseline')
            base = git('rev-parse', 'HEAD')
            test = package / 'unit/util/zst_bits2expr.cpp'
            test.parent.mkdir(parents=True)
            test.write_text('synthetic test\n')
            git('add', '.')
            overlay = git('write-tree')
            (package / 'src/util/simplify_utils.cpp').write_text('fixed\n')
            git('add', '.')
            git('commit', '-qm', 'Synthetic source')
            source = git('rev-parse', 'HEAD')
            cfg = {'source_sha': source,
                   'source_tree': git('rev-parse', 'HEAD^{tree}'),
                   'baseline_test_overlay_tree': overlay,
                   'source_changed_files': ['src/util/simplify_utils.cpp',
                                            'unit/util/zst_bits2expr.cpp'],
                   'focused': [], 'neighbours': [], 'unit_focused': []}
            with patch.object(r, 'BASE', base), \
                    patch.object(r, 'HERE', package / 'scripts/zst-bits2expr'), \
                    patch.object(r, 'config', return_value=cfg):
                delta = r.test_delta(package, source)
                cfg['test_delta_sha256'] = hashlib.sha256(delta).hexdigest()
                for abbrev in ('4', '10', '40'):
                    with self.subTest(abbrev=abbrev):
                        git('config', 'core.abbrev', abbrev)
                        git('config', 'color.ui', 'always')
                        git('config', 'diff.noprefix', 'true')
                        git('config', 'diff.context', '0')
                        git('config', 'diff.external', '/nonexistent/zst-diff')
                        self.assertEqual(r.test_delta(package, source), delta)
                self.assertRegex(delta.decode(), r'index [0-9a-f]{40}\.\.[0-9a-f]{40}')
                cases = [('baseline', {}), ('fix', {}),
                         ('baseline', {'test_delta_sha256': '0' * 64}),
                         ('baseline', {'baseline_test_overlay_tree': '0' * 40}),
                         ('fix', {'source_tree': '0' * 40}),
                         ('fix', {'source_changed_files': []})]
                for index, (variant, wrong) in enumerate(cases):
                    with self.subTest(variant=variant, wrong=wrong):
                        report = root / f'report-{index}'
                        report.mkdir()
                        model = root / f'model-{index}'
                        with patch.object(r, 'config', return_value=dict(cfg, **wrong)):
                            if wrong:
                                with self.assertRaises(AssertionError):
                                    r.prepare(package, model, report, variant)
                                self.assertFalse((report / 'identity.json').exists())
                            else:
                                r.prepare(package, model, report, variant)
                                import json
                                meta = json.loads((report / 'identity.json').read_text())
                                expected = overlay if variant == 'baseline' else cfg['source_tree']
                                self.assertEqual(meta['test_overlay_tree'], expected)
                                self.assertEqual(meta['build'], 'NOT_RUN')
                                self.assertFalse(meta['proof_credit'])

    def test_positive_and_negative(self):
        ok = r.classify('[main.assertion.1] payload: SUCCESS\nVERIFICATION SUCCESSFUL', 0, 0)
        self.assertTrue(r.intended(ok))
        bad = r.classify('[main.assertion.1] zst-payload-negative: FAILURE\nVERIFICATION FAILED', 10, 0)
        self.assertTrue(r.intended(bad, True))
        self.assertFalse(r.intended(bad))
        extra = r.classify('[x] zst-payload-negative: FAILURE\n[y] other: FAILURE\nVERIFICATION FAILED', 10, 0)
        self.assertFalse(r.intended(extra, True))
        self.assertFalse(ok['proof_credit'])

    def test_error_timeout_partial_missing(self):
        inv = 'Invariant check failed\nfunction: bits2expr\nCondition: el_size_opt'
        self.assertEqual(r.classify(inv, 134, 0)['status'], 'ZST_ARRAY_INVARIANT')
        self.assertEqual(r.classify(inv, None, 6)['status'], 'ZST_ARRAY_INVARIANT')
        self.assertEqual(r.classify(inv, '134', '0')['status'], 'INVALID_STATUS')
        for text, rc, sig, complete, timeout in [
                ('VERIFICATION SUCCESSFUL', 1, 0, True, False),
                ('VERIFICATION SUCCESSFUL', 0, 0, True, True),
                ('VERIFICATION SUCCESSFUL', 0, 0, False, False),
                ('VERIFICATION SUCCESSFUL', None, None, True, False),
                ('VERIFICATION SUCCESSFUL', 0, 9, True, False),
                ('VERIFICATION SUCCESSFUL', '0', '0', True, False),
                ('NOT_RUN', 0, 0, True, False),
                ('', 0, 0, True, False)]:
            self.assertFalse(r.intended(r.classify(text, rc, sig, complete, timeout)))

    def test_empty_unit_selection_and_not_run(self):
        rec = {'status': 'EXITED', 'exit': 0, 'signal': 0, 'complete': True}
        self.assertTrue(r.unit_ok(rec, 'All tests passed (3 assertions in 1 test case)'))
        self.assertFalse(r.unit_ok(rec, 'No tests ran'))
        self.assertFalse(r.unit_ok(rec, 'No test cases matched\nAll tests passed'))
        self.assertFalse(r.unit_ok(dict(rec, status='NOT_RUN'), 'All tests passed'))
        self.assertFalse(r.unit_ok(dict(rec, complete=False), 'All tests passed'))

    def test_source_stage_target_mismatch(self):
        cfg = {'source_sha': 'fix', 'test_delta_sha256': 'delta'}
        meta = {'variant': 'fix', 'source_ref': 'fix', 'test_delta_sha256': 'delta',
                'flags': r.FLAGS, 'build': 'BUILT'}
        self.assertTrue(r.identity_ok(meta, 'fix', cfg))
        for key, value in [('source_ref', r.BASE), ('build', 'NOT_RUN'),
                           ('test_delta_sha256', None), ('variant', 'baseline'),
                           ('flags', 'wrong-type')]:
            self.assertFalse(r.identity_ok(dict(meta, **{key: value}), 'fix', cfg))
        self.assertFalse(r.identity_ok(None, 'fix', cfg))
        self.assertFalse(r.identity_ok({}, 'fix', cfg))

    def test_pair_compare(self):
        import copy
        cfg = {'source_sha': 'fix', 'test_delta_sha256': 'delta',
               'base_tree': 'base-tree', 'source_tree': 'fix-tree',
               'baseline_test_overlay_tree': 'overlay-tree'}
        common = {'flags': r.FLAGS, 'build': 'BUILT',
                  'test_delta_sha256': 'delta', 'tests': {'test': 'hash'},
                  'fixtures': {'literal': 'hash'}, 'package_sha': 'package',
                  'package_tree': 'package-tree', 'workflow_sha256': 'workflow',
                  'runner_sha256': 'runner',
                  'binaries': {'cbmc': {'sha256': 'cbmc'}, 'unit': {'sha256': 'unit'}},
                  'build_stages': {n: {'log_sha256': n} for n in
                      ('compiler-c', 'compiler-cxx', 'preprocessor-version',
                       'target', 'cmake-version', 'packages')}}
        base = dict(common, variant='baseline', source_ref=r.BASE,
                    source_ref_tree='base-tree', test_overlay_tree='overlay-tree', baseline_gate='INVARIANT_OBSERVED',
                    baseline_reproduced=True,
                    focused_results={'zst-bits2expr-memcpy': True})
        fix = dict(common, variant='fix', source_ref='fix', source_ref_tree='fix-tree', test_overlay_tree='fix-tree',
                   focused='ORACLES_MET', unit_focused='ORACLES_MET',
                   neighbours='ORACLES_MET', unit_neighbours='ORACLES_MET')
        self.assertEqual(compare(base, fix, cfg), 'OBSERVED_C_BASELINE_AND_FIXED_C_ORACLES_MET')
        for key, value in [('source_ref', r.BASE), ('focused', 'NOT_RUN'),
                           ('fixtures', None), ('binaries', {}),
                           ('tests', {'test': 'other-hash'})]:
            self.assertNotEqual(compare(base, dict(fix, **{key: value}), cfg),
                                'OBSERVED_C_BASELINE_AND_FIXED_C_ORACLES_MET')
        self.assertEqual(compare(dict(base, baseline_reproduced=False), fix, cfg),
                         'STOP_DEVELOP_REPRO_NOT_ESTABLISHED')
        changed = copy.deepcopy(fix)
        changed['build_stages']['target']['log_sha256'] = 'different'
        self.assertEqual(compare(base, changed, cfg), 'REJECT_TOOLCHAIN_MISMATCH')

    def test_process_success_error_signal_timeout_and_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)
            def run(code, name, seconds=3):
                return r.execute([sys.executable, '-c', code], p, p / name, seconds)
            good = run('print("synthetic")', 'success.log')
            self.assertEqual(good['exit'], 0)
            self.assertTrue(good['complete'])
            self.assertEqual(run('raise SystemExit(7)', 'error.log')['exit'], 7)
            killed = run('import os, signal; os.kill(os.getpid(), signal.SIGTERM)', 'signal.log')
            self.assertEqual(killed['signal'], 15)
            self.assertEqual(run('import time; time.sleep(10)', 'timeout.log', .05)['status'], 'TIMEOUT')
            missing = r.execute(['/nonexistent/zst-synthetic'], p, p / 'missing.log', 1)
            self.assertEqual(missing['status'], 'START_ERROR')
            limited = r.execute([sys.executable, '-c', 'print("x" * 100000)'],
                                p, p / 'limited.log', 3, 1024)
            self.assertFalse(limited['complete'])
            self.assertEqual(limited['status'], 'OUTPUT_LIMIT')


if __name__ == '__main__':
    unittest.main()
