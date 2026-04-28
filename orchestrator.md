# Test-First Driven Development (TFDD)

A development strategy where tests are written in full before any implementation
exists. Every function starts as `raise NotImplementedError`. The test suite is
the specification. Code exists only to make tests pass — nothing more.

---

## Philosophy

> Write the contract first. Then fill it in, one stub at a time.

- Tests define behaviour precisely before implementation begins.
- A passing test is proof of a working obligation, not just optimism.
- A failing test is a clear, actionable task — not a surprise.
- Implementation scope is bounded: stop when the target cluster passes.
- After each implementation, read the "Newly Passing" summary to understand what was proven.

---

## Project layout

```
curiosity/
├── db.py           ← implement here (database layer)
└── pipeline.py     ← implement here (LLM pipeline)

test_harness.py     ← 66 tests across 8 suites — do not modify
meta_test.py        ← validates the test harness itself — do not modify
orchestrator.md     ← this file
logs/
├── test_run_<timestamp>.log   ← full output of every run, auto-saved
├── last_passing.json          ← tracks which tests passed last run
```

---

## Commands

| Action | Command |
|---|---|
| Run full suite | `python3 test_harness.py` |
| Re-run one test | `python3 test_harness.py ClassName.test_name` |
| Run meta test | `python3 meta_test.py` |
| Run live LLM tests | `CURIOSITY_LIVE_API=1 ANTHROPIC_API_KEY=sk-... python3 test_harness.py` |

Every run writes a timestamped log to `logs/` automatically.
The re-run command is printed beneath every failing test — copy and paste it directly.

---

## Development loop

```
1. Run the full suite.
   → python3 test_harness.py

2. Find the first FAIL. Identify which stub function(s) it depends on.
   Check how many other failing tests share those same stubs —
   they will all pass together (a "cluster").

3. Re-run the first failing test alone to confirm the failure.
   → python3 test_harness.py ClassName.test_name

4. Implement the stub(s) in curiosity/db.py or curiosity/pipeline.py.
   Implement only what the failing tests require — nothing more.

5. Re-run the single test. Confirm it passes.
   → python3 test_harness.py ClassName.test_name

6. Run the full suite. Check for regressions.
   → python3 test_harness.py

7. Echo the "Newly Passing" summary from the log output.
   State what each newly passing test proves — this is the implementation diary.

8. State the line number of the next failing test.
   → e.g. "Next: test_insert_memory_note [test_harness.py:253]"

9. Go to step 3 with the next failing test.
```

Repeat until the suite reports `66 passed   0 failed`.

---

## Observations from practice

- **One stub unlocks many tests.** Implementing a single function often passes
  several tests at once because multiple tests share the same dependency.
  This is expected and desirable — it means the tests are well-scoped.

- **Setup dependencies cascade.** A test that appears to test function B may
  require function A just to set up its state. When the first failing test
  needs two stubs, implement both.

- **The cluster is the unit of work.** Think in terms of "which stub am I
  implementing?" not "which single test am I fixing?". The newly passing
  summary after each run shows the full cluster.

- **The "Newly Passing" summary is the implementation diary.** Each entry
  records a guarantee the system now makes. Review it after every run.

---

## Rules

1. **Never implement more than the failing cluster asks for.**
2. **Never modify a test to make it pass.** If a test is wrong, discuss it.
3. **A test must fail before it can pass.** Vacuous passes must be fixed.
4. **Run the meta test before starting a session.**
   `python3 meta_test.py` — all meta-checks must pass first.
5. **Commit after each cluster turns green.**
   Each commit is one stub fulfilled. The git log becomes a readable
   implementation history.

---

## Suite order

Implement in suite order — later suites depend on earlier ones:

| # | Suite | File | Key stubs |
|---|---|---|---|
| 1 | Database Schema | `db.py` | `init_db` |
| 2 | Data Insertion & Retrieval | `db.py` | `insert_entity`, `insert_fact`, `insert_memory_note`, `enqueue_question`, `advance_question_status` |
| 3 | Extraction Pipeline | `pipeline.py` | `extract_knowledge` |
| 4 | Temporary Staging | — | (passes once suites 1–2 are done) |
| 5 | Consolidation | `pipeline.py` | `consolidate` |
| 6 | Curiosity Queue | `pipeline.py` | `generate_curiosity` |
| 7 | Memory Decay | `db.py` | `apply_decay` |
| 8 | End-to-End | all | full pipeline integration |
