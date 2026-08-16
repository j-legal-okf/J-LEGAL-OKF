"""Offline coverage for the repository-tree boundary and DCO checkers.

A checker that only ever passes proves nothing, so every rule here is tested
against a planted violation as well as against the real tree.
"""

from __future__ import annotations

import io
from pathlib import Path
import subprocess
import sys
import tarfile
import zipfile

import pytest

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"

# `tools/` is deliberately excluded from the source distribution (MANIFEST.in),
# and the CI package job runs this suite from an extracted sdist. The checkers
# under test are repository automation rather than distributed code, so this
# module has nothing to test there. The condition is the tooling's absence, not
# a blanket skip: in a real checkout the files are present and every test below
# runs.
if not (TOOLS / "check_boundary.py").is_file():
    pytest.skip(
        "repository tooling is not part of the source distribution",
        allow_module_level=True,
    )

sys.path.insert(0, str(TOOLS))

import check_boundary  # noqa: E402
import check_dco  # noqa: E402
import verify_distribution  # noqa: E402


# --------------------------------------------------------------------------
# check_boundary: the real tree


def test_real_tree_passes_the_boundary_check() -> None:
    issues, notes = check_boundary.check_tree(ROOT)
    assert issues == []
    assert any(note.startswith("scanned ") for note in notes)


def test_self_exemption_is_exactly_the_one_file_that_needs_it() -> None:
    """The content-scan exemption must not quietly widen."""

    assert check_boundary.SELF_EXEMPT_PATHS == ("tests/test_boundary_checks.py",)
    tracked, issues = check_boundary.tracked_files(ROOT)
    assert issues == []
    for path in check_boundary.SELF_EXEMPT_PATHS:
        assert path in tracked, f"{path} is exempt but not tracked"


def test_the_checkers_own_sources_need_no_exemption() -> None:
    """A pattern that matches this checker has to be reconsidered, not exempted."""

    for name in ("check_boundary.py", "check_dco.py"):
        text = (TOOLS / name).read_text(encoding="utf-8")
        assert check_boundary.check_content(f"tools/{name}", text) == []


def test_the_exempt_file_is_still_path_checked() -> None:
    """The exemption covers content only."""

    assert check_boundary.check_path("tests/test_boundary_checks.py") == []
    assert check_boundary.check_path("tests/private/test_boundary_checks.py") != []


def test_builtin_patterns_are_structural_rather_than_named() -> None:
    """A private name is itself private; it belongs in --extra-patterns.

    This repository cannot spell out the names it must not carry without
    carrying them, so it asserts the shape instead: every built-in pattern is a
    character-class or delimiter construction, not a bare literal token. The
    literal-token check runs from the side that owns those names, where the
    supplied patterns are applied to this checker's own source like any other
    file.
    """

    structural = ("[", "\\", "://")
    for label, expression in check_boundary.CONTENT_PATTERNS:
        assert any(marker in expression for marker in structural), (
            f"built-in pattern {label!r} is a bare literal: {expression!r}"
        )


# --------------------------------------------------------------------------
# check_boundary: path rules


@pytest.mark.parametrize(
    "path",
    [
        "src/private_overlay/model.py",
        "docs/legacy-notes.md",
        "tests/fixtures/municipal_sample.xml",
        "src/jlegal_okf/enrichment.py",
        "tools/openrouter_client.py",
    ],
)
def test_private_path_markers_are_reported(path: str) -> None:
    issues = check_boundary.check_path(path)
    assert issues, f"{path} should have been reported"
    assert any("private path marker" in issue for issue in issues)


@pytest.mark.parametrize(
    "path, expected",
    [
        ("/etc/passwd", "absolute tracked path"),
        ("docs\\notes.md", "backslash in tracked path"),
        ("docs/../../etc/passwd", "parent traversal component"),
    ],
)
def test_unsafe_path_shapes_are_reported(path: str, expected: str) -> None:
    issues = check_boundary.check_path(path)
    assert any(expected in issue for issue in issues), issues


def test_ordinary_public_paths_are_accepted() -> None:
    for path in (
        "src/jlegal_okf/pipeline.py",
        "docs/known-limitations.md",
        "examples/synthetic_egov_law.xml",
        ".github/workflows/ci.yml",
    ):
        assert check_boundary.check_path(path) == []


