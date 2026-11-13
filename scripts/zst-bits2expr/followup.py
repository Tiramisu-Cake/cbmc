#!/usr/bin/env python3
"""Coordinator-only fix/unit follow-up; historical paired evidence is reused."""
from collections import Counter
import json
import os
from pathlib import Path
import shutil
import sys
import xml.etree.ElementTree as ET
import runner as r

SELECTION = '[util]~[zst-bits2expr]'
R2 = 'https://github.com/Tiramisu-Cake/cbmc/actions/runs/43334186094'


def exited(record, code=0):
    return (isinstance(record, dict) and record.get('status') == 'EXITED'
            and type(record.get('exit')) is int and record['exit'] == code
            and type(record.get('signal')) is int and record['signal'] == 0
            and record.get('complete') is True)


def load(report):
    return json.loads((report / 'identity.json').read_text())


def store(report, meta):
    r.save(report / 'identity.json', meta)


def prepare(package, model, report):
    r.prepare(package, model, report, 'fix')
    meta = load(report)
    meta.update(scope='environment/util gap only', unit_focused='NOT_RUN',
                unit_neighbours='NOT_RUN', z3_preflight='NOT_RUN',
                result='NOT_RUN', binary_mode='NEW_BUILD_UNIT_ONLY',
                baseline='REUSED_R2', focused='REUSED_R2', neighbours='REUSED_R2',
                historical_evidence={'url': R2, 'ci_sha': '91062c7dba9da7541c0e607a3735482e38d28d36',
                                     'assurance': 'coordinator-reported; not rerun here'},
                selection=SELECTION, r2_expected_count=212,
                followup_sha256=r.sha(r.HERE / 'followup.py'))
    meta['case_states'] = {name: 'REUSED_R2' for name in meta['case_states']}
    meta['fixture_states'] = {name: 'REUSED_R2' for name in meta['fixture_states']}
    store(report, meta)


def install(package, report):
    workspace = package.parent
    formatter = workspace / 'format-env'
    stages = [('apt-update', ['sudo', 'apt-get', 'update'], 120),
              ('apt-install', ['sudo', 'apt-get', 'install', '--no-install-recommends', '-y',
                               'gcc-13', 'g++-13', 'flex', 'bison', 'make', 'git', 'curl',
                               'patch', 'cmake', 'perl', 'python3', 'python3-venv', 'z3'], 300),
              ('formatter-venv', ['python3', '-m', 'venv', str(formatter)], 30),
              ('formatter-install', [str(formatter / 'bin/pip'), 'install', 'clang-format==18.1.8'], 90)]
    receipt = {'status': 'IN_PROGRESS', 'stages': {name: 'NOT_RUN' for name, _, _ in stages}}
    r.save(report / 'install-result.json', receipt)
    for name, argv, timeout in stages:
        receipt['stages'][name] = r.execute(argv, package, report / (name + '.log'), timeout, None)
        if not exited(receipt['stages'][name]):
            receipt['status'] = 'SETUP_FAILURE'
            r.save(report / 'install-result.json', receipt)
            return 1
        r.save(report / 'install-result.json', receipt)
    toolchain = workspace / 'toolchain'
    toolchain.mkdir()
    (toolchain / 'gcc').symlink_to('/usr/bin/gcc-13')
    (toolchain / 'g++').symlink_to('/usr/bin/g++-13')
    with open(os.environ['GITHUB_PATH'], 'a') as stream:
        stream.write(str(toolchain) + '\n')
    receipt['status'] = 'PASS'
    r.save(report / 'install-result.json', receipt)
    return 0


