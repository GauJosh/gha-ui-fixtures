#!/usr/bin/env bash
# Dispatch every scenario so each workflow has at least one passing and one failing run.
# Requires: gh CLI authenticated with permission to dispatch workflows on this repository.
# Usage: scripts/trigger-all.sh [owner/repo]
set -euo pipefail
REPO=${1:-GauJosh/gha-ui-fixtures}
run() { echo "dispatch $*"; gh workflow run --repo "$REPO" "$@"; }

# Pass first, then fail, so "previous successful run" exists for comparison.
for wf in s02-unit-test-failure s03-matrix-failure s04-compile-error s05-cascade-skip s06-timeout s16-composite-then-step \
          s08-dependency-failure s10-log-groups s11-annotations s12-reusable-composite; do
  run "$wf.yml" -f outcome=pass
done
run s09-huge-log.yml -f outcome=pass -f megabytes=5
run s01-baseline.yml
run s13-workflow-change.yml                                   # passes on main
for i in 1 2 3 4 5 6; do run s07-flaky.yml; done              # ~30% fail rate
run s15-rerun-passes.yml                                      # attempt 1 fails

echo "waiting 90s before dispatching failing variants..."; sleep 90
for wf in s02-unit-test-failure s03-matrix-failure s04-compile-error s05-cascade-skip s06-timeout s16-composite-then-step \
          s08-dependency-failure s10-log-groups s11-annotations s12-reusable-composite; do
  run "$wf.yml" -f outcome=fail
done
run s09-huge-log.yml -f outcome=fail -f megabytes=30
run s13-workflow-change.yml --ref scenario/workflow-change    # only the YAML differs -> fails

# Cancellation: the second dispatch cancels the first via the concurrency group.
run s14-cancellation.yml -f seconds=180; sleep 20; run s14-cancellation.yml -f seconds=10

# Re-run attempt 2 of s15 once attempt 1 has failed.
echo "waiting for s15 attempt 1..."; sleep 60
S15=$(gh run list --repo "$REPO" --workflow s15-rerun-passes.yml --limit 1 --json databaseId --jq '.[0].databaseId')
gh run watch --repo "$REPO" "$S15" >/dev/null 2>&1 || true
gh run rerun --repo "$REPO" "$S15" --failed
echo "done; capture with: python scripts/capture.py --repo $REPO --latest-per-workflow 6"
