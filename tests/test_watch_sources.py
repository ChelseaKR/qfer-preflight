"""The source watcher, and the one distinction it exists to keep.

`docs/source-manifest.md` records a digest for every published document this project
cites, and the README says the tool is wrong until updated when one of them changes.
Watching that by hand before a filing deadline is the kind of promise that lapses
quietly, so `scripts/watch_sources.py` does it on a schedule.

The distinction that matters is **could not check** versus **has not changed**. A watcher
that reported "no drift" because the Commission's web server was down would be worse than
no watcher: a green light nobody earned. Every test below that is not about parsing is
about that boundary.

Offline throughout. `fetch` is monkeypatched; nothing here opens a socket.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import urllib.error
from collections.abc import Callable, Iterator
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "watch_sources.py"


def _load() -> ModuleType:
    """Import the script by path: `scripts/` is not a package and must not become one."""
    spec = importlib.util.spec_from_file_location("watch_sources", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["watch_sources"] = module
    spec.loader.exec_module(module)
    return module


watch_sources = _load()

#: A manifest shaped exactly like the real one, including the blank line after each
#: heading and the trailing `cited by:` field, because an earlier parser matched a
#: single regex across those lines and silently found nothing.
MANIFEST = """# Source manifest

Prose that is not an entry, with a ### that is not a heading inside a sentence.

## Manifest

### CEC-1306A instructions, rev. 07/14/2025

- url: https://www.energy.ca.gov/sites/default/files/2025-07/1306A_Instructions_07142025_ada.pdf
- sha256: aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
- retrieved: 2026-08-26
- cited by: CEC-1306A-S1 and CEC-1306A-S2 profiles; most field rules

### CEC-1306B instructions, rev. 07/14/2025

- url: https://www.energy.ca.gov/sites/default/files/2025-07/1306B_Instructions_07142025_ada.pdf
- sha256: bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb
- retrieved: 2026-08-26
- cited by: the CEC-1306B profile

### A section with no digest at all

- url: https://example.invalid/nothing
- retrieved: 2026-08-26
"""

_A_URL = "https://www.energy.ca.gov/sites/default/files/2025-07/1306A_Instructions_07142025_ada.pdf"
_B_URL = "https://www.energy.ca.gov/sites/default/files/2025-07/1306B_Instructions_07142025_ada.pdf"


@pytest.fixture
def manifest(tmp_path: Path) -> Path:
    path = tmp_path / "source-manifest.md"
    path.write_text(MANIFEST, encoding="utf-8")
    return path


@pytest.fixture
def no_network(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Any unstubbed fetch is a bug in the test, not a network call."""

    def forbidden(url: str) -> bytes:
        raise AssertionError(f"the test opened the network for {url}")

    monkeypatch.setattr(watch_sources, "fetch", forbidden)
    yield


def _stub(monkeypatch: pytest.MonkeyPatch, responses: dict[str, Callable[[], bytes]]) -> None:
    def fake(url: str) -> bytes:
        return responses[url]()

    monkeypatch.setattr(watch_sources, "fetch", fake)


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------


def test_the_real_manifest_parses_to_every_entry_it_holds() -> None:
    """A manifest that reads as empty is a broken watcher, not a clean one.

    Pinned against the real file, because the first parser here matched one regex
    across the heading and the bullet list, found zero entries, and would have exited
    0 with "0 documents" had the emptiness guard not existed.
    """
    text = (ROOT / "docs" / "source-manifest.md").read_text(encoding="utf-8")
    entries = watch_sources.parse_manifest(text)
    assert len(entries) == text.count("\n- sha256: "), (
        "the parser and the file disagree about how many entries there are"
    )
    assert len(entries) > 1


def test_a_section_missing_a_digest_is_skipped_not_half_parsed(manifest: Path) -> None:
    entries = watch_sources.parse_manifest(manifest.read_text(encoding="utf-8"))
    assert [entry.url for entry in entries] == [_A_URL, _B_URL]


# ---------------------------------------------------------------------------
# The distinction that matters
# ---------------------------------------------------------------------------