def preflight(model, report):
    meta = load(report)
    meta['z3_preflight'] = 'IN_PROGRESS'
    store(report, meta)
    stages = [('z3-command', ['bash', '-c', 'command -v z3']),
              ('z3-package', ['dpkg-query', '-W', '-f=${Package}\t${Version}\t${Status}\n', 'z3']),
              ('z3-package-files', ['dpkg-query', '-L', 'z3']),
              ('z3-version', ['z3', '--version']),
              ('z3-check-sat', ['bash', '-o', 'pipefail', '-c', "printf '(check-sat)\\n' | z3 -in"])]
    meta['z3_stages'] = {}
    for name, argv in stages:
        record = r.execute(argv, model, report / (name + '.log'), 30)
        meta['z3_stages'][name] = record
        text = (report / (name + '.log')).read_text().strip()
        ok = exited(record)
        if name == 'z3-command':
            path = shutil.which('z3')
            ok = ok and path is not None and text == path
            if ok:
                resolved = Path(path).resolve(strict=True)
                meta['z3_binary'] = {'path': path, 'realpath': str(resolved), 'sha256': r.sha(resolved)}
        if name == 'z3-package':
            fields = text.split('\t')
            ok = ok and len(fields) == 3 and fields[0] == 'z3' and bool(fields[1]) and fields[2] == 'install ok installed'
            if ok:
                meta['z3_package_version'] = fields[1]
        if name == 'z3-package-files':
            paths = text.splitlines()
            binary = meta.get('z3_binary', {})
            ok = ok and binary.get('path') in paths and binary.get('realpath') in paths
        if name == 'z3-version':
            meta['z3_version'] = text
            ok = ok and text.startswith('Z3 version ')
        if name == 'z3-check-sat':
            ok = ok and text == 'sat'
        if not ok:
            meta.update(z3_preflight='FAILED', result='SETUP_FAILURE',
                        unit_focused='NOT_RUN', unit_neighbours='NOT_RUN')
            store(report, meta)
            return 1
        store(report, meta)
    meta['z3_preflight'] = 'PASS'
    store(report, meta)
    return 0


def build(model, report):
    meta = load(report)
    assert meta['z3_preflight'] == 'PASS'
    assert Path(shutil.which('gcc')).resolve() == Path('/usr/bin/gcc-13').resolve()
    meta['preprocessor'] = {'path': shutil.which('gcc'), 'realpath': str(Path(shutil.which('gcc')).resolve())}
    stages = [('compiler-c', ['/usr/bin/gcc-13', '--version'], 30),
              ('compiler-cxx', ['/usr/bin/g++-13', '--version'], 30),
              ('preprocessor-version', ['gcc', '--version'], 30),
              ('target', ['gcc', '-dumpmachine'], 30),
              ('cmake-version', ['cmake', '--version'], 30),
              ('packages', ['dpkg-query', '-W', 'gcc-13', 'g++-13', 'flex', 'bison',
                            'cmake', 'make', 'patch', 'perl', 'python3', 'z3'], 30),
              ('configure', ['cmake', '-S', str(model), '-B', str(model / 'build'),
                             '-DCMAKE_BUILD_TYPE=Release', '-DWITH_JBMC=OFF',
                             '-DWITH_MEMORY_ANALYZER=OFF', '-Dsat_impl=minisat2',
                             '-DCMAKE_C_COMPILER=/usr/bin/gcc-13',
                             '-DCMAKE_CXX_COMPILER=/usr/bin/g++-13'], 600),
              ('compile', ['cmake', '--build', str(model / 'build'),
                           '--target', 'unit', '--parallel', '2'], 2700)]
    meta['build'] = 'IN_PROGRESS'
    meta['build_stages'] = {name: 'NOT_RUN' for name, _, _ in stages}
    store(report, meta)
    for name, argv, timeout in stages:
        meta['build_stages'][name] = {'status': 'IN_PROGRESS', 'argv': argv}
        store(report, meta)
        record = r.execute(argv, model, report / (name + '.log'), timeout, None)
        meta['build_stages'][name] = record
        if not exited(record):
            meta.update(build='FAILED', result='SETUP_FAILURE')
            store(report, meta)
            return 1
        store(report, meta)
    binary = (model / 'build/bin/unit').resolve(strict=True)
    meta['binaries'] = {'unit': {'path': str(binary), 'sha256': r.sha(binary)}}
    shutil.copyfile(model / 'build/CMakeCache.txt', report / 'CMakeCache.txt')
    meta.update(build='BUILT', cmake_cache_sha256=r.sha(report / 'CMakeCache.txt'))
    store(report, meta)
    return 0


def names_from_list(record, text):
    # Pinned Catch 2 returns the list count as its exit status, modulo 256 on POSIX.
    names = text.splitlines()
    if not names or any(not name.strip() for name in names) or len(set(names)) != len(names):
        raise ValueError('missing/invalid/duplicate selected test names')
    if not exited(record, len(names) % 256):
        raise ValueError('incomplete list or unexpected Catch listing exit')
    return names


