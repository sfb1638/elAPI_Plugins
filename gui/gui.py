import logging
import os
import sys
import tempfile
import threading
import time
import webbrowser
from pathlib import Path

import yaml
from flask import Flask, flash, redirect, render_template, request, send_file, url_for
from werkzeug.serving import make_server
from werkzeug.utils import secure_filename
from werkzeug.wrappers.response import Response as WerkzeugResponse

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _bootstrap_sys_path() -> None:
    root = str(PROJECT_ROOT)
    if root not in sys.path:
        sys.path.insert(0, root)

    if os.name == "nt":
        return

    windows_build_site_packages = "/.build/Lib/site-packages"
    sys.path[:] = [
        entry
        for entry in sys.path
        if not entry.replace("\\", "/").rstrip("/").endswith(windows_build_site_packages)
    ]


_bootstrap_sys_path()

from src.factories import ExporterFactory, ImporterFactory
from src.updater.updater import check_for_update
from src.utils import endpoints
from src.utils.common import paged_fetch
from src.utils.logging_config import setup_logging

LOG_LEVEL = "DEBUG"
setup_logging(level=LOG_LEVEL, force=True)
logger = logging.getLogger(__name__)

ELAPI_CONFIG_PATH = os.path.join(
    os.environ.get("XDG_CONFIG_HOME", os.path.join(os.path.expanduser("~"), ".config")),
    "elapi.yml",
)

if getattr(sys, "frozen", False):
    os.environ["PATH"] = os.pathsep.join(
        [
            os.environ.get("PATH", ""),
            "/usr/local/bin",
            "/opt/homebrew/bin",
        ]
    )
    try:
        os.chdir(os.path.expanduser("~"))
    except Exception:
        pass


def resource_path(rel_path: str) -> str:
    """Return path to a bundled resource (handles PyInstaller _MEIPASS)."""
    base_path = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base_path, rel_path)


def _elapi_config_ok() -> bool:
    """Check whether elapi config file has host and api_token set."""
    try:
        with open(ELAPI_CONFIG_PATH, "r") as fh:
            cfg = yaml.safe_load(fh)
        if not isinstance(cfg, dict):
            return False
        return bool(cfg.get("host")) and bool(cfg.get("api_token"))
    except Exception:
        return False


def _read_elapi_config() -> dict:
    """Return current host/api_token values from the config file."""
    try:
        with open(ELAPI_CONFIG_PATH, "r") as fh:
            cfg = yaml.safe_load(fh)
        if isinstance(cfg, dict):
            return {"host": cfg.get("host", ""), "api_token": cfg.get("api_token", "")}
    except Exception:
        pass
    return {"host": "", "api_token": ""}

app = Flask(
    __name__,
    template_folder=resource_path("templates"),
    static_folder=resource_path("static"),
)
app.secret_key = os.urandom(24)

