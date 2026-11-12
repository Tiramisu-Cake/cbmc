#!/usr/bin/env python3
"""Bounded coordinator-only CBMC CI; no verifier is run by self-tests."""
import hashlib
import json
import os
from pathlib import Path
import re
import resource
import shutil
import signal
import subprocess
import sys
import time

BASE = '107a1e504cd69a2f3483717c8bcfcfa59814c557'
HERE = Path(__file__).resolve().parent
LIMIT = 1024 * 1024
MEMORY = 6 * 1024**3
FLAGS = ['--gcc', '--c11', '--64', '--little-endian',
         '--validate-goto-model', '--validate-ssa-equation']


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    Path(path).write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')


def git(root, *args):
    return subprocess.check_output(['git', '-C', str(root), *args]).decode().strip()


def limits(output_limit):
    resource.setrlimit(resource.RLIMIT_AS, (MEMORY, MEMORY))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    resource.setrlimit(resource.RLIMIT_FSIZE, (output_limit, output_limit))


def descendants(pid):
    """Include test.pl's separately grouped child before an outer timeout kill."""
    result = []
    try:
        children = Path(f'/proc/{pid}/task/{pid}/children').read_text().split()
    except FileNotFoundError:
        return result
    for child in children:
        result += descendants(int(child)) + [int(child)]
    return result


