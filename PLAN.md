# GraderGuard plan

GraderGuard audits the grader of a benchmark task for AI coding agents before the task ships.
A task is only useful if an agent cannot pass it without doing the work, so GraderGuard runs a
library of generic "lazy agent" attempts against the task's own grader inside a sandbox and
reports every attempt the grader wrongly accepts (a hole). It also measures grader strength with
mutation testing and checks the grader for flakiness.

## Decisions

- Fresh repository, MIT. A search for small permissive projects to build on (reward-hacking
  audits, Python mutation testing) found research code and full mutation frameworks with a
  different architecture; neither would be built on directly, so the code starts clean.
- Python 3.12, uv, src layout, Typer CLI, ruff, mypy --strict, pytest with an 85% coverage gate.
- Graders are treated as black boxes: a grader is a command whose exit status (and, later, an
  optional result file) decides pass or fail. The first supported grader style is pytest.
- Every attempt runs in a fresh temporary copy of the task, never in the task directory itself.
  The local sandbox is the default so the tool works without Docker; Docker with
  `--network=none` is added in slice 3 and chosen automatically when available.
- Memory limits use `resource.setrlimit` where the OS honours it (Linux); on macOS only the
  wall-clock timeout is enforced locally, and this is documented as a known limitation.
- All sample tasks and graders are original and small. No LLM or network access is needed.

## Core (deliverable)

- [ ] Smallest end-to-end audit:
  - Task loader for the documented layout: `task.toml` (name, grader command, solution
    command, timeout, output paths, whether tests are visible to the agent), `instruction.md`,
    `environment/`, `solution/`, `tests/`. Clear errors for a malformed task.
  - Local runner: copy the task into a temp workspace, run a command with a timeout and
    process-group kill, capture exit status and truncated output.
  - Baselines: the reference solution must pass and an empty attempt must fail; otherwise the
    audit stops with a clear verdict.
  - Cheat plugin interface (name, description, applicability check, apply step) and the first
    five cheats from the spec.
  - Hole report in JSON and Markdown with a simple severity per cheat.
  - `graderguard audit TASK_DIR [--format json|md] [--out PATH]`, non-zero exit when holes exist.
  - Three original sample tasks under `examples/tasks/`: a grader that only checks the exit
    code, a grader that can be satisfied by hardcoding, and a robust grader. Tests pin that the
    first two have holes and the third has none.
  - `make demo` audits the three samples offline in under a minute; the Docker image runs the
    same demo and the CI docker job runs it.
  - README with real output and measured numbers, and `delivery/graderguard.md`.

## Slices

- [ ] 1. Cheat library, part 1: test-harness integrity. Add the spec's cheats that target the
  test runner itself (editing tests, runner configuration and markers, early-exit tricks,
  patched comparison helpers), bringing the library to at least 11 plugins. Each plugin has
  unit tests for its applicability check and an integration test that pins which sample tasks
  accept it. `graderguard cheats list` prints the catalogue.
- [ ] 2. Cheat library, part 2: environment, output and timing. Add the spec's cheats that target
  what the grader reads rather than how it runs (runtime fixture reads, stubbed processes,
  direct writes to verifier paths, links to expected output, environment injection, oversized
  and empty output, timeouts treated as success), bringing the library to at least 18 plugins.
  Extend the robust sample so it still shows zero holes, and pin every result in tests.
- [ ] 3. Isolation and task layouts. Docker sandbox (`--network=none`, memory and pids limits,
  read-only task copy mounted into a scratch workspace, non-root) chosen by
  `--sandbox auto|local|docker`; an adapter for the plain "pytest directory + solution script"
  layout; `graderguard validate TASK_DIR` for layout checks. Tests cover limit enforcement and
  fall back cleanly when Docker is absent.
- [ ] 4. Reports for CI. A documented severity model (impact x effort), minimal evidence per hole
  (command, workspace diff against the pristine copy, truncated grader output), SARIF 2.1.0
  output checked against the required structure, `--fail-on SEVERITY`, and a composite GitHub
  Action (`action.yml`) with a workflow that runs it on the sample tasks and uploads SARIF.
- [ ] 5. Grader strength via mutation testing. AST mutants of a Python reference solution
  (operator, comparison, constant and return-value mutations) and byte-level mutants of its
  output files; mutants whose output equals the reference output are treated as equivalent and
  skipped. Report a mutation score and the surviving mutants with their diffs;
  `graderguard mutate TASK_DIR [--min-score]`. Tests pin scores on the sample tasks.
- [ ] 6. Determinism. `graderguard flaky TASK_DIR --runs N` reruns the grader on the reference
  solution with shuffled test order (a small bundled pytest plugin), varied `PYTHONHASHSEED`,
  `TZ` and locale, and flags graders whose verdict or per-test outcomes change. A deliberately
  order-dependent fixture task in the test suite proves detection; the robust sample stays
  stable.
