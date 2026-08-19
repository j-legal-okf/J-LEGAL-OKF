#!/usr/bin/env python3
"""Verify every source-code citation in the tracked docs still resolves.

A citation by line number drifts the moment anyone edits the cited file, and
nothing verified it still pointed at what a sentence claimed.  This project's
docs instead cite a *symbol*: a fixed-format pair of inline-code spans naming
the source file and the module-level function, class, or constant a claim is
about, for example:

    `src/jlegal_okf/egov.py` `egov_xml_adapter()`

This checker finds every occurrence of that two-span pattern in every tracked
Markdown file and confirms, by parsing the cited file with `ast` (never by
string matching, which would accept a symbol that only appears in a comment
or a string literal), that the named symbol is actually defined at module
level there.

It fails closed: a citation whose file does not exist, whose file cannot be
parsed as Python, or whose named symbol is not defined at module level in
that file, is a reported failure, not a silently skipped citation.

Resolving symbol citations is only half the job. On its own it cannot stop
the old line-number form from being reintroduced, because a line-number
citation simply does not match the symbol pattern and would be scanned past
in silence -- so the drift this checker exists to prevent could return while
the checker still reported success. A second pass therefore rejects any
Python line-number citation outright.

Known residual: the ban covers Python targets only. Line-number references
into non-Python files (a workflow YAML, a changelog) are equally drift-prone
and two of them were found to be already wrong when this checker was written.
They are counted and reported as a note so the residual is visible rather
than assumed absent, but they are not failures, because converting them
needs a per-file notion of a stable anchor that this checker does not have.
"""

from __future__ import annotations

import argparse
import ast
import re
import subprocess
import sys
from pathlib import Path

# Two adjacent single-backtick inline-code spans: a `src/...` or `tests/...`
# path ending in `.py`, then (separated by exactly one space) a bare
# identifier optionally followed by `()`. This is deliberately narrower than
# "any two adjacent backtick spans" -- the path shape is what marks a span as
# this checker's citation format rather than an unrelated pair of inline-code
# mentions that happen to sit next to each other.
CITATION_RE = re.compile(
    r"`((?:src|tests)/[A-Za-z0-9_./-]+\.py)`"
    r" "
    r"`([A-Za-z_][A-Za-z0-9_]*)(\(\))?`"
)

# The banned form this checker replaced: any Python filename -- with or
# without a directory prefix -- followed by a colon and a line number, with an
# optional range. Deliberately does not require the `src/` or `tests/` prefix
# that CITATION_RE does: the bare spelling is exactly the shape that was
# missed when these citations were first enumerated.
LINE_CITATION_RE = re.compile(r"[A-Za-z0-9_./-]*[A-Za-z0-9_-]\.py:\d+(?:-\d+)?")

# The same shape aimed at a non-Python file. Not a failure -- see the module
# docstring's "Known residual" -- but counted so it cannot be assumed absent.
OTHER_LINE_CITATION_RE = re.compile(r"[A-Za-z0-9_./-]*[A-Za-z0-9_-]\.(?!py:)[A-Za-z0-9]+:\d+(?:-\d+)?")


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def tracked_markdown_files(repo_root: Path) -> tuple[list[str], list[str]]:
    """Return tracked POSIX Markdown paths, plus issues if the baseline is unusable."""

    try:
        result = subprocess.run(
            ["git", "-C", str(repo_root), "ls-files", "*.md"],
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError as exc:
        return [], [f"repository baseline unavailable: git ls-files failed: {exc}"]
    if result.returncode != 0:
        detail = result.stderr.strip() or f"exit status {result.returncode}"
        return [], [f"repository baseline unavailable: git ls-files failed: {detail}"]
    paths = sorted(line for line in result.stdout.splitlines() if line)
    return paths, []


def module_level_symbols(source: str) -> set[str] | None:
    """Every module-level function/class/constant name, or None if unparseable."""

    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError):
        # SyntaxError alone is not enough. Measured on CPython 3.12.3: a null
        # byte in the source surfaces as SyntaxError, but a lone surrogate
        # makes ast.parse raise UnicodeEncodeError, which is a ValueError and
        # not a SyntaxError. Letting that escape would replace this checker's
        # fail-closed diagnostic with a traceback. Which spelling raises which
        # exception has moved between CPython releases, and this project's CI
        # runs 3.10 through 3.13, so both are caught rather than relying on
        # one version's behaviour.
        return None
    names: set[str] = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    names.add(target.id)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names.add(node.target.id)
    return names