def test_a_404_is_an_error_outcome_and_never_unchanged(
    manifest: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """`Done when`: distinct from unchanged, and the summary says so."""

    def gone() -> bytes:
        raise urllib.error.HTTPError(_A_URL, 404, "Not Found", {}, None)  # type: ignore[arg-type]

    _stub(monkeypatch, {_A_URL: gone, _B_URL: lambda: b"anything"})

    code = watch_sources.main(["--manifest", str(manifest), "--json"])
    payload = json.loads(capsys.readouterr().out)

    by_url = {row["url"]: row for row in payload["results"]}
    assert by_url[_A_URL]["outcome"] == "error"
    assert by_url[_A_URL]["observed_sha256"] is None, (
        "a document we never fetched must not carry a digest"
    )
    assert "NOT unchanged" in by_url[_A_URL]["detail"]
    assert payload["counts"]["error"] == 1
    assert payload["every_document_was_fetched"] is False
    assert code == 2, "a run that could not look must not exit 0"


def test_a_connection_failure_is_also_an_error_not_unchanged(
    manifest: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A dead connection carries no HTTP status and must still not read as clean."""

    def refused() -> bytes:
        raise urllib.error.URLError(ConnectionRefusedError(111, "Connection refused"))

    _stub(monkeypatch, {_A_URL: refused, _B_URL: lambda: b"anything"})

    code = watch_sources.main(["--manifest", str(manifest)])
    out = capsys.readouterr().out

    assert "ERROR" in out
    assert "did not establish that the sources are current" in out
    assert code == 2


def test_drift_is_reported_for_the_changed_entry_only_and_names_its_rules(
    manifest: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """`Done when`: that entry only, with the rules whose citations point into it."""
    _stub(monkeypatch, {_A_URL: lambda: b"a revised document", _B_URL: lambda: b"also revised"})

    code = watch_sources.main(["--manifest", str(manifest), "--json"])
    payload = json.loads(capsys.readouterr().out)

    by_url = {row["url"]: row for row in payload["results"]}
    assert by_url[_A_URL]["outcome"] == "drifted"
    assert by_url[_A_URL]["observed_sha256"] != by_url[_A_URL]["recorded_sha256"]

    # The registry is the real one: these are the rules that actually cite the 1306A
    # instructions, so triage starts from the registry rather than a full text diff.
    assert "QP010" in by_url[_A_URL]["rules"]
    assert by_url[_B_URL]["rules"] != by_url[_A_URL]["rules"]
    assert code == 1, "drift is not an error, and it is not success either"


def test_an_unchanged_document_is_reported_as_unchanged(
    manifest: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The control for every test above: the happy path must actually be reachable.

    Without this, "drifted" could be the only outcome the code can produce and every
    assertion above would still hold.
    """
    import hashlib

    body_a = b"the recorded 1306A bytes"
    body_b = b"the recorded 1306B bytes"
    text = manifest.read_text(encoding="utf-8")
    text = text.replace("a" * 64, hashlib.sha256(body_a).hexdigest())
    text = text.replace("b" * 64, hashlib.sha256(body_b).hexdigest())
    manifest.write_text(text, encoding="utf-8")

    _stub(monkeypatch, {_A_URL: lambda: body_a, _B_URL: lambda: body_b})

    code = watch_sources.main(["--manifest", str(manifest)])
    out = capsys.readouterr().out

    assert "2 unchanged, 0 drifted" in out
    assert "Every cited document re-hashes as recorded." in out
    assert code == 0


# ---------------------------------------------------------------------------
# The dry run, which is the workflow's offline self-test
# ---------------------------------------------------------------------------


def test_a_dry_run_reports_not_checked_and_never_unchanged(
    manifest: Path, capsys: pytest.CaptureFixture[str], no_network: None
) -> None:
    """A dry run that printed "unchanged" would be this script's own defect.

    It did, in the first version: "13 unchanged" and "Every cited document re-hashes
    as recorded", with no request made. The `no_network` fixture makes the claim
    structural rather than a matter of trust.
    """
    code = watch_sources.main(["--manifest", str(manifest), "--dry-run", "--json"])
    payload = json.loads(capsys.readouterr().out)

    assert payload["counts"]["not-checked"] == 2
    assert payload["counts"]["unchanged"] == 0
    assert payload["every_document_was_fetched"] is False
    for row in payload["results"]:
        assert row["observed_sha256"] is None
        assert row["rules"] is not None, "a dry run still resolves the citing rules"
    assert code == 0


def test_the_dry_run_text_refuses_to_claim_anything_about_drift(
    manifest: Path, capsys: pytest.CaptureFixture[str], no_network: None
) -> None:
    out_code = watch_sources.main(["--manifest", str(manifest), "--dry-run"])
    out = capsys.readouterr().out
    assert "DRY RUN" in out
    assert "says NOTHING about whether the published documents have changed" in out
    assert "Every cited document re-hashes as recorded." not in out
    assert out_code == 0


def test_an_empty_manifest_is_refused_rather_than_reported_as_clean(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], no_network: None
) -> None:
    """Zero documents, zero drift, exit 0 would be a green run over nothing at all."""
    empty = tmp_path / "empty.md"
    empty.write_text("# Source manifest\n\nNo entries here.\n", encoding="utf-8")

    code = watch_sources.main(["--manifest", str(empty)])

    assert code == 2
    assert "broken watcher, not a clean one" in capsys.readouterr().err


def test_a_missing_manifest_is_an_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], no_network: None
) -> None:
    code = watch_sources.main(["--manifest", str(tmp_path / "nope.md")])
    assert code == 2
    assert "could not read" in capsys.readouterr().err
