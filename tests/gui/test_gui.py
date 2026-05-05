from __future__ import annotations

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
