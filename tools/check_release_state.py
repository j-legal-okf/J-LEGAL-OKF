#!/usr/bin/env python3
"""Scan the tracked tree for restatements of whether anything has been released.

`CHANGELOG.md` is the single source of truth for release state.  Before this
checker existed, four other files asserted that state in their own words, and
each one of them would have gone false the moment a tag was cut while the
others stayed current.  That is the failure this checker exists to prevent: not
a wrong sentence, but the same sentence in several places, ageing at different
rates.

Scope, stated plainly because a checker that is believed to cover more than it
does is worse than none: this matches a fixed set of English and Japanese
phrasings of the *negated-existence* claim ("nothing has been tagged", "no
releases exist yet", 「まだタグもリリースも作成されていない」).  A paraphrase
outside that set can still pass.  It is a ratchet against the phrasings this
project has actually written, not a semantic judge.  Add a pattern when a new
phrasing appears; do not add an exemption.

Every exemption is printed on every run, passing or failing, so an exemption
cannot become a silent blind spot.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

# Each entry is (label, regex).  The label is reported with the violation so a
# false positive is diagnosable without re-deriving which rule fired.
#
# The predicates are what carry the meaning, not the nouns.  "tag" and
# "release" appear in plenty of legitimate sentences in this repository — who
# may cut a release, where release state is recorded, that no release preceded
# a change — so a pattern that keys on the nouns alone is a false-positive
# machine.  Every pattern below requires a negated-existence predicate.
RESTATEMENT_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "nothing has been tagged/released",
        re.compile(r"(?i)\bnothing\s+(?:has|is|was)\s+(?:yet\s+)?(?:been\s+)?(?:tagged|released|published)"),
    ),
    (
        "has not/never been tagged/released",
        re.compile(r"(?i)\b(?:has|have|had)\s+(?:not|never)\s+(?:yet\s+)?been\s+(?:tagged|released|published)"),
    ),
    (
        "there is/are no tags/releases",
        re.compile(r"(?i)\bthere\s+(?:is|are)\s+no\s+(?:tags?|releases?|released\s+versions?|tagged\s+versions?)\b"),
    ),
    (
        "no tag/release has been cut",
        re.compile(
            r"(?i)\bno\s+(?:tags?|releases?|versions?)\s+(?:has|have)\s+(?:ever\s+)?been\s+"
            r"(?:tagged|released|cut|published|created|made)"
        ),
    ),
    (
        "no tags/releases exist",
        re.compile(r"(?i)\bno\s+(?:tags?|releases?)(?:\s+or\s+(?:tags?|releases?))?\s+(?:exist|exists)\b"),
    ),
    (
        "a release has not happened",
        re.compile(
            r"(?i)\b(?:releases?|tags?)\s+(?:has|have)\s+(?:not|never)\s+(?:yet\s+)?"
            r"(?:happened|occurred|taken\s+place)"
        ),
    ),
    (
        "タグ／リリースがされていない",
        re.compile(r"(?:タグ|リリース)[^。]{0,30}(?:されていない|されてない|存在しない|されたことがない)"),
    ),
    (
        "タグ／リリースがまだ無い",
        re.compile(r"(?:タグ|リリース)[^。]{0,25}(?:まだ無い|まだない|ありません|存在しません)"),
    ),
)

# `CHANGELOG.md` is the single source of truth, so its own assertion of release
# state is the statement, not a restatement of one.  The other three
# necessarily contain a trigger phrase in order to do their jobs: this file
# holds the patterns, the test holds the positive match cases, and the
# tag-and-release runbook quotes verbatim the CHANGELOG.md sentence it
# instructs the reader to delete.
EXEMPT_PATHS: tuple[tuple[str, str], ...] = (
    ("CHANGELOG.md", "the single source of truth for release state"),
    ("tools/check_release_state.py", "holds the patterns"),
    ("tests/test_version_contract.py", "holds the positive match cases"),
    (
        "docs/oss-release/tag-and-release-runbook-2026-08-16.md",
        "quotes the CHANGELOG.md sentence it instructs the reader to delete",
    ),
    (
        "okf/log.md",
        "dated append-only history; past entries are corrected by a new dated "
        "entry, never rewritten in place",
    ),
)

# A residual gap that follows from an exemption above, printed so that nobody
# has to read this source to discover it.
RESIDUAL_GAPS: tuple[str, ...] = (
    "okf/log.md is exempt as a whole file, so a future dated log entry that "
    "restates release state is not scanned. It is append-only history by "
    "convention, not by enforcement.",
)

BINARY_EXTENSIONS = frozenset(
    {".png", ".jpg", ".jpeg", ".gif", ".pdf", ".zip", ".whl", ".ico", ".woff", ".woff2"}
)

_EXEMPT_PATH_SET = frozenset(path for path, _ in EXEMPT_PATHS)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def tracked_files(repo_root: Path) -> tuple[list[str], list[str]]:
    """Return tracked POSIX paths, plus issues if the baseline is unusable.

    Fails closed, like `check_boundary.py`: a checker that cannot enumerate
    what it is supposed to check has not passed, it has not run.
    """

    try:
        result = subprocess.run(
            ["git", "-C", str(repo_root), "ls-files"],
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError as exc:
        return [], [f"repository baseline unavailable: git ls-files failed: {exc}"]
    if result.returncode != 0:
        detail = result.stderr.strip() or f"exit status {result.returncode}"
        return [], [f"repository baseline unavailable: git ls-files failed: {detail}"]
    paths = [line for line in result.stdout.splitlines() if line]
    if not paths:
        return [], ["repository baseline unavailable: no tracked files"]
    return sorted(paths), []


def paragraphs(text: str) -> list[tuple[int, str]]:
    """Split text into (first line number, joined text) blank-line paragraphs.

    Markdown prose soft-wraps one sentence across physical lines, so a
    per-line scan misses a trigger phrase split across a line break — measured,
    not assumed: "Nothing has\\nbeen tagged or released yet." slipped through a
    per-line version of this scan.  Joining each paragraph before matching
    closes that gap.  The reported line number is the paragraph's first line,
    which is not necessarily the line the match sits on.
    """

    result: list[tuple[int, str]] = []
    buffer: list[str] = []
    start: int | None = None
    for lineno, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if not stripped:
            if buffer and start is not None:
                result.append((start, " ".join(buffer)))
            buffer = []
            start = None
            continue
        if start is None:
            start = lineno
        buffer.append(stripped)
    if buffer and start is not None:
        result.append((start, " ".join(buffer)))
    return result


def matching_pattern(text: str) -> str | None:
    """Return the label of the first pattern that fires, or None.

    Each pattern is tried against the text as given and against the text with
    all whitespace removed.  The second form exists because `paragraphs()`
    joins soft-wrapped lines with a space, which is right for English — words
    are space-separated there — and wrong for Japanese, which is not.  A
    sentence wrapped as 「…リリースされて / いない」 joins to
    「リリースされて いない」 and a pattern requiring 「されていない」 misses
    it.  This was measured, not anticipated: scanning the pre-change tree
    found three of its four restatements and silently skipped the Japanese
    one, which was the specific instance this scan was widened to catch.
    English patterns cannot match the squashed form (they all require `\\s+`),
    so trying both costs nothing and closes the gap for CJK text.
    """

    squashed = re.sub(r"\s+", "", text)
    for label, pattern in RESTATEMENT_PATTERNS:
        if pattern.search(text) or pattern.search(squashed):
            return label
    return None


def scan_tree(repo_root: Path) -> tuple[list[str], list[str]]:
    """Scan every tracked file outside the exemptions. Returns (issues, notes)."""

    paths, issues = tracked_files(repo_root)
    if issues:
        return issues, []

    notes = [f"scanned {len(paths)} tracked files", f"patterns: {len(RESTATEMENT_PATTERNS)}"]
    for path, reason in EXEMPT_PATHS:
        notes.append(f"exempt: {path} ({reason})")
    for gap in RESIDUAL_GAPS:
        notes.append(f"residual gap: {gap}")

    scanned = 0
    for path in paths:
        if path in _EXEMPT_PATH_SET:
            continue
        if Path(path).suffix.lower() in BINARY_EXTENSIONS:
            continue
        file_path = repo_root / path
        try:
            text = file_path.read_text(encoding="utf-8")
        except FileNotFoundError:
            issues.append(f"{path}: tracked file is missing from the working tree")
            continue
        except UnicodeDecodeError:
            continue
        except OSError as exc:
            issues.append(f"{path}: unreadable: {exc}")
            continue
        scanned += 1
        for start_line, paragraph in paragraphs(text):
            label = matching_pattern(paragraph)
            if label is not None:
                issues.append(f"{path}:{start_line}: {label}: {paragraph!r}")
    notes.append(f"content-scanned {scanned} of them as text")
    return issues, notes


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=None,
        help="repository to scan (default: the checkout containing this script)",
    )
    args = parser.parse_args(argv)

    issues, notes = scan_tree(args.repo_root or _repo_root())
    for note in notes:
        print(f"[release-state] {note}")
    if issues:
        print("release-state check failed", file=sys.stderr)
        for issue in sorted(dict.fromkeys(issues)):
            print(f"- {issue}", file=sys.stderr)
        return 1
    print("release-state check passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
