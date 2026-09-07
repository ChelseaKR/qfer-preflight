"""The CI surfaces must say what the command line does, and be able to fail.

Two files publish this validator into somebody else's automation: `action.yml`,
a composite GitHub Action, and `.pre-commit-hooks.yaml`, the hook manifest a
filer lists under `repos:`. Neither can be run from a test the way the CLI can,
so what is held here is everything about them a test can reach.

Three kinds of claim are checked.

The first is that they name things that exist. An action input describing a
flag the CLI does not have, or a hook whose `entry` names a console script that
was renamed, fails only in somebody else's repository, weeks later, and the
message they get does not say what went wrong. What the CLI accepts is read out
of its own `--help`, not out of argparse internals, so this reads the published
surface rather than a private one.

The second is the exit code contract, which is the whole point of the action.
`.github/workflows/action-selftest.yml` carries a matrix of cases and, beside
each, the exit code and job outcome it expects. Those are constants sitting in
a YAML file that nothing else reads, so every one of them is put through the
CLI here and compared against what actually comes back. The empty directory
case matters most: a run that validated nothing must never leave a green job
behind, and the value deciding that is a `"2"` in a workflow file.

The third is that nothing in the action can pass quietly. A
`continue-on-error`, a `|| true` or a trailing `exit 0` anywhere in it turns a
filing that failed validation into a green job, which is the defect this
project exists to refuse. That scan reads the shell with its comments removed,
because `action.yml` explains in prose why it does not use those constructs,
and a check that matches the explanation instead of the code is the failure
`tests/test_gate_parity.py` already had once.

The self test workflow does use `continue-on-error`, because a job status is
the only place an action's verdict can be read from and most of its cases are
meant to fail. Each such step is held to having a later step that reads its
recorded outcome, so a case that quietly stopped failing would be caught.
"""

from __future__ import annotations

import contextlib
import io
import re
import subprocess
import sys
import tomllib
from pathlib import Path
from typing import Any

import pytest
import yaml

from qfer_preflight.cli import EXIT_USAGE, build_parser, main

ROOT = Path(__file__).resolve().parents[1]
ACTION = ROOT / "action.yml"
HOOKS = ROOT / ".pre-commit-hooks.yaml"
WORKFLOWS = ROOT / ".github" / "workflows"
SELFTEST = WORKFLOWS / "action-selftest.yml"
PYPROJECT = ROOT / "pyproject.toml"

# The Python floor the action checks for before it runs anything. It is a
# literal in a shell one liner there, because parsing pyproject.toml to find it
# would need the very interpreter whose version is in question.
ACTION_PYTHON_FLOOR = (3, 12)

# Workflows that `tests/test_gate_parity.py` does not hold to the "every gate
# step is a make target" rule, and why. Written down rather than left implicit,
# so a new workflow cannot slip out of parity without somebody stating a
# reason.
PARITY_EXEMPT = {
    # Release time verification of a signed tag, not a gate over the working
    # tree. Exercised by tests/test_release_workflow.py.
    "release.yml",
    # Publish time verification of a tag release.yml has already published,
    # plus the upload itself. Same reason as release.yml: it verifies a signed
    # tag and builds at that commit, and none of it is something a contributor
    # runs locally before pushing. Exercised by
    # tests/test_release_workflow.py, which holds the properties that decide
    # whether it can publish at all.
    "publish-pypi.yml",
    # Runs the published composite action and the published pre-commit hook.
    # No make target reproduces a GitHub Actions job status, which is the thing
    # under test. Exercised by this file.
    "action-selftest.yml",
    # A quarterly NETWORK watcher over docs/source-manifest.md, not a gate over the
    # working tree: it re-fetches the Commission's published documents and opens a
    # review request when one has changed. No `make` target can reproduce it, because
    # the whole point is reaching the live site, and the validator itself stays
    # offline. The half that IS runnable locally is run locally and in CI:
    # `uv run pytest tests/test_watch_sources.py` and
    # `uv run python scripts/watch_sources.py --dry-run`, which is the workflow's own
    # selftest job. Exercised by tests/test_watch_sources.py.
    "source-watch.yml",
}

