from __future__ import annotations

import json
import logging
import os
import pathlib
import platform
import re
import sys
from dataclasses import dataclass
from typing import Callable, Iterable, Mapping, Optional

import requests
from requests.exceptions import HTTPError

logger = logging.getLogger(__name__)

GITHUB_REPO = "sfb1638/elAPI_Plugins"
GITHUB_API_LATEST = (f"https://api.github.com/repos/"
                     f"{GITHUB_REPO}/releases/latest")
DEFAULT_TIMEOUT = 8


@dataclass(slots=True)
class UpdateInfo:
    current_version: str
    latest_version: str
    is_update_available: bool
    download_url: str | None
    asset_name: str | None
    html_url: str | None
    release_notes: str | None
    published_at: str | None
    etag: str | None

    def to_dict (self) -> dict[str, object]:
        return {
            "current_version": self.current_version,
            "latest_version": self.latest_version,
            "is_update_available": self.is_update_available,
            "download_url": self.download_url,
            "asset_name": self.asset_name,
            "html_url": self.html_url,
            "release_notes": self.release_notes,
            "published_at": self.published_at,
            "etag": self.etag,
            }


def _strip_prefix (v: str) -> str:
    return v.lstrip("vV").strip()


def _normalize_version_parts (v: str) -> tuple:
    v = _strip_prefix(v)
    parts: list[str] = re.split(r"[.+-]", v)
    norm: list[tuple[int | str, bool]] = []
    for part in parts:
        if part.isdigit():
            norm.append((int(part), True))
        else:
            norm.append((part.lower(), False))
    return tuple(norm)


def compare_versions (a: str, b: str) -> int:
    """
    Compare two version strings.
    Returns -1 if a < b, 0 if equal, 1 if a > b.
    """
    try:
        from packaging.version import Version

        va, vb = Version(_strip_prefix(a)), Version(_strip_prefix(b))
        if va < vb:
            return -1
        if va > vb:
            return 1
        return 0
    except Exception:
        na, nb = _normalize_version_parts(a), _normalize_version_parts(b)
        if na < nb:
            return -1
        if na > nb:
            return 1
        return 0


def _is_macos () -> bool:
    return platform.system() == "Darwin"


def _is_windows () -> bool:
    return platform.system() == "Windows"


def _is_linux () -> bool:
    return platform.system() == "Linux"


def _mac_arch_tag () -> str | None:
    """
    Returns 'arm64' for Apple Silicon, 'x86_64' for Intel, or None if not
    macOS.
    """
    if not _is_macos():
        return None
    m = platform.machine().lower()
    if m in ("arm64", "aarch64"):
        return "arm64"
    if m in ("x86_64", "amd64", "i386"):
        return "x86_64"
    return m or None


def _asset_name_matches_mac_arch (name: str) -> bool:
    """
    Heuristic: match common naming conventions in release assets.
    Adjust the keywords to match YOUR actual release filenames.
    """
    arch = _mac_arch_tag()
    if not arch:
        return True

    n = name.lower()

    if "universal" in n:
        return True

    if arch == "arm64":
        return any(
            k in n for k in ("arm64", "aarch64", "apple", "m1", "m2", "m3"))
    if arch == "x86_64":
        return any(k in n for k in ("x86_64", "amd64", "intel", "x64"))
    return True


def _pick_asset (
    assets: Iterable[Mapping[str, object]],
    preferred_exts: tuple[str, ...],
    *,
    name_predicate: Callable[[str], bool] | None = None,
    ) -> tuple[str | None, str | None]:
    for ext in preferred_exts:
        for asset in assets:
            name = str(asset.get("name", ""))
            if not name.lower().endswith(ext):
                continue
            if name_predicate and not name_predicate(name):
                continue
            return name, str(asset.get("browser_download_url") or "")

    for asset in assets:
        name = str(asset.get("name") or "")
        if name_predicate and name and not name_predicate(name):
            continue
        url = asset.get("browser_download_url")
        if url:
            return name, str(url)

    return None, None


