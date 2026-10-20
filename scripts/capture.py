#!/usr/bin/env python3
"""Capture GitHub Actions run data as durable, sanitized test fixtures.

Uses the GitHub CLI (`gh api`) for all requests, so this script never reads,
stores or prints a token. Read-only: it issues GET requests only.

Output layout (one directory per run):
    fixtures/<owner>__<repo>/<run_id>/
        manifest.json              what was captured, when, and how it was sanitized
        run.json                   GET /actions/runs/{id}
        attempts/<n>/jobs.json     GET /actions/runs/{id}/attempts/{n}/jobs (all attempts)
        logs/<job_id>.log.gz       GET /actions/jobs/{job_id}/logs (or a .status file if unavailable)
        annotations/<job_id>.json  GET /check-runs/{job_id}/annotations
        workflow.yml               workflow file at the run's head_sha

Examples:
    python scripts/capture.py --repo GauJosh/gha-ui-fixtures --run 123 --run 456
    python scripts/capture.py --repo GauJosh/gha-ui-fixtures --latest-per-workflow 3
"""
from __future__ import annotations

import argparse
import base64
import datetime as dt
import gzip
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCHEMA_VERSION = 1

# Patterns redacted from every captured file. Synthetic data should never match,
# but captures of real repositories (e.g. external cases) may.
REDACTIONS: list[tuple[str, re.Pattern[str], str]] = [
    ("github-token", re.compile(r"\b(gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})\b"), "[REDACTED:github-token]"),
    ("bearer", re.compile(r"(?i)\b(bearer|token)\s+[A-Za-z0-9._~+/=-]{20,}"), r"\1 [REDACTED]"),
    ("aws-key", re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "[REDACTED:aws-key]"),
    ("private-key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----"), "[REDACTED:private-key]"),
    ("signed-url", re.compile(r"([?&](sig|signature|X-Amz-Signature|token)=)[^&\s\"']+", re.I), r"\1[REDACTED]"),
    ("email", re.compile(r"\b[A-Za-z0-9._%+-]+@(?!users\.noreply\.github\.com\b)[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"), "redacted@example.invalid"),
]


class GhError(RuntimeError):
    def __init__(self, path: str, status: str, message: str):
        super().__init__(f"{path}: HTTP {status} {message}")
        self.status = status


def gh_api(path: str, raw: bool = False) -> bytes | dict:
    proc = subprocess.run(["gh", "api", "-H", "Accept: application/vnd.github+json", path], capture_output=True)
    if proc.returncode != 0:
        err = proc.stderr.decode("utf-8", "replace")
        match = re.search(r"HTTP (\d{3})", err)
        raise GhError(path, match.group(1) if match else "?", err.strip()[:200])
    return proc.stdout if raw else json.loads(proc.stdout)


def sanitize(text: str, counts: dict[str, int]) -> str:
    for name, pattern, repl in REDACTIONS:
        text, n = pattern.subn(repl, text)
        if n:
            counts[name] = counts.get(name, 0) + n
    return text


def write_json(path: Path, data: object, counts: dict[str, int]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(sanitize(json.dumps(data, indent=2, sort_keys=True), counts) + "\n", encoding="utf-8", newline="\n")


def capture_run(repo: str, run_id: int, out_root: Path) -> Path:
    counts: dict[str, int] = {}
    out = out_root / repo.replace("/", "__") / str(run_id)
    out.mkdir(parents=True, exist_ok=True)

    run = gh_api(f"repos/{repo}/actions/runs/{run_id}")
    write_json(out / "run.json", run, counts)

    logs: dict[str, str] = {}
    for attempt in range(1, run["run_attempt"] + 1):
        jobs = gh_api(f"repos/{repo}/actions/runs/{run_id}/attempts/{attempt}/jobs?per_page=100")
        write_json(out / "attempts" / str(attempt) / "jobs.json", jobs, counts)
        for job in jobs["jobs"]:
            jid = str(job["id"])
            try:
                text = gh_api(f"repos/{repo}/actions/jobs/{jid}/logs", raw=True).decode("utf-8", "replace")
                (out / "logs").mkdir(exist_ok=True)
                with gzip.open(out / "logs" / f"{jid}.log.gz", "wt", encoding="utf-8", newline="") as fh:
                    fh.write(sanitize(text, counts))
                logs[jid] = "ok"
            except GhError as e:  # 410 = expired, 404 = never produced (e.g. skipped job)
                logs[jid] = f"unavailable:{e.status}"
            try:
                write_json(out / "annotations" / f"{jid}.json", gh_api(f"repos/{repo}/check-runs/{jid}/annotations"), counts)
            except GhError:
                pass

    try:
        content = gh_api(f"repos/{repo}/contents/{run['path']}?ref={run['head_sha']}")
        (out / "workflow.yml").write_text(sanitize(base64.b64decode(content["content"]).decode("utf-8"), counts), encoding="utf-8", newline="\n")
    except (GhError, KeyError):
        pass

    write_json(out / "manifest.json", {
        "schema_version": SCHEMA_VERSION,
        "source": {"repo": repo, "run_id": run_id, "html_url": run["html_url"]},
        "workflow": run["name"], "conclusion": run["conclusion"], "event": run["event"],
        "head_branch": run["head_branch"], "head_sha": run["head_sha"], "attempts": run["run_attempt"],
        "captured_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "logs": logs, "redactions": counts,
    }, {})
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", required=True, help="owner/name")
    ap.add_argument("--run", type=int, action="append", default=[], help="run id (repeatable)")
    ap.add_argument("--latest-per-workflow", type=int, metavar="N", help="capture the N latest completed runs of every workflow")
    ap.add_argument("--out", type=Path, default=ROOT / "fixtures")
    ap.add_argument("--allow-private", action="store_true", help="permit capturing a private repository (fixtures are published publicly)")
    args = ap.parse_args()

    if gh_api(f"repos/{args.repo}")["private"] and not args.allow_private:
        print(f"refusing: {args.repo} is private and this fixture repo is public (use --allow-private deliberately)", file=sys.stderr)
        return 2

    run_ids = list(args.run)
    if args.latest_per_workflow:
        for wf in gh_api(f"repos/{args.repo}/actions/workflows?per_page=100")["workflows"]:
            runs = gh_api(f"repos/{args.repo}/actions/workflows/{wf['id']}/runs?status=completed&per_page={args.latest_per_workflow}")
            run_ids += [r["id"] for r in runs["workflow_runs"]]
    if not run_ids:
        ap.error("nothing to capture: pass --run or --latest-per-workflow")

    for rid in dict.fromkeys(run_ids):
        try:
            print(f"captured {capture_run(args.repo, rid, args.out).relative_to(ROOT)}")
        except GhError as e:
            print(f"skipped run {rid}: {e}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
