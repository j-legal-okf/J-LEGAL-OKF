"""Version-identity and release-state-restatement contract checks.

This project tracks four independent version systems (see README.md
"Versioning"): the normative profile, the git tag (SemVer), the Python
package (PEP 440), and wire schema ids. Confusing the package version with
the profile version, or letting the package version leak into a recorded
digest, or letting "nothing has been tagged or released" get restated
outside CHANGELOG.md (the single source of truth for that state) are the
three concrete failure modes this file guards against.
"""

from __future__ import annotations

import importlib.metadata
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

import jlegal_okf
from jlegal_okf.cli import build_parser
from jlegal_okf.pipeline import JLEGAL_CONVERTER, JLEGAL_PROFILE, compile_corpus

ROOT = Path(__file__).resolve().parents[1]
PACKAGE_NAME = "jlegal-okf"
PUBLIC_FIXTURE = ROOT / "examples" / "synthetic_egov_law.xml"


def _installed_version() -> str:
    return importlib.metadata.version(PACKAGE_NAME)


# --- package version identity (README.md "Versioning" row 3) -------------


def test_pyproject_version_matches_installed_metadata() -> None:
    """`pyproject.toml`'s version literal must agree with what got installed.

    The two can drift when `pyproject.toml` is edited without reinstalling
    (an editable install carries the metadata recorded at install time), or
    when a version bump is reverted without reinstalling. Skips, rather than
    fails, in an install-only tree that has no `pyproject.toml` at all.
    """

    pyproject_path = ROOT / "pyproject.toml"
    if not pyproject_path.is_file():
        pytest.skip("no pyproject.toml in this tree (install-only checkout)")
    try:
        import tomllib
    except ImportError:
        pytest.skip("tomllib unavailable on this interpreter (Python < 3.11)")
    data = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))
    pyproject_version = data["project"]["version"]
    assert pyproject_version == _installed_version()


def test_dunder_version_matches_installed_metadata() -> None:
    assert jlegal_okf.__version__ == _installed_version()


# --- `--version` reports both version systems -----------------------------


def test_cli_version_flag_reports_package_and_profile_versions(
    capsys: pytest.CaptureFixture[str],
) -> None:
    parser = build_parser()
    with pytest.raises(SystemExit) as excinfo:
        parser.parse_args(["--version"])
    assert excinfo.value.code == 0
    out = capsys.readouterr().out
    assert _installed_version() in out, out
    assert JLEGAL_PROFILE in out, out


# --- the package version never leaks into a compiled artifact -------------


def test_package_version_not_leaked_into_compiled_artifacts(tmp_path: Path) -> None:
    """Bumping the Python package version must never move a recorded digest.

    `manifest["conversion"]` must stay exactly `JLEGAL_CONVERTER` (the fixed
    `JORI Engine` / profile pair, hash-covered by `build_options_sha256`),
    and the package version string must not appear anywhere in any generated
    artifact byte stream.
    """

    result = compile_corpus(
        PUBLIC_FIXTURE,
        adapter="egov_xml",
        out_dir=tmp_path / "corpus",
        corpus_id="version-contract-fixture",
    )
    manifest = json.loads(Path(result["manifest"]).read_text(encoding="utf-8"))
    assert manifest["conversion"] == JLEGAL_CONVERTER

    package_version = _installed_version()
    for name in ("manifest.json", "corpus.jsonl", "crosswalk.jsonl", "projection.jsonl"):
        text = (tmp_path / "corpus" / name).read_text(encoding="utf-8")
        assert package_version not in text, f"package version leaked into {name}"


# --- release-state restatement scan ---------------------------------------

# The scan itself lives in tools/check_release_state.py, not here, for two
# reasons measured rather than guessed. First, its exemption inventory has to
# be printed on every run to stay honest, and pytest captures and discards a
# passing test's output, so a test is the wrong container for it. Second,
# MANIFEST.in ships tests/ into the sdist and prunes tools/, and CI runs the
# suite from an unpacked sdist that is not a git work tree; a scan that shells
# out to `git ls-files` from there fails with exit status 128. Keeping the
# scan in tools/ puts it where it runs (the checkout-based `boundary` job) and
# lets these tests skip cleanly where it cannot.
TOOL_PATH = ROOT / "tools" / "check_release_state.py"


