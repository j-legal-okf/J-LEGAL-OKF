#!/usr/bin/env python3
"""Scan the tracked repository tree for public/private boundary violations.

`verify_distribution.py` checks what a *built artifact* contains.  This checker
covers the gap in front of it: the repository tree itself.  Every finding this
project has had to remediate by hand — a local absolute path in a blob, a
private repository name in a commit's tree, a username — lived in the tree
before it ever reached an artifact, and nothing ran automatically against the
tree.

It fails closed: an unreadable baseline, an undecodable text file, or an
unclassifiable path is an issue, not a skip.

The built-in patterns name nothing outside this project.  A name that is
private is itself private information, so it does not belong in a repository
that will be published: supply such patterns with `--extra-patterns FILE`,
keeping the file wherever that knowledge already lives.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from verify_distribution import PRIVATE_PATH_MARKERS  # noqa: E402

# The test plants a violation for every rule, so it necessarily contains the
# strings the content patterns look for.  This checker's own source does not:
# a test asserts that, so an added pattern that matches this file has to be
# reconsidered rather than exempted.  The exemption applies to the content scan
# only, the path scan still covers the exempt file, and it is printed on every
# run so it cannot become a silent blind spot.
SELF_EXEMPT_PATHS = ("tests/test_boundary_checks.py",)

# Extensions whose contents are not scanned as text.  A file outside this set
# that cannot be decoded as UTF-8 is reported rather than skipped.
BINARY_EXTENSIONS = frozenset(
    {".png", ".jpg", ".jpeg", ".gif", ".pdf", ".zip", ".whl", ".ico", ".woff", ".woff2"}
)

# The identity every commit and every document in this repository may carry.
ALLOWED_EMAILS = frozenset({"294216476+okf-works@users.noreply.github.com"})

# Domains reserved for documentation examples (RFC 2606) never count as a
# real address.
EXAMPLE_EMAIL_DOMAINS = ("example.com", "example.org", "example.net")

CONTENT_PATTERNS: tuple[tuple[str, str], ...] = (
    ("local absolute home path", r"/home/[A-Za-z0-9._-]+/"),
    ("Windows user path", r"[A-Za-z]:\\Users\\"),
    ("WSL mount path", r"/mnt/[a-z]/"),
    ("AWS access key id", r"AKIA[0-9A-Z]{16}"),
    ("GitHub token", r"gh[pousr]_[A-Za-z0-9]{20,}"),
    ("OpenAI-style token", r"\bsk-[A-Za-z0-9]{20,}"),
    ("Slack token", r"xox[baprs]-[A-Za-z0-9-]{10,}"),
    ("PEM private key block", r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    (
        "secret assignment",
        r"(?i)\b(password|secret|api[_-]?key|access[_-]?token|client[_-]?secret)"
        r"\s*[:=]\s*['\"][^'\"]{6,}['\"]",
    ),
    (
        "credentialed connection string",
        r"(?i)\b(postgres|postgresql|mysql|mongodb|redis|amqp)(\+\w+)?://[^\s/@]+:[^\s/@]+@",
    ),
)

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def load_extra_patterns(path: Path) -> tuple[tuple[tuple[str, str], ...], list[str]]:
    """Load `label = regex` lines from a file kept outside this repository.

    Returns the patterns and any issues. A missing file, a malformed line, or
    an invalid regex is an issue: a caller that asked for extra patterns must
    not silently get fewer checks than it asked for.
    """

    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        return (), [f"extra patterns unavailable: {path}: {exc}"]

    patterns: list[tuple[str, str]] = []
    issues: list[str] = []
    for lineno, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        label, separator, expression = line.partition("=")
        if not separator or not label.strip() or not expression.strip():
            issues.append(f"{path}:{lineno}: expected 'label = regex', got {raw!r}")
            continue
        expression = expression.strip()
        try:
            re.compile(expression)
        except re.error as exc:
            issues.append(f"{path}:{lineno}: invalid regex {expression!r}: {exc}")
            continue
        patterns.append((label.strip(), expression))
    if not patterns and not issues:
        issues.append(f"extra patterns file has no patterns: {path}")
    return tuple(patterns), issues


def tracked_files(repo_root: Path) -> tuple[list[str], list[str]]:
    """Return tracked POSIX paths, plus issues if the baseline is unusable."""

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


def check_path(path: str) -> list[str]:
    """Report private markers and unsafe shapes in a tracked path."""

    issues: list[str] = []
    lowered = path.lower()
    for marker in PRIVATE_PATH_MARKERS:
        if marker in lowered:
            issues.append(f"{path}: private path marker {marker!r}")
    if path.startswith("/") or re.match(r"^[A-Za-z]:", path):
        issues.append(f"{path}: absolute tracked path")
    if "\\" in path:
        issues.append(f"{path}: backslash in tracked path")
    if any(part == ".." for part in path.split("/")):
        issues.append(f"{path}: parent traversal component in tracked path")
    return issues


def check_content(
    path: str,
    text: str,
    patterns: tuple[tuple[str, str], ...] = CONTENT_PATTERNS,
) -> list[str]:
    """Report boundary-violating content in one tracked text file."""

    issues: list[str] = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        for label, pattern in patterns:
            match = re.search(pattern, line)
            if match:
                issues.append(f"{path}:{lineno}: {label}: {match.group(0)!r}")
        for match in EMAIL_RE.finditer(line):
            address = match.group(0)
            if address in ALLOWED_EMAILS:
                continue
            if address.lower().endswith(EXAMPLE_EMAIL_DOMAINS):
                continue
            issues.append(f"{path}:{lineno}: e-mail address: {address!r}")
    return issues


def check_tree(
    repo_root: Path,
    extra_patterns: tuple[tuple[str, str], ...] = (),
) -> tuple[list[str], list[str]]:
    """Check every tracked file. Returns (issues, notes)."""

    paths, issues = tracked_files(repo_root)
    if issues:
        return issues, []

    patterns = CONTENT_PATTERNS + tuple(extra_patterns)
    notes = [
        f"scanned {len(paths)} tracked files",
        f"content patterns: {len(CONTENT_PATTERNS)} built in, {len(extra_patterns)} supplied",
        "content scan exempts (each necessarily contains the patterns): "
        + ", ".join(SELF_EXEMPT_PATHS),
    ]
    scanned = 0
    for path in paths:
        issues.extend(check_path(path))
        if path in SELF_EXEMPT_PATHS:
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
            issues.append(f"{path}: tracked file is not UTF-8 text and has no binary extension")
            continue
        except OSError as exc:
            issues.append(f"{path}: unreadable: {exc}")
            continue
        scanned += 1
        issues.extend(check_content(path, text, patterns))
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
    parser.add_argument(
        "--extra-patterns",
        type=Path,
        default=None,
        help=(
            "file of additional 'label = regex' content patterns, kept outside "
            "this repository (see the module docstring)"
        ),
    )
    args = parser.parse_args(argv)

    extra: tuple[tuple[str, str], ...] = ()
    if args.extra_patterns is not None:
        extra, extra_issues = load_extra_patterns(args.extra_patterns)
        if extra_issues:
            print("boundary check failed", file=sys.stderr)
            for issue in extra_issues:
                print(f"- {issue}", file=sys.stderr)
            return 1

    repo_root = args.repo_root or _repo_root()
    issues, notes = check_tree(repo_root, extra)
    for note in notes:
        print(f"[boundary] {note}")
    if issues:
        print("boundary check failed", file=sys.stderr)
        for issue in sorted(dict.fromkeys(issues)):
            print(f"- {issue}", file=sys.stderr)
        return 1
    print("boundary check passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
