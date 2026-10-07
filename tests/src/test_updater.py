from __future__ import annotations

import responses

from src.updater.updater import GITHUB_API_LATEST, check_for_update, compare_versions


def test_compare_versions_simple() -> None:
    assert compare_versions("0.1.0", "0.1.0") == 0
    assert compare_versions("0.1.0", "0.2.0") < 0
    assert compare_versions("v1.0.0", "0.9.9") > 0


@responses.activate
def test_check_for_update_with_github_latest() -> None:
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
