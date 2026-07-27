<h1 align="center">elAPI Plugins</h1>

<p align="center">
  <img alt="License" src="https://img.shields.io/github/license/sfb1638/elAPI_Plugins">
  <img alt="Version" src="https://img.shields.io/badge/dynamic/toml?url=https://raw.githubusercontent.com/sfb1638/elAPI_Plugins/main/pyproject.toml&amp;query=$.project.version&amp;label=version&amp;prefix=v&amp;color=green">
  <img alt="Python" src="https://img.shields.io/badge/dynamic/toml?url=https://raw.githubusercontent.com/sfb1638/elAPI_Plugins/main/pyproject.toml&amp;query=$.project['requires-python']&amp;label=python&amp;color=blue">
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
  <a href="https://github.com/dantypas3/elAPI_Plugins/releases">Releases</a> &middot;
  <a href="https://github.com/uhd-urz/elAPI">elAPI Framework</a> &middot;
  <a href="https://www.elabftw.net/">eLabFTW</a>
</p>

---

## About

elAPI Plugins is a desktop application for bulk importing and exporting **resources** and **experiments** in [eLabFTW](https://www.elabftw.net/) instances. It provides a browser-based GUI for researchers and lab managers who need to migrate, back up, or batch-update electronic lab notebook entries from CSV and Excel files.

The project is developed as part of the **INF Project** of [CRC 1638](https://www.sfb1638.de/) at the [Heidelberg University Biochemistry Center (BZH)](https://bzh.db-engine.de/) and is built on top of the [elAPI](https://github.com/uhd-urz/elAPI) framework.

---

## Features

### Export

- Export **resources** (by category) or **experiments** to `.xlsx` files
- Automatically extracts and flattens extra fields from eLabFTW metadata
- Strips HTML from the main text (body) for clean spreadsheet output

### Import

- Create new resources or experiments from CSV files
- Update existing entries by providing entity IDs in the CSV
- Supported fields per entry:
  - Title, main text (body), date, category, template
  - Tags (via the eLabFTW `/tags` sub-endpoint)
  - File attachments (single files or directories)
  - Extra fields (matched to existing template fields with type coercion)
  - Entity links (experiment-to-experiment, experiment-to-resource)
- Intelligent column matching: handles non-breaking spaces, tabs, and case variations
- Automatic delimiter detection for CSV files (comma, semicolon, tab, pipe)

### CSV Templates

- Download a pre-filled CSV template for any resource category or experiment template
- Templates include all standard columns plus the extra fields defined in the eLabFTW template, ready to fill in and re-import

### Automatic Updates

- The application checks for new releases on GitHub at startup and displays a notification banner when an update is available

---

## Prerequisites

[elAPI](https://github.com/uhd-urz/elAPI) must be installed and configured with a valid eLabFTW API key before using these tools.

```bash
pip install elapi
elapi init
```

Follow the [elAPI installation guide](https://github.com/uhd-urz/elAPI?tab=readme-ov-file#installation) for detailed instructions on setting up API credentials.

---

## Installation

### macOS

1. Download the latest `.dmg` from the [Releases](https://github.com/dantypas3/elAPI_Plugins/releases) page:
   - **Apple Silicon** (M1 / M2 / M3 / M4): `elAPI_Plugins_arm64.dmg`
   - **Intel**: `elAPI_Plugins_x86_64.dmg`
2. Open the `.dmg` and drag **elAPI Plugins** into your Applications folder.
3. Launch the application from Launchpad or Finder.

> **Note:** On first launch, macOS may block the application because it is not distributed through the App Store.
> To resolve this, go to **System Settings > Privacy & Security**, scroll to the Security section, and click **Open Anyway**. Then relaunch the application.

### Windows

1. Download the latest `.exe` installer from the [Releases](https://github.com/dantypas3/elAPI_Plugins/releases) page.
2. Run the installer and follow the on-screen instructions.
3. Launch **elAPI Plugins** from the Start Menu or desktop shortcut.

### Linux

Linux users can run the application from source. Python 3.11 or later is required.

```bash
git clone https://github.com/dantypas3/elAPI_Plugins.git
cd elAPI_Plugins
./scripts/setup_env.sh
source .build/bin/activate
python gui/gui.py
```

`.build` is the canonical project virtual environment for local development and notebooks. Packaging uses a separate temporary environment so it does not overwrite your working interpreter.

### Development / notebooks

Create or refresh the shared project environment with:

```bash
./scripts/setup_env.sh
source .build/bin/activate
```

If you want Jupyter to use the same interpreter, register `.build` as the kernel:

```bash
.build/bin/python -m ipykernel install --user --name elapi-plugins --display-name "elAPI Plugins"
```

---

## Usage

After launching, the GUI opens automatically in your default browser at `http://127.0.0.1:1991`.

| Action | Description |
|--------|-------------|
| **Export resources** | Select a category and download all matching resources as an `.xlsx` file. |
| **Export experiments** | Download all experiments as an `.xlsx` file. |
| **Download resource template** | Select a resource category and download a blank CSV with all standard and extra-field columns for that category. |
| **Download experiment template** | Select an experiment template and download a blank CSV with all standard and extra-field columns for that template. |
| **Import from CSV** | Upload a CSV file to create new entries or update existing ones. Select the target type, assign a category or template, and optionally enable update mode. |

### CSV format

The importer automatically detects delimiters and encoding. Column names are matched flexibly (case-insensitive, whitespace-tolerant). Recognized columns include:

| Column | Purpose |
|--------|---------|
| `title` | Entry title |
| `body` | **Main text** of the entry — plain text or **HTML** (rendered as rich text in eLabFTW). Matched flexibly, so `Body Text` / `Main Body` also work. |
| `tags` | Comma-, semicolon-, or pipe-separated tags |
| `category` / `category id` | Numeric category ID |
| `template` | Numeric template ID (used on creation) |
| `date` | Entry date (various formats supported) |
| `experiment id` / `resource id` | Existing entry ID (for update mode) |
| `attachments` / `files_path` | Path to a file or directory to attach |
| `experiments links` | Comma-separated experiment IDs to link |
| `resources links` | Comma-separated resource IDs to link |

Any additional columns are matched against the extra fields defined in the entry's template and updated accordingly.

### Linking entries vs. link-type extra fields

There are two different ways a link can end up on an entry, and the **column header decides which one you get**:

| Column header | What happens | Where it appears in eLabFTW |
|---------------|--------------|-----------------------------|
| A recognized **link column** (see below) | A real entity link is created via the `experiments_links` / `items_links` sub-endpoint | In the **linked entries section at the bottom** of the entry page |
| A template extra field of type *items*/*experiments* | The linked id is written into `metadata.extra_fields` **and** a real link is created | Both **inside the field** and in the **bottom linked section** (same as picking it in the eLabFTW UI) |
| Any other column name | The value is written into the entry's `metadata.extra_fields` | Inside the field only |

Recognized link columns (matching ignores case, spaces and underscores, so
`experiments links`, `Experiments_Links` and `experimentslinks` are equivalent):

| Column | Links to |
|--------|----------|
| `experiments links` / `experiment link` | Experiments |
| `resources links` / `resource link` / `items links` / `item link` | Resources (items) |

Link values are comma- or semicolon-separated numeric IDs (e.g. `12, 34`); for a
template *items*/*experiments* field it is the single linked entity ID. Non-numeric
values are ignored and a warning is logged. This behaviour is identical whether the
entry is being created or updated.

### Update behavior

When updating an existing entry, a field that **already has a value** is either
**overwritten** or **appended to**, depending on the field:

| Field | On update |
|-------|-----------|
| `title` | **Overwritten** with the new value. |
| Extra (template) fields | **Overwritten** with the new value. |
| `date`, `category` | **Overwritten** with the new value. |
| **Main text** (`body`) | **Appended** — the new text is added *after* the existing main text (kept, not replaced), separated by a line break. |
| `tags` | **Appended** — new tags are added to the existing ones; duplicates are skipped. |
| `attachments` / `files_path` | **Appended** — new files are uploaded alongside the existing attachments. |
| Entity links (`experiments links` / `resources links`, and *items*/*experiments* extra fields) | **Appended** — new links are added; existing links are kept (not de-duplicated). |

In short: **most fields overwrite** the previous value, but the **main text is the
exception — it is appended.** To **replace** the main text instead of appending, first
clear it with the `$delete_V` marker (see below), then import the new text — which is
then written into the now-empty main text.

### Update markers

When CSV import is used in update mode, you can place special marker values in individual cells:

| Marker | Effect |
|--------|--------|
| `$delete_V` | Clears the existing value of that field (the main text, or an extra field's value). |
| `$delete_F` | Removes the existing extra field from metadata. |
| `$rename$New Name` | Renames the existing extra field to `New Name`, keeping its value and definition. |

`$delete_V` and `$delete_F` must match exactly. For example, `delete_V` or ` $delete_v ` are treated as normal text.

`$delete_V` is also the way to **overwrite the main text**: because the main text is otherwise appended, put `$delete_V` in the `body` cell to clear it, then import the new text in a subsequent update. Note that `$delete_V` clears the **main text** and **extra-field values** only — it does not remove tags, attachments, or links that have already been added (those are append-only).

For renaming, place `$rename$New Name` in the cell under the column whose header is the field's **current** name; everything after the `$rename$` prefix becomes the new field name (surrounding whitespace is trimmed). The prefix must appear at the very start of the cell — ` $rename$X` (leading space) or `rename$X` (no leading `$`) are treated as normal text. The cell is consumed by the rename, so it does not also set a value. If a field named `New Name` already exists, the rename is skipped (the existing field is not overwritten), and renaming a field the entry does not have is a no-op.

The `title` column is read before markers are applied, so markers in the `title` cell have no effect — the title is always sent as-is and can never be cleared, removed or renamed this way.

### Downloading CSV templates

The **Download Templates** tab generates an empty CSV skeleton for a chosen resource category or experiment template, so the columns always line up with that entry's extra fields.

- **Resources**: columns are `title`, `tags`, `body`, followed by the extra fields defined in the category's metadata. Downloaded as `resource_<category id>_template.csv`.
- **Experiments**: columns are `title`, `tags`, `date`, `status`, `body`, followed by the extra fields defined in the template's metadata. Downloaded as `experiment_<template id>_template.csv`.

The file contains headers only (no data rows) and uses `;` as the delimiter. If the category/template's metadata can't be parsed, the extra-field columns are simply omitted and only the standard columns are included.

---

## Project Structure

```
src/
  factories/          Factory classes for instantiating importers and exporters
  services/
    importers/        CSV-to-eLabFTW import logic (resources, experiments)
    exporters/        eLabFTW-to-Excel export logic
  updater/            GitHub release checker and asset downloader
  utils/              Shared utilities (CSV parsing, endpoints, logging)
gui/                  Flask-based web GUI
config/               Runtime configuration files
tests/                Test suite
```

---

## License

Copyright (c) 2025 Biochemistry Center(BZH), CRC 1638, Heidelberg University.

This project is licensed under the [GNU Affero General Public License v3.0 or later](LICENSE).

---

<p align="center">
  <sub>Heidelberg University &middot; <a href="https://bzh.db-engine.de/">Biochemistry Center (BZH)</a> &middot; <a href="https://www.sfb1638.de/">SFB 1638</a> &middot; INF Project</sub>
</p>
