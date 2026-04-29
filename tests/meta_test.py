"""
meta_test.py — higher-level expectation harness for the test harness itself.

Encodes the meta-rules of Test-First Driven Development (TFDD):

  1. The harness contains exactly 66 tests.
  2. Before any implementation, all 66 fail with NotImplementedError.
  3. Every failure shows its line number in test_harness.py.
  4. Every failure shows a re-run command.
  5. A single test can be re-run in isolation and reports the same failure.

Run with:  python3 meta_test.py
"""

import os
import re
import subprocess
import sys

HARNESS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_harness.py")
PYTHON  = sys.executable
WIDTH   = 64


def _run(*args):
    r = subprocess.run([PYTHON, HARNESS, *args], capture_output=True, text=True)
    return r.stdout + r.stderr, r.returncode


passed = failed = 0


def check(condition: bool, name: str, detail: str = ""):
    global passed, failed
    if condition:
        print(f"  PASS  {name}")
        passed += 1
    else:
        print(f"  FAIL  {name}")
        if detail:
            print(f"        {detail}")
        failed += 1


print(f"\n{'─' * WIDTH}")
print("  Meta Test — test harness contract")
print(f"{'─' * WIDTH}")

out, code = _run()

# 1. Exactly 66 tests
check("66 tests" in out,
      "harness reports exactly 66 tests")

# 2. All fail before implementation
check("66 failed" in out,
      "all 66 tests fail before implementation")

check("0 passed" in out,
      "zero tests pass before implementation")

check(code != 0,
      "harness exits non-zero when tests fail")

# 3. Every failure is NotImplementedError
not_impl_count = out.count("NotImplementedError")
check(not_impl_count == 66,
      "every failure reports NotImplementedError",
      f"found {not_impl_count} occurrences, expected 66")

# 4. Every failure shows a line number
line_refs = re.findall(r'\[test_harness\.py:\d+\]', out)
check(len(line_refs) == 66,
      "every failure shows a line number  [test_harness.py:NNN]",
      f"found {len(line_refs)} line references, expected 66")

# 5. Every failure shows a re-run command
rerun_cmds = re.findall(r'→ python3 test_harness\.py \S+\.\S+', out)
check(len(rerun_cmds) == 66,
      "every failure shows a re-run command",
      f"found {len(rerun_cmds)} re-run commands, expected 66")

# 6. Single test re-run works and reports the same failure
single_out, single_code = _run("TestDatabaseSchema.test_all_four_tables_created")
check("Re-running:" in single_out,
      "single test re-run shows targeted header")

check("FAIL" in single_out and "NotImplementedError" in single_out,
      "single test re-run reports NotImplementedError")

check("[test_harness.py:" in single_out,
      "single test re-run shows line number")

check(single_code != 0,
      "single test re-run exits non-zero on failure")

total = passed + failed
print(f"\n{'═' * WIDTH}")
print(f"  {total} meta-tests   {passed} passed   {failed} failed")
print(f"{'═' * WIDTH}\n")
sys.exit(0 if failed == 0 else 1)
