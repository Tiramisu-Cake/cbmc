#!/usr/bin/env python3
"""Check only clean source patch formatting, without mutating either checkout."""
import json
from pathlib import Path
import subprocess
import sys
import runner

bin_dir, report = map(Path, sys.argv[1:])
package = runner.HERE.parents[1]
cfg = runner.config()
version = subprocess.check_output([str(bin_dir / 'clang-format'), '--version'], text=True)
if '18.1.8' not in version:
    raise RuntimeError(version)
record = runner.execute([str(bin_dir / 'git-clang-format'), '--binary',
                         str(bin_dir / 'clang-format'), '--diff', runner.BASE,
                         cfg['source_sha']], package, report / 'format.log', 90)
text = (report / 'format.log').read_text()
ok = (record['status'] == 'EXITED' and record['exit'] == 0 and record['complete']
      and text.strip() in ('', 'no modified files to format', 'clang-format did not modify any files'))
runner.save(report / 'format-result.json', {'oracle_met': ok, 'version': version,
                                          'source_sha': cfg['source_sha'],
                                          'execution': record})
sys.exit(0 if ok else 1)
