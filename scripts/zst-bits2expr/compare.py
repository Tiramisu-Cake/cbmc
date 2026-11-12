#!/usr/bin/env python3
"""Coordinator comparison of two bounded FINAL.json reports, not raw archives."""
import json
from pathlib import Path
import sys
import runner as r


def compare(base, fix, cfg):
    for variant, meta in [('baseline', base), ('fix', fix)]:
        if not r.identity_ok(meta, variant, cfg):
            return 'REJECT_SOURCE_STAGE_TARGET_MISMATCH'
        tree = cfg['base_tree'] if variant == 'baseline' else cfg['source_tree']
        overlay = cfg['baseline_test_overlay_tree'] if variant == 'baseline' else cfg['source_tree']
        if meta.get('source_ref_tree') != tree or meta.get('test_overlay_tree') != overlay:
            return 'REJECT_SOURCE_TREE_MISMATCH'
        if not all(meta.get('binaries', {}).get(n, {}).get('sha256')
                   for n in ('cbmc', 'unit')):
            return 'REJECT_MISSING_BINARY_IDENTITY'
    for key in ('test_delta_sha256', 'tests', 'fixtures', 'flags',
                'package_sha', 'package_tree', 'workflow_sha256', 'runner_sha256'):
        if not base.get(key) or base.get(key) != fix.get(key):
            return 'REJECT_OVERLAY_OR_INPUT_MISMATCH'
    for stage in ('compiler-c', 'compiler-cxx', 'preprocessor-version', 'target',
                  'cmake-version', 'packages'):
        a = base.get('build_stages', {}).get(stage, {})
        b = fix.get('build_stages', {}).get(stage, {})
        if not a.get('log_sha256') or a.get('log_sha256') != b.get('log_sha256'):
            return 'REJECT_TOOLCHAIN_MISMATCH'
    if base.get('baseline_gate') != 'INVARIANT_OBSERVED' or base.get('baseline_reproduced') is not True:
        return 'STOP_DEVELOP_REPRO_NOT_ESTABLISHED'
    if base.get('focused_results', {}).get('zst-bits2expr-memcpy') is not True:
        return 'REJECT_BASELINE_MEMCPY_CONTROL'
    for key in ('focused', 'unit_focused', 'neighbours', 'unit_neighbours'):
        if fix.get(key) != 'ORACLES_MET':
            return 'REJECT_FIXED_ORACLES'
    return 'OBSERVED_C_BASELINE_AND_FIXED_C_ORACLES_MET'


if __name__ == '__main__':
    base, fix = [json.loads(Path(p).read_text()) for p in sys.argv[1:]]
    status = compare(base, fix, r.config())
    print(json.dumps({'status': status, 'proof_credit': False,
                      'actual_kani_rust_replay': 'NOT_RUN'}))
    sys.exit(0 if status == 'OBSERVED_C_BASELINE_AND_FIXED_C_ORACLES_MET' else 1)
