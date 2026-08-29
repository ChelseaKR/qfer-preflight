"""What CI enforces and what `make verify` enforces must not drift apart.

`CLAUDE.md` says `make verify` "is the same set CI runs". It was not quite.
`ci.yml` did run `make verify`, but `security.yml` ran three more gates, two of
them by repeating their commands inline rather than calling the targets that
already existed. `make audit` was in the Makefile and no workflow invoked it,
while the dependency-audit job carried its own copy of the same four commands.
The secret scan had no target at all.

Two failures follow from that shape, and they point in opposite directions. A
tree can be green under `make verify` and rejected by CI, which is the one a
contributor meets. And a make target can rot with no run to notice, which is
the one nobody meets until it is needed.

So every gate CI runs is a make target, and this file holds it that way. The
alternative, keeping two copies of each command in step, is the arrangement
that produced the drift in the first place.

`release.yml` is deliberately out of scope. Its steps are release-time
verification of a signed tag rather than gates over the working tree, they are
not things a contributor runs locally, and `tests/test_release_workflow.py`
exercises them directly.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"
MAKEFILE = ROOT / "Makefile"

# The workflows whose `run:` steps are gates over the working tree.
GATE_WORKFLOWS = ("ci.yml", "security.yml")

# Steps that install something rather than checking something. A step is
# allowed not to call make only if its script is one of these. Kept as an
# explicit list, because "looks like setup" is exactly the judgement that lets
# a real gate slip out of the parity requirement.
_SETUP_PATTERNS = (
    re.compile(r"^uv python install\b"),
    re.compile(r"^uv sync --locked$"),
    # The pinned gitleaks download, identified by the hash check that makes it
    # safe. A step that stops verifying the checksum stops matching this.
    re.compile(r"sha256sum -c -", re.MULTILINE),
)

_MAKE_INVOCATION = re.compile(r"\bmake\s+([a-z][a-z-]*)\b")


def _load(name: str) -> dict[str, Any]:
    data = yaml.safe_load((WORKFLOWS / name).read_text(encoding="utf-8"))
    assert isinstance(data, dict), f"{name} did not parse as a mapping"
    return data


def _run_steps(name: str) -> list[tuple[str, str]]:
    """Every (step name, shell script) pair in a workflow."""
    workflow = _load(name)
    steps: list[tuple[str, str]] = []
    for job in workflow["jobs"].values():
        for step in job.get("steps", []):
            if "run" in step:
                steps.append((step.get("name", "<unnamed>"), str(step["run"]).strip()))
    return steps


def _makefile_targets() -> set[str]:
    pattern = re.compile(r"^([a-z][a-z-]*):", re.MULTILINE)
    return set(pattern.findall(MAKEFILE.read_text(encoding="utf-8")))


def _recipe_lines(target: str) -> str:
    """The commands a target actually runs, with comments removed.

    Comments are stripped deliberately. The first draft of the two tests below
    read the whole block, and the block explains what `--no-git` is for, so
    deleting the `--no-git` command left the assertion passing on the sentence
    describing it. A gate that reads the documentation instead of the code is
    the failure this file is about.
    """
    text = MAKEFILE.read_text(encoding="utf-8")
    start = text.index(f"\n{target}:") + 1
    commands: list[str] = []
    for line in text[start:].splitlines()[1:]:
        if line.startswith("\t"):
            commands.append(line)
            continue
        if not line.strip() or line.lstrip().startswith("#"):
            continue  # blank line, or a comment sitting inside the recipe
        break  # the next target
    assert commands, f"found no command lines for the {target} target"
    return "\n".join(commands)


def _is_setup(script: str) -> bool:
    return any(pattern.search(script) for pattern in _SETUP_PATTERNS)


# ---------------------------------------------------------------------------
# The gate must have something to look at
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("workflow", GATE_WORKFLOWS)
def test_the_workflow_parses_and_has_run_steps(workflow: str) -> None:
    """A parity check over an empty step list passes without checking anything."""
    steps = _run_steps(workflow)
    assert steps, f"{workflow} yielded no run steps, so the parity check is vacuous"


def test_the_makefile_targets_were_actually_found() -> None:
    targets = _makefile_targets()
    assert {"verify", "test", "lint", "typecheck", "security", "audit", "secrets"} <= targets, (
        f"the Makefile parser found {sorted(targets)}, which is missing targets "
        "known to be there. It has stopped reading the file correctly"
    )


# ---------------------------------------------------------------------------
# Parity
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("workflow", GATE_WORKFLOWS)
def test_every_gate_step_runs_a_make_target(workflow: str) -> None:
    """No gate exists only in a workflow file, where nobody can run it locally."""
    offenders = [
        (name, script)
        for name, script in _run_steps(workflow)
        if not _is_setup(script) and not _MAKE_INVOCATION.search(script)
    ]
    assert not offenders, (
        f"{workflow} runs gates that are not make targets, so `make verify` can "
        "be green on a tree CI rejects and the check cannot be reproduced "
        "locally:\n"
        + "\n".join(f"  step {name!r}: {script.splitlines()[0]}" for name, script in offenders)
    )


@pytest.mark.parametrize("workflow", GATE_WORKFLOWS)
def test_every_make_target_a_workflow_calls_exists(workflow: str) -> None:
    """A workflow calling a renamed target fails in CI and nowhere else."""
    targets = _makefile_targets()
    for name, script in _run_steps(workflow):
        for called in _MAKE_INVOCATION.findall(script):
            assert called in targets, (
                f"{workflow} step {name!r} runs `make {called}`, which is not a "
                f"target in the Makefile. Targets: {sorted(targets)}"
            )


def test_ci_runs_the_whole_gate() -> None:
    scripts = [script for _, script in _run_steps("ci.yml")]
    assert any("make verify" in script for script in scripts), (
        "ci.yml no longer runs `make verify`, so the target CLAUDE.md calls the "
        "whole gate is not what CI enforces"
    )


def test_the_security_workflow_runs_the_targets_it_is_named_for() -> None:
    """Each of the three security gates goes through the Makefile."""
    scripts = " ".join(script for _, script in _run_steps("security.yml"))
    for target in ("secrets", "security", "audit"):
        assert f"make {target}" in scripts, (
            f"security.yml does not run `make {target}`. A gate that exists only "
            "in the workflow cannot be run before pushing"
        )


def test_the_secret_scan_reads_the_working_tree_and_not_only_the_history() -> None:
    """The step name has always said both. The command used to do only one.

    `gitleaks detect` walks git history. `--no-git` walks the files on disk.
    A secret present in the tree and absent from history is invisible to the
    first and caught by the second, so the target runs both passes.
    """
    body = _recipe_lines("secrets")
    assert "--no-git" in body, (
        "`make secrets` does not scan the working tree. `gitleaks detect` alone "
        "reads git history, while the step that runs it is named for both"
    )
    assert body.count("detect") >= 2, "the history pass and the working tree pass are both needed"


def test_a_missing_gitleaks_is_a_failure_rather_than_a_skip() -> None:
    """A gate that passes quietly on machines that cannot run it is counted anyway."""
    body = _recipe_lines("secrets")
    assert "exit 127" in body, (
        "`make secrets` does not fail when gitleaks is absent, so it reports "
        "success for a check that did not happen"
    )


# ---------------------------------------------------------------------------
# The parity check itself must be able to fail
# ---------------------------------------------------------------------------


def test_the_parity_check_would_notice_an_inlined_gate() -> None:
    """Planted directly, because a check nobody has watched fail is not a check."""
    inlined = "uv run pytest --cov-fail-under=90"
    assert not _is_setup(inlined)
    assert not _MAKE_INVOCATION.search(inlined), (
        "a step running pytest directly would be treated as a make invocation, "
        "so the parity check could not see an inlined gate"
    )


def test_the_parity_check_accepts_a_real_make_step() -> None:
    """And a check that flags everything is no better than one that flags nothing."""
    assert _MAKE_INVOCATION.search("make verify")
    assert _MAKE_INVOCATION.findall("make secrets") == ["secrets"]


def test_setup_steps_are_recognised_narrowly() -> None:
    """The exemption must not stretch to cover a gate."""
    assert _is_setup("uv sync --locked")
    assert _is_setup("uv python install 3.12")
    assert not _is_setup("uv run bandit -q -c pyproject.toml -r src")
    assert not _is_setup("./gitleaks detect --source .")


def test_the_recipe_reader_ignores_comments() -> None:
    """Proved directly, because reading a comment is how the check above died once."""
    body = _recipe_lines("secrets")
    assert "#" not in body, f"comments leaked into the recipe text: {body}"
    assert "gitleaks" in body.lower(), "the reader returned no gitleaks command at all"
