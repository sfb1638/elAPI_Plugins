# v1.3.0 — Permissions, Templates, Row Validation & Safer Imports

This release lets you set read/write permissions and manage templates straight from a CSV, checks every row before anything is sent to eLabFTW, and fixes a long list of bugs that could lose or misplace data. If you are coming from v1.2.0, everything below is new to you; the first two sections were also in the 1.3.0b1 beta.

## ⚠️ Please read before updating

A few things behave differently from v1.2.0:

- **Rows with unusable values are skipped, not half-imported.** Link columns, link-type fields and select fields are checked against eLabFTW first. A row that points at an entry that does not exist, or uses a value that is not one of a select field's options, is skipped as a whole and listed after the import with the reason. Before, such values were silently dropped and the rest of the row was imported.
- **A failing row no longer stops the import.** When creating entries, a row whose request fails is reported as skipped and the import continues. Rows created before the failure stay in eLabFTW, so re-running the *whole* CSV after a partial import would create them again — check the list of skipped rows and import only those.
- **An entry that cannot be read is not updated.** In update mode the importer first reads the entry. If that fails (entry not found, server error) the row is skipped. Before, the error reply was mistaken for the entry and the existing main text could be **overwritten** instead of appended to.
- **Tags may mix separators.** `a; b, c` is now three tags. A tag that itself contains a comma can no longer be written in a cell that also uses another separator.
- **The `status` column takes a number.** The numeric eLabFTW status ID is applied; a status *name* is ignored with a warning in the log.

## 🔐 Permissions from the CSV

New columns set who can read and write an entry: `canread_base` / `canwrite_base` (the eLabFTW levels 10–50, or the words `owner`, `admins`, `team`, `everyone`, `public`) together with `canread_users`, `canread_teams` and `canread_teamgroups` (and the `canwrite` counterparts). They work when creating and when updating an entry. Only the lists you fill in are replaced, so granting a user access never drops teams set elsewhere, and an invalid level or a non-numeric ID is skipped with a warning rather than sent.

## 🧩 Import and update templates

Resource templates and experiment templates can now be created and updated from a CSV, using the same engine as entries and keyed on a `Template ID` column when updating. Title, main text, extra fields, tags and permissions all behave as they do for entries, including the `$delete_V`, `$delete_F` and `$rename$` markers — so you can rename or remove a field in a large template without clicking through the interface. Templates have no uploads or links in eLabFTW, so attachment and link columns are ignored with a warning.

## ✨ Also new

- **Row validation.** Before a row is imported its values are checked: link columns and link-type fields must be numeric IDs of entries that exist, select fields must use one of their options, and the category must be a number. The GUI lists each skipped row with the reason, and the log keeps the full list. Only a "not found" answer counts as missing, so a network or permission error never skips a good row. The update markers `$delete_V`, `$delete_F` and `$rename$` are exempt.
- **Attachments folder.** The import form has a new optional **Attachments folder** field. Relative paths in the `files_path` / `attachments` columns are resolved against it — or against the CSV's own folder when the CSV is given by path. Bare folder names work too. A folder that does not exist is refused before anything is created.

- **Relaunching replaces the running app.** If you start elAPI Plugins while an earlier copy is still open — this version or an older one — the old copy is closed and the new one opens, instead of nothing happening. An import still running in the old copy is stopped. Another program using port 1991 is left alone.

## 🐛 Fixes

**Import — values and columns**

- **`date` and `status` are applied when creating entries.** For resources both used to end up as extra fields instead.
- **Category columns.** `category_id` and `Category-ID` are recognised, and the category column is no longer also written as an extra field. A category like `12.0` is accepted; a bad one skips only its row in update mode instead of aborting the run.
- **`Body Weight` is not the body.** A column whose name merely contains the word "body" is no longer taken for the main text when the template defines a field of that name.
- **Entity IDs with decimals are rejected.** `12.7` used to be cut to `12`, which could update the wrong entry. `12.0` is still accepted.
- **Entries with `null` or malformed metadata** no longer crash an update.
- **Quoted ID cells.** A value typed as `"351, 352"` in a spreadsheet used to parse to nothing; the stray quotes are now ignored.

**CSV and export**

- **Non-ASCII characters are kept.** A file that started with plain ASCII and contained `Müller` further down lost the `ü`. Files are now read as UTF-8 in full first, falling back to a detected encoding; undecodable characters are replaced and logged, never silently dropped.
- **HTML bodies are exported in full.** Only the text inside paragraphs used to be kept; headings, lists, line breaks and tables were lost.

**The app**

- **A page reload no longer shuts the app down.** The shutdown is delayed a few seconds and cancelled by the next request. Closing the tab still stops the app.
- **Other websites can no longer drive the local server.** Cross-site requests and foreign `Host` headers are rejected, so a web page open in your browser cannot trigger imports, change your connection settings or stop the app.
- **The API token file is private.** `~/.config/elapi.yml` is written readable by you only. A file saved by an earlier version stays as it is until you save the setup page again — or run `chmod 600 ~/.config/elapi.yml`.
- **Temporary files are cleaned up.** Uploaded CSVs and exported spreadsheets are deleted after use, and two uploads with the same name no longer overwrite each other.
- **Pages no longer hang forever** when the eLabFTW server keeps timing out; the error is shown instead.
- **The update banner is accurate.** It shows the real version, and missing release links no longer appear as "None".
- **`LOG_LEVEL` is honoured** by the GUI (the default stays `DEBUG`).

**Packaging**

- Packaged apps write their logs to a per-user folder (`~/.local/state/elAPI_Plugins/logs` on Linux, `~/Library/Logs/elAPI_Plugins` on macOS, `%LOCALAPPDATA%\elAPI_Plugins\logs` on Windows) and bundle `pyproject.toml`, so they report their real version and the "Update available" banner no longer shows permanently.
- The Windows build no longer fails at "Creating virtual environment" when `python` resolves to the Microsoft Store alias; it now finds a real interpreter and stops at the first failing step.

## 🔧 Under the hood

- The permission columns in the importer configs match the code (`canread_users`, `*_teamgroups`), and the experiments importer reads its own config file.
- Removed unused code: the `IDValidator` module, unused upload and patch helpers, `download_asset` and `config/misc_config.json`.
- The full test suite passes (265 tests), and `ruff` and `mypy` are clean. Type stubs for `requests` and `PyYAML` were added to the development dependencies.

## 📦 Install

Download the installer for your system from the assets below, or on Linux `sudo apt install ./elapi-plugins_1.3.0_amd64.deb`.