APP_NAME = "elAPI_Plugins"
UPLOAD_DIR = os.path.join(tempfile.gettempdir(), APP_NAME, "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)
app.config["UPLOAD_FOLDER"] = UPLOAD_DIR

server = None


@app.route("/setup", methods=["GET", "POST"])
def setup() -> str | WerkzeugResponse:
    if request.method == "POST":
        DEFAULT_HOST = "https://elabftw.uni-heidelberg.de/api/v2"
        host = (request.form.get("host") or "").strip() or DEFAULT_HOST
        api_token = (request.form.get("api_token") or "").strip()

        if not api_token:
            flash("API token is required.", "error")
            return render_template("setup.html", host=host, api_token=api_token)

        # Normalise host: ensure it ends with /api/v2
        host = host.rstrip("/")
        if not host.endswith("/api/v2"):
            if host.endswith("/api"):
                host += "/v2"
            else:
                host += "/api/v2"

        # Read existing config to preserve extra fields, or use defaults
        existing: dict = {}
        try:
            with open(ELAPI_CONFIG_PATH, "r") as fh:
                loaded = yaml.safe_load(fh)
            if isinstance(loaded, dict):
                existing = loaded
        except Exception:
            pass

        if not existing:
            existing = {
                "host": "",
                "api_token": "",
                "export_dir": os.path.join(os.path.expanduser("~"), "Downloads"),
                "elab_version_mode": "warn",
                "unsafe_api_token_warning": True,
                "enable_http2": False,
                "verify_ssl": True,
                "timeout": 90,
                "async_rate_limit": None,
                "async_capacity": None,
                "development_mode": False,
            }

        existing["host"] = host
        existing["api_token"] = api_token

        os.makedirs(os.path.dirname(ELAPI_CONFIG_PATH), exist_ok=True)
        with open(ELAPI_CONFIG_PATH, "w") as fh:
            yaml.safe_dump(existing, fh, default_flow_style=False, sort_keys=False)

        # Set env vars so Dynaconf picks them up immediately
        os.environ["ELAPI_HOST"] = host
        os.environ["ELAPI_API_TOKEN"] = api_token

        # Update elapi's in-memory singleton so the new values are used immediately
        # without requiring a restart. MinimalActiveConfiguration is a singleton whose
        # _container dict is populated at import time; we must patch it directly.
        try:
            from elapi.configuration._config_history import (
                AppliedConfigIdentity,
                MinimalActiveConfiguration,
            )
            from elapi.configuration.config import KEY_API_TOKEN, KEY_HOST, APIToken

            MinimalActiveConfiguration()[KEY_HOST] = AppliedConfigIdentity(
                host, "setup_page"
            )
            try:
                token_obj = APIToken(api_token)
            except Exception:
                token_obj = api_token
            MinimalActiveConfiguration()[KEY_API_TOKEN] = AppliedConfigIdentity(
                token_obj, "setup_page"
            )
        except Exception as e:
            logger.warning("Could not update elapi in-memory config: %s", e)

        flash("Configuration saved successfully.", "success")
        return redirect(url_for("index"))

    # GET
    cfg = _read_elapi_config()
    return render_template("setup.html", host=cfg["host"], api_token=cfg["api_token"])


@app.route("/", methods=["GET", "POST"])
def index() -> str | WerkzeugResponse:
    if not _elapi_config_ok():
        return redirect(url_for("setup"))

    try:
        update_info = check_for_update(timeout=5)
    except Exception as exc:
        logger.info("Update check skipped: %s", exc)
        update_info = None

    try:
        endpoint = endpoints.get_fixed("categories")

        def get_page(limit: int, offset: int) -> list[dict]:
            response = endpoint.get(query={"limit": limit, "offset": offset})
            response.raise_for_status()
            data = response.json()
            page = data["data"] if isinstance(data, dict) and "data" in data else data
            return list(page)

        categories = list(
            paged_fetch(
                get_page,
                start_offset=0,
                page_size=30,
                max_retries=3,
                on_progress=lambda n, off, lim: logger.info(
                    "Fetched %d categories (offset=%d, limit=%d)", n, off, lim
                ),
            )
        )
        categories = sorted(categories, key=lambda c: c.get("title", "").lower())
    except (SystemExit, Exception) as exc:
        logger.error("Failed to load categories: %s", exc)
        flash("eLabFTW connection failed. Please check your configuration.", "error")
        return redirect(url_for("setup"))

    if request.method == "POST":
        action = (request.form.get("export_type") or "").strip().lower()

        if action == "resources":
            cid = int(request.form["category"])
            fname = request.form.get("filename") or None
            exporter = ExporterFactory.get_exporter("resources", cid)
            path = exporter.xlsx_export(fname)
            return send_file(path, as_attachment=True)  # type: ignore[arg-type]

        if action == "experiments":
            fname = request.form.get("exp_filename") or None
            exporter = ExporterFactory.get_exporter("experiments")
            path = exporter.xlsx_export(fname)
            return send_file(path, as_attachment=True)  # type: ignore[arg-type]

        if action == "imports":
            update_existing = (request.form.get("update_existing") or "no").strip().lower() == "yes"

            # When update-existing is enabled the category dropdown is disabled in the UI
            # and the request may not include a category. Treat it as optional here.
            cid_raw = request.form.get("category")
            cid = int(cid_raw) if cid_raw else None
            logger.info("Update existing requested? %s", update_existing)

            # (Optional) support "path import" in future
            import_path = (request.form.get("import_path") or "").strip()
            import_target = (request.form.get("import_target") or "resources").strip().lower()
            logger.info("Import target: %s", import_target)

            # Decide source path
            if import_path:
                source = os.path.abspath(import_path)
                if not os.path.isfile(source):
                    flash(f"No file found at {source}", "error")
                    return redirect(url_for("index"))
            else:
                uploaded = request.files.get("import_file")
                if not uploaded or not uploaded.filename:
                    flash("No file selected and no path provided", "error")
                    return redirect(url_for("index"))

                filename = secure_filename(uploaded.filename)
                source = os.path.join(app.config["UPLOAD_FOLDER"], filename)
                uploaded.save(source)

            try:
                if import_target == "resources":
                    importer = ImporterFactory.get_importer(
                        "resources",
                        csv_path=source,
                        template_id=cid,
                        category_id=cid,
                        update_existing=update_existing,
                    )
                    ids = importer.create_all_from_csv()
                    count = len(ids)
                elif import_target == "experiments":
                    importer = ImporterFactory.get_importer(
                        "experiments",
                        csv_path=source,
                        update_existing=update_existing,
                    )
                    ids = importer.create_all_from_csv()
                    count = len(ids)
                else:
                    flash(f"Unknown import target: {import_target}", "error")
                    return redirect(url_for("index"))

                if update_existing:
                    skipped = getattr(importer, "skipped_count", 0)
                    flash(
                        f"Updated {count} existing {import_target} from {source}"
                        + (f"; skipped {skipped} invalid IDs" if skipped else ""),
                        "success",
                    )
                else:
                    flash(f"Imported {count} {import_target} from {source}", "success")

            except Exception as e:
                flash(f"Import failed: {e}", "error")

            return redirect(url_for("index"))

    return render_template("index.html", categories=categories, update_info=update_info)


@app.route("/shutdown", methods=["POST"])
def shutdown() -> tuple[str, int]:
    global server
    if server:
        threading.Thread(target=server.shutdown).start()
    return "Shutting down", 200


def _open_browser() -> None:
    time.sleep(1)
    webbrowser.open("http://127.0.0.1:1991")


if __name__ == "__main__":
    server = make_server("127.0.0.1", 1991, app)
    threading.Thread(target=_open_browser, daemon=True).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()
