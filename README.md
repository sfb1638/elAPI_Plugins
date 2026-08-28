# elAPI Plugins

<p align="center">
  <img alt="License" src="https://img.shields.io/github/license/sfb1638/elAPI_Plugins">
  <img alt="Version" src="https://img.shields.io/badge/dynamic/toml?url=https://raw.githubusercontent.com/sfb1638/elAPI_Plugins/main/pyproject.toml&query=$.project.version&label=version&prefix=v&color=green">
  <img alt="Python" src="https://img.shields.io/badge/dynamic/toml?url=https://raw.githubusercontent.com/sfb1638/elAPI_Plugins/main/pyproject.toml&query=$.project['requires-python']&label=python&color=blue">
  <img alt="Last commit" src="https://img.shields.io/github/last-commit/sfb1638/elAPI_Plugins">
  <img alt="Release" src="https://img.shields.io/github/v/release/sfb1638/elAPI_Plugins">
  <img alt="Issues" src="https://img.shields.io/github/issues/sfb1638/elAPI_Plugins">
</p>

<p align="center">
  <img src="https://github.com/user-attachments/assets/e8ce314e-2f66-47af-9d08-b94324646984" alt="SFB1638 Logo" width="200">
</p>

<p align="center">
  <strong>Data import and export tools for eLabFTW electronic lab notebooks</strong>
</p>

<p align="center">
  <a href="https://github.com/sfb1638/elAPI_Plugins/releases">Releases</a> · <a href="https://github.com/uhd-urz/elAPI">elAPI Framework</a> · <a href="https://www.elabftw.net/">eLabFTW</a>
</p>

---

## About