def counts_from(node):
    if node is None:
        raise ValueError('missing totals')
    values = {}
    for key in ('successes', 'failures', 'expectedFailures'):
        text = node.attrib[key]
        if not text or not text.isascii() or not text.isdecimal():
            raise ValueError('invalid total: ' + key)
        values[key] = int(text)
    return values


def parse_xml(text, names, execution):
    root = ET.fromstring(text)
    if root.tag != 'Catch':
        raise ValueError('wrong reporter root')
    totals = root.find('OverallResultsCases')
    assertions = root.find('OverallResults')
    if totals is None or assertions is None:
        raise ValueError('missing run totals')
    counts = counts_from(totals)
    assertion_counts = counts_from(assertions)
    groups = root.findall('Group')
    if not groups:
        raise ValueError('missing groups')
    for tag, expected in (('OverallResults', assertion_counts), ('OverallResultsCases', counts)):
        group_counts = [counts_from(group.find(tag)) for group in groups]
        if any(sum(group[key] for group in group_counts) != expected[key] for key in expected):
            raise ValueError('group totals differ from run totals')
    cases = []
    for case in root.findall('./Group/TestCase'):
        outcome = case.find('OverallResult')
        if outcome is None or outcome.get('success') not in ('true', 'false'):
            raise ValueError('missing/wrong case outcome')
        row = {'name': case.attrib['name'], 'source': case.attrib['filename'],
               'line': int(case.attrib['line']), 'tags': case.attrib['tags'],
               'passed': outcome.get('success') == 'true',
               'execution_exit': execution.get('exit'), 'execution_signal': execution.get('signal'),
               'failures': []}
        for node in case.iter():
            if (node.tag == 'Expression' and node.get('success') == 'false') or node.tag in (
                    'Exception', 'FatalErrorCondition', 'Failure'):
                row['failures'].append({'kind': node.tag, 'attributes': dict(node.attrib),
                                        'text': ''.join(node.itertext()).strip()})
        cases.append(row)
    if Counter(row['name'] for row in cases) != Counter(names):
        raise ValueError('parsed records differ from predeclared selection')
    if sum(counts.values()) != len(cases):
        raise ValueError('run totals differ from parsed records')
    if counts['successes'] != sum(row['passed'] for row in cases):
        raise ValueError('case outcomes and totals differ')
    # No expected-failure bypass: all selected cases and assertions must pass.
    ok = (exited(execution) and counts['successes'] == len(names)
          and counts['failures'] == counts['expectedFailures'] == 0
          and assertion_counts['failures'] == assertion_counts['expectedFailures'] == 0
          and all(row['passed'] and not row['failures'] for row in cases))
    return {'parsed_complete': True, 'actual_count': len(cases), 'counts': counts,
            'assertion_counts': assertion_counts,
            'cases': cases, 'all_selected_passed': ok}


def run_selection(model, report, meta, selection, label):
    binary = meta['binaries']['unit']['path']
    listing = r.execute([binary, selection, '--list-test-names-only', '--order', 'lex'],
                        model / 'unit', report / (label + '-list.log'), 30, 4 * r.LIMIT)
    names = names_from_list(listing, (report / (label + '-list.log')).read_text())
    r.save(report / (label + '-selection.json'), {'selection': selection, 'names': names,
           'actual_count': len(names), 'r2_expected_count': 212 if selection == SELECTION else 1,
           'listing_execution': listing, 'source_sha': meta['source_ref'],
           'binary': meta['binaries']['unit'], 'status': 'RECORDED_BEFORE_TEST_EXECUTION'})
    execution = r.execute([binary, selection, '--reporter', 'xml', '--order', 'lex'],
                          model / 'unit', report / (label + '.xml'), 300, 4 * r.LIMIT)
    result = {'selection': selection, 'execution': execution, 'parsed_complete': False,
              'all_selected_passed': False, 'binary': meta['binaries']['unit'],
              'source_sha': meta['source_ref'], 'package_sha': meta['package_sha']}
    try:
        result.update(parse_xml((report / (label + '.xml')).read_text(), names, execution))
    except (ET.ParseError, ValueError, KeyError, TypeError) as error:
        result['parse_error'] = str(error)
    r.save(report / (label + '-result.json'), result)
    return result