_SHA_PIN = re.compile(r"^[^@]+@[0-9a-f]{40}$")
_FORMAT_CHOICES = re.compile(r"--format \{([a-z,-]+)\}")
_SUBCOMMANDS = re.compile(r"\{(check(?:,[a-z]+)*)\}")
_LONG_OPTION = re.compile(r"--[a-z][a-z-]*")


# ---------------------------------------------------------------------------
# Reading the two published files, and the CLI's own published help
# ---------------------------------------------------------------------------


def _load(path: Path) -> Any:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _action() -> dict[str, Any]:
    data = _load(ACTION)
    assert isinstance(data, dict), "action.yml did not parse as a mapping"
    return data


def _action_steps() -> list[dict[str, Any]]:
    steps = _action()["runs"]["steps"]
    assert isinstance(steps, list) and steps, "action.yml declares no steps"
    return [dict(step) for step in steps]


def _hooks() -> list[dict[str, Any]]:
    data = _load(HOOKS)
    assert isinstance(data, list), ".pre-commit-hooks.yaml did not parse as a list"
    return [dict(hook) for hook in data]


def _selftest() -> dict[str, Any]:
    data = _load(SELFTEST)
    assert isinstance(data, dict), "action-selftest.yml did not parse as a mapping"
    return data


def _help(argv: list[str]) -> str:
    """The CLI's own help text, which is the surface a caller reads."""
    buffer = io.StringIO()
    with contextlib.suppress(SystemExit), contextlib.redirect_stdout(buffer):
        build_parser().parse_args(argv)
    text = buffer.getvalue()
    assert text.strip(), f"`{' '.join(argv)}` printed no help"
    return text


def _check_options() -> set[str]:
    return set(_LONG_OPTION.findall(_help(["check", "--help"])))


def _check_format_choices() -> tuple[str, ...]:
    match = _FORMAT_CHOICES.search(_help(["check", "--help"]))
    assert match, "`check --help` no longer shows the --format choices"
    return tuple(match.group(1).split(","))


def _subcommands() -> tuple[str, ...]:
    match = _SUBCOMMANDS.search(_help(["--help"]))
    assert match, "the top level help no longer lists the subcommands"
    return tuple(match.group(1).split(","))


def _shell(script: str) -> str:
    """A run script with its comment lines removed.

    Comments are stripped deliberately. `action.yml` says in prose that it does
    not use `continue-on-error` or `|| true`, so a scan reading the whole block
    would match the sentence describing the absence and report the presence.
    That is the exact way the parity check in tests/test_gate_parity.py died
    once.
    """
    return "\n".join(line for line in script.splitlines() if not line.lstrip().startswith("#"))


# ---------------------------------------------------------------------------
# The readers above must actually be reading something
# ---------------------------------------------------------------------------


def test_the_help_readers_find_the_real_surface() -> None:
    """Readers returning nothing would make every parity check below vacuous."""
    assert {"--profile", "--strict", "--format"} <= _check_options()
    assert _check_format_choices() == (
        "text",
        "json",
        "sarif",
        "findings-csv",
        "findings-jsonl",
    )
    assert "check" in _subcommands()


def test_the_comment_stripper_removes_comments_and_keeps_code() -> None:
    """Proved directly, because reading a comment is how such a check dies."""
    stripped = _shell("  # not continue-on-error\n  echo hello\n    # || true\n")
    assert "continue-on-error" not in stripped
    assert "|| true" not in stripped
    assert "echo hello" in stripped


def test_the_published_files_exist() -> None:
    for path in (ACTION, HOOKS, SELFTEST):
        assert path.exists(), f"{path} is missing"


# ---------------------------------------------------------------------------
# The action names things that exist
# ---------------------------------------------------------------------------


def test_the_action_is_a_composite_action() -> None:
    assert _action()["runs"]["using"] == "composite"


def test_the_action_declares_the_inputs_the_issue_names() -> None:
    inputs = set(_action()["inputs"])
    assert inputs == {"paths", "profile", "strict", "format", "upload-sarif"}, (
        f"action.yml declares inputs {sorted(inputs)}. An input added without a "
        "case in the self test workflow is an input nothing runs"
    )


def test_the_action_declares_the_outputs_the_issue_names() -> None:
    outputs = _action()["outputs"]
    assert set(outputs) == {"exit-code", "report-path"}
    for name, spec in outputs.items():
        assert "steps.run.outputs" in str(spec["value"]), (
            f"the {name} output does not come from the step that runs the "
            "validator, so it could report something no run produced"
        )


