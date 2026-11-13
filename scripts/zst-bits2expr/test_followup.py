#!/usr/bin/env python3
"""Synthetic runner tests only: no local compiler, Z3, or verification."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import followup as f
import runner as r

EXEC = {'status': 'EXITED', 'exit': 0, 'signal': 0, 'complete': True}
XML = '''<Catch><Group name="unit"><TestCase name="one" filename="unit/util/test.cpp" line="7" tags="[util]">
<OverallResult success="true"/></TestCase><OverallResults successes="1" failures="0" expectedFailures="0"/>
<OverallResultsCases successes="1" failures="0" expectedFailures="0"/></Group>
<OverallResults successes="1" failures="0" expectedFailures="0"/>
<OverallResultsCases successes="1" failures="0" expectedFailures="0"/></Catch>'''


class Followup(unittest.TestCase):
    def test_xml_success_and_failure_details(self):
        self.assertTrue(f.parse_xml(XML, ['one'], EXEC)['all_selected_passed'])
        failed = XML.replace('<OverallResult success="true"/>', '''<Expression success="false" filename="unit/util/test.cpp" line="9">
<Original>response == "sat"</Original><Expanded>"Launching" == "sat"</Expanded></Expression>
<OverallResult success="false"/>''').replace('successes="1" failures="0"', 'successes="0" failures="1"')
        parsed = f.parse_xml(failed, ['one'], dict(EXEC, exit=1))
        self.assertFalse(parsed['all_selected_passed'])
        self.assertEqual(parsed['cases'][0]['failures'][0]['attributes']['line'], '9')
        self.assertIn('Launching', parsed['cases'][0]['failures'][0]['text'])
        self.assertEqual(parsed['cases'][0]['execution_exit'], 1)

    def test_status_partial_missing_null_wrong_type_and_counts(self):
        for changed in ({'status': 'TIMEOUT'}, {'status': 'NOT_RUN'}, {'complete': False},
                        {'exit': None}, {'exit': '0'}, {'exit': False}, {'signal': 9}, {'signal': '0'}):
            self.assertFalse(f.parse_xml(XML, ['one'], dict(EXEC, **changed))['all_selected_passed'])
        for value in (None, {}, {'status': 'NOT_RUN'}):
            self.assertFalse(f.exited(value))
        for text, names in ((XML, ['other']), (XML, []),
                            (XML.replace('successes="1"', 'successes="2"'), ['one']),
                            (XML.replace('<OverallResult success="true"/>', ''), ['one']),
                            (XML.replace('success="true"', 'success="null"'), ['one'])):
            with self.assertRaises((ValueError, KeyError)):
                f.parse_xml(text, names, EXEC)
        with self.assertRaises(f.ET.ParseError):
            f.parse_xml(XML[:-8], ['one'], EXEC)

    def test_all_assertion_totals_required_and_consistent(self):
        for field in ('successes', 'failures', 'expectedFailures'):
            for value in (None, 'null', 'wrong-type', '-1', '1.5', ''):
                root = f.ET.fromstring(XML)
                node = root.find('OverallResults')
                if value is None:
                    del node.attrib[field]
                else:
                    node.set(field, value)
                with self.assertRaises((ValueError, KeyError)):
                    f.parse_xml(f.ET.tostring(root, encoding='unicode'), ['one'], EXEC)
        root = f.ET.fromstring(XML)
        root.find('OverallResults').set('successes', '2')
        with self.assertRaisesRegex(ValueError, 'group totals'):
            f.parse_xml(f.ET.tostring(root, encoding='unicode'), ['one'], EXEC)

    def test_list_exit_is_catch_count_not_zero(self):
        self.assertEqual(f.names_from_list(dict(EXEC, exit=2), 'one\ntwo\n'), ['one', 'two'])
        names = ''.join('case' + str(i) + '\n' for i in range(260))
        self.assertEqual(len(f.names_from_list(dict(EXEC, exit=4), names)), 260)
        for rec, text in ((EXEC, ''), (EXEC, 'one\n'), (dict(EXEC, exit=2), 'one\none\n'),
                          (dict(EXEC, exit=1, complete=False), 'one\n')):
            with self.assertRaises(ValueError):
                f.names_from_list(rec, text)

    def test_preflight_failure_keeps_units_not_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = Path(tmp)
            r.save(report / 'identity.json', {'z3_preflight': 'NOT_RUN'})
            def missing(argv, cwd, log, timeout):
                Path(log).write_text('')
                return dict(EXEC, exit=1)
            with patch.object(r, 'execute', side_effect=missing):
                self.assertEqual(f.preflight(report, report), 1)
            meta = f.load(report)
            self.assertEqual(meta['result'], 'SETUP_FAILURE')
            self.assertEqual(meta['unit_neighbours'], 'NOT_RUN')
            self.assertEqual(meta['unit_focused'], 'NOT_RUN')

    def test_z3_preflight_package_binding_success_and_failure(self):
        for scenario in ('success', 'not-installed', 'wrong-path'):
            with tempfile.TemporaryDirectory() as tmp:
                report = Path(tmp)
                binary = report / 'z3'
                binary.write_text('synthetic binary bytes, never executed')
                r.save(report / 'identity.json', {'z3_preflight': 'NOT_RUN'})
                outputs = {'z3-command': str(binary),
                           'z3-package': 'z3\t4.8.12-3\tinstall ok installed',
                           'z3-package-files': str(binary),
                           'z3-version': 'Z3 version 4.8.12 - 64 bit',
                           'z3-check-sat': 'sat'}
                if scenario == 'not-installed':
                    outputs['z3-package'] = 'z3\t4.8.12-3\tdeinstall ok config-files'
                if scenario == 'wrong-path':
                    outputs['z3-package-files'] = '/another/z3'
                def execute(argv, cwd, log, timeout):
                    Path(log).write_text(outputs[Path(log).stem] + '\n')
                    return dict(EXEC)
                with patch.object(r, 'execute', side_effect=execute), \
                        patch.object(f.shutil, 'which', return_value=str(binary)):
                    self.assertEqual(f.preflight(report, report), 0 if scenario == 'success' else 1)
                meta = f.load(report)
                self.assertEqual(meta['z3_preflight'], 'PASS' if scenario == 'success' else 'FAILED')
                if scenario != 'success':
                    self.assertEqual(meta['unit_neighbours'], 'NOT_RUN')

    def test_source_stage_target_guard_before_any_test(self):
        base = {'variant': 'fix', 'source_ref': r.config()['source_sha'],
                'test_delta_sha256': r.config()['test_delta_sha256'],
                'flags': r.FLAGS, 'build': 'BUILT', 'z3_preflight': 'PASS'}
        for changed in ({'variant': 'baseline'}, {'source_ref': r.BASE},
                        {'build': 'NOT_RUN'}, {'test_delta_sha256': None},
                        {'flags': []}, {'z3_preflight': 'FAILED'}):
            with tempfile.TemporaryDirectory() as tmp:
                report = Path(tmp)
                r.save(report / 'identity.json', dict(base, **changed))
                with patch.object(r, 'execute') as execute:
                    with self.assertRaises(AssertionError):
                        f.tests(report, report)
                    execute.assert_not_called()

    def test_drain_overflow_preserves_original_exit_and_build_file_size(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            # This producer must finish even after its retained log fills.
            code = ('from pathlib import Path; import sys; '
                    'print("x" * 200000); Path("completed").write_text("yes"); sys.exit(7)')
            rec = r.execute([sys.executable, '-c', code], root, root / 'overflow.log', 3, 1024)
            self.assertEqual(rec['exit'], 7)
            self.assertEqual(rec['status'], 'OUTPUT_LIMIT')
            self.assertGreater(rec['overflow_bytes'], 0)
            self.assertEqual((root / 'completed').read_text(), 'yes')
            self.assertEqual((root / 'overflow.log').stat().st_size, 1024)
            code = ('import resource; from pathlib import Path; '
                    'assert resource.getrlimit(resource.RLIMIT_FSIZE)[0] == resource.RLIM_INFINITY; '
                    'Path("library.a").write_bytes(b"a" * 200000)')
            rec = r.execute([sys.executable, '-c', code], root, root / 'build.log', 3, None)
            self.assertTrue(f.exited(rec))
            self.assertIsNone(rec['file_size_limit'])


if __name__ == '__main__':
    unittest.main()
