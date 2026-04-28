# Curiosity Memory System — Claude Code Context

Read `session.txt` at the start of every session. It contains the full project
state, what was built, what is next, and key commands.

## Quick orientation

- **66/66 mock tests passing.** Run `python3 test_harness.py` to verify.
- **8 live tests written but not yet run.** Need `MISTRAL_API_KEY` in env.
- **Next action:** run the live suite once the Mistral API key is available.

## Development rules

This project uses Test-First Driven Development (TFDD). See `orchestrator.md`.

- Never implement more than the current failing test requires
- Never modify a test to make it pass
- Always re-run the failing test alone before implementing
- Always run the full suite after implementing to check for regressions
- Always echo the "Newly Passing" summary and state the next failing test's line number

## Key files

| File | Purpose |
|---|---|
| `curiosity/db.py` | Database layer — fully implemented |
| `curiosity/pipeline.py` | LLM pipeline — fully implemented, Mistral API |
| `test_harness.py` | 66 mock + 8 live tests |
| `meta_test.py` | Validates the test harness itself |
| `orchestrator.md` | TFDD strategy |
| `session.txt` | Full session history and current state |
| `logs/` | Timestamped test run output |

## Commands

```bash
python3 test_harness.py                                          # mock suite
CURIOSITY_LIVE_API=1 MISTRAL_API_KEY=... python3 test_harness.py # live suite
python3 test_harness.py ClassName.test_name                      # single test
python3 meta_test.py                                             # meta checks
```
