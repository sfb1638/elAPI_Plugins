<h1 align="center">elAPI Plugins</h1>

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
- Strips HTML from body content for clean spreadsheet output

### Import

- Create new resources or experiments from CSV files
- Update existing entries by providing entity IDs in the CSV
- Supported fields per entry:
  - Title, body, date, category, template
  - Tags (via the eLabFTW `/tags` sub-endpoint)
  - File attachments (single files or directories)
  - Extra fields (matched to existing template fields with type coercion)
  - Entity links (experiment-to-experiment, experiment-to-resource)
- Intelligent column matching: handles non-breaking spaces, tabs, and case variations
- Automatic delimiter detection for CSV files (comma, semicolon, tab, pipe)

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
python -m venv .venv
source .venv/bin/activate
pip install .
python gui/gui.py
```

---

## Usage

After launching, the GUI opens automatically in your default browser at `http://127.0.0.1:1991`.

| Action | Description |
|--------|-------------|
| **Export resources** | Select a category and download all matching resources as an `.xlsx` file. |
| **Export experiments** | Download all experiments as an `.xlsx` file. |
| **Import from CSV** | Upload a CSV file to create new entries or update existing ones. Select the target type, assign a category or template, and optionally enable update mode. |

### CSV format

The importer automatically detects delimiters and encoding. Column names are matched flexibly (case-insensitive, whitespace-tolerant). Recognized columns include:

| Column | Purpose |
|--------|---------|
| `title` | Entry title |
| `body` | Main text / body content |
| `tags` | Comma-, semicolon-, or pipe-separated tags |
| `category` / `category id` | Numeric category ID |
| `template` | Numeric template ID (used on creation) |
| `date` | Entry date (various formats supported) |
| `experiment id` / `resource id` | Existing entry ID (for update mode) |
| `attachments` / `files_path` | Path to a file or directory to attach |
| `experiments links` | Comma-separated experiment IDs to link |
| `resources links` | Comma-separated resource IDs to link |

Any additional columns are matched against the extra fields defined in the entry's template and updated accordingly.

---

## Project Structure

```
src/
  factories/          Factory classes for instantiating importers and exporters
  services/
    importers/        CSV-to-eLabFTW import logic (resources, experiments)
    exporters/        eLabFTW-to-Excel export logic
  utils/              Shared utilities (CSV parsing, endpoints, logging)
gui/                  Flask-based web GUI
config/               Runtime configuration files
tests/                Test suite
```

---

## License

This project is licensed under the [GNU Affero General Public License v3.0 or later](LICENSE).

---

<p align="center">
  <sub>Heidelberg University &middot; <a href="https://bzh.db-engine.de/">Biochemistry Center (BZH)</a> &middot; <a href="https://www.sfb1638.de/">SFB 1638</a> &middot; INF Project</sub>
</p>
