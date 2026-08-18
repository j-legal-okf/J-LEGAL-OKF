#!/usr/bin/env python3
"""Check that every commit in a range carries a valid DCO sign-off.

`CONTRIBUTING.md` requires a `Signed-off-by` line on every contribution and
`GOVERNANCE.md` states that contributions are accepted under the DCO from the
start.  Until now nothing enforced either sentence.

The check runs over a commit range rather than over all history, so it applies
to what a pull request proposes.  The repository's own first two commits
predate this check and carry no sign-off; re-writing them is not possible
without discarding the audited single-commit history, so they are out of
range by design rather than by exemption.

Merge commits are skipped: a merge is created by the forge, not authored by
the contributor whose certification the DCO is about.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys

SIGNED_OFF_BY_RE = re.compile(
    r"^Signed-off-by:\s*(?P<name>.+?)\s*<(?P<email>[^<>]+)>\s*$",
    re.MULTILINE,
)

RECORD_SEPARATOR = "\x1e"
FIELD_SEPARATOR = "\x1f"


def _git(args: list[str]) -> tuple[int, str, str]:
    try:
        result = subprocess.run(
            ["git", *args], check=False, capture_output=True, text=True
        )
    except OSError as exc:  # pragma: no cover - depends on a broken environment
        return 1, "", str(exc)
    return result.returncode, result.stdout, result.stderr


def commits_in_range(commit_range: str, repo_root: str | None = None) -> tuple[list[dict[str, str]], list[str]]:
    """Return one record per non-merge commit in the range."""

    prefix = ["-C", repo_root] if repo_root else []
    fmt = FIELD_SEPARATOR.join(["%H", "%an", "%ae", "%cn", "%ce", "%B"]) + RECORD_SEPARATOR
    code, out, err = _git([*prefix, "log", "--no-merges", f"--format={fmt}", commit_range])
    if code != 0:
        detail = err.strip() or f"exit status {code}"
        return [], [f"commit range unavailable: git log {commit_range} failed: {detail}"]

    commits: list[dict[str, str]] = []
    for raw in out.split(RECORD_SEPARATOR):
        record = raw.strip("\n")
        if not record.strip():
            continue
        fields = record.split(FIELD_SEPARATOR)
        if len(fields) != 6:
            return commits, [f"unparsable git log record: {record!r}"]
        sha, author_name, author_email, committer_name, committer_email, body = fields
        commits.append(
            {
                "sha": sha,
                "author_name": author_name,
                "author_email": author_email,
                "committer_name": committer_name,
                "committer_email": committer_email,
                "body": body,
            }
        )
    return commits, []


def check_commit(commit: dict[str, str]) -> list[str]:
    """Report DCO problems for one commit."""

    short = commit["sha"][:12]
    signoffs = [
        (match.group("name").strip(), match.group("email").strip().lower())
        for match in SIGNED_OFF_BY_RE.finditer(commit["body"])
    ]
    if not signoffs:
        return [
            f"{short}: no Signed-off-by line "
            f"(author {commit['author_name']} <{commit['author_email']}>); "
            "commit with `git commit -s`"
        ]

    accepted = {
        commit["author_email"].strip().lower(),
        commit["committer_email"].strip().lower(),
    }
    if any(email in accepted for _name, email in signoffs):
        return []
    listed = ", ".join(sorted(f"<{email}>" for _name, email in signoffs))
    return [
        f"{short}: Signed-off-by {listed} matches neither the author "
        f"<{commit['author_email']}> nor the committer <{commit['committer_email']}>"
    ]


def check_range(commit_range: str, repo_root: str | None = None) -> tuple[list[str], list[str]]:
    commits, issues = commits_in_range(commit_range, repo_root)
    if issues:
        return issues, []
    notes = [f"checked {len(commits)} non-merge commit(s) in {commit_range}"]
    for commit in commits:
        issues.extend(check_commit(commit))
    return issues, notes


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "range",
        help="commit range to check, e.g. origin/main..HEAD or <base-sha>..<head-sha>",
    )
    parser.add_argument("--repo-root", default=None, help="repository to inspect")
    args = parser.parse_args(argv)

    issues, notes = check_range(args.range, args.repo_root)
    for note in notes:
        print(f"[dco] {note}")
    if issues:
        print("DCO check failed", file=sys.stderr)
        for issue in sorted(dict.fromkeys(issues)):
            print(f"- {issue}", file=sys.stderr)
        return 1
    print("DCO check passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
