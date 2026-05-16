from pathlib import Path

import pytest

from scripts import capture_ctrip_snapshot


def test_snapshot_output_defaults_to_ignored_debug_directory(tmp_path: Path) -> None:
    output = capture_ctrip_snapshot.resolve_snapshot_output(
        project_root=tmp_path,
        explicit_output=None,
        allow_fixture_overwrite=False,
    )

    assert output == tmp_path / "data/debug/ctrip_search_results.html"


def test_snapshot_output_resolves_relative_paths_from_project_root(tmp_path: Path) -> None:
    output = capture_ctrip_snapshot.resolve_snapshot_output(
        project_root=tmp_path,
        explicit_output=Path("data/debug/custom.html"),
        allow_fixture_overwrite=False,
    )

    assert output == tmp_path / "data/debug/custom.html"


def test_snapshot_output_requires_explicit_fixture_overwrite_flag(tmp_path: Path) -> None:
    fixture_output = tmp_path / "tests/fixtures/ctrip_search_results.html"

    with pytest.raises(ValueError, match="--allow-fixture-overwrite"):
        capture_ctrip_snapshot.resolve_snapshot_output(
            project_root=tmp_path,
            explicit_output=fixture_output,
            allow_fixture_overwrite=False,
        )


def test_snapshot_output_allows_fixture_overwrite_when_requested(tmp_path: Path) -> None:
    fixture_output = tmp_path / "tests/fixtures/ctrip_search_results.html"

    output = capture_ctrip_snapshot.resolve_snapshot_output(
        project_root=tmp_path,
        explicit_output=fixture_output,
        allow_fixture_overwrite=True,
    )

    assert output == fixture_output
