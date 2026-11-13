# Coordinator handoff: CBMC ZST-BITS2EXPR (NOT_COMPILED)

Owner fork: https://github.com/Tiramisu-Cake/cbmc (default develop unchanged).
Source base: 107a1e504cd69a2f3483717c8bcfcfa59814c557, tree b5a15d682996f745e0a02004d813e18d08f3a068.
Clean source + tests: cd41a5c74b0c42edf4f08834b3e2808dd3344cab, tree 92c03401d6c2a6da069670260244bc021bbdba99.
CI branch: ci/zst-bits2expr-20261113-r1. CI-only SHA/tree are in the research CI-MANIFEST.json;
this file intentionally cannot contain its own commit SHA. All commits are LOCAL ONLY.

Only the coordinator may push the CI-only HEAD to the existing owner fork. Do not push
intermediate source HEAD: it inherits upstream workflows. Do not change default develop.
The CI-only tree removes every inherited file under .github/workflows (including helper
scripts/assets) and leaves exactly cbmc-zst-bits2expr.yml. Its only trigger is push on
ci/zst-bits2expr-*. No issue, PR, dispatch or worker push is authorized by this package.
Cloud budget $0; Actions quota is separate and controlled by the coordinator.

## Recipe and identities

One ubuntu-24.04 matrix baseline/fix, max-parallel=1, fail-fast=false, no retries.
Package checkout is CI-only HEAD. Execution worktrees are created separately at the
exact base/source SHAs. The baseline applies ONLY the regression/unit test delta;
its staged tree must be 5ef52ba174f95b3ae51d19805b592a468db3c432.
Against the fixed source tree the only difference is src/util/simplify_utils.cpp.
Both jobs read the same committed config.json, runner.py and fixture bytes. No old
release binary, local build cache or upstream workflow overlay supplies execution code.
config.json records test-only patch SHA256 and every source changed path. Reports bind
source ref/tree, actual test-overlay tree, package/workflow/scripts, test bytes,
compiler/preprocessor/target/configuration, argv and resolved absolute binary SHA256.

Stock CMake recipe from pinned COMPILING.md / CMakeLists.txt / unit/CMakeLists.txt:
- apt packages: gcc-13 g++-13 flex bison make git curl patch cmake perl python3 python3-venv;
  dpkg-query, compiler versions, gcc -dumpmachine and CMake version are reported.
- gcc/g++ PATH links resolve to /usr/bin/gcc-13 and /usr/bin/g++-13; compiler options
  are explicit. The CBMC C frontend uses GCC preprocessing, GNU extensions, C11,
  --gcc --c11 --64 --little-endian (x86_64 Linux, 8-bit bytes, 32-bit int).
  gcc-only is an exclusion tag for MSVC, not a dialect flag. Layout assertions bind
  target-dependent assumptions; the int backing is union-aligned and fully written.
- cmake -S MODEL -B MODEL/build -DCMAKE_BUILD_TYPE=Release -DWITH_JBMC=OFF
  -DWITH_MEMORY_ANALYZER=OFF -Dsat_impl=minisat2
  -DCMAKE_C_COMPILER=/usr/bin/gcc-13 -DCMAKE_CXX_COMPILER=/usr/bin/g++-13
- cmake --build MODEL/build --target cbmc unit --parallel 2
- Minisat2 is the pinned source CMake recipe's downloaded dependency, not a release CBMC.
  Java submodule is not needed with WITH_JBMC=OFF. No new solver matrix or benchmarks.

## Gates and outcomes

13 new CORE cases are run independently in both jobs, plus separate literal-owner
and Kani-like C inputs. Full explicit lists and focused unit names are in config.json.
No crashing test can hide another C case: each invocation has its own output/result.
From MODEL/regression/cbmc the runner calls:
  ../test.pl -C -p -e -t 90 -s zst-ci -c "ABS_CBMC --gcc --c11 --64 --little-endian --validate-goto-model --validate-ssa-equation" CASE
