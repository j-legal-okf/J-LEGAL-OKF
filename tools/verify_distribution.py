#!/usr/bin/env python3
"""Verify the public allowlist of the J-LEGAL-OKF distributions.

The verifier reads archive member names only.  It deliberately does not
extract either archive, and it fails closed when the repository baseline, an
archive entry, or a requested external pattern file cannot be classified.
"""

from __future__ import annotations

import argparse
import re
import stat
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path


DIST_NAME = "jlegal_okf"
SDIST_ROOT_RE = re.compile(r"^jlegal(?:[-_.]+)okf-[^/]+$")

FIXED_SDIST_FILES = {
    "pyproject.toml",
    "README.md",
    "LICENSE",
    "NOTICE",
    "ARCHITECTURE_BOUNDARY.md",
    "CHANGELOG.md",
    "CODE_OF_CONDUCT.md",
    "CONTRIBUTING.md",
    "GOVERNANCE.md",
    "SECURITY.md",
}

# Setuptools-generated files observed in a source distribution.  These are
# metadata, not public source content, and are intentionally kept narrow.
SDIST_METADATA_FILES = {
    "MANIFEST.in",
    "PKG-INFO",
    "setup.cfg",
    "src/jlegal_okf.egg-info/PKG-INFO",
    "src/jlegal_okf.egg-info/SOURCES.txt",
    "src/jlegal_okf.egg-info/dependency_links.txt",
    "src/jlegal_okf.egg-info/entry_points.txt",
    "src/jlegal_okf.egg-info/requires.txt",
    "src/jlegal_okf.egg-info/top_level.txt",
}

FORBIDDEN_SDIST_ROOTS = {".github", "okf", "tools"}
FORBIDDEN_SDIST_FILES = {".gitignore", "OKF.md"}
FORBIDDEN_WHEEL_ROOTS = {
    ".github",
    ".git",
    "docs",
    "examples",
    "okf",
    "tests",
    "tools",
}
FORBIDDEN_WHEEL_FILES = {".gitignore", "OKF.md", "AGENTS.md"}

# These markers are private-boundary indicators, even when an attacker gives
# a path an otherwise plausible public-looking suffix.
PRIVATE_PATH_MARKERS = (
    "municipal",
    "private",
    "openrouter",
    "audition",
    "evaluation",
    "enrichment",
    "legacy",
)


def _repo_root() -> Path:
    """Return the checkout containing this verifier."""

    return Path(__file__).resolve().parents[1]


def load_extra_patterns(path: Path) -> tuple[tuple[tuple[str, str], ...], list[str]]:
    """Load fail-closed ``label = regex`` path patterns from *path*.

    Names that belong only to a Private consumer stay outside this public
    repository.  Callers that own those names can supply them for both the
    repository-tree and distribution-member scans.
    """

    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
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


def _extra_pattern_issues(
    prefix: str,
    member_path: str,
    patterns: tuple[tuple[str, str], ...],
) -> list[str]:
    """Report every supplied pattern that matches an archive member path."""

    issues: list[str] = []
    for label, expression in patterns:
        if re.search(expression, member_path):
            issues.append(
                f"{prefix}: supplied private path pattern {label!r}: {member_path}"
            )
    return issues