def execute(argv, cwd, log, seconds, output_limit=LIMIT):
    start = time.monotonic()
    record = {'argv': list(map(str, argv)), 'cwd': str(cwd),
              'status': 'NOT_RUN', 'timeout_seconds': seconds,
              'memory_limit_bytes_per_process': MEMORY,
              'output_limit_bytes': output_limit}
    log = Path(log)
    with log.open('wb') as stream:
        try:
            proc = subprocess.Popen(argv, cwd=cwd, stdout=stream,
                                    stderr=subprocess.STDOUT,
                                    start_new_session=True,
                                    preexec_fn=lambda: limits(output_limit))
        except OSError as error:
            record.update(status='START_ERROR', error=str(error), exit=None,
                          signal=None)
        else:
            try:
                rc = proc.wait(timeout=seconds)
                record.update(status='EXITED', exit=rc if rc >= 0 else None,
                              signal=-rc if rc < 0 else 0)
            except subprocess.TimeoutExpired:
                for pid in descendants(proc.pid):
                    try:
                        os.kill(pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                os.killpg(proc.pid, signal.SIGKILL)
                rc = proc.wait()
                record.update(status='TIMEOUT', exit=None,
                              signal=-rc if rc < 0 else 0)
    record.update(seconds=time.monotonic() - start,
                  rawKiB=log.stat().st_size / 1024,
                  log_sha256=sha(log),
                  children_maxrss_KiB=resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss)
    record['complete'] = log.stat().st_size < output_limit
    if not record['complete']:
        record['status'] = 'OUTPUT_LIMIT'
    save(log.with_suffix('.json'), record)
    return record


def classify(text, exit_code, signal_num, complete=True, timeout=False):
    """Never grant proof credit to crashes, truncated output or missing status."""
    failed = re.findall(r'^\[.*\].*: FAILURE\s*$', text, re.M)
    result = {'failed_properties': failed, 'proof_credit': False}
    if timeout or 'TIMEOUT=1' in text:
        status = 'TIMEOUT'
    elif not complete:
        status = 'INCOMPLETE'
    elif signal_num is None or (exit_code is None and signal_num == 0):
        status = 'MISSING_STATUS'
    elif (type(signal_num) is not int or signal_num < 0 or
          (exit_code is not None and (type(exit_code) is not int or exit_code < 0))):
        status = 'INVALID_STATUS'
    elif 'Invariant check failed' in text:
        status = ('ZST_ARRAY_INVARIANT' if 'bits2expr' in text and
                  'el_size_opt' in text else 'OTHER_INVARIANT')
    elif signal_num != 0 or exit_code in (134, 137, 139, 152, 153):
        status = 'SIGNAL_OR_KILL_UNKNOWN'
    elif exit_code == 0 and 'VERIFICATION SUCCESSFUL' in text and not failed:
        status = 'VERIFIED_C_INPUT'
    elif exit_code == 10 and 'VERIFICATION FAILED' in text and failed:
        status = 'ASSERTION_FAILURE'
    else:
        status = 'UNEXPECTED_RESULT'
    result['status'] = status
    return result


def intended(result, negative=False):
    if negative:
        return (result['status'] == 'ASSERTION_FAILURE' and
                len(result['failed_properties']) == 1 and
                'zst-payload-negative' in result['failed_properties'][0])
    return result['status'] == 'VERIFIED_C_INPUT'


def identity_ok(meta, variant, cfg):
    expected = BASE if variant == 'baseline' else cfg['source_sha']
    return (isinstance(meta, dict) and meta.get('variant') == variant
            and meta.get('source_ref') == expected
            and meta.get('test_delta_sha256') == cfg['test_delta_sha256']
            and meta.get('flags') == FLAGS and meta.get('build') == 'BUILT')


def unit_ok(record, text):
    return (record['status'] == 'EXITED' and record['exit'] == 0 and
            record['signal'] == 0 and record['complete'] and
            'All tests passed' in text and 'No test cases matched' not in text
            and 'No tests ran' not in text)


def config():
    return json.loads((HERE / 'config.json').read_text())


def test_delta(package, source):
    """Hash a full-index patch independent of local diff display settings."""
    return subprocess.check_output([
        'git', '-C', str(package), 'diff', '--binary', '--full-index',
        '--no-ext-diff', '--no-textconv', '--no-color', '--no-renames',
        '--no-relative', '--src-prefix=a/', '--dst-prefix=b/', '--unified=3',
        BASE, source, '--', 'regression/cbmc/zst-bits2expr-*',
        'unit/util/zst_bits2expr.cpp'])


def prepare(package, model, report, variant):
    cfg = config()
    source = cfg['source_sha']
    assert git(package, 'rev-parse', source + '^') == BASE
    assert git(package, 'rev-parse', source + '^{tree}') == cfg['source_tree']
    ref = BASE if variant == 'baseline' else source
    subprocess.run(['git', '-C', str(package), 'worktree', 'add', '--detach',
                    str(model), ref], check=True)
    delta = test_delta(package, source)
    assert hashlib.sha256(delta).hexdigest() == cfg['test_delta_sha256']
    (report / 'test-only.patch').write_bytes(delta)
    if variant == 'baseline':
        subprocess.run(['git', '-C', str(model), 'apply', '--index', '-'],
                       input=delta, check=True)
    overlay_tree = git(model, 'write-tree')
    assert overlay_tree == (cfg['baseline_test_overlay_tree'] if variant == 'baseline' else cfg['source_tree'])
    names = git(package, 'diff', '--name-only', BASE, source).splitlines()
    assert set(names) == set(cfg['source_changed_files'])
    for name in names:
        if name != 'src/util/simplify_utils.cpp':
            assert sha(model / name) == sha(package / name)
    workflow = package / '.github/workflows/cbmc-zst-bits2expr.yml'
    assert sorted(p.relative_to(package).as_posix() for p in
                  (package / '.github/workflows').rglob('*') if p.is_file()) == [
                      '.github/workflows/cbmc-zst-bits2expr.yml']
    meta = {'variant': variant, 'source_ref': ref,
            'source_ref_tree': git(model, 'rev-parse', 'HEAD^{tree}'),
            'test_overlay_tree': git(model, 'write-tree'),
            'test_delta_sha256': hashlib.sha256(delta).hexdigest(),
            'package_sha': git(package, 'rev-parse', 'HEAD'),
            'package_tree': git(package, 'rev-parse', 'HEAD^{tree}'),
            'workflow_sha256': sha(workflow),
            'runner_sha256': sha(HERE / 'runner.py'),
            'flags': FLAGS, 'model': str(model),
            'tests': {n: sha(model / n) for n in names
                      if n != 'src/util/simplify_utils.cpp'},
            'fixtures': {p.name: sha(p) for p in (HERE / 'fixtures').glob('*.c')},
            'build': 'NOT_RUN', 'focused': 'NOT_RUN', 'neighbours': 'NOT_RUN',
            'unit_neighbours': 'NOT_RUN', 'unit_focused': 'NOT_RUN',
            'case_states': {n: 'NOT_RUN' for n in cfg['focused'] + cfg['neighbours']},
            'fixture_states': {n: 'NOT_RUN' for n in ('owner-literal', 'kani-like')},
            'unit_states': {n: 'NOT_RUN' for n in cfg['unit_focused'] + ['[util]~[zst-bits2expr]']},
            'proof_credit': False}
    save(report / 'identity.json', meta)
    save(report / 'selected-cases.json', cfg)


def build(model, report):
    meta_path = report / 'identity.json'
    meta = json.loads(meta_path.read_text())
    stages = [('compiler-c', ['/usr/bin/gcc-13', '--version'], 30),
              ('compiler-cxx', ['/usr/bin/g++-13', '--version'], 30),
              ('preprocessor-version', ['gcc', '--version'], 30),
              ('target', ['gcc', '-dumpmachine'], 30),
              ('cmake-version', ['cmake', '--version'], 30),
              ('packages', ['dpkg-query', '-W', 'gcc-13', 'g++-13', 'flex', 'bison',
                            'cmake', 'make', 'patch', 'perl', 'python3'], 30),
              ('configure', ['cmake', '-S', str(model), '-B', str(model / 'build'),
                             '-DCMAKE_BUILD_TYPE=Release', '-DWITH_JBMC=OFF',
                             '-DWITH_MEMORY_ANALYZER=OFF', '-Dsat_impl=minisat2',
                             '-DCMAKE_C_COMPILER=/usr/bin/gcc-13',
                             '-DCMAKE_CXX_COMPILER=/usr/bin/g++-13'], 600),
              ('compile', ['cmake', '--build', str(model / 'build'),
                           '--target', 'cbmc', 'unit', '--parallel', '2'], 2700)]
    assert Path(shutil.which('gcc')).resolve() == Path('/usr/bin/gcc-13').resolve()
    meta['preprocessor'] = {'path': shutil.which('gcc'), 'realpath': str(Path(shutil.which('gcc')).resolve())}
    meta['build'] = 'IN_PROGRESS'
    meta['build_stages'] = {name: 'NOT_RUN' for name, _, _ in stages}
    save(meta_path, meta)
    for name, argv, timeout in stages:
        meta['build_stages'][name] = {'status': 'IN_PROGRESS', 'argv': argv}
        save(meta_path, meta)
        r = execute(argv, model, report / (name + '.log'), timeout, 16 * LIMIT)
        meta['build_stages'][name] = r
        if r['status'] != 'EXITED' or r['exit'] != 0 or not r['complete']:
            meta['build'] = 'FAILED'
            save(meta_path, meta)
            return 1
        save(meta_path, meta)
    meta['binaries'] = {}
    for name in ('cbmc', 'unit'):
        path = (model / 'build/bin' / name).resolve(strict=True)
        meta['binaries'][name] = {'path': str(path), 'sha256': sha(path)}
    shutil.copyfile(model / 'build/CMakeCache.txt', report / 'CMakeCache.txt')
    version = execute([meta['binaries']['cbmc']['path'], '--version'], model, report / 'cbmc-version.log', 30)
    if version['status'] != 'EXITED' or version['exit'] != 0:
        meta['build'] = 'FAILED_VERSION_CHECK'
        save(meta_path, meta)
        return 1
    meta['cmake_cache_sha256'] = sha(report / 'CMakeCache.txt')
    meta['build'] = 'BUILT'
    save(meta_path, meta)
    return 0


def regression(model, report, meta, case, focused):
    folder = model / 'regression/cbmc' / case
    out = report / case
    out.mkdir()
    descriptors = sorted(folder.glob('*.desc'))
    assert descriptors, f'zero descriptors for {case}'
    binary = meta['binaries']['cbmc']['path']
    command = ' '.join([binary] + FLAGS)
    argv = ['../test.pl', '-C', '-p', '-e', '-t', '90', '-s', 'zst-ci',
            '-c', command, case]
    r = execute(argv, model / 'regression/cbmc', out / 'runner.log',
                90 * len(descriptors) + 60, 4 * LIMIT)
    rows = []
    for desc in descriptors:
        output = folder / (desc.stem + '-zst-ci.out')
        row = {'descriptor': str(desc.relative_to(model)),
               'descriptor_sha256': sha(desc), 'case': case}
        lines = [line for line in desc.read_text().splitlines() if not line.startswith('//')]
        source = folder / lines[1]
        row['input'] = str(source.relative_to(model))
        row['input_sha256'] = sha(source)
        if output.exists():
            shutil.copyfile(output, out / output.name)
            raw = output.read_bytes()
            text = raw.decode(errors='replace')
            exits = re.findall(r'^EXIT=(\d+)\s*$', text, re.M)
            signals = re.findall(r'^SIGNAL=(\d+)\s*$', text, re.M)
            rc = int(exits[-1]) if len(exits) == 1 else None
            sig = int(signals[-1]) if len(signals) == 1 else None
            row.update(classify(text, rc, sig, len(raw) < LIMIT,
                                r['status'] == 'TIMEOUT'))
            row.update(exit=rc, signal=sig, rawKiB=len(raw) / 1024,
                       output_sha256=sha(output))
        else:
            row.update(status='MISSING_OUTPUT', exit=None, signal=None,
                       failed_properties=[], proof_credit=False)
        if focused:
            row['oracle_met'] = intended(row, case.endswith('-negative'))
        else:
            # Neighbour descriptors include intentional failed properties.
            row['oracle_met'] = (r['status'] == 'EXITED' and r['exit'] == 0
                                 and r['complete'] and row['exit'] is not None
                                 and row['signal'] == 0
                                 and row['status'] not in ('TIMEOUT', 'INCOMPLETE',
                                     'MISSING_STATUS', 'ZST_ARRAY_INVARIANT',
                                     'OTHER_INVARIANT', 'SIGNAL_OR_KILL_UNKNOWN')
                                 and 'skipped' not in (out / 'runner.log').read_text())
        rows.append(row)
    log = model / 'regression/cbmc/tests-zst-ci.log'
    if log.exists():
        shutil.copyfile(log, out / 'testpl.log')
    result = {'case': case, 'execution': r, 'outputs': rows,
              'oracle_met': (r['status'] == 'EXITED' and r['complete']
                             and r['exit'] == 0 and all(x['oracle_met'] for x in rows)),
              'identity': meta, 'proof_credit': False}
    save(out / 'result.json', result)
    return result


def fixture(model, report, meta, name):
    path = HERE / 'fixtures' / (name + '.c')
    binary = meta['binaries']['cbmc']['path']
    r = execute([binary] + FLAGS + [str(path)], model,
                report / (name + '.log'), 90)
    text = (report / (name + '.log')).read_text(errors='replace')
    result = classify(text, r.get('exit'), r.get('signal'), r['complete'],
                      r['status'] == 'TIMEOUT')
    result.update(execution=r, source_sha256=sha(path), identity=meta)
    result['oracle_met'] = r['status'] == 'EXITED' and intended(result)
    save(report / (name + '-result.json'), result)
    return result


def unit(model, report, meta, selection, name):
    r = execute([meta['binaries']['unit']['path'], selection], model / 'unit',
                report / (name + '.log'), 300, 4 * LIMIT)
    text = (report / (name + '.log')).read_text(errors='replace')
    r['oracle_met'] = unit_ok(r, text)
    r['selection'] = selection
    r['identity'] = meta
    save(report / (name + '-result.json'), r)
    return r


def tests(model, report):
    meta_path = report / 'identity.json'
    meta = json.loads(meta_path.read_text())
    assert meta['build'] == 'BUILT', 'build failure means tests NOT_RUN'
    assert identity_ok(meta, meta['variant'], config()), 'source-stage-target mismatch'
    for entry in meta['binaries'].values():
        assert sha(entry['path']) == entry['sha256']
    assert git(model, 'rev-parse', 'HEAD') == meta['source_ref']
    assert git(model, 'write-tree') == meta['test_overlay_tree']
    cfg = config()
    meta['focused'] = 'IN_PROGRESS'
    save(meta_path, meta)
    # Run every focused input separately, even if a preceding input crashes.
    results = []
    for c in cfg['focused']:
        meta['case_states'][c] = 'IN_PROGRESS'
        save(meta_path, meta)
        r = regression(model, report, meta, c, True)
        results.append(r)
        meta['case_states'][c] = 'ORACLE_MET' if r['oracle_met'] else 'FAILED'
        save(meta_path, meta)
    fixtures = {}
    for n in ('owner-literal', 'kani-like'):
        meta['fixture_states'][n] = 'IN_PROGRESS'
        save(meta_path, meta)
        fixtures[n] = fixture(model, report, meta, n)
        meta['fixture_states'][n] = fixtures[n]['status']
        save(meta_path, meta)
    meta['focused_results'] = {r['case']: r['oracle_met'] for r in results}
    meta['fixture_results'] = {n: r['status'] for n, r in fixtures.items()}
    baseline_repro = (fixtures['owner-literal']['status'] == 'ZST_ARRAY_INVARIANT'
                      and ((fixtures['owner-literal']['execution']['exit'] == 134
                            and fixtures['owner-literal']['execution']['signal'] == 0)
                           or fixtures['owner-literal']['execution']['signal'] == 6)
                      and any(o['status'] == 'ZST_ARRAY_INVARIANT' and
                              (o['exit'] == 134 or o['signal'] == 6)
                              for r in results if r['case'].endswith('-deref')
                              for o in r['outputs']))
    meta['baseline_reproduced'] = baseline_repro
    meta['focused'] = ('ORACLES_MET' if all(r['oracle_met'] for r in results)
                        and all(r['oracle_met'] for r in fixtures.values()) else 'FAILED')
    save(meta_path, meta)
    if meta['variant'] == 'baseline':
        # This is an observation, never a passing verification suite.
        meta['baseline_gate'] = ('INVARIANT_OBSERVED' if baseline_repro else
                                 'STOP_DEVELOP_REPRO_NOT_ESTABLISHED')
        meta['unit_focused'] = 'NOT_RUN_BASELINE_FOCUSED_FAILED'
        save(meta_path, meta)
        return 1
    if meta['focused'] != 'ORACLES_MET':
        return 1
    meta['unit_focused'] = 'IN_PROGRESS'
    save(meta_path, meta)
    units = []
    for i, selection in enumerate(cfg['unit_focused']):
        meta['unit_states'][selection] = 'IN_PROGRESS'
        save(meta_path, meta)
        r = unit(model, report, meta, selection, 'unit-focused-' + str(i))
        units.append(r)
        meta['unit_states'][selection] = 'ORACLE_MET' if r['oracle_met'] else 'FAILED'
        save(meta_path, meta)
    meta['unit_focused'] = 'ORACLES_MET' if all(r['oracle_met'] for r in units) else 'FAILED'
    save(meta_path, meta)
    if meta['unit_focused'] != 'ORACLES_MET':
        return 1
    meta['neighbours'] = 'IN_PROGRESS'
    meta['unit_neighbours'] = 'IN_PROGRESS'
    save(meta_path, meta)
    neighbours = []
    for c in cfg['neighbours']:
        meta['case_states'][c] = 'IN_PROGRESS'
        save(meta_path, meta)
        r = regression(model, report, meta, c, False)
        neighbours.append(r)
        meta['case_states'][c] = 'ORACLE_MET' if r['oracle_met'] else 'FAILED'
        save(meta_path, meta)
    meta['unit_states']['[util]~[zst-bits2expr]'] = 'IN_PROGRESS'
    save(meta_path, meta)
    util = unit(model, report, meta, '[util]~[zst-bits2expr]', 'unit-util')
    meta['unit_states']['[util]~[zst-bits2expr]'] = 'ORACLE_MET' if util['oracle_met'] else 'FAILED'
    meta['neighbours'] = 'ORACLES_MET' if all(r['oracle_met'] for r in neighbours) else 'FAILED'
    meta['unit_neighbours'] = 'ORACLES_MET' if util['oracle_met'] else 'FAILED'
    save(meta_path, meta)
    return 0 if meta['neighbours'] == meta['unit_neighbours'] == 'ORACLES_MET' else 1


def main():
    action, variant, package_arg, model_arg, report_arg = sys.argv[1:]
    package, model, report = map(lambda x: Path(x).resolve(),
                                 (package_arg, model_arg, report_arg))
    report.mkdir(exist_ok=True, parents=True)
    if action == 'prepare':
        prepare(package, model, report, variant)
        return 0
    if action == 'finalize':
        path = report / 'identity.json'
        meta = json.loads(path.read_text()) if path.exists() else {
            'build': 'NOT_RUN', 'focused': 'NOT_RUN', 'neighbours': 'NOT_RUN',
            'unit_neighbours': 'NOT_RUN', 'reason': 'PREPARE_INCOMPLETE'}
        meta['proof_credit'] = False
        meta['note'] = 'C inputs only; no actual Kani/Rust replay; coordinator must compare both variants.'
        save(report / 'FINAL.json', meta)
        summary = {k: meta.get(k, 'NOT_RUN') for k in ('variant', 'build', 'focused', 'unit_focused', 'neighbours', 'unit_neighbours', 'baseline_gate', 'baseline_reproduced', 'source_ref', 'source_ref_tree', 'test_overlay_tree', 'package_sha', 'workflow_sha256', 'runner_sha256', 'test_delta_sha256', 'binaries')}
        summary['proof_credit'] = False
        print(json.dumps(summary, indent=2))
        if os.environ.get('GITHUB_STEP_SUMMARY'):
            with open(os.environ['GITHUB_STEP_SUMMARY'], 'a') as stream:
                stream.write('```json\n' + json.dumps(summary, indent=2) + '\n```\n')
        return 0
    if os.environ.get('GITHUB_ACTIONS') != 'true':
        raise RuntimeError('build/test restricted to owner Actions coordinator')
    assert json.loads((report / 'identity.json').read_text())['variant'] == variant
    if action == 'build':
        return build(model, report)
    if action == 'test':
        return tests(model, report)
    raise ValueError(action)


if __name__ == '__main__':
    sys.exit(main())
