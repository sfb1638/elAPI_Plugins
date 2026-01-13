import logging
import os
import sys
import tempfile
import threading
import time
import webbrowser

from flask import Flask, flash, redirect, render_template, request, send_file, url_for
from werkzeug.serving import make_server
from werkzeug.utils import secure_filename
from werkzeug.wrappers.response import Response as WerkzeugResponse

from src.factories import ExporterFactory, ImporterFactory
from src.updater.updater import check_for_update
from src.utils import endpoints
from src.utils.common import paged_fetch
from src.utils.logging_config import setup_logging

LOG_LEVEL = "DEBUG"
setup_logging(level=LOG_LEVEL, force=True)
logger = logging.getLogger(__name__)

# Extend PATH for Finder-launched app so external tools can be found
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


# Ensure local modules can be imported
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

# Configure Flask to look up templates and static files in the bundled locations
app = Flask(
    __name__,
    template_folder=resource_path("templates"),
    static_folder=resource_path("static"),
)
app.secret_key = os.urandom(24)

# Use a writable directory for uploads (outside the application bundle)
APP_NAME = "elAPI_Plugins"
UPLOAD_DIR = os.path.join(tempfile.gettempdir(), APP_NAME, "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)
app.config["UPLOAD_FOLDER"] = UPLOAD_DIR

server = None


@app.route("/", methods=["GET", "POST"])
def index() -> str | WerkzeugResponse:
    try:
        update_info = check_for_update(timeout=5)
    except Exception as exc:
        logger.info("Update check skipped: %s", exc)
        update_info = None

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

    if request.method == "POST":
        action = request.form.get("export_type")
        if action == "resources":
            cid = int(request.form["category"])
            fname = request.form.get("filename") or None
            exporter = ExporterFactory.get_exporter("resources", cid)
            path = exporter.xlsx_export(fname)
            return send_file(path, as_attachment=True)  # type: ignore[arg-type]

        elif action == "experiments":
            fname = request.form.get("exp_filename") or None
            exporter = ExporterFactory.get_exporter("experiments")
            path = exporter.xlsx_export(fname)
            return send_file(path, as_attachment=True)  # type: ignore[arg-type]

        elif action == "imports":
            cid = int(request.form["category"])
            import_path = request.form.get("import_path", "").strip()
            import_target = (
                (request.form.get("import_target") or "resources").strip().lower()
            )

            if import_path:
                full_path = os.path.abspath(import_path)
                if not os.path.isfile(full_path):
                    flash(f"No file found at {full_path}", "error")
                    return redirect(url_for("index"))
                source = full_path
            else:
                uploaded = request.files.get("import_file")
                if not uploaded or not uploaded.filename:
                    flash("No file selected and no path provided", "error")
                    return redirect(url_for("index"))
                filename = secure_filename(uploaded.filename)
                full_path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
                uploaded.save(full_path)
                source = full_path

            try:
                if import_target == "resources":
                    importer = ImporterFactory.get_importer(
                        "resources", csv_path=full_path, template_id=cid,
                        category_id=cid
                    )
                    ids = importer.create_all_from_csv()
                    count = len(ids)
                else:
                    flash(f"Unknown import target: {import_target}", "error")
                    return redirect(url_for("index"))

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
    # Open the web interface in the default browser after the server starts
    time.sleep(1)
    webbrowser.open("http://127.0.0.1:1991")


if __name__ == "__main__":
    server = make_server("127.0.0.1", 1991, app)
    threading.Thread(target=_open_browser, daemon=True).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()