The -e option matches EXIT/SIGNAL descriptors in pinned regression/test.pl. Actual
CBMC commands (including each descriptor's flags/input) are retained in testpl.log.
The literal and Kani-like fixtures use the same binary and global flags directly.

Positive: exit0, signal0, VERIFICATION SUCCESSFUL, no invariant/failed property.
Negative: exit10, signal0, VERIFICATION FAILED, exactly one failed property named
zst-payload-negative, no extra failure. A crash or generic failure never satisfies it.
Baseline is expected to be RED as a verification suite: observed array invariant
on both deref and literal is recorded separately as INVARIANT_OBSERVED; it is not
suite PASS. Baseline memcpy must pass. If develop does not reproduce the pinned
array invariant (exit134 or SIGABRT), report STOP_DEVELOP_REPRO_NOT_ESTABLISHED;
do not transfer the historical 6.11.0 result or grant credit. The fixed matrix job
still executes independently; coordinator stops further work if the baseline gate fails.

After all fixed focused C cases pass: three focused unit tests separately, then
13 explicit neighbour directories (14 descriptors: byte_extract1 has two) and
unit selection [util]~[zst-bits2expr]. Zero selection is failure. Neighbour descriptors
include intentional exit10 checks; their own full oracles remain authoritative.
No CTest/default CORE/full make test is invoked and no full suite is run twice.
Baseline neighbour/unit stages remain explicit NOT_RUN after its focused failure.

The small array neighbour list is Array_Initialization1/2, Array_Propagation1,
Array_Access1. Other neighbours are Empty_struct1/2/3, empty_compound_type2/3/4,
byte_extract1, Struct_Bytewise1, union-unequal-element-size1. Selection was checked
against pinned files and actual descriptors; names alone are not coverage claims.

## Limits and reports

Job120min; install10min; prepare5min; runner self-check2min; configure600s;
compile2700s; combined build step58min; testing step25min; format3min. Reserve
remains for finalization/upload; hard job cancellation may leave reports incomplete.
Per C input90s; test.pl outer envelope90s*descriptor_count+60s; unit invocation300s.
Process address-space cap6GiB, no core dumps, compiler parallelism2, tests serial.
No whole-job memory guarantee is claimed; unexplained kill/OOM remains UNKNOWN,
with original exit/signal preserved. Tests are NOT_RUN on build failure. Stage/case
states are written before execution so interruption remains IN_PROGRESS, never PASS.
Per-case raw bytes/KiB, elapsed time, output/descriptor/input hashes, complete failed
properties, EXIT/SIGNAL, and original runner exit are in bounded reports. Per process
log caps: configure/build16MiB, test.pl4MiB, direct CBMC1MiB, unit4MiB. Any output
limit or timeout rejects the oracle. No grep/head acceptance or swallowed failure.
Synthetic Python runner checks exercise error/timeout/partial/missing/null/wrong-type,
NOT_RUN and source-stage-target mismatch, without executing a compiler or verifier.

Format check uses pip clang-format==18.1.8 and git-clang-format --diff BASE SOURCE;
it runs without altering source. A formatting failure fails that job. Locally formatter
was unavailable: NOT_RUN. Actual C/C++ compilation and CBMC/unit/regression results
are all NOT_RUN in this worker session. Source static review is not a compiled PASS.

Upload bounded reports with always(), retention14days, including FINAL.json and
per-case JSON. Finalization prints a bounded identity/status summary. Coordinator
compares only approved bounded reports; do not fetch raw CI/GCS archives/full logs.
Using the two bounded FINAL.json files, compare.py rejects source/tree/overlay/input/
toolchain mismatches and missing controls. Its successful label is a measured C-input
comparison, not independent formal proof credit. The baseline job remains red.
The literal input is byte-identical to the research owner-literal.c; strengthened
zst-bits2expr-deref checks every pad byte. Kani-like padded-union C is not actual
Kani/Rust replay and does not close Kani#5085/case B. Do not revert the B3 workaround.

After paired CI the owner decides issue -> PR to upstream develop; broader regression
needs separate coordinator agreement. Required future PR disclosure:
Disclosure: this change and description were prepared with the help of AI assistants.
STOP here: SOURCE_AND_CI_PACKAGE_READY / NOT_COMPILED. No worker CI was run.

## R1 preparation repair

Coordinator reports run 43329473713 on the previous package failed both variants
before compilation: patch SHA mismatch, plus a source formatting diff from 18.1.8.
The source contains exactly the supplied formatting patch. The runner now emits
full 40-character index IDs and pins patch display options, retaining the patch
SHA, exact source parent/tree, overlay tree, changed-path and test-byte checks.
config.json pins the regenerated patch SHA and formatted source/overlay trees.
Synthetic Git fixtures exercise abbreviation/display differences, both variants
and rejection of wrong patch SHA, overlay/source tree and changed paths. Existing
process/oracle checks remain. Actual paired preparation/builds/CI remain for the
coordinator; this worker runs only static and isolated synthetic checks.
Use the new R1 branch; no force push or rewrite of the previously published branch.
