"""The release workflow must fail closed when it is not configured.

GitHub Actions cannot be run from a test, so what is exercised here is the part
that can be: the guard itself, lifted out of the workflow file and executed in
a real shell, plus the structural properties that decide whether a release can
happen at all.

The property that matters is that a repository whose signer list names no
principal publishes nothing. `.github/allowed_signers` holds the
allowed-signers line for the key that signs release tags. While it holds only
comments and blank lines, `git verify-tag` has no key to verify against, so
the workflow stops before it reaches that point rather than proceeding with an
unverifiable tag. See the "Releasing" section of CONTRIBUTING.md.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_PATH = ROOT / ".github" / "workflows" / "release.yml"
WORKFLOW = WORKFLOW_PATH.read_text(encoding="utf-8")
SIGNERS_PATH = ROOT / ".github" / "allowed_signers"

GUARD = "grep -qv '^[[:space:]]*\\(#\\|$\\)' .github/allowed_signers"
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


def _run_guard(signers_content: str | None, tmp_path: Path) -> int:
    """Run the guard line lifted verbatim from the workflow.

    `signers_content` becomes the body of `.github/allowed_signers` in a
    scratch tree, and `None` means the file does not exist at all.
    """
    bash = shutil.which("bash")
    assert bash, "these tests need bash, which is also what the workflow runs"
    tree = tmp_path / "tree"
    (tree / ".github").mkdir(parents=True)
    if signers_content is not None:
        (tree / ".github" / "allowed_signers").write_text(signers_content, encoding="utf-8")
    completed = subprocess.run(
        [bash, "-c", f"set -euo pipefail\n{GUARD}\n"],
        cwd=tree,
        env={"PATH": "/usr/bin:/bin"},
        capture_output=True,
        text=True,
        check=False,
    )
    return completed.returncode


def test_the_guard_under_test_is_the_one_in_the_workflow() -> None:
    """Stops this test from drifting away from the file it is testing."""
    assert GUARD in VERIFY_SCRIPT


def test_a_missing_signer_file_stops_the_job(tmp_path: Path) -> None:
    assert _run_guard(None, tmp_path) != 0


def test_an_empty_signer_file_stops_the_job(tmp_path: Path) -> None:
    assert _run_guard("", tmp_path) != 0


def test_a_comment_only_signer_file_stops_the_job(tmp_path: Path) -> None:
    """Present is not the same as populated."""
    assert _run_guard("# a comment\n\n   \n# another comment\n", tmp_path) != 0


def test_a_populated_signer_file_lets_the_job_continue(tmp_path: Path) -> None:
    line = 'someone@example.invalid namespaces="git" ssh-ed25519 AAAA\n'
    assert _run_guard(line, tmp_path) == 0


def test_the_committed_signer_file_names_exactly_one_principal(
    tmp_path: Path,
) -> None:
    """The file in this repository must itself pass the guard, with one key."""
    content = SIGNERS_PATH.read_text(encoding="utf-8")
    assert _run_guard(content, tmp_path) == 0
    lines = [
        line.strip()
        for line in content.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    assert len(lines) == 1, "exactly one signing identity is expected"
    principal, *rest = lines[0].split()
    assert "@" in principal, "the principal is the signer's email"
    assert "ssh-ed25519" in rest, "the recorded key is an ed25519 public key"


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
        f"{later!r} runs before the allowed_signers guard, so an "
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


def test_the_committed_signer_file_reaches_git_config() -> None:
    assert "git config gpg.ssh.allowedSignersFile .github/allowed_signers" in VERIFY_SCRIPT


# ---------------------------------------------------------------------------
# The product gates run before anything is published
# ---------------------------------------------------------------------------


def test_the_full_gate_runs_at_the_exact_tagged_commit() -> None:
    """An untested commit must not be taggable into a release."""
    gate = _run_block("Run the full gate at the tagged commit")
    assert 'git checkout --detach "${TAG}^{commit}"' in gate
    assert "make verify" in gate


def test_the_tag_and_the_package_version_must_agree() -> None:
    """A prior incident shipped a mismatched __version__; the tag is checked."""
    agree = _run_block("Confirm the tag and the package version agree")
    assert "pyproject.toml" in agree
    assert 'test "${want}" = "${have}"' in agree


# ---------------------------------------------------------------------------
# Structure: who may verify, who may write
# ---------------------------------------------------------------------------


def test_publishing_cannot_start_without_a_successful_verification() -> None:
    assert "needs: verify-tag" in WORKFLOW


def test_the_release_notes_are_the_signed_tag_annotation() -> None:
    """What is published is the text that was signed, not generated notes.

    The v0.2.0 release failed here. `gh release create` refuses
    --notes-from-tag together with --repo, and --repo is not optional in this
    job: it never checks out repository content, so gh has no local repository
    to infer one from. The annotation is read through the API instead. This
    test exists because the combination is accepted by the YAML, rejected by
    gh, and therefore invisible until a release is actually attempted.
    """
    create = _run_block("Create the GitHub release")
    # The step explains the gh restriction in a comment, and a comment naming
    # a flag is not the step using it. Assert against the commands alone.
    commands = "\n".join(line for line in create.splitlines() if not line.lstrip().startswith("#"))
    assert "--notes-from-tag" not in commands, (
        "gh refuses --notes-from-tag alongside --repo, which this job requires"
    )
    assert "--repo" in commands, "the publishing job checks out nothing and must name the repo"
    assert "--notes-file notes.md" in commands
    assert "git/tags/${SHA}" in commands, (
        "the notes must come from the tag object that verification resolved, "
        "so the published text is the signed text"
    )
    assert "--verify-tag" in commands, "the tag must already exist on the remote"
    assert "test -s notes.md" in commands, "empty release notes must stop the publish"


def test_the_publishing_job_never_checks_out_repository_content() -> None:
    """The separation the workflow header promises, asserted rather than trusted."""
    publish = WORKFLOW[WORKFLOW.index("  publish:") :]
    assert "actions/checkout" not in publish, (
        "the job that can write must never check out content it could publish"
    )


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


def test_the_workflow_states_its_own_signer_list() -> None:
    assert ".github/allowed_signers" in WORKFLOW
    assert "gpg.ssh.allowedSignersFile" in WORKFLOW


def test_contributing_documents_the_release_setup() -> None:
    contributing = (ROOT / "CONTRIBUTING.md").read_text(encoding="utf-8")
    assert ".github/allowed_signers" in contributing, (
        "where the signer list lives must be written down somewhere a human will look"
    )
