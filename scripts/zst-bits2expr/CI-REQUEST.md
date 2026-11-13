# Coordinator handoff: CBMC ZST PRREADY environment/util follow-up

LOCAL ONLY. Only the coordinator may push this CI-only HEAD directly to
Tiramisu-Cake/cbmc on `ci/zst-bits2expr-util-z3-20261113-prready` and run CI.
No worker push/dispatch, issue or PR. Cloud $0. Do not push intermediate source
or change default develop. This branch derives from exact r2 CI-only
91062c7dba9da7541c0e607a3735482e38d28d36, preserving both coordinator fixes.
The clean PR head remains cd41a5c74b0c42edf4f08834b3e2808dd3344cab;
its source/tests/base are unchanged. Workflow deletions never enter that PR.

Exactly one branch-filtered push workflow, one ubuntu-24.04 fix job, 120 min;
no matrix, baseline/repro/C regression/neighbours rerun and no paired compare.py
oracle. Those results are REUSED_R2, explicitly linked to
https://github.com/Tiramisu-Cake/cbmc/actions/runs/43334186094.
Owner-literal/Kani-like C statuses remain coordinator-reported historical claims.
No new C verification, Kani replay, Kani#5085/B3 closure or full matrix claim.

No preserved r2 binary artifact with exact hash/source/config receipt was supplied.
Use a fresh CI build from clean exact cd41 source with r2 configuration:
CMake Release, WITH_JBMC=OFF, WITH_MEMORY_ANALYZER=OFF, sat_impl=minisat2,
/usr/bin/gcc-13 and g++-13; build target unit only, parallel 2. Record the
absolute binary path/hash and CMakeCache hash. Source is a detached worktree;
CI overlay is not the compilation source. Java and other targets are excluded.

Install r2 dependencies plus Ubuntu z3. Before configure/build/tests, record
`command -v z3`, dpkg package/version/status and installed paths, binary realpath
and SHA256, `z3 --version`, and `(check-sat)` through `z3 -in` = sat. Preflight
failure is SETUP_FAILURE and unit states NOT_RUN. Never filter .z3 tags or edit
piped_process source/expected values to make the selection green.

Before each invocation persist exact selection, list, actual count and Catch list
exit. Pinned Catch2 returns the list count (POSIX exit modulo256), not zero.
The remaining util selection is exactly `[util]~[zst-bits2expr]` (r2 expected212;
actual count is reported, not forced). Newly built unit also runs all three
focused unit selections from unchanged r2 config.json. Invocation timeout300s.
Reporter XML preserves case names, source/line/tags, failed expressions/expanded
values, original process exit/signal and totals. Parsed names/counts must exactly
match the predeclared list and totals; every selected case and assertion must
pass. Truncation, partial XML, missing/wrong-type status and zero selection fail.
A green job alone is not parsed completeness. If failures remain with Z3 PASS,
STOP_UNIT_FAILURE; hand off concrete records without asserting patch unrelatedness.

The r2 empty-format-diff acceptance is unchanged (clang-format18.1.8).
No RLIMIT_FSIZE on configure/build/ar/link. Shared execution now captures stdout
via pipe with continued drain after retained-log cap (build/install16MiB,
units/list4MiB); stores rawKiB, retained bytes, overflow bytes, exit/signal/time,
log hash and per-process memory cap6GiB. Overflow rejects acceptance while
preserving the producer's actual exit; no SIGPIPE producer. Deadline kills tracked
descendants/process group; timeout remains timeout. This is not a whole-job RAM cap.
Install10min, prepare5, synthetic checks2, preflight3, build58, units23,
format3, finalize2; job120 leaves upload reserve. Build configure600s/compile2700s.

Finalization and bounded report upload use always(), retention14days. Partial
states remain NOT_RUN/IN_PROGRESS; no automatic PASS on setup failure. FINAL.json
contains source/package/workflow/runner/followup/binary identities, Z3 receipts,
format and current states. `ENVIRONMENT_UTIL_GAP_CLOSED` is only the fresh util
scope, with explicit C evidence reuse; no independent proof credit. Read curated
coordinator receipts, not raw archives/full logs. Historical results/ledgers remain
unchanged. The source-only PR checklist and upstream observation are in the
research prready package. Next action belongs exclusively to the coordinator.

Disclosure: this change and description were prepared with the help of AI assistants.
