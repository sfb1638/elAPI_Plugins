from __future__ import annotations

import csv
import io
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
                            "metadata": '{"extra_fields": {"strain": {}, "plasmid": {}}}',
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
    saved = tmp_path / "upload.csv"
    assert saved.exists()


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
    assert text == (
        "Skipped 1 row with invalid values:\nRow 1: Experiment 100 does not exist"
    )


def test_format_skipped_rows_caps_the_list() -> None:
    text = gui._format_skipped_rows(_skipped(13))
    lines = text.splitlines()
    assert lines[0] == "Skipped 13 rows with invalid values:"
    assert len(lines) == 1 + gui.MAX_SKIPPED_ROWS_SHOWN + 1
    assert lines[-1] == "...and 3 more (see app.log)."


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
    assert flashes["warning"].startswith("Skipped 2 rows with invalid values:")
    assert "Row 2: Experiment 200 does not exist" in flashes["warning"]


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
