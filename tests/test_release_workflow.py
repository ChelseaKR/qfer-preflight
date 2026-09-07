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

import re
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


def _run_block_of(workflow: str, step_name: str) -> str:
    """Return the shell script of the step whose name contains `step_name`."""
    start = workflow.index(step_name)
    body = workflow[workflow.index("run: |", start) :]
    lines: list[str] = []
    for line in body.splitlines()[1:]:
        if line.strip() and not line.startswith(_RUN_BLOCK_INDENT):
            break
        lines.append(line)
    return "\n".join(lines)


def _run_block(step_name: str) -> str:
    """`_run_block_of` against `release.yml`, which most of this file reads."""
    return _run_block_of(WORKFLOW, step_name)


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


# ---------------------------------------------------------------------------
# The publish path: dispatch-only, OIDC-only, and inert until it is dispatched
# ---------------------------------------------------------------------------
#
# `release.yml` above makes a GitHub release and stops there. `publish-pypi.yml`
# is the second half: it takes a tag that release.yml has already published,
# re-verifies it against main, builds at that commit, and uploads over PyPI
# Trusted Publishing. Everything below is a property where getting it wrong is
# silent -- a stored token that nobody notices, a publish job that quietly
# rebuilds what it uploads, a trigger that hands the release authority to
# whoever can push a tag.

PUBLISH_PATH = ROOT / ".github" / "workflows" / "publish-pypi.yml"
PUBLISH = PUBLISH_PATH.read_text(encoding="utf-8")
PUBLISH_IDENTITY = _run_block_of(PUBLISH, "Establish tag identity from trusted main")


def test_publishing_is_dispatched_and_never_triggered_by_a_push() -> None:
    """A `push: tags:` trigger runs the definition stored at the tagged ref.

    Whoever can push a tag would then also be choosing what the publish does.
    Dispatching from main keeps that authority on the reviewed branch.
    """
    assert "workflow_dispatch:" in PUBLISH
    assert "\n  push:" not in PUBLISH
    assert 'test "${GITHUB_REF}" = refs/heads/main' in PUBLISH_IDENTITY


def test_no_pypi_token_is_stored_or_read_anywhere() -> None:
    """Trusted Publishing exists so that no long-lived credential has to.

    A `password:` input or a `secrets.PYPI_*` reference would mean a token is
    sitting in this repository's secret store, which is the thing OIDC
    replaces. `id-token: write` without `environment:` is also refused: the
    environment name is half of what PyPI matches the OIDC claim against.
    """
    assert "PYPI_API_TOKEN" not in PUBLISH
    assert "password:" not in PUBLISH
    assert "secrets." not in PUBLISH
    assert "id-token: write" in PUBLISH
    assert "name: pypi" in PUBLISH


def test_the_publish_job_holds_no_write_access_to_the_repository() -> None:
    publish_job = PUBLISH[PUBLISH.index("  publish:") :]
    assert "actions/checkout" not in publish_job, (
        "the job that can upload must never check out content it could publish"
    )
    assert "contents: write" not in PUBLISH
    assert "id-token: write" in publish_job


def test_the_uploaded_bytes_are_the_bytes_the_build_job_built() -> None:
    """A rebuild in the publish job is a different artifact than the one verified."""
    publish_job = PUBLISH[PUBLISH.index("  publish:") :]
    assert "download-artifact" in publish_job
    assert "uv build" not in publish_job


def test_the_publish_path_verifies_the_signature_before_anything_else() -> None:
    """The same guard as release.yml, in the same position: first."""
    assert GUARD in PUBLISH_IDENTITY
    for later in ("git fetch", "git cat-file", "git verify-tag", "git merge-base"):
        assert later in PUBLISH_IDENTITY
        assert PUBLISH_IDENTITY.index(GUARD) < PUBLISH_IDENTITY.index(later), (
            f"{later!r} runs before the allowed_signers guard in publish-pypi.yml"
        )
    assert "set -euo pipefail" in PUBLISH_IDENTITY


def test_only_a_stable_semver_tag_that_is_already_released_may_be_published() -> None:
    """A pre-release tag, or one release.yml never published, is not a release.

    PyPI is not revocable in any useful sense: an upload can be yanked, never
    unmade. So the tag has to be one that already survived release.yml.
    """
    assert "^v(0|[1-9][0-9]*)\\.(0|[1-9][0-9]*)\\.(0|[1-9][0-9]*)$" in PUBLISH_IDENTITY
    assert "gh release view" in PUBLISH_IDENTITY
    assert "isDraft" in PUBLISH_IDENTITY


def test_the_built_artifacts_must_carry_the_tags_own_version() -> None:
    build = _run_block_of(PUBLISH, "Build and confirm the artefacts carry the tag's version")
    assert 'test -f "dist/qfer_preflight-${VERSION}.tar.gz"' in build
    assert 'test -f "dist/qfer_preflight-${VERSION}-py3-none-any.whl"' in build
    assert 'test "$(ls dist | wc -l)" -eq 2' in build, (
        "an extra file in dist/ would be uploaded too, unexamined"
    )


def test_every_action_in_the_publish_workflow_is_pinned_to_a_commit() -> None:
    """A moving tag is somebody else deciding what runs in a job that can publish."""
    unpinned = [
        line.strip()
        for line in PUBLISH.splitlines()
        if line.strip().startswith("uses:")
        and not re.match(r"^uses:\s+[^@]+@[0-9a-f]{40}\b", line.strip())
    ]
    assert not unpinned, f"unpinned action references in publish-pypi.yml: {unpinned}"


def test_the_workflow_records_the_registration_only_the_owner_can_make() -> None:
    """Trusted Publishing needs a web-UI registration no automation can do.

    The five values PyPI's form asks for are written into the workflow header,
    because a job that fails closed with a trusted-publisher error and no
    instructions is a job nobody can act on. `workflow_name` in particular is
    the filename, and getting it wrong is a failure that reads as a
    permissions problem.
    """
    header = PUBLISH[: PUBLISH.index("name: publish-pypi")]
    for value in ("qfer-preflight", "ChelseaKR", "publish-pypi.yml", "pypi"):
        assert value in header, f"the header does not record {value!r} for the registration"
