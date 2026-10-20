from __future__ import annotations

import pytest
import responses

from src.updater import updater
from src.updater.updater import GITHUB_API_LATEST, check_for_update, compare_versions


def test_compare_versions_simple() -> None:
    assert compare_versions("0.1.0", "0.1.0") == 0
    assert compare_versions("0.1.0", "0.2.0") < 0
    assert compare_versions("v1.0.0", "0.9.9") > 0


@responses.activate
def test_check_for_update_with_github_latest(monkeypatch: pytest.MonkeyPatch) -> None:
    # The asset has no architecture in its name, which is only acceptable off macOS.
    monkeypatch.setattr(updater, "_is_macos", lambda: False)
    payload = {
        "tag_name": "v0.2.0",
        "html_url": "https://github.com/dantypas3/elAPI_Plugins/releases/tag/v0.2.0",
        "body": "Changelog",
        "published_at": "2026-01-09T00:00:00Z",
        "assets": [
            {
                "name": "elAPI_Plugins.dmg",
                "browser_download_url": "https://example.com/elAPI_Plugins.dmg",
            }
        ],
    }
    responses.add(
        responses.GET,
        GITHUB_API_LATEST,
        json=payload,
        status=200,
        headers={"ETag": '"etag-123"'},
    )

    info = check_for_update(current_version="0.1.0")

    assert info.is_update_available is True
    assert info.latest_version == "v0.2.0"
    assert info.download_url == "https://example.com/elAPI_Plugins.dmg"
    assert info.etag == '"etag-123"'


@responses.activate
def test_check_for_update_handles_missing_releases() -> None:
    responses.add(responses.GET, GITHUB_API_LATEST, status=404)
    info = check_for_update(current_version="0.1.0")
    assert info.is_update_available is False
    assert info.latest_version == "0.1.0"


@responses.activate
def test_check_for_update_leaves_missing_fields_as_none() -> None:
    responses.add(
        responses.GET,
        GITHUB_API_LATEST,
        json={"tag_name": "v9.9.9", "assets": []},
        status=200,
    )

    info = check_for_update(current_version="1.0.0")

    assert info.html_url is None
    assert info.release_notes is None
    assert info.published_at is None


@pytest.mark.parametrize(
    ("arch", "expected"),
    [("arm64", "elAPI_Plugins_arm64.dmg"), ("x86_64", "elAPI_Plugins_x86_64.dmg")],
)
def test_macos_picks_the_dmg_for_its_own_architecture(
    monkeypatch: pytest.MonkeyPatch, arch: str, expected: str
) -> None:
    monkeypatch.setattr(updater, "_is_macos", lambda: True)
    monkeypatch.setattr(updater, "_mac_arch_tag", lambda: arch)
    assets = [
        {"name": "elAPI_Plugins_x86_64.dmg", "browser_download_url": "u/x86"},
        {"name": "elAPI_Plugins_arm64.dmg", "browser_download_url": "u/arm"},
        {"name": "elapi-plugins_1.3.0_amd64.deb", "browser_download_url": "u/deb"},
    ]

    name, _ = updater._pick_asset(
        assets,
        (".dmg",),
        name_predicate=updater._asset_name_matches_mac_arch,
    )

    assert name == expected


def test_macos_ignores_a_dmg_without_architecture(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(updater, "_is_macos", lambda: True)
    monkeypatch.setattr(updater, "_mac_arch_tag", lambda: "arm64")
    assets = [{"name": "elAPI_Plugins.dmg", "browser_download_url": "u/plain"}]

    assert updater._pick_asset(
        assets, (".dmg",), name_predicate=updater._asset_name_matches_mac_arch
    ) == (None, None)