def tests(model, report):
    meta = load(report)
    cfg = r.config()
    assert meta['z3_preflight'] == 'PASS', 'preflight failure means tests NOT_RUN'
    assert r.identity_ok(meta, 'fix', cfg), 'source-stage-target mismatch'
    assert meta['source_ref_tree'] == meta['test_overlay_tree'] == cfg['source_tree']
    assert r.git(model, 'rev-parse', 'HEAD') == cfg['source_sha']
    assert r.git(model, 'write-tree') == cfg['source_tree']
    assert not r.git(model, 'diff', '--name-only', 'HEAD', '--', 'src', 'unit', 'regression')
    binary = meta['binaries']['unit']
    assert r.sha(binary['path']) == binary['sha256']
    meta['unit_focused'] = 'IN_PROGRESS'
    store(report, meta)
    focused = []
    for index, selection in enumerate(cfg['unit_focused']):
        meta['unit_states'][selection] = 'IN_PROGRESS'
        store(report, meta)
        result = run_selection(model, report, meta, selection, 'unit-focused-' + str(index))
        focused.append(result)
        meta['unit_states'][selection] = 'PASS' if result['all_selected_passed'] else 'FAILED'
        store(report, meta)
    meta['unit_focused'] = 'PASS' if all(row['all_selected_passed'] for row in focused) else 'FAILED'
    meta['unit_neighbours'] = 'IN_PROGRESS'
    meta['unit_states'][SELECTION] = 'IN_PROGRESS'
    store(report, meta)
    util = run_selection(model, report, meta, SELECTION, 'unit-util')
    meta['unit_neighbours'] = 'PASS' if util['all_selected_passed'] else 'FAILED'
    meta['unit_states'][SELECTION] = meta['unit_neighbours']
    meta['util_actual_count'] = util.get('actual_count')
    meta['util_parsed_complete'] = util['parsed_complete']
    meta['result'] = ('ENVIRONMENT_UTIL_GAP_CLOSED' if meta['unit_focused'] ==
                      meta['unit_neighbours'] == 'PASS' else 'STOP_UNIT_FAILURE')
    store(report, meta)
    return 0 if meta['result'] == 'ENVIRONMENT_UTIL_GAP_CLOSED' else 1


def finalize(report):
    meta = load(report) if (report / 'identity.json').exists() else {
        'result': 'SETUP_FAILURE', 'reason': 'PREPARE_INCOMPLETE',
        'build': 'NOT_RUN', 'z3_preflight': 'NOT_RUN',
        'unit_focused': 'NOT_RUN', 'unit_neighbours': 'NOT_RUN'}
    path = report / 'format-result.json'
    meta['format'] = json.loads(path.read_text()) if path.exists() else {'oracle_met': False, 'status': 'NOT_RUN'}
    meta['proof_credit'] = False
    meta['note'] = 'Environment/util follow-up only; paired C evidence REUSED_R2; no Kani replay/full matrix.'
    r.save(report / 'FINAL.json', meta)
    summary = {key: meta.get(key) for key in ('result', 'build', 'z3_preflight',
               'unit_focused', 'unit_neighbours', 'util_actual_count', 'util_parsed_complete',
               'source_ref', 'package_sha', 'binaries', 'format')}
    print(json.dumps(summary, indent=2))
    return 0 if meta['result'] == 'ENVIRONMENT_UTIL_GAP_CLOSED' and meta['format'].get('oracle_met') is True else 1


def main():
    action, package_arg, model_arg, report_arg = sys.argv[1:]
    package, model, report = map(lambda value: Path(value).resolve(), (package_arg, model_arg, report_arg))
    report.mkdir(parents=True, exist_ok=True)
    if action == 'prepare':
        prepare(package, model, report)
        return 0
    if action == 'finalize':
        return finalize(report)
    if os.environ.get('GITHUB_ACTIONS') != 'true':
        raise RuntimeError('build/preflight/test restricted to owner Actions coordinator')
    if action == 'install':
        return install(package, report)
    return {'preflight': preflight, 'build': build, 'test': tests}[action](model, report)


if __name__ == '__main__':
    sys.exit(main())
