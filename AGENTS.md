# AGENTS.md

Guidance for working in this repository.

## Project overview

**elAPI Plugins** is a desktop/GUI tool for migrating and syncing data with
[eLabFTW](https://www.elabftw.net/) (and Labfolder). It wraps the `elapi` client
and exposes three capabilities through a local Flask web GUI:

- **Export** experiments and resources to `.xlsx`.
- **Import** entries from CSV — create new entries or update existing ones.
- **Download CSV templates** pre-populated with a category/template's columns.

Developed for the INF Project of CRC 1638 at Heidelberg University (BZH).

- Language: Python (>= 3.11)
- License: AGPL-3.0-or-later
- Version: see `pyproject.toml` (`[project].version`)

## Tech stack

- **Flask / Werkzeug** — local web GUI (`gui/`)
- **pandas / numpy / openpyxl** — CSV & XLSX processing
- **elapi** — eLabFTW API client (`FixedEndpoint`)
- **requests / chardet / beautifulsoup4** — HTTP, encoding detection, HTML parsing
- **pytest** — tests; **ruff** + **mypy** — lint/format/type-check
- **PyInstaller** — packaged desktop builds (Windows `.spec`, macOS script)

## Environment & common commands

The canonical dev environment is `.build/`, created with **uv**:

```bash
./scripts/setup_env.sh          # uv venv --clear .build && uv sync (all extras/groups)
source .build/bin/activate
```

There is also a local `.venv/` used for running tools directly. When a shell
isn't activated, call interpreters explicitly, e.g.:

```bash
.venv/bin/python -m pytest -q                       # run the whole test suite
.venv/bin/python -m pytest tests/src/services/importers -q
.venv/bin/python -m pytest tests/src/services/importers/test_experiments_importer.py -k rename
```

Lint / type-check / format:

```bash
ruff check .            # line-length 89, rules: E,F,I,B,UP
ruff format .           # double quotes, space indent
mypy .                  # config in mypy.ini
```

Run the GUI (opens the browser automatically):

```bash
python gui/gui.py       # serves http://127.0.0.1:1991
```

Packaged builds:

- Windows: `scripts/package_windows.ps1` (generates its own PyInstaller spec at
  build time), installer via `packaging/installer.iss`
  (Inno Setup: `ISCC /DArch=x64 packaging\installer.iss`)
- macOS: `scripts/package_mac.sh` → `.app` + `.dmg`
- Linux: `scripts/package_linux.sh` → standalone binary + `.deb` (needs `fpm`);
  desktop entry lives in `packaging/elapi-plugins.desktop`

## Project structure

```
elAPI_Plugins/
├── gui/                              # Flask web GUI (entry point)
│   ├── gui.py                        # routes: /setup, /, /shutdown; runs on 127.0.0.1:1991
│   ├── templates/                    # index.html (export/import/templates), setup.html
│   ├── static/                       # style.css, logo
│   └── assets/                       # app icons (.ico/.icns)
│
├── src/
│   ├── factories/                    # Instantiate importers/exporters by name
│   │   ├── exporter_factory.py       # ExporterFactory.get_exporter("resources"|"experiments")
│   │   └── importer_factory.py       # ImporterFactory.get_importer(...)
│   │
│   ├── services/
│   │   ├── importers/                # CSV -> eLabFTW
│   │   │   ├── base_importer.py      # shared logic: extras, tags, files, links, markers
│   │   │   ├── experiments_importer.py
│   │   │   └── resources_importer.py
│   │   └── exporters/                # eLabFTW -> XLSX
│   │       ├── base_exporter.py      # xlsx_export / fetch_data / process_data
│   │       ├── experiments_exporter.py
│   │       └── resources_exporter.py
│   │
│   ├── utils/
│   │   ├── common.py                 # canonicalize(), ensure_series() helpers
│   │   ├── csv_tools.py              # CsvTools: encoding/delimiter detection, normalization
│   │   ├── endpoints.py              # get_fixed(name) -> elapi FixedEndpoint
│   │   ├── paths.py                  # resource/config path resolution
│   │   ├── validators.py             # IDValidator and friends
│   │   └── logging_config.py         # logging setup
│   │
│   └── updater/                      # self-update logic
│
├── config/                           # runtime JSON config
│   ├── exp_importer_config.json
│   ├── res_importer_config.json
│   ├── logging_config.json
│   └── misc_config.json
│
├── tests/                            # pytest suite (mirrors src/ layout)
│   ├── conftest.py                   # FakeEndpoint, FakeResponse, write_csv helpers
│   ├── gui/ , src/services/ , src/...
│
├── scripts/                          # setup_env.sh/.ps1, package_{linux,mac,windows}
├── packaging/                        # installer.iss (Windows), .desktop (Linux)
├── pyproject.toml                    # deps, ruff, build config
├── mypy.ini
└── README.md
```

## Architecture & data flow

```
        Flask GUI (gui/gui.py)
                │
        ┌───────┴────────┐
   ExporterFactory   ImporterFactory        (src/factories)
        │                │
   BaseExporter      BaseImporter           (src/services)
   ├ Experiments…    ├ ExperimentsImporter
   └ Resources…      └ ResourcesImporter
        │                │
        └──── utils.endpoints.get_fixed() ──┘
                │
        elapi FixedEndpoint  ──►  eLabFTW REST API
```

- The GUI reads/writes host + API token via the **/setup** page, then the
  **/** page dispatches actions (`export_type` form field): `resources`,
  `experiments`, `template_resources`, `template_experiments`, `imports`.
- **Exporters** fetch entities and emit `.xlsx`.
- **Importers** read a CSV (encoding/delimiter auto-detected), then per row call
  `create_new(...)` or, in update mode, `patch_existing(...)`.
- Extra (template) fields are matched to CSV columns by **canonicalized** name
  (`canonicalize()` — case-insensitive, whitespace/underscore tolerant).

## Import update semantics

When updating an existing entry (`patch_existing`), columns are applied with
different semantics — this is intentional (see `README.md` "Update behavior"):

| Field                                   | Behavior                                    |
|-----------------------------------------|---------------------------------------------|
| `title`                                 | **Overwritten**                             |
| Extra (template) fields                 | **Overwritten**                             |
| `body`                                  | **Appended** to existing body               |
| `tags`                                  | **Appended** (duplicates skipped)           |
| `attachments` / `files_path`            | **Appended** (existing files kept)          |
| `experiments links` / `resources links` | **Appended** (existing links kept)         |

Tags use `append_tags(...)` (keeps existing, skips already-present) rather than
`replace_tags(...)`; the latter is still used by `create_new`.

## Entity links vs. link-type extra fields

A frequent source of confusion. The **column header** alone decides which of two
different eLabFTW mechanisms is used — identical for `create_new` and
`patch_existing`:

| Column header | Code path | Result |
|---------------|-----------|--------|
| Matches `_LINK_COLUMN_MAP` (`experiments links`, `resources links`, ...) | `_post_links()` → `POST /{entity}/{id}/{experiments_links,items_links}/{link_id}` | Real link only |
| Template extra field of type *items*/*experiments* (e.g. `GMO_Project`) | writes `metadata.extra_fields[...].value` **and** `_post_links()` | Field shows the linked entity **and** it appears in the bottom linked section |
| Anything else | written into `metadata.extra_fields` | Plain field value |

- Link headers are normalized by `link_key()` (module-level in `base_importer.py`):
  `canonicalize()` **plus** underscore stripping, so `experiments links`,
  `Experiments_Links` and `experimentslinks` all match.
- Note `canonicalize()` alone keeps `_`, so never match link columns with it
  directly — that was a real bug (underscore headers silently became extra fields).
- Values are parsed by `_parse_link_ids()` (comma/semicolon separated integers);
  non-numeric values log a warning and create no links.
- Link creation **requires** an `{"action": "create"}` JSON body:
  `POST /{entity}/{id}/{..._links}/{subid}` with the subid in the path. Omitting
  the body makes eLabFTW return **HTTP 500** and create nothing (apidoc v2). This
  was a real bug — links were posted with an empty body and silently failed.
- `_post_links` **catches and logs** per-link failures (does not raise), so a
  failing link does not abort the import. Check `logs/error.log` for
  `Failed to link entry ...` if links don't appear.
- Links **append** — `_post_links` does not dedupe against existing links, so
  re-importing the same row accumulates duplicates.

For the **extra-field** path (type *items*/*experiments*), the importer mirrors
what eLabFTW's own UI does when you pick an entity in such a field
(`src/ts/Metadata.class.ts`): it BOTH stores the id in `metadata.extra_fields`
AND creates a real link via `_post_links` (`{type}_links` sub-endpoint). Setting
only the metadata value renders nothing and shows no bottom link — this was the
"manual link works, API link doesn't" bug. The id in metadata is written as a
JSON **string** (`"value": "2311"`), never a number; `_coerce_for_field` parses
it via `_parse_integer_id` (dropping any `.0` from float-parsed CSV cells) and
returns `str(...)`.

## Update markers (cell values, update mode only)

Special cell values trigger metadata operations. All are handled in
`patch_existing` + `BaseImporter.post_extra_fields_from_row`:

| Marker              | Effect                                                              |
|---------------------|--------------------------------------------------------------------|
| `$delete_V`         | Clears the existing value of that field.                           |
| `$delete_F`         | Removes the extra field from metadata entirely.                    |
| `$rename$New Name`  | Renames the extra field (column header = old name) to `New Name`, keeping its value/definition. |

Notes:
- The rename prefix is defined by `BaseImporter._RENAME_PREFIX` (currently
  `"$rename$"`); the text after the prefix becomes the new field name (trimmed).
- `$delete_V` / `$delete_F` must match the cell **exactly**; leading/trailing
  spaces or altered casing are treated as normal text.
- `title` is read **before** markers are applied, so markers in the `title`
  cell have no effect — the title can't be cleared/renamed this way.
- Rename **collisions** (target name already exists) are skipped with a warning;
  renaming a field the entity doesn't have is a no-op.

## Conventions

- Match the existing style: type hints, `logging` (module-level `logger`),
  `region` comment blocks in the importer/exporter classes.
- Prefer `canonicalize()` for any column/field-name comparison.
- Keep `ruff` (line length 89) and `mypy` clean.
- Add/extend tests under `tests/` mirroring `src/` layout; use the
  `FakeEndpoint` / `FakeResponse` / `write_csv` helpers from `tests/conftest.py`.
- **Git commits: do NOT add "Co-Authored-By" trailers or any Codex/AI
  attribution.** Keep the author history clean.

## Known test state

A few tests fail on the base branch independently of recent changes (e.g.
`test_create_new_with_files`, `test_get_tags_parsing`). Verify new failures
against a clean checkout (`git stash`) before assuming your change caused them.