def test_every_action_input_that_names_a_flag_names_one_the_cli_has() -> None:
    """An input describing a flag the CLI does not have fails in somebody else's repo."""
    options = _check_options()
    for name in ("profile", "strict", "format"):
        assert f"--{name}" in options, (
            f"action.yml offers a {name!r} input, and `qfer-preflight check` has "
            f"no --{name}. Options it does have: {sorted(options)}"
        )


#: What the action's `format` input offers. Deliberately not every format the CLI
#: has: `findings-csv` and `findings-jsonl` write the ungrouped findings TABLE, which
#: is not a report. The action's contract is a report file plus an optional SARIF
#: upload, and an input that made `report-path` point at something that is not a
#: report -- and that says nothing about which rules were never evaluated -- would
#: quietly weaken the one promise this action exists to keep on a CI surface.
_ACTION_REPORT_FORMATS = ("text", "json", "sarif")


def test_the_action_accepts_exactly_the_formats_the_cli_accepts() -> None:
    """A format accepted here and unknown to the CLI fails after the job started."""
    refusal = _shell(str(_action_steps()[0]["run"]))
    marker = 'case "${FORMAT}" in'
    assert marker in refusal, "the first step no longer validates the format input"
    lines = refusal[refusal.index(marker) :].splitlines()[1:]
    pattern = next(line.strip() for line in lines if line.strip())
    accepted = tuple(pattern.split(")")[0].split("|"))
    cli = _check_format_choices()
    unknown = [fmt for fmt in accepted if fmt not in cli]
    assert not unknown, (
        f"the action accepts {unknown}, which the CLI does not: the job would start "
        f"and then fail. The CLI accepts {cli}"
    )
    assert accepted == _ACTION_REPORT_FORMATS, (
        f"the action accepts {accepted}, and the report formats are "
        f"{_ACTION_REPORT_FORMATS}. If a findings format is being added to the "
        "action, `report-path` stops naming a report and this test is the place to "
        "argue for that deliberately"
    )
    described = str(_action()["inputs"]["format"]["description"])
    for choice in accepted:
        assert choice in described, f"the format input does not mention {choice!r}"


def test_the_action_runs_the_checkout_it_was_resolved_from() -> None:
    body = ACTION.read_text(encoding="utf-8")
    assert 'PYTHONPATH="${ACTION_PATH}/src"' in body, (
        "the action no longer runs the source tree it was checked out with, so a "
        "caller pinning a tag may not be running the bytes that tag names"
    )
    assert "python3 -m qfer_preflight" in body


def test_running_from_the_checkout_is_still_legal() -> None:
    """The action installs nothing, which is only safe while nothing needs installing."""
    data = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    assert data["project"]["dependencies"] == [], (
        "the package has gained a runtime dependency. action.yml puts `src` on "
        "PYTHONPATH and installs nothing, so that dependency would be missing on "
        "the runner. Either drop it, or change the action to install the package"
    )


def test_the_actions_python_floor_matches_requires_python() -> None:
    """A literal in a shell one liner, pinned against the packaging metadata."""
    data = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    declared = str(data["project"]["requires-python"])
    expected = ">=" + ".".join(str(part) for part in ACTION_PYTHON_FLOOR)
    assert declared == expected, f"pyproject.toml requires {declared} and this test pins {expected}"
    literal = f"sys.version_info >= ({ACTION_PYTHON_FLOOR[0]}, {ACTION_PYTHON_FLOOR[1]})"
    assert literal in ACTION.read_text(encoding="utf-8"), (
        f"action.yml does not check for {literal}. Its Python floor and "
        f"`requires-python = {declared!r}` have drifted apart, so a runner would "
        "get past the guard and fail on an import instead"
    )


# ---------------------------------------------------------------------------
# Nothing in the action can pass quietly
# ---------------------------------------------------------------------------


def test_no_step_of_the_action_is_continue_on_error() -> None:
    offenders = [
        step.get("name", "<unnamed>") for step in _action_steps() if step.get("continue-on-error")
    ]
    assert not offenders, (
        f"these action steps are continue-on-error: {offenders}. A step that "
        "fails without failing the job turns a bad filing into a green run"
    )