def _git_tracked_files(repo_root: Path) -> tuple[set[str], list[str]]:
    """Return tracked POSIX paths and a diagnostic list on Git failure."""

    try:
        result = subprocess.run(
            ["git", "-C", str(repo_root), "ls-files"],
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError as exc:
        return set(), [f"repository baseline unavailable: git ls-files failed: {exc}"]
    if result.returncode != 0:
        detail = result.stderr.strip() or f"exit status {result.returncode}"
        return set(), [f"repository baseline unavailable: git ls-files failed: {detail}"]
    return {line for line in result.stdout.splitlines() if line}, []


def _expected_source_files(repo_root: Path) -> tuple[set[str], set[str], list[str]]:
    """Build the dynamic allowlists from Git-tracked public files."""

    tracked, issues = _git_tracked_files(repo_root)
    docs = {
        path
        for path in tracked
        if path.startswith("docs/") and path.endswith(".md")
    }
    examples = {
        path
        for path in tracked
        if path.startswith("examples/") and path.endswith((".xml", ".json"))
    }
    tests = {
        path
        for path in tracked
        if path.startswith("tests/") and path.endswith(".py")
    }
    package = {
        path.removeprefix("src/")
        for path in tracked
        if path.startswith("src/jlegal_okf/") and path.endswith(".py")
    }
    sdist = FIXED_SDIST_FILES | docs | examples | tests | {
        path
        for path in tracked
        if path.startswith("src/jlegal_okf/") and path.endswith(".py")
    }
    return sdist, package, issues


def _safe_member_name(raw_name: str) -> tuple[str | None, list[str]]:
    """Validate an archive name before any root-prefix normalization."""

    issues: list[str] = []
    if not raw_name:
        return None, ["empty archive member name"]

    # Archive paths are POSIX paths.  Treat backslashes as separators while
    # checking so a Windows-style traversal cannot bypass the '..' check.
    posix_name = raw_name.replace("\\", "/")
    if posix_name != raw_name:
        issues.append("backslash path separator")
    if posix_name.startswith("/") or re.match(r"^[A-Za-z]:/", posix_name):
        issues.append("absolute path")

    parts = posix_name.split("/")
    while parts and parts[-1] == "":
        parts.pop()
    if any(part == ".." for part in parts):
        issues.append("parent traversal component '..'")
    if any(part == "." for part in parts):
        issues.append("non-canonical path component '.'")
    if any(part == "" for part in parts):
        issues.append("empty path component")
    if issues:
        return None, issues
    if not parts:
        return None, ["empty archive member path"]
    return "/".join(parts), []


def _private_marker(path: str) -> str | None:
    lowered = path.lower()
    for marker in PRIVATE_PATH_MARKERS:
        if marker in lowered:
            return marker
    return None


def _forbidden_sdist_path(path: str) -> str | None:
    parts = path.split("/")
    if path in FORBIDDEN_SDIST_FILES:
        return "forbidden public-candidate file"
    if parts and parts[0] in FORBIDDEN_SDIST_ROOTS:
        return "forbidden public-candidate tree"
    return None


def _forbidden_wheel_path(path: str) -> str | None:
    parts = path.split("/")
    if path in FORBIDDEN_WHEEL_FILES:
        return "forbidden wheel file"
    if parts and parts[0] in FORBIDDEN_WHEEL_ROOTS:
        return "forbidden wheel tree"
    if parts and parts[0].endswith(".data"):
        return "wheel .data tree is forbidden"
    return None


def _is_prefix_of_allowed(path: str, allowed: set[str]) -> bool:
    return any(candidate.startswith(path + "/") for candidate in allowed)


def verify_sdist(
    path: Path,
    repo_root: Path,
    extra_patterns: tuple[tuple[str, str], ...] = (),
) -> list[str]:
    """Verify a source archive without extracting it."""

    prefix = f"sdist {path}"
    issues: list[str] = []
    expected, _package, baseline_issues = _expected_source_files(repo_root)
    issues.extend(f"{prefix}: {issue}" for issue in baseline_issues)
    if not path.is_file():
        return issues + [f"{prefix}: archive is missing"]

    entries: list[tuple[str, bool, bool]] = []
    seen: set[str] = set()
    try:
        with tarfile.open(path, mode="r:*") as archive:
            for member in archive.getmembers():
                raw_name = member.name
                normalized, safety_issues = _safe_member_name(raw_name)
                for reason in safety_issues:
                    issues.append(f"{prefix}: unsafe path {raw_name!r}: {reason}")
                if normalized is None:
                    continue
                issues.extend(_extra_pattern_issues(prefix, normalized, extra_patterns))
                if normalized in seen:
                    issues.append(f"{prefix}: duplicate archive path: {raw_name}")
                seen.add(normalized)
                is_dir = member.isdir()
                if not is_dir and not member.isreg():
                    issues.append(
                        f"{prefix}: unsafe non-regular archive entry: {raw_name}"
                    )
                entries.append((normalized, is_dir, member.isreg()))
    except (OSError, tarfile.TarError) as exc:
        return issues + [f"{prefix}: unable to read archive: {exc}"]

    if not entries:
        issues.append(f"{prefix}: archive has no safe entries")
        return issues

    roots = {normalized.split("/", 1)[0] for normalized, _is_dir, _is_reg in entries}
    root = sorted(roots)[0]
    if len(roots) != 1:
        for normalized, _is_dir, _is_reg in entries:
            if normalized.split("/", 1)[0] != root:
                issues.append(
                    f"{prefix}: entry is outside the single distribution root: {normalized}"
                )
    if not SDIST_ROOT_RE.fullmatch(root):
        issues.append(f"{prefix}: unexpected distribution root: {root}")

    relative_entries: list[tuple[str, bool, bool]] = []
    for normalized, is_dir, is_reg in entries:
        if normalized == root:
            if not is_dir:
                issues.append(f"{prefix}: distribution root is not a directory: {normalized}")
            continue
        root_prefix = root + "/"
        if not normalized.startswith(root_prefix):
            continue
        relative = normalized[len(root_prefix) :]
        if not relative:
            issues.append(f"{prefix}: empty path after distribution root: {normalized}")
            continue
        relative_entries.append((relative, is_dir, is_reg))

    actual_files: set[str] = set()
    allowed_paths = expected | SDIST_METADATA_FILES
    for relative, is_dir, is_reg in relative_entries:
        forbidden = _forbidden_sdist_path(relative)
        if forbidden:
            issues.append(f"{prefix}: {forbidden}: {relative}")
        marker = _private_marker(relative)
        if marker:
            issues.append(f"{prefix}: private identifier/path marker {marker!r}: {relative}")
        if is_reg:
            actual_files.add(relative)
            if relative not in allowed_paths:
                issues.append(f"{prefix}: unexpected file: {relative}")
        elif is_dir and not _is_prefix_of_allowed(relative, allowed_paths):
            issues.append(f"{prefix}: unexpected directory: {relative}")

    root_label = root if root else "<distribution-root>"
    for missing in sorted(expected - actual_files):
        issues.append(f"{prefix}: missing required path: {root_label}/{missing}")

    # A regular archive member outside the normalized root was already
    # reported above; this catches a root with no usable relative entries too.
    for normalized, _is_dir, _is_reg in entries:
        if normalized.split("/", 1)[0] != root:
            issues.append(f"{prefix}: unexpected top-level path: {normalized}")
    return issues


def _dist_info_required_paths(dist_info: str) -> tuple[set[str], set[str]]:
    required = {
        f"{dist_info}/METADATA",
        f"{dist_info}/WHEEL",
        f"{dist_info}/RECORD",
        f"{dist_info}/entry_points.txt",
        f"{dist_info}/top_level.txt",
    }
    license_alternatives = {
        f"{dist_info}/LICENSE",
        f"{dist_info}/licenses/LICENSE",
    }
    notice_alternatives = {
        f"{dist_info}/NOTICE",
        f"{dist_info}/licenses/NOTICE",
    }
    return required, license_alternatives | notice_alternatives


def verify_wheel(
    path: Path,
    repo_root: Path,
    extra_patterns: tuple[tuple[str, str], ...] = (),
) -> list[str]:
    """Verify a wheel's package and setuptools metadata allowlist."""

    prefix = f"wheel {path}"
    issues: list[str] = []
    _expected_sdist, expected_package, baseline_issues = _expected_source_files(repo_root)
    issues.extend(f"{prefix}: {issue}" for issue in baseline_issues)
    if not path.is_file():
        return issues + [f"{prefix}: archive is missing"]

    entries: list[tuple[str, bool]] = []
    seen: set[str] = set()
    try:
        with zipfile.ZipFile(path) as archive:
            for info in archive.infolist():
                raw_name = info.filename
                normalized, safety_issues = _safe_member_name(raw_name)
                for reason in safety_issues:
                    issues.append(f"{prefix}: unsafe path {raw_name!r}: {reason}")
                if normalized is None:
                    continue
                issues.extend(_extra_pattern_issues(prefix, normalized, extra_patterns))
                if normalized in seen:
                    issues.append(f"{prefix}: duplicate archive path: {raw_name}")
                seen.add(normalized)
                mode = (info.external_attr >> 16) & 0xFFFF
                if stat.S_ISLNK(mode):
                    issues.append(f"{prefix}: unsafe symlink entry: {raw_name}")
                is_dir = info.is_dir() or raw_name.endswith(("/", "\\"))
                entries.append((normalized, is_dir))
    except (OSError, zipfile.BadZipFile) as exc:
        return issues + [f"{prefix}: unable to read archive: {exc}"]

    if not entries:
        return issues + [f"{prefix}: archive has no safe entries"]

    dist_info_dirs = {
        normalized.split("/", 1)[0]
        for normalized, _is_dir in entries
        if ".dist-info" in normalized.split("/", 1)[0]
    }
    valid_dist_info_dirs = {
        candidate
        for candidate in dist_info_dirs
        if re.fullmatch(rf"{re.escape(DIST_NAME)}-[^/]+\.dist-info", candidate)
    }
    for candidate in sorted(dist_info_dirs - valid_dist_info_dirs):
        issues.append(f"{prefix}: unexpected dist-info directory: {candidate}")
    if len(valid_dist_info_dirs) != 1:
        issues.append(
            f"{prefix}: expected exactly one {DIST_NAME}-*.dist-info directory, "
            f"found {sorted(valid_dist_info_dirs)}"
        )
    dist_info = sorted(valid_dist_info_dirs)[0] if len(valid_dist_info_dirs) == 1 else None

    allowed_metadata = (
        {
            f"{dist_info}/METADATA",
            f"{dist_info}/WHEEL",
            f"{dist_info}/RECORD",
            f"{dist_info}/entry_points.txt",
            f"{dist_info}/top_level.txt",
            f"{dist_info}/LICENSE",
            f"{dist_info}/NOTICE",
            f"{dist_info}/licenses/LICENSE",
            f"{dist_info}/licenses/NOTICE",
        }
        if dist_info is not None
        else set()
    )
    allowed_wheel_files = expected_package | allowed_metadata

    actual_package: set[str] = set()
    actual_files: set[str] = set()
    for normalized, is_dir in entries:
        forbidden = _forbidden_wheel_path(normalized)
        if forbidden:
            issues.append(f"{prefix}: {forbidden}: {normalized}")
        marker = _private_marker(normalized)
        if marker:
            issues.append(f"{prefix}: private identifier/path marker {marker!r}: {normalized}")
        if is_dir:
            if not _is_prefix_of_allowed(normalized, allowed_wheel_files):
                issues.append(f"{prefix}: unexpected wheel directory: {normalized}")
            continue

        actual_files.add(normalized)

        first = normalized.split("/", 1)[0]
        if first == DIST_NAME:
            actual_package.add(normalized)
            if normalized not in expected_package:
                issues.append(f"{prefix}: unexpected package file: {normalized}")
        elif dist_info is None or first != dist_info:
            issues.append(f"{prefix}: unexpected wheel entry: {normalized}")
        elif normalized not in allowed_metadata:
            issues.append(f"{prefix}: unexpected dist-info entry: {normalized}")

    for missing in sorted(expected_package - actual_package):
        issues.append(f"{prefix}: missing required package path: {missing}")

    if dist_info is not None:
        required, license_alternatives = _dist_info_required_paths(dist_info)
        for missing in sorted(required - actual_files):
            issues.append(f"{prefix}: missing required metadata path: {missing}")
        license_paths = {path for path in license_alternatives if path.endswith("LICENSE")}
        notice_paths = {path for path in license_alternatives if path.endswith("NOTICE")}
        if not (license_paths & actual_files):
            issues.append(
                f"{prefix}: missing required metadata path: "
                f"{dist_info}/licenses/LICENSE (or {dist_info}/LICENSE)"
            )
        if not (notice_paths & actual_files):
            issues.append(
                f"{prefix}: missing required metadata path: "
                f"{dist_info}/licenses/NOTICE (or {dist_info}/NOTICE)"
            )

    return issues


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sdist", required=True, type=Path)
    parser.add_argument("--wheel", required=True, type=Path)
    parser.add_argument(
        "--extra-patterns",
        type=Path,
        default=None,
        help=(
            "file of additional 'label = regex' archive-member path patterns, "
            "kept outside this repository"
        ),
    )
    args = parser.parse_args(argv)

    extra: tuple[tuple[str, str], ...] = ()
    if args.extra_patterns is not None:
        extra, extra_issues = load_extra_patterns(args.extra_patterns)
        if extra_issues:
            print("distribution verification failed", file=sys.stderr)
            for issue in extra_issues:
                print(f"- {issue}", file=sys.stderr)
            return 1

    repo_root = _repo_root()
    issues = verify_sdist(args.sdist, repo_root, extra)
    issues.extend(verify_wheel(args.wheel, repo_root, extra))
    if issues:
        print("distribution verification failed", file=sys.stderr)
        for issue in sorted(dict.fromkeys(issues)):
            print(f"- {issue}", file=sys.stderr)
        return 1
    print("distribution verification passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
