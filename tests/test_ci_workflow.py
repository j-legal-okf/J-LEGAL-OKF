"""Structural and decision coverage for the `ci-passed` aggregate job.

A structural assertion that never fails proves nothing, so each one here is
written to fail when the specific control it names is weakened: the job
dropped from `needs`, `if: always()` removed or loosened, `continue-on-error`
added to the job or its decision step, the decision step's `run` gaining a
trailing fallback, or `EVENT_NAME` dropped from its `env`. The decision tests
below cover `check_ci_needs.evaluate()` and `main()` the same way: against a
planted violation, not only against a clean input.

Follows the same skip-if-absent pattern as `tests/test_boundary_checks.py`.
"""

from __future__ import annotations

import json
from pathlib import Path
import sys

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"

# `tools/` and `.github/` are deliberately excluded from the source
# distribution (MANIFEST.in), and the CI package job runs this suite from an
# extracted sdist. The checker and workflow under test are repository
# automation rather than distributed code, so this module has nothing to
# test there. The condition is their absence, not a blanket skip: in a real
# checkout the files are present and every test below runs.
if not (TOOLS / "check_ci_needs.py").is_file() or not WORKFLOW.is_file():
    pytest.skip(
        "repository tooling is not part of the source distribution",
        allow_module_level=True,
    )

sys.path.insert(0, str(TOOLS))

import check_ci_needs  # noqa: E402


# --------------------------------------------------------------------------
# structure: .github/workflows/ci.yml


def _load_workflow() -> dict:
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


def _ci_passed_job() -> dict:
    return _load_workflow()["jobs"]["ci-passed"]


def _decision_steps(job: dict) -> list[dict]:
    """The step(s) whose `run` invokes `check_ci_needs.py`.

    This is the discriminator used throughout this module to identify *the*
    decision step: a step is one only if its `run` names the script.
    """

    return [step for step in job.get("steps", []) if "check_ci_needs.py" in step.get("run", "")]


def test_ci_passed_needs_every_other_job() -> None:
    jobs = _load_workflow()["jobs"]
    other_job_ids = set(jobs) - {"ci-passed"}
    assert set(jobs["ci-passed"]["needs"]) == other_job_ids


def test_ci_passed_needs_at_least_the_current_five_jobs() -> None:
    job = _ci_passed_job()
    current = {"boundary", "dco", "tests", "cli-e2e", "package-distribution"}
    assert current <= set(job["needs"])


def test_ci_passed_runs_regardless_of_dependency_outcome() -> None:
    job = _ci_passed_job()
    assert job.get("if") in ("always()", "${{ always() }}")


def test_ci_passed_job_has_no_continue_on_error() -> None:
    assert "continue-on-error" not in _ci_passed_job()


def test_ci_passed_has_a_positive_integer_timeout() -> None:
    timeout = _ci_passed_job().get("timeout-minutes")
    assert isinstance(timeout, int) and not isinstance(timeout, bool)
    assert timeout > 0


def test_ci_passed_has_exactly_one_decision_step() -> None:
    assert len(_decision_steps(_ci_passed_job())) == 1


def test_decision_step_cannot_be_individually_disabled() -> None:
    (step,) = _decision_steps(_ci_passed_job())
    assert "if" not in step
    assert "continue-on-error" not in step


def test_decision_step_run_is_exactly_the_two_expected_lines() -> None:
    (step,) = _decision_steps(_ci_passed_job())
    lines = [line.strip() for line in step["run"].splitlines() if line.strip()]
    assert lines == ["set -euo pipefail", "python tools/check_ci_needs.py"]


def test_decision_step_env_passes_the_needs_context_and_event_name() -> None:
    (step,) = _decision_steps(_ci_passed_job())
    env = step.get("env", {})
    assert env.get("NEEDS") == "${{ toJSON(needs) }}"
    assert env.get("EVENT_NAME") == "${{ github.event_name }}"


# --------------------------------------------------------------------------
# decision: check_ci_needs.evaluate()

BASE_NEEDS: dict[str, dict[str, str]] = {
    "boundary": {"result": "success"},
    "dco": {"result": "success"},
    "tests": {"result": "success"},
    "cli-e2e": {"result": "success"},
    "package-distribution": {"result": "success"},
}