def test_no_shell_in_the_action_can_swallow_a_failure() -> None:
    for step in _action_steps():
        script = _shell(str(step.get("run", "")))
        for forbidden in ("|| true", "exit 0"):
            assert forbidden not in script, (
                f"the step {step.get('name', '<unnamed>')!r} contains "
                f"{forbidden!r}, which discards the outcome it was measuring"
            )


def test_the_last_step_decides_the_job_and_refuses_a_missing_verdict() -> None:
    gate = _action_steps()[-1]
    assert "always()" in str(gate.get("if", "")), (
        "the final step does not run unconditionally, so a failure earlier in "
        "the action could leave the exit code unread"
    )
    script = _shell(str(gate["run"]))
    assert 'exit "${STATUS}"' in script, (
        "the final step no longer exits with the validator's own code"
    )
    assert '"" )' in script, (
        "the final step does not handle an empty recorded exit code. An empty "
        "value means the validator never reached a verdict, and it must fail"
    )
    assert "*[!0-9]*" in script, "the final step does not reject a non numeric recorded exit code"


def test_the_validating_step_records_the_code_rather_than_discarding_it() -> None:
    run_step = next(step for step in _action_steps() if step.get("id") == "run")
    script = _shell(str(run_step["run"]))
    assert "set +e" in script and "status=$?" in script, (
        "the step that runs the validator no longer captures its exit status, so "
        "the code the job's verdict is made of is thrown away"
    )
    assert 'echo "exit-code=${status}" >> "${GITHUB_OUTPUT}"' in script


def test_asking_to_upload_sarif_without_sarif_is_refused_not_skipped() -> None:
    """A skipped upload leaves an empty code scanning view, which reads as clean."""
    refusal = _shell(str(_action_steps()[0]["run"]))
    assert '[ "${UPLOAD_SARIF}" = "true" ] && [ "${FORMAT}" != "sarif" ]' in refusal, (
        "the action no longer refuses upload-sarif alongside a non SARIF format"
    )


def test_every_action_reference_is_pinned_to_a_commit() -> None:
    """A moving tag is somebody else deciding what runs inside a filer's CI."""
    unpinned: list[tuple[str, str]] = []
    for path in (ACTION, SELFTEST):
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped.startswith("uses:"):
                continue
            reference = stripped.split("uses:", 1)[1].split("#", 1)[0].strip()
            if reference in ("./", "."):
                continue  # the action under test, from this checkout
            if not _SHA_PIN.match(reference):
                unpinned.append((path.name, reference))
    assert not unpinned, f"these action references are not pinned to a commit SHA: {unpinned}"


# ---------------------------------------------------------------------------
# The pre-commit hook names an entry point that exists
# ---------------------------------------------------------------------------


def test_the_manifest_publishes_one_hook_with_an_id() -> None:
    hooks = _hooks()
    assert len(hooks) == 1, f"expected one published hook, found {[h.get('id') for h in hooks]}"
    assert hooks[0]["id"] == "qfer-preflight"


def test_the_hook_entry_names_a_console_script_that_exists() -> None:
    scripts = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))["project"]["scripts"]
    entry = str(_hooks()[0]["entry"]).split()
    assert entry[0] in scripts, (
        f"the hook runs {entry[0]!r}, and pyproject declares the console scripts "
        f"{sorted(scripts)}. Renaming the script breaks the hook in every "
        "repository that uses it, and nowhere here"
    )


def test_the_hook_entry_names_a_real_cli_subcommand() -> None:
    entry = str(_hooks()[0]["entry"]).split()
    assert len(entry) >= 2, "the hook entry names no subcommand"
    assert entry[1] in _subcommands(), (
        f"the hook runs `{' '.join(entry)}`, and {entry[1]!r} is not a "
        f"subcommand. Subcommands: {list(_subcommands())}"
    )


def test_the_hook_is_built_from_this_package_and_selects_csv_files() -> None:
    hook = _hooks()[0]
    assert hook["language"] == "python"
    assert "csv" in hook["types"], (
        "the hook no longer selects CSV files, so a staged filing would not reach it"
    )


def test_the_hook_does_not_pass_strict_by_default() -> None:
    """Strict would refuse every commit, because every form leaves rules unevaluated."""
    hook = _hooks()[0]
    assert "--strict" not in hook.get("args", [])
    assert "--strict" not in str(hook["entry"])