# --------------------------------------------------------------------------
# check_boundary: content rules
#
# Every credential below is invented for this test and is not a real secret.


@pytest.mark.parametrize(
    "line, expected",
    [
        ("run it from /home/someone/checkout", "local absolute home path"),
        (r"open C:\Users\someone\file.txt", "Windows user path"),
        ("the drive is mounted at /mnt/f/archive", "WSL mount path"),
        ("key = AKIAIOSFODNN7EXAMPLE", "AWS access key id"),
        ("token: ghp_0123456789abcdefghijABCDEFGHIJ", "GitHub token"),
        ("use sk-0123456789abcdefghijABCDEFGHIJ", "OpenAI-style token"),
        ("xoxb-1234567890-abcdefghij", "Slack token"),
        ("-----BEGIN RSA PRIVATE KEY-----", "PEM private key block"),
        ('password = "hunter2000"', "secret assignment"),
        ('api_key: "abcdef123456"', "secret assignment"),
        ("postgres://user:pass@db.internal/app", "credentialed connection string"),
    ],
)
def test_content_patterns_report_planted_violations(line: str, expected: str) -> None:
    issues = check_boundary.check_content("docs/planted.md", line)
    assert issues, f"{line!r} should have been reported"
    assert any(expected in issue for issue in issues), issues


def test_content_issue_names_the_line_number() -> None:
    text = "clean line\nanother clean line\nbuilt in /home/someone/checkout\n"
    issues = check_boundary.check_content("docs/planted.md", text)
    assert len(issues) == 1
    assert issues[0].startswith("docs/planted.md:3:")


# --------------------------------------------------------------------------
# check_boundary: patterns supplied from outside the repository