def _needs_with(overrides: dict[str, object]) -> dict[str, object]:
    merged: dict[str, object] = {name: dict(value) for name, value in BASE_NEEDS.items()}
    merged.update(overrides)
    return merged


def test_all_success_is_accepted() -> None:
    issues, notes = check_ci_needs.evaluate(BASE_NEEDS, "push")
    assert issues == []
    assert len(notes) == len(BASE_NEEDS)


def test_one_failure_is_rejected() -> None:
    issues, _ = check_ci_needs.evaluate(_needs_with({"tests": {"result": "failure"}}), "pull_request")
    assert issues


def test_one_cancelled_is_rejected() -> None:
    issues, _ = check_ci_needs.evaluate(_needs_with({"cli-e2e": {"result": "cancelled"}}), "pull_request")
    assert issues


def test_tests_skipped_is_rejected() -> None:
    issues, _ = check_ci_needs.evaluate(_needs_with({"tests": {"result": "skipped"}}), "push")
    assert issues


def test_dco_skipped_on_pull_request_is_rejected() -> None:
    issues, _ = check_ci_needs.evaluate(_needs_with({"dco": {"result": "skipped"}}), "pull_request")
    assert issues


@pytest.mark.parametrize("event_name", ["push", "workflow_dispatch"])
def test_dco_skipped_is_accepted_on_push_and_workflow_dispatch(event_name: str) -> None:
    issues, notes = check_ci_needs.evaluate(_needs_with({"dco": {"result": "skipped"}}), event_name)
    assert issues == []
    assert any("dco" in note for note in notes)


@pytest.mark.parametrize("event_name", ["merge_group", "pull_request_target"])
def test_dco_skipped_is_rejected_on_events_other_than_push_and_workflow_dispatch(
    event_name: str,
) -> None:
    issues, _ = check_ci_needs.evaluate(_needs_with({"dco": {"result": "skipped"}}), event_name)
    assert issues


@pytest.mark.parametrize("needs", [{}, ["not", "a", "dict"], "also not a dict"])
def test_needs_must_be_a_non_empty_object(needs: object) -> None:
    issues, notes = check_ci_needs.evaluate(needs, "push")
    assert issues
    assert notes == []


def test_needs_entry_must_be_an_object() -> None:
    issues, _ = check_ci_needs.evaluate(_needs_with({"tests": "success"}), "push")
    assert issues


def test_needs_entry_must_have_a_result() -> None:
    issues, _ = check_ci_needs.evaluate(_needs_with({"tests": {}}), "push")
    assert issues


# --------------------------------------------------------------------------
# decision: check_ci_needs.main()


def test_main_fails_when_needs_is_unset(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("NEEDS", raising=False)
    monkeypatch.setenv("EVENT_NAME", "push")
    assert check_ci_needs.main() == 1
    assert "NEEDS" in capsys.readouterr().err


def test_main_fails_when_needs_is_empty(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("NEEDS", "")
    monkeypatch.setenv("EVENT_NAME", "push")
    assert check_ci_needs.main() == 1
    assert "NEEDS" in capsys.readouterr().err


def test_main_fails_when_needs_is_invalid_json(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("NEEDS", "{not valid json")
    monkeypatch.setenv("EVENT_NAME", "push")
    assert check_ci_needs.main() == 1
    assert "JSON" in capsys.readouterr().err


def test_main_fails_when_event_name_is_unset(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("NEEDS", json.dumps(BASE_NEEDS))
    monkeypatch.delenv("EVENT_NAME", raising=False)
    assert check_ci_needs.main() == 1
    assert "EVENT_NAME" in capsys.readouterr().err


def test_main_fails_when_event_name_is_empty(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("NEEDS", json.dumps(BASE_NEEDS))
    monkeypatch.setenv("EVENT_NAME", "")
    assert check_ci_needs.main() == 1
    assert "EVENT_NAME" in capsys.readouterr().err


def test_main_passes_on_a_normal_run(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("NEEDS", json.dumps(BASE_NEEDS))
    monkeypatch.setenv("EVENT_NAME", "push")
    assert check_ci_needs.main() == 0
    assert "ci-needs check passed" in capsys.readouterr().out