def test_a_header_matching_no_profile_is_what_the_hook_would_refuse(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The hook refuses what the CLI refuses, so the CLI's answer is the claim.

    `pre-commit try-repo` runs the manifest end to end in the self test
    workflow. What can be measured here is the half that decides the outcome:
    the exit code the hook's entry produces for a staged CSV whose header
    matches no published template.
    """
    entry = str(_hooks()[0]["entry"]).split()
    wrong_header = ROOT / "tests" / "fixtures" / "wrong_header.csv"
    code = main([*entry[1:], str(wrong_header)])
    capsys.readouterr()
    assert code == EXIT_USAGE, (
        f"`{' '.join(entry)}` returned {code} for a header matching no published "
        "template. The hook would let that file through"
    )


# ---------------------------------------------------------------------------
# The self test workflow's constants, measured against the CLI
# ---------------------------------------------------------------------------


def _selftest_cases() -> list[dict[str, Any]]:
    cases = _selftest()["jobs"]["run-the-action"]["strategy"]["matrix"]["include"]
    assert cases, "the self test workflow has no cases, so it measures nothing"
    return [dict(case) for case in cases]


def _target(paths: str, scratch: Path) -> str:
    """Turn a workflow `paths` value into something on this machine.

    Everything the workflow points at is a tracked fixture except the empty
    directory, which git cannot carry, so the workflow makes it and so does
    this. An unrecognised value fails rather than skipping: a case nobody can
    reproduce locally is a case nobody is measuring.
    """
    if paths == "selftest-empty":
        scratch.mkdir(parents=True)
        return str(scratch)
    resolved = ROOT / paths
    assert resolved.exists(), (
        f"the self test workflow points at {paths!r}, which is not in this "
        "checkout, so the case cannot be reproduced here"
    )
    return str(resolved)


def test_every_case_states_both_an_outcome_and_an_exit_code() -> None:
    for case in _selftest_cases():
        for key in ("case", "paths", "strict", "format", "expect-outcome", "expect-exit"):
            assert key in case, f"the case {case.get('case')!r} states no {key}"
        assert case["expect-outcome"] in ("success", "failure")


def test_the_workflow_expects_the_exit_codes_the_cli_actually_produces(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Every `expect-exit` in the matrix, put through the CLI and compared.

    These are constants in a YAML file that nothing else reads. A rule moving
    severity, or a fixture edited, changes what the tool returns and leaves the
    workflow asserting the old number, which then either fails in CI for a
    reason invisible from the file, or passes while measuring the wrong thing.
    """
    for index, case in enumerate(_selftest_cases()):
        target = _target(str(case["paths"]), tmp_path / f"case-{index}")
        argv = ["check"]
        if case.get("profile"):
            argv += ["--profile", str(case["profile"])]
        if str(case["strict"]) == "true":
            argv.append("--strict")
        argv += ["--format", str(case["format"]), target]

        code = main(argv)
        capsys.readouterr()

        assert str(code) == str(case["expect-exit"]), (
            f"the case {case['case']!r} expects exit {case['expect-exit']}, and "
            f"`qfer-preflight {' '.join(argv)}` returned {code}"
        )


def test_the_expected_job_outcome_follows_from_the_expected_exit_code() -> None:
    """The action's whole contract: exit 0 is a green job, anything else is red."""
    for case in _selftest_cases():
        expected = "success" if str(case["expect-exit"]) == "0" else "failure"
        assert case["expect-outcome"] == expected, (
            f"the case {case['case']!r} expects exit {case['expect-exit']} and job "
            f"outcome {case['expect-outcome']}. A non zero exit code that does not "
            "fail the job is the defect the action exists to prevent"
        )


def test_the_empty_directory_case_is_present_and_expects_a_failure() -> None:
    """Named on its own, because it is the case the whole surface is for.

    A directory with no files in it is a run that validated nothing. If that
    reads as a passing job, a filer's pipeline reports a clean filing for a
    filing it never opened.
    """
    empty = [case for case in _selftest_cases() if case["paths"] == "selftest-empty"]
    assert len(empty) == 1, (
        "the self test workflow has no empty directory case. Running on an empty "
        "directory must fail the job, and nothing else here checks it"
    )
    assert empty[0]["expect-outcome"] == "failure"
    assert str(empty[0]["expect-exit"]) == "2"


def test_an_empty_directory_really_does_exit_two(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Measured directly, rather than inferred from the workflow's own claim."""
    empty = tmp_path / "nothing-here"
    empty.mkdir()
    code = main(["check", str(empty)])
    captured = capsys.readouterr()
    assert code == EXIT_USAGE
    assert "no files found" in captured.err


def test_the_selftest_runs_on_the_inputs_the_issue_names() -> None:
    """Clean, dirty, an empty directory, and a header matching no template."""
    paths = {str(case["paths"]) for case in _selftest_cases()}
    for required in (
        "tests/fixtures/1306a_s1_clean.csv",
        "tests/fixtures/1306a_s1_dirty.csv",
        "selftest-empty",
        "tests/fixtures/wrong_header.csv",
    ):
        assert required in paths, f"the self test workflow never runs on {required}"


# ---------------------------------------------------------------------------
# The self test's own escape hatch is held to having an assertion behind it
# ---------------------------------------------------------------------------


def test_every_continue_on_error_step_is_followed_by_an_assertion() -> None:
    """`continue-on-error` with nothing reading the result is a swallowed failure."""
    for job_name, job in _selftest()["jobs"].items():
        steps = list(job.get("steps", []))
        for index, step in enumerate(steps):
            if not step.get("continue-on-error"):
                continue
            step_id = step.get("id")
            assert step_id, (
                f"{job_name} has a continue-on-error step with no id, so no later "
                "step can read what it did"
            )
            later = " ".join(str(rest.get("run", "")) for rest in steps[index + 1 :])
            later += " ".join(
                str(value)
                for rest in steps[index + 1 :]
                for value in (rest.get("env") or {}).values()
            )
            assert f"steps.{step_id}.outcome" in later, (
                f"{job_name} runs the action under continue-on-error and never "
                f"reads steps.{step_id}.outcome afterwards, so a case that stopped "
                "failing would go unnoticed"
            )


def test_the_selftest_asserts_on_every_case_it_runs() -> None:
    """A job that runs the action and checks nothing is a job that measures nothing."""
    for job_name, job in _selftest()["jobs"].items():
        steps = list(job.get("steps", []))
        runs_the_action = any(str(step.get("uses", "")).strip() in ("./", ".") for step in steps)
        if not runs_the_action:
            continue
        assert any("exit 1" in str(step.get("run", "")) for step in steps), (
            f"{job_name} runs the action and no step in it can fail on the result"
        )


def test_the_gate_workflows_never_run_anything_under_continue_on_error() -> None:
    """The exemption is for the self test alone. CI must feel a gate's verdict."""
    for name in ("ci.yml", "security.yml"):
        body = (WORKFLOWS / name).read_text(encoding="utf-8")
        assert "continue-on-error" not in body, (
            f"{name} contains continue-on-error, which lets a gate fail quietly"
        )


# ---------------------------------------------------------------------------
# A new workflow cannot slip out of gate parity unnoticed
# ---------------------------------------------------------------------------


def test_every_workflow_is_either_a_gate_or_a_written_down_exemption() -> None:
    gate_workflows = _gate_workflows()
    present = {path.name for path in WORKFLOWS.glob("*.yml")}
    accounted = gate_workflows | PARITY_EXEMPT

    unaccounted = present - accounted
    assert not unaccounted, (
        f"{sorted(unaccounted)} is neither held to gate parity by "
        "tests/test_gate_parity.py nor listed as exempt with a reason in "
        "tests/test_ci_action.py. A gate that exists only in a workflow file "
        "cannot be run before pushing"
    )

    stale = accounted - present
    assert not stale, f"{sorted(stale)} is named as a workflow and no longer exists"


def _gate_workflows() -> set[str]:
    """The tuple `tests/test_gate_parity.py` holds to parity, read from its source.

    Read rather than imported, because the two files sit in a directory with no
    package of its own and an import would depend on how pytest was invoked.
    """
    text = (ROOT / "tests" / "test_gate_parity.py").read_text(encoding="utf-8")
    match = re.search(r"^GATE_WORKFLOWS = \(([^)]*)\)", text, re.MULTILINE)
    assert match, "could not find GATE_WORKFLOWS in tests/test_gate_parity.py"
    names = set(re.findall(r'"([^"]+)"', match.group(1)))
    assert names, "GATE_WORKFLOWS parsed as empty, so this check is vacuous"
    return names


# ---------------------------------------------------------------------------
# The filer guide describes the surfaces that exist
# ---------------------------------------------------------------------------


def _guide_yaml_blocks() -> list[Any]:
    """Every ```yaml block in the filer guide, parsed.

    A block that does not parse is a failure rather than a skip. A filer copies
    these, and a copied block that YAML rejects is worse than no example.
    """
    text = (ROOT / "docs" / "filer-guide.md").read_text(encoding="utf-8")
    blocks = re.findall(r"^```yaml\n(.*?)^```$", text, re.MULTILINE | re.DOTALL)
    assert blocks, "the filer guide has no YAML examples, so this check is vacuous"
    return [yaml.safe_load(block) for block in blocks]


def _guide_action_inputs() -> set[str]:
    """The `with:` keys the guide hands to this action, across every example."""
    used: set[str] = set()
    for block in _guide_yaml_blocks():
        if not isinstance(block, dict):
            continue
        for job in (block.get("jobs") or {}).values():
            for step in job.get("steps", []):
                if str(step.get("uses", "")).startswith("ChelseaKR/qfer-preflight@"):
                    used.update(step.get("with", {}))
    return used


def test_the_guide_only_hands_the_action_inputs_it_declares() -> None:
    used = _guide_action_inputs()
    assert used, "no example in the guide configures the action"
    declared = set(_action()["inputs"])
    assert used <= declared, (
        f"the filer guide passes {sorted(used - declared)} to the action, which "
        f"declares {sorted(declared)}. A copied example would fail on the "
        "unknown input"
    )


def test_the_guide_documents_every_input_the_action_declares() -> None:
    """An input nobody documents is an input nobody knows to use."""
    text = (ROOT / "docs" / "filer-guide.md").read_text(encoding="utf-8")
    undocumented = [name for name in _action()["inputs"] if f"`{name}`" not in text]
    assert not undocumented, (
        f"the filer guide never mentions {undocumented}, which action.yml offers"
    )


def test_the_guide_names_the_hook_that_the_manifest_publishes() -> None:
    published = {str(hook["id"]) for hook in _hooks()}
    referenced: set[str] = set()
    for block in _guide_yaml_blocks():
        if not isinstance(block, dict) or "repos" not in block:
            continue
        for repo in block["repos"]:
            referenced.update(str(hook["id"]) for hook in repo.get("hooks", []))
    assert referenced, "the guide shows no pre-commit example"
    assert referenced <= published, (
        f"the guide tells filers to enable {sorted(referenced - published)}, and "
        f".pre-commit-hooks.yaml publishes {sorted(published)}"
    )


def test_the_guides_pinned_checkout_is_the_one_this_repository_uses() -> None:
    """A pin copied into the guide is a constant, and constants rot silently."""
    guide = (ROOT / "docs" / "filer-guide.md").read_text(encoding="utf-8")
    ci = (WORKFLOWS / "ci.yml").read_text(encoding="utf-8")
    pattern = re.compile(r"actions/checkout@([0-9a-f]{40})")
    in_ci = set(pattern.findall(ci))
    in_guide = set(pattern.findall(guide))
    assert len(in_ci) == 1, f"ci.yml pins checkout to {sorted(in_ci)}"
    assert in_guide, "the guide's examples no longer pin actions/checkout to a commit"
    assert in_guide == in_ci, (
        f"the filer guide pins actions/checkout to {sorted(in_guide)} and ci.yml "
        f"pins {sorted(in_ci)}. The guide is handing filers a stale commit"
    )


def test_the_guide_says_the_action_is_not_in_the_published_release() -> None:
    """It is not, and a guide that implies otherwise sends filers to a tag with no action.

    `action.yml` and `.pre-commit-hooks.yaml` arrive after v0.2.0. Until a
    release carries them, the only working reference is a commit. This holds
    the sentence that says so, so it cannot be deleted while it is still true.
    """
    guide = (ROOT / "docs" / "filer-guide.md").read_text(encoding="utf-8")
    version = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))["project"]["version"]
    assert version == "0.2.0", (
        f"the package version is now {version}. If a release carrying action.yml "
        "has been published, rewrite the pinning section of the filer guide and "
        "then update this test"
    )
    # Flattened, so a reflowed paragraph does not defeat the assertion. That is
    # the same reason tests/test_filer_guide.py collapses whitespace.
    flat = re.sub(r"\s+", " ", guide)
    assert "not in `v0.2.0`" in flat, "the guide no longer warns that v0.2.0 carries no action.yml"
    assert "carrying `.pre-commit-hooks.yaml`, which `v0.2.0` does not" in flat, (
        "the guide no longer warns that v0.2.0 carries no pre-commit manifest"
    )