class _FileStatus:
    """Cached resolution of one cited source file, computed once per path."""

    def __init__(self, problem: str | None, symbols: set[str] | None) -> None:
        self.problem = problem  # None means the file parsed cleanly.
        self.symbols = symbols


def _resolve_file(repo_root: Path, cited_path: str) -> _FileStatus:
    if ".." in Path(cited_path).parts:
        return _FileStatus("cited path contains a parent-traversal component", None)
    target = repo_root / cited_path
    if not target.is_file():
        return _FileStatus("cited file does not exist in this checkout", None)
    try:
        source = target.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return _FileStatus("cited file is not UTF-8 text", None)
    except OSError as exc:
        return _FileStatus(f"cited file is unreadable: {exc}", None)
    symbols = module_level_symbols(source)
    if symbols is None:
        return _FileStatus("cited file could not be parsed as Python", None)
    return _FileStatus(None, symbols)


def check_citations(repo_root: Path) -> tuple[list[str], list[str]]:
    """Check every citation in tracked Markdown. Returns (issues, notes)."""

    doc_paths, issues = tracked_markdown_files(repo_root)
    if issues:
        return issues, []

    file_status: dict[str, _FileStatus] = {}
    checked = 0
    other_line_refs = 0
    for doc_path in doc_paths:
        file_path = repo_root / doc_path
        try:
            text = file_path.read_text(encoding="utf-8")
        except FileNotFoundError:
            issues.append(f"{doc_path}: tracked file is missing from the working tree")
            continue
        except UnicodeDecodeError:
            issues.append(f"{doc_path}: tracked file is not UTF-8 text")
            continue
        except OSError as exc:
            issues.append(f"{doc_path}: unreadable: {exc}")
            continue
        for lineno, line in enumerate(text.splitlines(), start=1):
            for banned in LINE_CITATION_RE.finditer(line):
                issues.append(
                    f"{doc_path}:{lineno}: cites `{banned.group(0)}` by line number; "
                    "cite the module-level symbol instead, as "
                    "`<path>` `<symbol>`, so the reference cannot drift"
                )
            other_line_refs += len(OTHER_LINE_CITATION_RE.findall(line))
            for match in CITATION_RE.finditer(line):
                cited_path, symbol, _call_paren = match.groups()
                checked += 1
                status = file_status.get(cited_path)
                if status is None:
                    status = _resolve_file(repo_root, cited_path)
                    file_status[cited_path] = status
                if status.problem is not None:
                    issues.append(f"{doc_path}:{lineno}: cites `{cited_path}` `{symbol}` -- {status.problem}")
                    continue
                if symbol not in (status.symbols or set()):
                    issues.append(
                        f"{doc_path}:{lineno}: cites `{cited_path}` `{symbol}`, "
                        "which is not defined at module level in that file"
                    )

    notes = [
        f"scanned {len(doc_paths)} tracked Markdown file(s)",
        f"checked {checked} citation(s)",
        f"resolved {len(file_status)} distinct cited source file(s)",
        f"residual gap: {other_line_refs} line-number reference(s) into non-Python "
        "files are counted but not enforced; see this checker's module docstring",
    ]
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

    repo_root = args.repo_root or _repo_root()
    issues, notes = check_citations(repo_root)
    for note in notes:
        print(f"[doc-citations] {note}")
    if issues:
        print("doc citation check failed", file=sys.stderr)
        for issue in sorted(dict.fromkeys(issues)):
            print(f"- {issue}", file=sys.stderr)
        return 1
    print("doc citation check passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
