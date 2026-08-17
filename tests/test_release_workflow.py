"""The release workflow must fail closed when it is not configured.

GitHub Actions cannot be run from a test, so what is exercised here is the part
that can be: the guard itself, lifted out of the workflow file and executed in
a real shell, plus the structural properties that decide whether a release can
happen at all.

The property that matters is that an unconfigured repository publishes nothing.
`RELEASE_ALLOWED_SIGNERS` holds the allowed-signers line for the key that signs
release tags. Until it is set, `git verify-tag` has no key to verify against,
so the workflow stops before it reaches that point rather than proceeding with
an unverifiable tag. See the "Releasing" section of CONTRIBUTING.md for the
setup step.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

WORKFLOW_PATH = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "release.yml"
WORKFLOW = WORKFLOW_PATH.read_text(encoding="utf-8")

GUARD = 'test -n "${ALLOWED_SIGNERS}"'
_RUN_BLOCK_INDENT = " " * 10


def _run_block(step_name: str) -> str:
    """Return the shell script of the step whose name contains `step_name`."""
    start = WORKFLOW.index(step_name)
    body = WORKFLOW[WORKFLOW.index("run: |", start) :]
    lines: list[str] = []
    for line in body.splitlines()[1:]:
        if line.strip() and not line.startswith(_RUN_BLOCK_INDENT):
            break
        lines.append(line)
    return "\n".join(lines)


VERIFY_SCRIPT = _run_block("Verify the tag object, its signature and its ancestry")


# ---------------------------------------------------------------------------
# The guard, actually run
# ---------------------------------------------------------------------------


def _run_guard(value: str | None) -> int:
    """Run the guard line lifted verbatim from the workflow."""
    bash = shutil.which("bash")
    assert bash, "these tests need bash, which is also what the workflow runs"
    env = {"PATH": "/usr/bin:/bin"}
    if value is not None:
        env["ALLOWED_SIGNERS"] = value
    completed = subprocess.run(
        [bash, "-c", f"set -euo pipefail\n{GUARD}\n"],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    return completed.returncode


def test_the_guard_under_test_is_the_one_in_the_workflow() -> None:
    """Stops this test from drifting away from the file it is testing."""
    assert GUARD in VERIFY_SCRIPT


def test_an_unset_secret_stops_the_job() -> None:
    """No repository secret at all leaves the variable unset."""
    assert _run_guard(None) != 0


def test_an_empty_secret_stops_the_job() -> None:
    """An unset secret expands to an empty string, which is not configured."""
    assert _run_guard("") != 0


def test_a_configured_secret_lets_the_job_continue() -> None:
    assert _run_guard("someone@example.invalid namespaces=git ssh-ed25519 AAAA") == 0


# ---------------------------------------------------------------------------
# The guard is only worth something if it comes first
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "later",
    ["git fetch", "git cat-file", "git verify-tag", "git merge-base"],
)
def test_nothing_git_related_happens_before_the_guard(later: str) -> None:
    assert later in VERIFY_SCRIPT
    assert VERIFY_SCRIPT.index(GUARD) < VERIFY_SCRIPT.index(later), (
        f"{later!r} runs before the RELEASE_ALLOWED_SIGNERS guard, so an "
        "unconfigured repository would get further than it should"
    )


def test_the_verification_script_aborts_on_the_first_failure() -> None:
    """Without `set -e` a failing guard would print and carry on regardless."""
    assert "set -euo pipefail" in VERIFY_SCRIPT


def test_the_tag_must_be_a_signed_tag_object_reachable_from_main() -> None:
    """A lightweight tag carries no signature, so the object type is checked."""
    assert 'test "$(git cat-file -t "${TAG}")" = "tag"' in VERIFY_SCRIPT
    assert "git verify-tag" in VERIFY_SCRIPT
    assert "git merge-base --is-ancestor" in VERIFY_SCRIPT


def test_the_secret_reaches_the_step_that_needs_it() -> None:
    assert "ALLOWED_SIGNERS: ${{ secrets.RELEASE_ALLOWED_SIGNERS }}" in WORKFLOW


# ---------------------------------------------------------------------------
# Structure: who may verify, who may write
# ---------------------------------------------------------------------------


def test_publishing_cannot_start_without_a_successful_verification() -> None:
    assert "needs: verify-tag" in WORKFLOW


def test_only_the_publishing_job_can_write() -> None:
    """The job that reads repository content has no write permission at all."""
    assert WORKFLOW.count("contents: write") == 1
    verify_at = WORKFLOW.index("  verify-tag:")
    publish_at = WORKFLOW.index("  publish:")
    write_at = WORKFLOW.index("contents: write")
    assert verify_at < publish_at < write_at


def test_releases_are_manual_and_never_triggered_by_a_push() -> None:
    assert "workflow_dispatch:" in WORKFLOW
    assert "  push:" not in WORKFLOW


def test_the_workflow_states_its_own_setup_step() -> None:
    assert "RELEASE_ALLOWED_SIGNERS" in WORKFLOW
    assert "gpg.ssh.allowedSignersFile" in WORKFLOW


def test_contributing_documents_the_release_setup() -> None:
    contributing = (WORKFLOW_PATH.parents[2] / "CONTRIBUTING.md").read_text(encoding="utf-8")
    assert "RELEASE_ALLOWED_SIGNERS" in contributing, (
        "the one manual setup step a release needs must be written down somewhere a human will look"
    )
