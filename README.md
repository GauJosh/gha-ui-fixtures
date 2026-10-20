# gha-ui-fixtures

Reproducible GitHub Actions scenarios and captured run data for testing **GitHub Actions UI**, a failure-first run explorer. This repository holds test material only and has no application code.

All code, logs, and errors here are **synthetic**. The workflows request `contents: read` only and use no secrets.

## Scenarios

Every scenario runs via `workflow_dispatch`. Most take an `outcome` input (`pass`/`fail`), so the same workflow has both green and red runs to compare.

| # | Workflow | What it exercises |
|---|---|---|
| 01 | `s01-baseline.yml` | Clean pass with `needs` chain (lint, test → build) |
| 02 | `s02-unit-test-failure.yml` | Single pytest failure; final `##[error]` line is uninformative |
| 03 | `s03-matrix-failure.yml` | Same failure across a 2 OS × 3 Python matrix (grouping) |
| 04 | `s04-compile-error.yml` | TypeScript type errors (`tsc`) |
| 05 | `s05-cascade-skip.yml` | Build fails → dependents skipped; `if: always()` report job |
| 06 | `s06-timeout.yml` | Job exceeds `timeout-minutes` |
| 07 | `s07-flaky.yml` | Random ~30% failure (flakiness) |
| 08 | `s08-dependency-failure.yml` | Missing pip package, unresolvable host |
| 09 | `s09-huge-log.yml` | 30 MB log, ANSI colors, 20k-char lines, root cause mid-log |
| 10 | `s10-log-groups.yml` | 50 `::group::` sections, error inside group 37 |
| 11 | `s11-annotations.yml` | `::error/::warning/::notice` with file, line, and column |
| 12 | `s12-reusable-composite.yml` | Failure inside a reusable workflow and a composite action |
| 13 | `s13-workflow-change.yml` | Passes on `main`; branch `scenario/workflow-change` changes only the YAML and fails |
| 14 | `s14-cancellation.yml` | Run cancelled by a concurrency group |
| 15 | `s15-rerun-passes.yml` | Fails on attempt 1, passes on re-run (attempt 2) |
| 16 | `s16-composite-then-step.yml` | Passing composite action followed by a named step that fails, then an unnamed step (step-to-log mapping boundary) |

## Producing and capturing runs

```bash
scripts/trigger-all.sh                    # dispatch all scenarios (pass, then fail)
python scripts/capture.py --repo GauJosh/gha-ui-fixtures --latest-per-workflow 6
```

`capture.py` uses the `gh` CLI for every request, so it never reads or stores a token. It writes `fixtures/<owner>__<repo>/<run_id>/` containing run JSON, the jobs for every attempt, gzipped logs, annotations, the workflow file at `head_sha`, and a `manifest.json`. Files are redacted before they are written: tokens, keys, signed-URL signatures, and non-noreply emails. Private repositories are refused unless `--allow-private` is given.

Captured fixtures are committed, so tests don't depend on GitHub's retention period (default 90 days). Review the diff before committing any capture from a repository other than this one.

## External cases

`fixtures/GauJosh__kubernetes-ai-investigator/` holds read-only captures of that public repository's Actions history, used as real-world test material. No dependency on that project exists.

## License

[Apache-2.0](LICENSE)