def get_current_version (fallback: str = "0.0.0") -> str:
    """
    Attempt to read the app version from package metadata; fall back to
    pyproject.
    """
    try:
        from importlib.metadata import PackageNotFoundError, version

        return version("elapi-plugins")
    except Exception:
        pass

    pyproject = pathlib.Path(__file__).resolve().parents[2] / "pyproject.toml"
    if pyproject.is_file():
        try:
            import tomllib

            data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
            return str(data.get("project", {}).get("version") or fallback)
        except Exception:
            logger.debug("Could not read version from pyproject.toml",
                         exc_info=True)
    return fallback


def _auth_headers () -> dict[str, str]:
    headers: dict[str, str] = {
        "Accept": "application/vnd.github+json"
        }
    token = os.getenv("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def fetch_latest_release (
    etag: str | None = None,
    timeout: int = DEFAULT_TIMEOUT,
    session: Optional[requests.Session] = None,
    ) -> tuple[dict[str, object] | None, str | None]:
    """
    Fetch the latest release JSON from GitHub.
    Returns (payload, etag). If not modified (HTTP 304), payload is None.
    """
    sess = session or requests.Session()
    headers = _auth_headers()
    if etag:
        headers["If-None-Match"] = etag
    resp = sess.get(GITHUB_API_LATEST, headers=headers, timeout=timeout)
    if resp.status_code == 304:
        return None, etag
    try:
        resp.raise_for_status()
    except HTTPError as exc:
        if resp.status_code == 404:
            logger.warning("No releases found at %s", GITHUB_API_LATEST)
            return None, None
        raise
    return resp.json(), resp.headers.get("ETag")


def _default_preferred_exts () -> tuple[str, ...]:
    """Return preferred asset extensions for the current platform."""
    if _is_windows():
        return (".exe", ".zip")
    if _is_macos():
        return (".dmg", ".zip")
    # Linux / other: prefer source archives
    return (".tar.gz", ".zip")


def check_for_update (
    current_version: str | None = None,
    preferred_exts: tuple[str, ...] | None = None,
    etag: str | None = None,
    session: requests.Session | None = None,
    timeout: int = DEFAULT_TIMEOUT,
    ) -> UpdateInfo:
    """
    Compare the installed version to the latest GitHub Release.
    """
    if preferred_exts is None:
        preferred_exts = _default_preferred_exts()
    current = current_version or get_current_version()
    payload, new_etag = fetch_latest_release(etag=etag, timeout=timeout,
                                             session=session)
    if payload is None:
        return UpdateInfo(
            current_version=current,
            latest_version=current,
            is_update_available=False,
            download_url=None,
            asset_name=None,
            html_url=None,
            release_notes=None,
            published_at=None,
            etag=new_etag,
            )

    tag = str(payload.get("tag_name") or "").strip() or current
    assets = payload.get("assets") or []
    name_pred = _asset_name_matches_mac_arch if _is_macos() else None
    asset_name, asset_url = _pick_asset(assets, preferred_exts,
                                        name_predicate=name_pred)
    is_newer = compare_versions(current, tag) < 0

    return UpdateInfo(
        current_version=current,
        latest_version=tag,
        is_update_available=is_newer,
        download_url=asset_url or None,
        asset_name=asset_name,
        html_url=str(payload.get("html_url") or None),
        release_notes=str(payload.get("body") or None),
        published_at=str(payload.get("published_at") or None),
        etag=new_etag,
        )


def download_asset (
    url: str,
    dest: pathlib.Path | str,
    *,
    session: Optional[requests.Session] = None,
    timeout: int = DEFAULT_TIMEOUT,
    chunk_size: int = 1 << 16,
    ) -> pathlib.Path:
    """
    Stream-download a release asset to `dest`.
    """
    target = pathlib.Path(dest)
    target.parent.mkdir(parents=True, exist_ok=True)

    sess = session or requests.Session()
    with sess.get(url, stream=True, timeout=timeout,
                  headers=_auth_headers()) as resp:
        resp.raise_for_status()
        with target.open("wb") as fh:
            for chunk in resp.iter_content(chunk_size=chunk_size):
                if chunk:
                    fh.write(chunk)
    return target


def main (argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    current = args[0] if args else get_current_version()
    info = check_for_update(current_version=current)
    print(json.dumps(info.to_dict(), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
