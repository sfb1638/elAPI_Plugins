from __future__ import annotations

import csv
import io
import os
import threading
from pathlib import Path
from typing import Any

import pytest
from bs4 import BeautifulSoup

import gui.gui as gui
from tests.conftest import FakeEndpoint, FakeResponse, write_csv


@pytest.fixture(autouse=True)
def stub_elapi_config(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(gui, "_elapi_config_ok", lambda: True)


def test_index_get(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_get_fixed(name: str) -> FakeEndpoint:
        if name == "categories":
            return FakeEndpoint(
                get=lambda **kwargs: FakeResponse(
                    json_data={
                        "data": [
                            {"id": 1, "title": "Import Title"},
                            {"id": 1, "title": "Import Title"},
                            {"id": 3, "title": "Third Import"},
                            {"id": 2, "title": "Second Import"},
                            {"id": 4, "title": "Second Import"},
                        ]
                    }
                )
            )
        if name == "resources":
            return FakeEndpoint(
                get=lambda **kwargs: FakeResponse(
                    json_data={
                        "data": [
                            {"category": 1, "category_title": "Export Title"},
                            {"category": 1, "category_title": "Export Title"},
                            {"category": 3, "category_title": "Export Title"},
                            {"category": 2, "category_title": "Second Export"},
                            {"category": 4, "category_title": "Fourth Export"},
                        ]
                    }
                )
            )
        return FakeEndpoint(get=lambda **kwargs: FakeResponse(json_data={"data": []}))

    def fake_paged_fetch(get_page: Any, **kwargs: object) -> Any:
        return get_page(limit=kwargs["page_size"], offset=kwargs["start_offset"])

    monkeypatch.setattr(gui.endpoints, "get_fixed", fake_get_fixed)
    monkeypatch.setattr(gui, "paged_fetch", fake_paged_fetch)

    gui.app.testing = True
    client = gui.app.test_client()
    resp = client.get("/")
    assert resp.status_code == 200
    soup = BeautifulSoup(resp.get_data(as_text=True), "html.parser")
    export_options = soup.select("#category option")
    import_options = soup.select("#imp_category option")
    assert [option.get_text(strip=True) for option in export_options] == [
        "Export Title",
        "Export Title",
        "Fourth Export",
        "Second Export",
    ]
    assert [option.get_text(strip=True) for option in import_options] == [
        "Import Title",
        "Second Import",
        "Second Import",
        "Third Import",
    ]


def test_export_resources(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    def fake_get(**kwargs: object) -> FakeResponse:
        return FakeResponse(json_data={"data": []})

    def fake_paged_fetch(get_page: Any, **kwargs: object) -> list[Any]:
        return []

    monkeypatch.setattr(
        gui.endpoints, "get_fixed", lambda name: FakeEndpoint(get=fake_get)
    )
    monkeypatch.setattr(gui, "paged_fetch", fake_paged_fetch)

    class DummyExporter:
        def xlsx_export(self, filename: str | None = None) -> Path:
            out = tmp_path / "res.xlsx"
            out.write_text("x", encoding="utf-8")
            return out

    monkeypatch.setattr(
        gui.ExporterFactory,
        "get_exporter",
        lambda *args, **kwargs: DummyExporter(),
    )

    gui.app.testing = True
    client = gui.app.test_client()
    resp = client.post("/", data={"export_type": "resources", "category": "1"})
    assert resp.status_code == 200


def test_export_experiments(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    def fake_get(**kwargs: object) -> FakeResponse:
        return FakeResponse(json_data={"data": []})

    monkeypatch.setattr(
        gui.endpoints, "get_fixed", lambda name: FakeEndpoint(get=fake_get)
    )

    class DummyExporter:
        def xlsx_export(self, filename: str | None = None) -> Path:
            out = tmp_path / "exp.xlsx"
            out.write_text("x", encoding="utf-8")
            return out

    monkeypatch.setattr(
        gui.ExporterFactory,
        "get_exporter",
        lambda *args, **kwargs: DummyExporter(),
    )

    gui.app.testing = True
    client = gui.app.test_client()
    resp = client.post("/", data={"export_type": "experiments"})
    assert resp.status_code == 200


def test_download_resource_template_omits_category_and_template_columns(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_get_fixed(name: str) -> FakeEndpoint:
        if name == "categories":

            def get_category(**kwargs: object) -> FakeResponse:
                if kwargs.get("endpoint_id") == 1:
                    return FakeResponse(
                        json_data={
                            "id": 1,
                            "metadata": (
                                '{"extra_fields": {"strain": {}, "plasmid": {}}}'
                            ),
                        }
                    )
                return FakeResponse(json_data={"data": [{"id": 1, "title": "Cells"}]})

            return FakeEndpoint(get=get_category)

        if name == "resources":
            return FakeEndpoint(
                get=lambda **kwargs: FakeResponse(
                    json_data={"data": [{"category": 1, "category_title": "Cells"}]}
                )
            )

        return FakeEndpoint(get=lambda **kwargs: FakeResponse(json_data={"data": []}))

    monkeypatch.setattr(gui.endpoints, "get_fixed", fake_get_fixed)
    monkeypatch.setattr(
        gui,
        "paged_fetch",
        lambda get_page, **kwargs: get_page(
            limit=kwargs["page_size"], offset=kwargs["start_offset"]
        ),
    )

    gui.app.testing = True
    client = gui.app.test_client()
    resp = client.post("/", data={"export_type": "template_resources", "category": "1"})

    assert resp.status_code == 200
    raw_csv = resp.get_data(as_text=True)
    assert raw_csv.startswith("title;tags;body;")
    rows = list(csv.reader(io.StringIO(raw_csv), delimiter=";"))
    assert rows[0] == ["title", "tags", "body", "strain", "plasmid"]
    assert "category" not in rows[0]
    assert "template" not in rows[0]
    assert "main text" not in rows[0]


def test_download_experiment_template_uses_body_column(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_get_fixed(name: str) -> FakeEndpoint:
        if name == "categories":
            return FakeEndpoint(
                get=lambda **kwargs: FakeResponse(
                    json_data={"data": [{"id": 1, "title": "Cells"}]}
                )
            )

        if name == "resources":
            return FakeEndpoint(
                get=lambda **kwargs: FakeResponse(
                    json_data={"data": [{"category": 1, "category_title": "Cells"}]}
                )
            )

        if name == "experiments_templates":

            def get_template(**kwargs: object) -> FakeResponse:
                if kwargs.get("endpoint_id") == 7:
                    return FakeResponse(
                        json_data={
                            "id": 7,
                            "metadata": '{"extra_fields": {"temperature": {}}}',
                        }
                    )
                return FakeResponse(json_data={"data": [{"id": 7, "title": "Assay"}]})

            return FakeEndpoint(get=get_template)

        return FakeEndpoint(get=lambda **kwargs: FakeResponse(json_data={"data": []}))

    monkeypatch.setattr(gui.endpoints, "get_fixed", fake_get_fixed)
    monkeypatch.setattr(
        gui,
        "paged_fetch",
        lambda get_page, **kwargs: get_page(
            limit=kwargs["page_size"], offset=kwargs["start_offset"]
        ),
    )

    gui.app.testing = True
    client = gui.app.test_client()
    resp = client.post(
        "/", data={"export_type": "template_experiments", "exp_template_id": "7"}
    )

    assert resp.status_code == 200
    raw_csv = resp.get_data(as_text=True)
    assert raw_csv.startswith("title;tags;date;status;body;")
    rows = list(csv.reader(io.StringIO(raw_csv), delimiter=";"))
    assert rows[0] == ["title", "tags", "date", "status", "body", "temperature"]
    assert "main text" not in rows[0]


def test_import_resources_from_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def fake_get(**kwargs: object) -> FakeResponse:
        return FakeResponse(json_data={"data": []})

    def fake_paged_fetch(get_page: Any, **kwargs: object) -> list[Any]:
        return []

    monkeypatch.setattr(
        gui.endpoints, "get_fixed", lambda name: FakeEndpoint(get=fake_get)
    )
    monkeypatch.setattr(gui, "paged_fetch", fake_paged_fetch)

    class DummyImporter:
        def create_all_from_csv(self) -> list[str]:
            return ["1", "2"]

    monkeypatch.setattr(
        gui.ImporterFactory,
        "get_importer",
        lambda *args, **kwargs: DummyImporter(),
    )

    csv_path = write_csv(tmp_path / "imp.csv", ["title"], [["t"]])

    gui.app.testing = True
    client = gui.app.test_client()
    resp = client.post(
        "/",
        data={
            "export_type": "imports",
            "category": "1",
            "import_path": str(csv_path),
            "import_target": "resources",
        },
    )
    assert resp.status_code == 302


def test_import_unknown_target(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    def fake_get(**kwargs: object) -> FakeResponse:
        return FakeResponse(json_data={"data": []})

    def fake_paged_fetch(get_page: Any, **kwargs: object) -> list[Any]:
        return []

    monkeypatch.setattr(
        gui.endpoints, "get_fixed", lambda name: FakeEndpoint(get=fake_get)
    )
    monkeypatch.setattr(gui, "paged_fetch", fake_paged_fetch)

    gui.app.testing = True
    client = gui.app.test_client()
    resp = client.post(
        "/",
        data={
            "export_type": "imports",
            "category": "1",
            "import_path": str(tmp_path / "missing.csv"),
            "import_target": "unknown",
        },
    )
    assert resp.status_code == 302


def test_import_missing_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    def fake_get(**kwargs: object) -> FakeResponse:
        return FakeResponse(json_data={"data": []})

    def fake_paged_fetch(get_page: Any, **kwargs: object) -> list[Any]:
        return []

    monkeypatch.setattr(
        gui.endpoints, "get_fixed", lambda name: FakeEndpoint(get=fake_get)
    )
    monkeypatch.setattr(gui, "paged_fetch", fake_paged_fetch)

    gui.app.testing = True
    client = gui.app.test_client()
    resp = client.post(
        "/",
        data={
            "export_type": "imports",
            "category": "1",
            "import_path": str(tmp_path / "missing.csv"),
            "import_target": "resources",
        },
    )
    assert resp.status_code == 302


def test_import_uploads_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    def fake_get(**kwargs: object) -> FakeResponse:
        return FakeResponse(json_data={"data": []})

    monkeypatch.setattr(
        gui.endpoints, "get_fixed", lambda name: FakeEndpoint(get=fake_get)
    )
    monkeypatch.setattr(gui, "paged_fetch", lambda *args, **kwargs: [])

    class DummyImporter:
        def create_all_from_csv(self) -> list[str]:
            return ["1"]

    monkeypatch.setattr(
        gui.ImporterFactory,
        "get_importer",
        lambda *args, **kwargs: DummyImporter(),
    )

    gui.app.testing = True
    gui.app.config["UPLOAD_FOLDER"] = tmp_path
    client = gui.app.test_client()

    data = {
        "export_type": "imports",
        "category": "1",
        "import_target": "resources",
        "import_path": "",
        "import_file": (io.BytesIO(b"title\nx"), "upload.csv"),
    }
    resp = client.post("/", data=data, content_type="multipart/form-data")
    assert resp.status_code == 302
    # The upload is a temporary copy: it is removed once the import is done.
    assert list(tmp_path.iterdir()) == []


def test_shutdown(monkeypatch: pytest.MonkeyPatch) -> None:
    class DummyServer:
        def __init__(self) -> None:
            self.stopped = False

        def shutdown(self) -> None:
            self.stopped = True

    dummy = DummyServer()
    monkeypatch.setattr(gui, "server", dummy)

    gui.app.testing = True
    client = gui.app.test_client()
    resp = client.post("/shutdown")
    assert resp.status_code == 200


def _skipped(n: int) -> list[Any]:
    from src.services.importers.base_importer import SkippedRow

    return [
        SkippedRow(i, (f"Experiment {i}00 does not exist",)) for i in range(1, n + 1)
    ]


def test_format_skipped_rows_lists_rows_and_reasons() -> None:
    text = gui._format_skipped_rows(_skipped(1))
    assert text == "Skipped 1 row:\nRow 1: Experiment 100 does not exist"


def test_format_skipped_rows_caps_the_list() -> None:
    text = gui._format_skipped_rows(_skipped(13))
    lines = text.splitlines()
    assert lines[0] == "Skipped 13 rows:"
    assert len(lines) == 1 + gui.MAX_SKIPPED_ROWS_SHOWN + 1
    assert lines[-1] == "...and 3 more."


def test_import_flashes_warning_for_skipped_rows(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        gui.endpoints,
        "get_fixed",
        lambda name: FakeEndpoint(get=lambda **kw: FakeResponse(json_data={"data": []})),
    )
    monkeypatch.setattr(gui, "paged_fetch", lambda *args, **kwargs: [])

    class DummyImporter:
        skipped_rows = _skipped(2)

        def create_all_from_csv(self) -> list[str]:
            return ["1"]

    monkeypatch.setattr(
        gui.ImporterFactory, "get_importer", lambda *a, **kw: DummyImporter()
    )
    csv_path = write_csv(tmp_path / "imp.csv", ["title"], [["t"]])

    gui.app.testing = True
    client = gui.app.test_client()
    client.post(
        "/",
        data={
            "export_type": "imports",
            "category": "1",
            "import_path": str(csv_path),
            "import_target": "experiments",
        },
    )

    with client.session_transaction() as sess:
        flashes = dict((cat, msg) for cat, msg in sess["_flashes"])
    assert flashes["success"].startswith("Imported 1 experiments")
    warning = flashes["warning"]
    assert warning["text"].startswith("Skipped 2 rows:")
    assert "Row 2: Experiment 200 does not exist" in warning["text"]
    assert warning["link"] == "/logs/skipped-rows"


def test_cross_site_post_is_rejected() -> None:
    gui.app.testing = True
    client = gui.app.test_client()

    resp = client.post("/shutdown", headers={"Origin": "https://evil.example"})
    assert resp.status_code == 403
    resp = client.post("/shutdown", headers={"Sec-Fetch-Site": "cross-site"})
    assert resp.status_code == 403


def test_foreign_host_header_is_rejected() -> None:
    gui.app.testing = True
    resp = gui.app.test_client().get("/", headers={"Host": "evil.example:1991"})
    assert resp.status_code == 403


def test_same_origin_post_is_allowed() -> None:
    gui.app.testing = True
    resp = gui.app.test_client().post(
        "/shutdown", headers={"Origin": "http://127.0.0.1:1991"}
    )
    assert resp.status_code == 200


def test_shutdown_is_delayed_and_cancelled_by_next_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class DummyServer:
        stopped = False

        def shutdown(self) -> None:
            self.stopped = True

    dummy = DummyServer()
    monkeypatch.setattr(gui, "server", dummy)
    monkeypatch.setattr(gui, "SHUTDOWN_DELAY_SECONDS", 0.2)
    gui.app.testing = True
    client = gui.app.test_client()

    client.post("/shutdown")  # page unloading ...
    client.get("/setup")  # ... and the reloaded page arriving
    import time

    time.sleep(0.4)
    assert dummy.stopped is False

    client.post("/shutdown")  # real close: nothing follows
    time.sleep(0.4)
    assert dummy.stopped is True


def _capture_import_kwargs(
    monkeypatch: pytest.MonkeyPatch,
) -> dict[str, Any]:
    captured: dict[str, Any] = {}

    monkeypatch.setattr(
        gui.endpoints,
        "get_fixed",
        lambda name: FakeEndpoint(get=lambda **kw: FakeResponse(json_data={"data": []})),
    )
    monkeypatch.setattr(gui, "paged_fetch", lambda get_page, **kw: [])

    class DummyImporter:
        def create_all_from_csv(self) -> list[str]:
            return []

    def fake_get_importer(*args: Any, **kwargs: Any) -> DummyImporter:
        captured.update(kwargs)
        return DummyImporter()

    monkeypatch.setattr(gui.ImporterFactory, "get_importer", fake_get_importer)
    return captured


def test_import_by_path_resolves_attachments_next_to_the_csv(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    captured = _capture_import_kwargs(monkeypatch)
    csv_path = write_csv(tmp_path / "imp.csv", ["title"], [["t"]])

    gui.app.testing = True
    gui.app.test_client().post(
        "/",
        data={"export_type": "imports", "import_path": str(csv_path)},
    )

    assert captured["files_base_dir"] == str(tmp_path)


def test_import_uses_attachments_folder_from_the_form(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    captured = _capture_import_kwargs(monkeypatch)
    csv_path = write_csv(tmp_path / "imp.csv", ["title"], [["t"]])
    files = tmp_path / "files"
    files.mkdir()

    gui.app.testing = True
    gui.app.test_client().post(
        "/",
        data={
            "export_type": "imports",
            "import_path": str(csv_path),
            "files_base_dir": str(files),
        },
    )

    assert captured["files_base_dir"] == str(files)


def test_import_rejects_missing_attachments_folder(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    captured = _capture_import_kwargs(monkeypatch)
    csv_path = write_csv(tmp_path / "imp.csv", ["title"], [["t"]])

    gui.app.testing = True
    resp = gui.app.test_client().post(
        "/",
        data={
            "export_type": "imports",
            "import_path": str(csv_path),
            "files_base_dir": str(tmp_path / "nope"),
        },
    )

    assert resp.status_code == 302
    assert captured == {}  # the importer was never created


@pytest.mark.skipif(os.name == "nt", reason="POSIX permission bits")
@pytest.mark.parametrize("preexisting", [False, True])
def test_setup_writes_token_file_owner_only(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, preexisting: bool
) -> None:
    config = tmp_path / "cfg" / "elapi.yml"
    config.parent.mkdir()
    if preexisting:
        config.write_text("host: old\napi_token: old\n")
        config.chmod(0o644)
    monkeypatch.setattr(gui, "ELAPI_CONFIG_PATH", str(config))
    monkeypatch.setenv("ELAPI_HOST", "")
    monkeypatch.setenv("ELAPI_API_TOKEN", "")

    gui.app.testing = True
    resp = gui.app.test_client().post(
        "/setup",
        data={"host": "https://example.org", "api_token": "secret-token"},
    )

    assert resp.status_code == 302
    assert "secret-token" in config.read_text()
    assert (config.stat().st_mode & 0o777) == 0o600


def test_uploads_get_unique_names_and_are_removed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    seen: list[str] = []
    monkeypatch.setattr(
        gui.endpoints,
        "get_fixed",
        lambda name: FakeEndpoint(get=lambda **kw: FakeResponse(json_data={"data": []})),
    )
    monkeypatch.setattr(gui, "paged_fetch", lambda *args, **kwargs: [])

    class DummyImporter:
        def create_all_from_csv(self) -> list[str]:
            return []

    def fake_get_importer(*args: Any, **kwargs: Any) -> DummyImporter:
        assert Path(kwargs["csv_path"]).exists()  # still there while importing
        seen.append(kwargs["csv_path"])
        return DummyImporter()

    monkeypatch.setattr(gui.ImporterFactory, "get_importer", fake_get_importer)
    gui.app.testing = True
    gui.app.config["UPLOAD_FOLDER"] = tmp_path
    client = gui.app.test_client()

    for _ in range(2):
        client.post(
            "/",
            data={
                "export_type": "imports",
                "import_file": (io.BytesIO(b"title\nx"), "data.csv"),
            },
            content_type="multipart/form-data",
        )

    assert len(set(seen)) == 2  # same upload name, different temp files
    assert list(tmp_path.iterdir()) == []


def test_exported_file_is_deleted_after_download(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        gui.endpoints,
        "get_fixed",
        lambda name: FakeEndpoint(get=lambda **kw: FakeResponse(json_data={"data": []})),
    )
    monkeypatch.setattr(gui, "paged_fetch", lambda *args, **kwargs: [])
    out = tmp_path / "exp.xlsx"

    class DummyExporter:
        def xlsx_export(self, filename: str | None = None) -> Path:
            out.write_bytes(b"xlsx-bytes")
            return out

    monkeypatch.setattr(
        gui.ExporterFactory, "get_exporter", lambda *a, **k: DummyExporter()
    )
    gui.app.testing = True

    resp = gui.app.test_client().post("/", data={"export_type": "experiments"})

    assert resp.status_code == 200
    assert resp.data == b"xlsx-bytes"
    assert "exp.xlsx" in resp.headers["Content-Disposition"]
    assert not out.exists()


def test_log_level_defaults_to_debug_and_honours_the_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("LOG_LEVEL", raising=False)
    assert gui._resolve_log_level() == "DEBUG"

    monkeypatch.setenv("LOG_LEVEL", "  warning ")
    assert gui._resolve_log_level() == "warning"

    monkeypatch.setenv("LOG_LEVEL", "   ")
    assert gui._resolve_log_level() == "DEBUG"


def test_ping_identifies_the_app() -> None:
    gui.app.testing = True

    data = gui.app.test_client().get("/ping").get_json()

    assert data["app"] == "elAPI_Plugins"
    assert data["version"]


def test_quit_stops_the_server_at_once(monkeypatch: pytest.MonkeyPatch) -> None:
    stopped = threading.Event()

    class DummyServer:
        def shutdown(self) -> None:
            stopped.set()

    monkeypatch.setattr(gui, "server", DummyServer())
    gui.app.testing = True

    resp = gui.app.test_client().post("/quit")

    assert resp.status_code == 200
    assert stopped.wait(timeout=2)  # no delay, unlike /shutdown


def test_quit_is_refused_for_cross_site_requests() -> None:
    gui.app.testing = True

    resp = gui.app.test_client().post(
        "/quit", headers={"Origin": "https://evil.example"}
    )

    assert resp.status_code == 403


def test_skipped_log_page_shows_the_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    log = tmp_path / "skipped_rows.log"
    log.write_text("=== import ===\nRow 3: Müller is not valid\n", encoding="utf-8")
    monkeypatch.setattr(gui, "skipped_log_path", lambda: log)
    gui.app.testing = True

    resp = gui.app.test_client().get("/logs/skipped-rows")

    assert resp.status_code == 200
    assert resp.mimetype == "text/plain"
    assert "charset=utf-8" in resp.headers["Content-Type"]
    assert "Row 3: Müller is not valid" in resp.get_data(as_text=True)


def test_skipped_log_page_without_a_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(gui, "skipped_log_path", lambda: tmp_path / "missing.log")
    gui.app.testing = True

    resp = gui.app.test_client().get("/logs/skipped-rows")

    assert resp.status_code == 200
    assert "No rows have been skipped yet" in resp.get_data(as_text=True)


def test_warning_shows_a_link_to_the_log_and_escapes_the_text(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The link is rendered as a link; CSV text inside the message is not."""
    from src.services.importers.base_importer import SkippedRow

    monkeypatch.setattr(
        gui.endpoints,
        "get_fixed",
        lambda name: FakeEndpoint(get=lambda **kw: FakeResponse(json_data={"data": []})),
    )
    monkeypatch.setattr(gui, "paged_fetch", lambda *args, **kwargs: [])

    class DummyImporter:
        skipped_rows = [SkippedRow(1, ("'<script>alert(1)</script>' is not valid",))]
        log_context = ""

        def create_all_from_csv(self) -> list[str]:
            return []

    monkeypatch.setattr(
        gui.ImporterFactory, "get_importer", lambda *a, **kw: DummyImporter()
    )
    csv_path = write_csv(tmp_path / "imp.csv", ["title"], [["t"]])
    gui.app.testing = True

    resp = gui.app.test_client().post(
        "/",
        data={
            "export_type": "imports",
            "category": "1",
            "import_path": str(csv_path),
            "import_target": "experiments",
        },
        follow_redirects=True,
    )

    html = resp.get_data(as_text=True)
    assert 'href="/logs/skipped-rows"' in html
    assert "Open the full log of skipped rows" in html
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html


def test_import_names_itself_in_the_skipped_log_header(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        gui.endpoints,
        "get_fixed",
        lambda name: FakeEndpoint(get=lambda **kw: FakeResponse(json_data={"data": []})),
    )
    monkeypatch.setattr(gui, "paged_fetch", lambda *args, **kwargs: [])
    seen: dict[str, str] = {}

    class DummyImporter:
        skipped_rows: list[Any] = []

        def create_all_from_csv(self) -> list[str]:
            return []

    importer = DummyImporter()
    monkeypatch.setattr(gui.ImporterFactory, "get_importer", lambda *a, **kw: importer)
    csv_path = write_csv(tmp_path / "samples.csv", ["title"], [["t"]])
    gui.app.testing = True

    gui.app.test_client().post(
        "/",
        data={
            "export_type": "imports",
            "category": "1",
            "import_path": str(csv_path),
            "import_target": "resources",
            "update_existing": "yes",
        },
    )

    seen["context"] = importer.log_context  # type: ignore[attr-defined]
    assert "resources import of" in seen["context"]
    assert "samples.csv" in seen["context"]
    assert "update mode" in seen["context"]