def _load_release_state_tool():
    if not TOOL_PATH.is_file():
        pytest.skip("tools/check_release_state.py absent (sdist/wheel tree)")
    spec = importlib.util.spec_from_file_location("check_release_state", TOOL_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

# The three sentences this repository actually carried before the single-source
# rewrite, verbatim. Two of them were caught by the first version of the scan;
# the third — the Japanese one in okf/project.md — was not, which is why the
# patterns key on a semantic class in both languages rather than on one English
# surface form. Pinning the real prior text is what keeps that regression from
# coming back as "the pattern still passes its own examples".
#
# The Japanese entry is written the way the scan actually receives it, with
# the spurious space a soft wrap leaves behind ("リリースされて いない"), not
# the tidy form a person would retype. An earlier version of this test pinned
# the tidy form, passed, and hid the fact that the scan missed the real file.
# A fixture that has been cleaned up on the way into the test is a fixture
# that stops testing the thing.
PRE_CHANGE_RESTATEMENTS = (
    "Only the maintainer creates tags and releases. Nothing has been released.",
    "Nothing has been released or tagged yet. The only supported target is the "
    "current `main` branch, at profile version `0.1.0-draft`.",
    "実装仕様・手順・進捗を複製しない。CHANGELOG.md は「まだ何もタグ付け・リリースされて"
    " いない」と記録し、README.md はこの初期スライスを「完全なリリースではない」と明記する。",
)

# Paraphrases of the same claim that no sentence in this repository currently
# uses. They are here because the scan is a ratchet against phrasings people
# plausibly write, not only against the ones already written.
PARAPHRASE_RESTATEMENTS = (
    "Nothing has been tagged or released yet.",
    "Nothing has yet been tagged or released.",
    "Nothing is tagged or released yet.",
    "Nothing has been published or tagged.",
    "This project has not been tagged or released.",
    "The project has never been released.",
    "No tags or releases exist yet.",
    "There are no releases yet.",
    "There is no released version yet.",
    "No version has been tagged yet.",
    "No release has been cut so far.",
    "As of this writing there is no tag and no release.",
    "A release has not happened yet.",
    "まだタグもリリースも作成されていない。",
    "現時点でタグもリリースもまだ作成されていない。",
    "タグもリリースもまだ無い。",
)

# Sentences that legitimately name tags or releases and must never be flagged.
# Every one of these is live text in this repository right now; the fourth is
# the load-bearing case, because it contains both タグ and リリース and would
# match any Japanese pattern that keyed on the nouns instead of on a
# negated-existence predicate.
LEGITIMATE_SENTENCES = (
    "Only the maintainer creates tags and releases.",
    "Whether anything has been tagged or released is recorded in "
    "[`CHANGELOG.md`](CHANGELOG.md), which is the single place that assertion "
    "is made; it is not restated here.",
    "Since no release preceded this change, there is no migration path to document.",
    "タグ付け・リリースの有無という状態は [CHANGELOG.md](../CHANGELOG.md) だけが記録する"
    "正本であり、本バンドルはそれを再掲しない。",
    "The supported target is the current `main` branch, at profile version "
    "`0.1.0-draft`. Whether any tag or release exists is recorded in "
    "[`CHANGELOG.md`](CHANGELOG.md); a tagged release does not, by itself, "
    "narrow this scope away from `main`.",
)


def test_release_state_scan_reports_no_restatement_and_prints_every_exemption() -> None:
    """The scan passes, and its exemption inventory reaches the run's output.

    Asserting on the subprocess's stdout is the point, not an incidental
    detail: an exemption that is only visible in source is a silent blind
    spot, and this project has already shipped one.
    """

    if not TOOL_PATH.is_file():
        pytest.skip("tools/check_release_state.py absent (sdist/wheel tree)")
    if not (ROOT / ".git").exists():
        pytest.skip("not a git work tree; the scan runs in the checkout-based CI job")
    result = subprocess.run(
        [sys.executable, str(TOOL_PATH)],
        capture_output=True,
        text=True,
        cwd=str(ROOT),
    )
    assert result.returncode == 0, result.stdout + result.stderr
    tool = _load_release_state_tool()
    for path, _reason in tool.EXEMPT_PATHS:
        assert path in result.stdout, result.stdout
    for gap in tool.RESIDUAL_GAPS:
        assert gap in result.stdout, result.stdout
    assert "release-state check passed" in result.stdout


def test_release_state_scan_fails_on_an_injected_restatement(tmp_path: Path) -> None:
    """A planted restatement in a non-exempt tracked file must fail the scan.

    Built as a throwaway git repository so the scan's own `git ls-files`
    baseline is exercised, rather than stubbed.
    """

    tool = _load_release_state_tool()
    (tmp_path / "CHANGELOG.md").write_text("Nothing has been tagged or released yet.\n", encoding="utf-8")
    (tmp_path / "docs.md").write_text(
        "Some prose.\n\nNothing has\nbeen tagged or released yet.\n", encoding="utf-8"
    )
    # Soft-wrapped Japanese: the wrap leaves a space inside a word, which is
    # the shape that got past an earlier version of this scan.
    (tmp_path / "ja.md").write_text(
        "前置き。\n\nCHANGELOG.md は「まだ何もタグ付け・リリースされて\nいない」と記録する。\n",
        encoding="utf-8",
    )
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    subprocess.run(
        ["git", "-C", str(tmp_path), "add", "CHANGELOG.md", "docs.md", "ja.md"], check=True
    )
    issues, notes = tool.scan_tree(tmp_path)
    # Match on the reported path, not on substring containment anywhere in the
    # issue: ja.md's body mentions CHANGELOG.md by name, and a containment
    # check read that as "CHANGELOG.md was flagged".
    flagged = {issue.split(":", 1)[0] for issue in issues}
    assert flagged == {"docs.md", "ja.md"}, issues
    assert any("exempt: CHANGELOG.md" in note for note in notes), notes


def test_release_state_scan_fails_closed_without_a_git_baseline(tmp_path: Path) -> None:
    tool = _load_release_state_tool()
    (tmp_path / "docs.md").write_text("Nothing has been tagged or released yet.\n", encoding="utf-8")
    issues, notes = tool.scan_tree(tmp_path)
    assert issues and all("repository baseline unavailable" in issue for issue in issues), issues
    assert notes == []


@pytest.mark.parametrize("sentence", PRE_CHANGE_RESTATEMENTS)
def test_restatement_patterns_match_the_prior_text_of_this_repository(sentence: str) -> None:
    tool = _load_release_state_tool()
    assert tool.matching_pattern(sentence) is not None, sentence


@pytest.mark.parametrize("sentence", PARAPHRASE_RESTATEMENTS)
def test_restatement_patterns_match_plausible_paraphrases(sentence: str) -> None:
    tool = _load_release_state_tool()
    assert tool.matching_pattern(sentence) is not None, sentence


@pytest.mark.parametrize("sentence", LEGITIMATE_SENTENCES)
def test_restatement_patterns_do_not_match_legitimate_sentences(sentence: str) -> None:
    tool = _load_release_state_tool()
    assert tool.matching_pattern(sentence) is None, sentence
