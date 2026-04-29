# Curiosity Memory System — Claude Code Context

Read `session.txt` at the start of every session. It contains the full project
state, what was built, what is next, and key commands.

## Quick orientation

- **74/74 tests passing** (66 mock + 8 live Mistral API).
- **1 playwright test passing** (`tests/test_grid_visible.py`).
- Run everything: `source .envrc && CURIOSITY_LIVE_API=1 pytest tests/test_harness.py && .venv/bin/pytest tests/test_grid_visible.py`

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
| `tests/test_harness.py` | 66 mock + 8 live tests (custom TFDD runner) |
| `tests/test_grid_visible.py` | Playwright UI test |
| `tests/meta_test.py` | Validates the test harness itself (TFDD contract) |
| `orchestrator.md` | TFDD strategy |
| `session.txt` | Full session history and current state |
| `logs/` | Timestamped test run output |

## Commands

```bash
# Run all tests (recommended)
source .envrc && CURIOSITY_LIVE_API=1 pytest tests/test_harness.py
.venv/bin/pytest tests/test_grid_visible.py

# TFDD-formatted output (line numbers, newly-passing summary, log file)
source .envrc && CURIOSITY_LIVE_API=1 python3 tests/test_harness.py

# Single test re-run
python3 tests/test_harness.py ClassName.test_name

# Meta harness (validates pre-implementation contract — expects all 66 to fail)
python3 tests/meta_test.py
```