elAPI Plugins is a desktop application for bulk importing and exporting **resources** and **experiments** in [eLabFTW](https://www.elabftw.net/) instances. It provides a browser-based GUI for researchers and lab managers who need to migrate, back up, or batch-update electronic lab notebook entries from CSV and Excel files.

The project is developed as part of the **INF Project**  of [CRC 1638](https://www.sfb1638.de/) [(GEPRIS: 511488495)](https://gepris.dfg.de/project/511488495?lang=en) at the [Heidelberg University Biochemistry Center (BZH)](https://bzh.db-engine.de/) and is built on top of the [elAPI](https://github.com/uhd-urz/elAPI) framework.

---

## Features

### Export

- Export **resources** (by category) or **experiments** to `.xlsx` files.
- Automatically extracts and flattens extra fields from eLabFTW metadata.
- Strips HTML from the main text (body) for clean spreadsheet output.

### Import

- Create new resources or experiments from CSV files.
- Update existing entries by providing entity IDs in the CSV.
- Supported fields per entry:
 
  | Field | Details |
  |-------|---------|
  | Title, main text (body), date | Standard entry fields. Body accepts plain text or HTML. |
  | Category / template | Numeric category or template ID. |
  | Tags | Via the eLabFTW `/tags` sub-endpoint. |
  | File attachments | Single files or entire directories. |
  | Extra fields | Matched to existing template fields with type coercion. |
  | Entity links | Experiment-to-experiment, experiment-to-resource, resource-to-experiment and resource-to-resource links. |

- Intelligent column matching: tolerates non-breaking spaces, tabs, and case variations.
- Automatic delimiter detection for CSV files (comma, semicolon, tab, pipe).

### CSV Templates

- Download a pre-filled CSV template for any resource category or experiment template.
- Templates include all standard columns plus the extra fields defined in the eLabFTW template, ready to fill in and re-import.

### Automatic Updates

- The application checks for new releases on GitHub at startup and displays a notification banner when an update is available.

---

## Prerequisites

### For the packaged installers (recommended)

**No additional software is needed.** The macOS (`.dmg`) and Windows (`.exe`) installers include a self-contained Python environment and all required dependencies — including the [elAPI](https://github.com/uhd-urz/elAPI) framework — bundled inside the package. You do **not** need to install `elapi` separately to use the installers.

### For running from source / terminal

Python 3.11 or later and [elAPI](https://github.com/uhd-urz/elAPI) are required.

```bash
pip install elapi
elapi init
```

Follow the [elAPI installation guide](https://github.com/uhd-urz/elAPI?tab=readme-ov-file#installation) for detailed instructions on setting up your eLabFTW API credentials.

---

## Installation

### macOS

1. Download the latest `.dmg` from the [Releases](https://github.com/sfb1638/elAPI_Plugins/releases) page:

   - **Apple Silicon** (M1/M2/M3/M4): `elAPI_Plugins_arm64.dmg`
   - **Intel**: `elAPI_Plugins_x86_64.dmg`

2. Open the `.dmg` and drag **elAPI Plugins** into your Applications folder.
3. Launch the application from Launchpad or Finder.

> **Note:** On first launch, macOS may block the application because it is not distributed through the App Store. Go to **System Settings → Privacy & Security**, scroll to the Security section, and click **Open Anyway**. Then relaunch the application.

### Windows

1. Download the latest `.exe` installer from the [Releases](https://github.com/sfb1638/elAPI_Plugins/releases) page.
2. Run the installer and follow the on-screen instructions.
3. Launch **elAPI Plugins** from the Start Menu or the desktop shortcut (optional, selected during installation).

### Linux (Debian / Ubuntu)

1. Download the latest `.deb` package from the [Releases](https://github.com/sfb1638/elAPI_Plugins/releases) page, e.g. `elapi-plugins_1.3.0b1_amd64.deb`.
2. Install it:

   ```bash
   sudo apt install ./elapi-plugins_1.3.0b1_amd64.deb
   ```

3. Launch **elAPI Plugins** from your application menu, or run `elapi-plugins` in a terminal.

The package is self-contained — no separate Python installation is required. To remove it, run `sudo apt remove elapi-plugins`.

On other distributions, run the application from source:

```bash
git clone https://github.com/sfb1638/elAPI_Plugins.git
cd elAPI_Plugins
./scripts/setup_env.sh
source .build/bin/activate
python gui/gui.py
```

`.build` is the project's dedicated virtual environment. It is kept separate from your system Python so that building or packaging does not affect your working interpreter.

---

## Development & Notebooks

### Set up the development environment

```bash
./scripts/setup_env.sh
source .build/bin/activate
```

### Use with Jupyter

To run the GUI or import the package inside a Jupyter notebook, register the environment as a kernel:

```bash
.build/bin/python -m ipykernel install --user --name elapi-plugins --display-name "elAPI Plugins"
```

Then select the **elAPI Plugins** kernel in your notebook.

### Build the release artifacts

Each script builds into a throwaway `.pkg-build` environment, so your development interpreter is untouched. Run each on its target platform:

| Platform | Command | Output |
|----------|---------|--------|
| Linux | `./scripts/package_linux.sh` | `dist/elapi-plugins` and `dist/elapi-plugins_<version>_<arch>.deb` |
| macOS | `./scripts/package_mac.sh` | `dist/elAPI_Plugins_<arch>.app` and `.dmg` |
| Windows | `.\scripts\package_windows.ps1` then `ISCC /DArch=x64 packaging\installer.iss` | `dist/elAPI_Plugins_x64.exe` and an Inno Setup installer |

The Linux `.deb` step requires [fpm](https://fpm.readthedocs.io); without it the standalone binary is still built:

```bash
sudo apt install ruby ruby-dev build-essential && sudo gem install --no-document fpm
```

---

## Usage

After launching, the GUI opens automatically in your default browser at `http://127.0.0.1:1991`.

| Action | Description |
|--------|-------------|
| **Export resources** | Select a resource category and download all matching entries as an `.xlsx` file. |
| **Export experiments** | Download all experiments as an `.xlsx` file. |
| **Download resource template** | Select a resource category and download a blank CSV with all standard and extra-field columns for that category. |
| **Download experiment template** | Select an experiment template and download a blank CSV with all standard and extra-field columns for that template. |
| **Import from CSV** | Upload a CSV file to create new entries or update existing ones. Select the target type, assign a category or template, and optionally enable update mode. |

---

## CSV Format

The importer automatically detects the file's delimiter and encoding. Column names are matched flexibly (case-insensitive, whitespace-tolerant).

### Recognized columns

| Column | Purpose |
|--------|---------|
| `title` | Entry title |
| `body` | Main text of the entry — accepts plain text or HTML (rendered as rich text in eLabFTW). Matched flexibly, so `Body Text`, `Main Body`, etc. also work. |
| `tags` | Comma-, semicolon-, or pipe-separated tags |
| `category` / `category id` | Numeric category ID |
| `template` | Numeric template ID (used on creation) |
| `date` | Entry date (various formats supported) |
| `experiment id` / `resource id` | Existing entry ID — required for update mode |
| `attachments` / `files_path` | Path to a file or directory to attach |
| `experiments links` | Comma-separated experiment IDs to link to |
| `resources links` / `items links` | Comma-separated resource IDs to link to |

Any additional columns are matched against the extra fields defined in the entry's template and populated accordingly.

### Linking entries vs. link-type extra fields

There are two distinct ways a link can end up on an entry — the column header decides which one is used:

| What you write in the CSV | What happens | Where it appears in eLabFTW |
|---------------------------|--------------|-----------------------------|
| A **link column** (`experiments links`, `resources links`, etc.) | A real entity link is created via the `/experiments_links` or `/items_links` sub-endpoint | In the **linked entries section** at the bottom of the entry page |
| A template extra field of type *items*/*experiments* | The linked ID is written into `metadata.extra_fields` **and** a real link is created | Both **inside the field** and in the **bottom linked section** |
| Any other column name | The value is written into `metadata.extra_fields` only | Inside the field only |

Recognized link columns (matching ignores case, spaces, and underscores — `experiments links`, `Experiments_Links`, and `experimentslinks` are all equivalent):

| Column | Links to |
|--------|----------|
| `experiments links` / `experiment link` | Experiments |
| `resources links` / `resource link` / `items links` / `item link` | Resources (items) |

Link values are comma- or semicolon-separated numeric IDs (e.g. `12, 34`). Non-numeric values are ignored and a warning is logged. This behaviour is identical whether the entry is being created or updated.

### Update behaviour

When updating an existing entry, a field that **already has a value** is either **overwritten** or **appended**, depending on the field:

| Field | On update |
|-------|-----------|
| `title`, `date`, `category` | **Overwritten** |
| Extra (template) fields | **Overwritten** |
| **Main text** (`body`) | **Appended** — new text is added *after* the existing text, separated by a line break |
| `tags` | **Appended** — new tags are added; duplicates are skipped |
| `attachments` / `files_path` | **Appended** — new files are added alongside existing attachments |
| Entity links (link columns and *items*/*experiments* extra fields) | **Appended** — new links are added; existing links are kept |

> **To replace the main text instead of appending:** put `$delete_V` in the `body` cell (see [Update markers](#update-markers) below) to clear it first, then import the new text in a subsequent update.

### Update markers

When in update mode, special marker values can be placed in individual CSV cells:

| Marker | Effect |
|--------|--------|
| `$delete_V` | Clears the existing value of that field (main text or extra field value) |
| `$delete_F` | Removes the existing extra field from `metadata.extra_fields` entirely |
| `$rename$New Name` | Renames the existing extra field to `New Name`, keeping its value |

- `$delete_V` and `$delete_F` must match exactly — `delete_V` or ` $delete_v ` with a leading space or different case are treated as ordinary text.
- `$rename$` must appear at the very start of the cell — ` $rename$X` (leading space) or `rename$X` (no leading `$`) are treated as ordinary text.
- If a field named `New Name` already exists, the rename is skipped to avoid overwriting it.
- The `title` column is read before markers are applied, so markers in the `title` cell have no effect.

---

## Downloading CSV Templates

The **Download Templates** tab generates an empty CSV skeleton that matches a chosen resource category or experiment template exactly.

- **Resources**: columns are `title`, `tags`, `body`, followed by any extra fields defined in the category's metadata. File name: `resource_<category id>_template.csv`.
- **Experiments**: columns are `title`, `tags`, `date`, `status`, `body`, followed by any extra fields defined in the template's metadata. File name: `experiment_<template id>_template.csv`.

Templates use `;` as the delimiter and contain headers only (no data rows). If the category's or template's metadata cannot be parsed, the extra-field columns are omitted and only the standard columns are included.

---

## Project Structure

```
elAPI_Plugins/
├── src/
│   ├── factories/           Factory classes for importers and exporters
│   ├── services/
│   │   ├── importers/       CSV → eLabFTW import logic (resources, experiments)
│   │   └── exporters/       eLabFTW → Excel export logic
│   ├── updater/             GitHub release checker and asset downloader
│   └── utils/               CSV parsing, endpoint definitions, logging, validators
├── gui/
│   ├── gui.py               Flask-based web GUI entry point
│   ├── templates/           HTML templates
│   ├── static/              CSS, JavaScript, and other static assets
│   └── assets/              Application icons
├── config/                  Runtime configuration files
├── scripts/
│   ├── setup_env.sh         Create/refresh the .build virtual environment (Linux/macOS)
│   ├── setup_env.ps1        Create/refresh the .build virtual environment (Windows)
│   ├── package_linux.sh     Build a standalone Linux binary + .deb
│   ├── package_mac.sh       Build a self-contained macOS .app + .dmg
│   └── package_windows.ps1  Build a self-contained Windows .exe
├── packaging/
│   ├── elapi-plugins.desktop  Desktop entry installed by the .deb
│   └── installer.iss          Inno Setup script for the Windows installer
├── tests/                   Test suite
└── pyproject.toml           Project metadata and dependencies
```

---

## License

Copyright (c) 2025 Biochemistry Center (BZH), CRC 1638, Heidelberg University.

This project is licensed under the [GNU Affero General Public License v3.0 or later](LICENSE).

---

<p align="center">
  <sub>Heidelberg University · <a href="https://bzh.db-engine.de/">Biochemistry Center (BZH)</a> · <a href="https://www.sfb1638.de/">SFB 1638</a> · INF Project</sub>
</p>