def _write_patterns(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "extra-patterns.txt"
    path.write_text(body, encoding="utf-8")
    return path


def test_supplied_patterns_are_applied(tmp_path: Path) -> None:
    patterns, issues = check_boundary.load_extra_patterns(
        _write_patterns(
            tmp_path,
            "# a name this repository must not carry\n"
            "private repository name = PRIVATE-REPO-NAME\n",
        )
    )
    assert issues == []
    assert patterns == (("private repository name", "PRIVATE-REPO-NAME"),)

    line = "see the PRIVATE-REPO-NAME checklist"
    assert check_boundary.check_content("docs/x.md", line) == []
    found = check_boundary.check_content(
        "docs/x.md", line, check_boundary.CONTENT_PATTERNS + patterns
    )
    assert any("private repository name" in issue for issue in found), found


def test_supplied_patterns_reach_the_tree_scan(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path / "extra")
    (repo / "notes.md").write_text("see the PRIVATE-REPO-NAME checklist\n", encoding="utf-8")
    _git(repo, "add", "notes.md")
    patterns_file = _write_patterns(tmp_path, "private repository name = PRIVATE-REPO-NAME\n")

    assert check_boundary.check_tree(repo)[0] == []
    assert check_boundary.main(["--repo-root", str(repo)]) == 0
    assert (
        check_boundary.main(
            ["--repo-root", str(repo), "--extra-patterns", str(patterns_file)]
        )
        == 1
    )


@pytest.mark.parametrize(
    "body, expected",
    [
        ("no separator here\n", "expected 'label = regex'"),
        (" = PATTERN\n", "expected 'label = regex'"),
        ("label =\n", "expected 'label = regex'"),
        ("bad regex = [unclosed\n", "invalid regex"),
        ("# only a comment\n", "has no patterns"),
    ],
)
def test_malformed_patterns_file_fails_closed(tmp_path: Path, body: str, expected: str) -> None:
    _patterns, issues = check_boundary.load_extra_patterns(_write_patterns(tmp_path, body))
    assert issues
    assert any(expected in issue for issue in issues), issues


def test_missing_patterns_file_fails_closed(tmp_path: Path) -> None:
    _patterns, issues = check_boundary.load_extra_patterns(tmp_path / "absent.txt")
    assert issues
    assert "extra patterns unavailable" in issues[0]
    repo = _init_repo(tmp_path / "repo")
    (repo / "README.md").write_text("clean\n", encoding="utf-8")
    _git(repo, "add", "README.md")
    assert (
        check_boundary.main(
            ["--repo-root", str(repo), "--extra-patterns", str(tmp_path / "absent.txt")]
        )
        == 1
    )


def _write_synthetic_archives(tmp_path: Path) -> tuple[Path, Path]:
    sdist = tmp_path / "jlegal-okf-0.0.tar.gz"
    payload = b"synthetic\n"
    with tarfile.open(sdist, "w:gz") as archive:
        info = tarfile.TarInfo("jlegal-okf-0.0/forbidden_component.py")
        info.size = len(payload)
        archive.addfile(info, io.BytesIO(payload))

    wheel = tmp_path / "jlegal_okf-0.0-py3-none-any.whl"
    with zipfile.ZipFile(wheel, "w") as archive:
        archive.writestr("jlegal_okf/forbidden_component.py", payload)
    return sdist, wheel


def test_distribution_extra_patterns_reject_both_archive_types(tmp_path: Path) -> None:
    patterns = (("private-only component", r"forbidden_component"),)
    sdist, wheel = _write_synthetic_archives(tmp_path)

    sdist_issues = verify_distribution.verify_sdist(sdist, ROOT, patterns)
    wheel_issues = verify_distribution.verify_wheel(wheel, ROOT, patterns)

    assert any("private-only component" in issue for issue in sdist_issues), sdist_issues
    assert any("private-only component" in issue for issue in wheel_issues), wheel_issues


@pytest.mark.parametrize(
    "body, expected",
    [
        (None, "extra patterns unavailable"),
        ("# comments only\n", "has no patterns"),
        ("bad regex = [unclosed\n", "invalid regex"),
    ],
)
def test_distribution_extra_patterns_fail_closed_before_archive_read(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    body: str | None,
    expected: str,
) -> None:
    patterns_file = tmp_path / "distribution-patterns.txt"
    if body is not None:
        patterns_file.write_text(body, encoding="utf-8")

    result = verify_distribution.main(
        [
            "--sdist",
            str(tmp_path / "missing.tar.gz"),
            "--wheel",
            str(tmp_path / "missing.whl"),
            "--extra-patterns",
            str(patterns_file),
        ]
    )
    stderr = capsys.readouterr().err
    assert result == 1
    assert expected in stderr
    assert "archive is missing" not in stderr


def test_personal_email_is_reported_and_the_project_identity_is_not() -> None:
    assert check_boundary.check_content("docs/x.md", "reach me at someone@gmail.com")
    assert (
        check_boundary.check_content(
            "docs/x.md", "okf-works <294216476+okf-works@users.noreply.github.com>"
        )
        == []
    )
    assert check_boundary.check_content("docs/x.md", "write to maintainer@example.com") == []


def test_clean_public_prose_produces_no_issue() -> None:
    text = (
        "J-LEGAL-OKF accepts e-Gov national-law XML only.\n"
        "Run `jlegal compile examples/synthetic_egov_law.xml`.\n"
        "The canonical model is jori-corpus/v1.\n"
    )
    assert check_boundary.check_content("README.md", text) == []


# --------------------------------------------------------------------------
# check_boundary: fail-closed behavior


def test_missing_baseline_fails_closed(tmp_path: Path) -> None:
    """A directory that is not a Git checkout must not pass silently."""

    issues, notes = check_boundary.check_tree(tmp_path)
    assert issues
    assert all("repository baseline unavailable" in issue for issue in issues)
    assert notes == []


def test_planted_file_in_a_real_checkout_fails(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path / "planted")
    (repo / "docs").mkdir()
    (repo / "docs" / "notes.md").write_text(
        "the working copy lives in /home/someone/checkout\n", encoding="utf-8"
    )
    _git(repo, "add", "docs/notes.md")

    issues, _notes = check_boundary.check_tree(repo)
    assert any("local absolute home path" in issue for issue in issues), issues

    assert check_boundary.main(["--repo-root", str(repo)]) == 1


def test_undecodable_text_file_is_reported_not_skipped(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path / "binary")
    (repo / "notes.md").write_bytes(b"\xff\xfe\x00 not utf-8")
    _git(repo, "add", "notes.md")

    issues, _notes = check_boundary.check_tree(repo)
    assert any("not UTF-8 text" in issue for issue in issues), issues


def test_clean_checkout_passes(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path / "clean")
    (repo / "README.md").write_text("A clean public file.\n", encoding="utf-8")
    _git(repo, "add", "README.md")

    issues, notes = check_boundary.check_tree(repo)
    assert issues == []
    assert any("content-scanned" in note for note in notes)
    assert check_boundary.main(["--repo-root", str(repo)]) == 0


# --------------------------------------------------------------------------
# check_dco


def test_signed_off_commit_passes(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path / "dco-ok")
    base = _commit(repo, "base.txt", "base\n", "base commit", signoff=True)
    _commit(repo, "change.txt", "change\n", "a change", signoff=True)

    issues, notes = check_dco.check_range(f"{base}..HEAD", str(repo))
    assert issues == []
    assert notes == ["checked 1 non-merge commit(s) in " + f"{base}..HEAD"]


def test_unsigned_commit_is_reported(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path / "dco-missing")
    base = _commit(repo, "base.txt", "base\n", "base commit", signoff=True)
    _commit(repo, "change.txt", "change\n", "a change", signoff=False)

    issues, _notes = check_dco.check_range(f"{base}..HEAD", str(repo))
    assert len(issues) == 1
    assert "no Signed-off-by line" in issues[0]
    assert check_dco.main([f"{base}..HEAD", "--repo-root", str(repo)]) == 1


def test_signoff_by_a_third_party_is_reported(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path / "dco-mismatch")
    base = _commit(repo, "base.txt", "base\n", "base commit", signoff=True)
    _commit(
        repo,
        "change.txt",
        "change\n",
        "a change\n\nSigned-off-by: Someone Else <else@example.org>",
        signoff=False,
    )

    issues, _notes = check_dco.check_range(f"{base}..HEAD", str(repo))
    assert len(issues) == 1
    assert "matches neither the author" in issues[0]


def test_the_base_commit_is_out_of_range(tmp_path: Path) -> None:
    """The range form is what keeps the repository's own first commit out."""

    repo = _init_repo(tmp_path / "dco-range")
    base = _commit(repo, "base.txt", "base\n", "unsigned base commit", signoff=False)
    _commit(repo, "change.txt", "change\n", "a change", signoff=True)

    assert check_dco.check_range(f"{base}..HEAD", str(repo))[0] == []
    assert check_dco.check_range("HEAD", str(repo))[0] != []


def test_merge_commits_are_skipped(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path / "dco-merge")
    base = _commit(repo, "base.txt", "base\n", "base commit", signoff=True)
    _git(repo, "checkout", "-b", "side")
    _commit(repo, "side.txt", "side\n", "side change", signoff=True)
    _git(repo, "checkout", "main")
    _commit(repo, "main.txt", "main\n", "main change", signoff=True)
    _git(repo, "merge", "--no-ff", "--no-edit", "side")

    issues, notes = check_dco.check_range(f"{base}..HEAD", str(repo))
    assert issues == []
    assert notes == ["checked 2 non-merge commit(s) in " + f"{base}..HEAD"]


def test_bad_range_fails_closed(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path / "dco-badrange")
    _commit(repo, "base.txt", "base\n", "base commit", signoff=True)

    issues, notes = check_dco.check_range("no-such-ref..HEAD", str(repo))
    assert issues
    assert "commit range unavailable" in issues[0]
    assert notes == []


# --------------------------------------------------------------------------
# helpers


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _init_repo(path: Path) -> Path:
    path.mkdir(parents=True)
    subprocess.run(
        ["git", "init", "--initial-branch=main", str(path)],
        check=True,
        capture_output=True,
        text=True,
    )
    _git(path, "config", "user.name", "Test Author")
    _git(path, "config", "user.email", "author@example.org")
    _git(path, "config", "commit.gpgsign", "false")
    return path


def _commit(repo: Path, name: str, body: str, message: str, *, signoff: bool) -> str:
    (repo / name).write_text(body, encoding="utf-8")
    _git(repo, "add", name)
    args = ["commit", "-m", message]
    if signoff:
        args.insert(1, "-s")
    _git(repo, *args)
    return _git(repo, "rev-parse", "HEAD")