# ---------------------------------------------------------------------------
# The action's path splitting, run in a real shell
# ---------------------------------------------------------------------------


# The loop is lifted from action.yml. The printing after it is this harness's
# own, and it repeats the action's guard: under `set -u`, bash before 4.4
# treats "${targets[@]}" on an empty array as an unbound variable and aborts.
# Measured here on bash 3.2, which is what macOS ships. The action never
# expands the array until `test "${#targets[@]}" -gt 0` has passed, and
# test_the_action_counts_before_it_expands holds it that way.
_SPLIT_PATHS = """
declare -a targets=()
while IFS= read -r line; do
  case "${line}" in
    *[![:space:]]*) targets+=("${line}") ;;
  esac
done <<< "${PATHS}"
printf '%s\\n' "${#targets[@]}"
if [ "${#targets[@]}" -gt 0 ]; then
  printf '%s\\n' "${targets[@]}"
fi
"""


def _split(paths: str) -> list[str]:
    completed = subprocess.run(
        ["bash", "-c", "set -uo pipefail\n" + _SPLIT_PATHS],
        env={"PATHS": paths, "PATH": "/usr/bin:/bin"},
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    lines = completed.stdout.splitlines()
    count = int(lines[0])
    return lines[1 : 1 + count]


@pytest.mark.skipif(sys.platform == "win32", reason="the action runs bash")
def test_the_splitter_exercised_here_is_the_one_the_action_runs() -> None:
    """Lifted verbatim, so these tests cannot drift into testing a copy."""
    body = ACTION.read_text(encoding="utf-8")
    for line in ("while IFS= read -r line; do", '*[![:space:]]*) targets+=("${line}") ;;'):
        assert line in body, (
            f"action.yml no longer contains {line!r}, so the splitter exercised "
            "below is not the splitter the action runs"
        )


@pytest.mark.skipif(sys.platform == "win32", reason="the action runs bash")
def test_the_action_counts_before_it_expands() -> None:
    """Under `set -u`, an empty array expansion aborts bash before 4.4.

    Measured on bash 3.2, which macOS ships: `"${targets[@]}"` on an empty
    array is an unbound variable and the shell exits 127. Runners have bash 5,
    so the order below is what keeps the action honest on anything older: it
    counts first, and a count of zero fails the step on the `test` rather than
    on a shell error nobody can read.
    """
    run_step = next(step for step in _action_steps() if step.get("id") == "run")
    script = _shell(str(run_step["run"]))
    count = script.index('test "${#targets[@]}" -gt 0')
    expand = script.index('"${targets[@]}"')
    assert count < expand, (
        "the action expands the target array before checking it holds anything, "
        "which aborts on bash before 4.4 with an unbound variable rather than "
        "with the sentence the guard was written to print"
    )


@pytest.mark.skipif(sys.platform == "win32", reason="the action runs bash")
def test_a_path_with_a_space_stays_one_path() -> None:
    """The reason the input is one path per line rather than a space separated list."""
    assert _split("q3 filings/1306a.csv") == ["q3 filings/1306a.csv"]


@pytest.mark.skipif(sys.platform == "win32", reason="the action runs bash")
def test_several_lines_become_several_paths_and_blank_lines_are_dropped() -> None:
    assert _split("a.csv\n\n  \nb.csv\n") == ["a.csv", "b.csv"]


@pytest.mark.skipif(sys.platform == "win32", reason="the action runs bash")
def test_a_paths_input_of_only_whitespace_yields_nothing() -> None:
    """Which is what the refusal step ahead of it exists to catch first."""
    assert _split("   \n\n") == []
