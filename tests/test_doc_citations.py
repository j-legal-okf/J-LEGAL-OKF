"""Offline coverage for the source-code citation checker.

Follows the same skip-if-absent / test-against-a-planted-violation pattern as
`tests/test_boundary_checks.py`.
"""

from __future__ import annotations

import ast
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"

# `tools/` is deliberately excluded from the source distribution (MANIFEST.in);
# see the identical guard in tests/test_boundary_checks.py.
if not (TOOLS / "check_doc_citations.py").is_file():
    pytest.skip(
        "repository tooling is not part of the source distribution",
        allow_module_level=True,
    )

sys.path.insert(0, str(TOOLS))

import check_doc_citations as cdc  # noqa: E402


def _init_repo(path: Path) -> Path:
    path.mkdir(parents=True)
    subprocess.run(
        ["git", "init", "--initial-branch=main", str(path)],
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run(["git", "-C", str(path), "config", "user.name", "Test Author"], check=True)
    subprocess.run(["git", "-C", str(path), "config", "user.email", "author@example.org"], check=True)
    return path


def _git_add(repo: Path, *paths: str) -> None:
    subprocess.run(["git", "-C", str(repo), "add", *paths], check=True, capture_output=True, text=True)


# --------------------------------------------------------------------------
# the real tree


def test_real_tree_citations_all_resolve() -> None:
    issues, notes = cdc.check_citations(ROOT)
    assert issues == []
    assert any(note.startswith("scanned ") for note in notes)
    assert any(note.startswith("checked ") for note in notes)


# --------------------------------------------------------------------------
# module_level_symbols


def test_module_level_symbols_finds_functions_classes_and_constants() -> None:
    source = (
        "CONST = 1\n"
        "\n"
        "def a_function():\n"
        "    pass\n"
        "\n"
        "class AClass:\n"
        "    def method(self):\n"
        "        pass\n"
        "\n"
        "ANNOTATED: int = 2\n"
    )
    names = cdc.module_level_symbols(source)
    assert names == {"CONST", "a_function", "AClass", "ANNOTATED"}


def test_module_level_symbols_excludes_nested_names() -> None:
    source = "def outer():\n    def inner():\n        pass\n    LOCAL = 1\n"
    assert cdc.module_level_symbols(source) == {"outer"}


def test_module_level_symbols_does_not_string_match() -> None:
    """A name that only appears in a comment or string must not count as defined."""

    source = '# mentions not_a_real_symbol\nREAL = "not_a_real_symbol is just text here too"\n'
    names = cdc.module_level_symbols(source)
    assert names == {"REAL"}
    assert "not_a_real_symbol" not in names


def test_module_level_symbols_returns_none_for_unparseable_source() -> None:
    assert cdc.module_level_symbols("def broken(:\n    pass\n") is None


def test_module_level_symbols_returns_none_for_a_null_byte() -> None:
    """Pins observed behaviour: a null byte is refused rather than parsed.

    On CPython 3.12 this arrives as SyntaxError, so this test does not by
    itself justify catching ValueError -- see the surrogate test below, which
    does. It is kept because which exception this spelling raises has moved
    between CPython releases and CI runs 3.10 through 3.13.
    """

    assert cdc.module_level_symbols("REAL = 1\n\x00\n") is None


def test_module_level_symbols_returns_none_for_a_lone_surrogate() -> None:
    """A lone surrogate makes ast.parse raise a ValueError, not a SyntaxError.

    Catching only SyntaxError would let it escape as a traceback instead of
    the fail-closed diagnostic this checker promises. Measured, not assumed:
    ast.parse raises UnicodeEncodeError here, which subclasses ValueError.
    """

    with pytest.raises(ValueError):
        ast.parse("REAL = 1\n\udcff\n")
    assert cdc.module_level_symbols("REAL = 1\n\udcff\n") is None


# --------------------------------------------------------------------------
# the banned line-number form must not come back


def test_a_reintroduced_line_number_citation_is_rejected(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path / "line-citation")
    (repo / "src").mkdir()
    (repo / "src" / "widget.py").write_text("def real_function():\n    pass\n", encoding="utf-8")
    (repo / "notes.md").write_text("See src/widget.py:12 for details.\n", encoding="utf-8")
    _git_add(repo, "src/widget.py", "notes.md")

    issues, _notes = cdc.check_citations(repo)
    assert any("by line number" in issue for issue in issues), issues
    assert cdc.main(["--repo-root", str(repo)]) == 1


def test_a_bare_line_number_citation_without_a_directory_prefix_is_rejected(tmp_path: Path) -> None:
    """The prefix-less spelling is the one the original enumeration missed."""

    repo = _init_repo(tmp_path / "bare-line-citation")
    (repo / "notes.md").write_text("Normalization lives at `model.py:17`.\n", encoding="utf-8")
    _git_add(repo, "notes.md")

    issues, _notes = cdc.check_citations(repo)
    assert any("model.py:17" in issue for issue in issues), issues


def test_a_line_number_range_is_rejected(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path / "range-citation")
    (repo / "notes.md").write_text("Covered by `egov.py:36-37` today.\n", encoding="utf-8")
    _git_add(repo, "notes.md")

    issues, _notes = cdc.check_citations(repo)
    assert any("egov.py:36-37" in issue for issue in issues), issues


def test_a_line_reference_into_a_non_python_file_is_counted_not_failed(tmp_path: Path) -> None:
    """The residual gap is reported as a note so it cannot be assumed absent."""

    repo = _init_repo(tmp_path / "non-python-line-ref")
    (repo / "notes.md").write_text("See CHANGELOG.md:236 and ci.yml:79-95.\n", encoding="utf-8")
    _git_add(repo, "notes.md")

    issues, notes = cdc.check_citations(repo)
    assert issues == []
    assert any("residual gap: 2 line-number reference(s)" in note for note in notes)
    assert cdc.main(["--repo-root", str(repo)]) == 0


# --------------------------------------------------------------------------
# check_citations: detects a broken citation (this is the checker's whole job)


def test_a_citation_naming_a_nonexistent_symbol_is_detected(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path / "broken-symbol")
    (repo / "src").mkdir()
    (repo / "src" / "widget.py").write_text("def real_function():\n    pass\n", encoding="utf-8")
    (repo / "notes.md").write_text(
        "See `src/widget.py` `does_not_exist()` for details.\n", encoding="utf-8"
    )
    _git_add(repo, "src/widget.py", "notes.md")

    issues, _notes = cdc.check_citations(repo)
    assert issues, "a citation to a nonexistent symbol must be reported"
    assert any("does_not_exist" in issue and "not defined at module level" in issue for issue in issues)
    assert cdc.main(["--repo-root", str(repo)]) == 1


def test_a_citation_to_a_missing_file_is_detected(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path / "missing-file")
    (repo / "notes.md").write_text(
        "See `src/jlegal_okf/does_not_exist.py` `whatever()` for details.\n", encoding="utf-8"
    )
    _git_add(repo, "notes.md")

    issues, _notes = cdc.check_citations(repo)
    assert any("does not exist" in issue for issue in issues), issues


def test_a_citation_into_an_unparseable_python_file_is_detected(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path / "unparseable")
    (repo / "src").mkdir()
    (repo / "src" / "broken.py").write_text("def broken(:\n    pass\n", encoding="utf-8")
    (repo / "notes.md").write_text("See `src/broken.py` `broken()` here.\n", encoding="utf-8")
    _git_add(repo, "src/broken.py", "notes.md")

    issues, _notes = cdc.check_citations(repo)
    assert any("could not be parsed as Python" in issue for issue in issues), issues


def test_a_citation_with_parent_traversal_is_rejected(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path / "traversal")
    (repo / "notes.md").write_text(
        "See `src/../../etc/passwd.py` `whatever()` here.\n", encoding="utf-8"
    )
    _git_add(repo, "notes.md")

    issues, _notes = cdc.check_citations(repo)
    assert any("parent-traversal" in issue for issue in issues), issues


def test_a_valid_citation_to_a_function_class_and_constant_all_pass(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path / "clean")
    (repo / "src").mkdir()
    (repo / "src" / "widget.py").write_text(
        "CONST = 1\n\n\ndef a_function():\n    pass\n\n\nclass AClass:\n    pass\n",
        encoding="utf-8",
    )
    (repo / "notes.md").write_text(
        "Cites `src/widget.py` `a_function()`, `src/widget.py` `AClass`, "
        "and `src/widget.py` `CONST`.\n",
        encoding="utf-8",
    )
    _git_add(repo, "src/widget.py", "notes.md")

    issues, notes = cdc.check_citations(repo)
    assert issues == []
    assert any("checked 3 citation" in note for note in notes)
    assert cdc.main(["--repo-root", str(repo)]) == 0


def test_a_symbol_mentioned_only_inside_a_function_is_not_module_level(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path / "nested")
    (repo / "src").mkdir()
    (repo / "src" / "widget.py").write_text(
        "def outer():\n    def inner():\n        pass\n", encoding="utf-8"
    )
    (repo / "notes.md").write_text("See `src/widget.py` `inner()` here.\n", encoding="utf-8")
    _git_add(repo, "src/widget.py", "notes.md")

    issues, _notes = cdc.check_citations(repo)
    assert any("inner" in issue and "not defined at module level" in issue for issue in issues), issues


# --------------------------------------------------------------------------
# fail-closed behavior


def test_missing_baseline_fails_closed(tmp_path: Path) -> None:
    issues, notes = cdc.check_citations(tmp_path)
    assert issues
    assert all("repository baseline unavailable" in issue for issue in issues)
    assert notes == []


def test_clean_checkout_with_no_citations_passes(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path / "empty")
    (repo / "README.md").write_text("Nothing to cite here.\n", encoding="utf-8")
    _git_add(repo, "README.md")

    issues, notes = cdc.check_citations(repo)
    assert issues == []
    assert any("checked 0 citation" in note for note in notes)
    assert cdc.main(["--repo-root", str(repo)]) == 0


def test_no_local_absolute_path_is_printed_for_a_broken_citation(tmp_path: Path) -> None:
    """Failure messages must stay repo-relative (see tools/check_boundary.py's own rule)."""

    repo = _init_repo(tmp_path / "path-safe")
    (repo / "src").mkdir()
    (repo / "src" / "widget.py").write_text("def real():\n    pass\n", encoding="utf-8")
    (repo / "notes.md").write_text("See `src/widget.py` `missing()` here.\n", encoding="utf-8")
    _git_add(repo, "src/widget.py", "notes.md")

    issues, _notes = cdc.check_citations(repo)
    assert issues
    for issue in issues:
        assert str(repo) not in issue
        assert not issue.startswith("/")
