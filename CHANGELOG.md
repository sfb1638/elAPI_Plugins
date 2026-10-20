# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.3.0] — 2026-10-13

The first stable release of the 1.3 series. It includes everything from
1.3.0b1 (permissions from the CSV, importing and patching templates) plus row
validation, an attachments-folder field for imports, and a long list of fixes.

### Added

- **Row validation on import.** Before a row is imported its values are checked
  against eLabFTW, and a row with an unusable value is skipped as a whole and
  reported. The check covers link columns, link-type extra fields (the entry
  must exist), select extra fields (the value must be one of the options) and
  the category column (must be numeric). After the import the GUI lists each
  skipped row with the reason, and the log keeps the full list. Only a "not
  found" answer counts as missing, so a network or permission error never skips
  a row. Update markers (`$delete_V`, `$delete_F`, `$rename$`) are exempt.
- **Attachments folder.** The import form has an optional "Attachments folder"
  field. Relative paths in the `files_path` / `attachments` columns are resolved
  against it, or against the CSV's own folder when the CSV is given by path.

### Changed

- A select value that is not one of the field's options used to be dropped
  quietly while the rest of the row was imported; the row is now skipped.
- A non-numeric category used to abort the whole import; it now skips only that
  row.
- A link-column value that is not a numeric ID used to be ignored with a log
  warning; the row is now skipped.
- In update mode the success message reads "skipped N" instead of
  "skipped N invalid IDs", as rows can now be skipped for other reasons.
- Creating entries no longer stops at the first row that fails: the row is
  reported as skipped and the import goes on. Re-running a half-finished import
  no longer duplicates the rows that were already created.
- Tags in one cell may mix `;`, `,` and `|` as separators.
- A column such as `Body Weight` is no longer taken for the body when the
  template defines a field of that name.
- The app logs to a per-user folder in packaged builds and reports its real
  version, so the "Update available" banner no longer shows permanently.

- **Starting the app again replaces a copy that is still running.** Before, the
  second launch failed on the busy port and nothing seemed to happen. The new
  copy now asks the old one to quit (older versions included) and takes its
  place; a program that is not this app is never touched.

### Fixed

- **Create mode** now applies the `date` column (and a numeric `status`); for
  resources both used to be stored as extra fields.
- `category_id` and `Category-ID` are recognised as the category column, and the
  category column is no longer also written as an extra field. A category like
  `12.0` is accepted, and a bad one skips only its row in update mode.
- An entry that cannot be read (404, server error) is no longer updated; before,
  its error reply was taken for the entry and the body was overwritten instead
  of appended to.
- Entity IDs with decimals (`12.7`) are rejected instead of being cut to `12`.
- Entries whose `metadata` is `null` or malformed no longer crash the update.
- CSV files keep non-ASCII characters (`Müller`) that appear after an
  ASCII-only start; undecodable bytes are replaced and logged, not dropped.
- HTML bodies are exported in full, not just the text inside paragraphs.
- Missing release fields in the update banner no longer show as "None".
- A page reload no longer shuts the app down; the shutdown is delayed and
  cancelled by the next request.
- The local server rejects cross-site requests and foreign `Host` headers.
- The API token file `~/.config/elapi.yml` is written readable by its owner only.
- Uploaded CSVs and exported spreadsheets are deleted after use, and two uploads
  with the same name no longer overwrite each other.
- Loading a page no longer hangs forever when the server keeps timing out.
- The `LOG_LEVEL` environment variable is honoured by the GUI.
- The permission columns in the importer configs match the code
  (`canread_users`, `*_teamgroups`), and the experiments importer reads its own
  config file.

### Removed

- Unused code: `IDValidator`, `_attach_files`, `patch_decoded_extra_fields`,
  `download_asset`, `config/misc_config.json` and a few unused attributes.

## [1.3.0b1] — 2026-08-28

Beta release. The two new capabilities below are only lightly tested against a
live instance — please report anything that misbehaves.

### Added

- **Read and write permissions from the CSV.** New columns `canread_base` /
  `canwrite_base` (the eLabFTW levels 10–50, or the words `owner`, `admins`,
  `team`, `everyone`, `public`) together with `canread_users`, `canread_teams`
  and `canread_teamgroups` (and their `canwrite` counterparts). They apply both
  when creating and when updating an entry. Only the lists actually filled in
  are replaced, so granting a user access never drops teams set elsewhere, and
  an invalid level or a non-numeric ID is skipped with a warning rather than
  sent.
- **Importing and patching templates.** Resource templates (`items_types`) and
  experiment templates (`experiments_templates`) can now be created and updated
  from a CSV through the same engine as entries, keyed on a `Template ID`
  column when updating. Title, main text, extra fields, tags and permissions all
  behave as they do for entries, including the `$delete_V`, `$delete_F` and
  `$rename$` markers — which makes it possible to rename or remove a field in a
  large template without clicking through the interface. Templates have no
  uploads or link sub-endpoints in eLabFTW, so attachment and link columns are
  ignored with a warning instead of being sent.

### Fixed

- Numeric ID columns tolerate the quote characters spreadsheets leave in a cell:
  a value typed as `"351, 352"` used to parse to nothing.
- The Windows build failed at "Creating virtual environment" when `python`
  resolved to the Microsoft Store alias. The build now locates a real
  interpreter (preferring the `py` launcher), calls the build environment
  directly instead of activating it, and stops at the first failing step.

### Changed

- Two comments no longer matched the code and were corrected: the rename prefix
  was still documented as `$rename->`, and the `patch_existing` docstrings still
  claimed tags are replaced although they are appended.

## [1.2.0] — 2026-07-28

### Added

- Rename extra fields during a CSV import with the `$rename$New Name` marker. The
  field keeps its value and definition; renaming onto an existing field name is
  skipped with a warning, and renaming a field the entry does not have is a no-op.
- Linux packaging: `scripts/package_linux.sh` builds a standalone binary and a
  `.deb` package that installs `elapi-plugins` to `/usr/bin` together with a
  desktop entry and icon.
- Extra fields of type *items* / *experiments* now create a real entity link in
  addition to storing the linked ID, mirroring the behaviour of the eLabFTW
  interface.
- Logging for previously silent code paths: page-fetch retries and retry
  exhaustion during export, the CSV delimiter-detection fallback, and the
  version-lookup fallback in the updater.

### Changed

- **Update semantics.** When updating an existing entry, the main text (`body`)
  is now **appended** to the existing text instead of replacing it. Tags,
  attachments and entity links are likewise appended, keeping what is already
  there. `title`, extra (template) fields, `date` and `category` continue to
  overwrite. To replace the main text, clear it first with `$delete_V`.
- Link columns are matched independently of spaces and underscores, so
  `experiments links`, `Experiments_Links` and `experimentslinks` are equivalent.
- Downloaded CSV templates use `;` as the delimiter and the column names the
  importer actually recognises, so they can be re-imported without edits.
- Build scripts were consolidated under `scripts/` and packaging definitions
  under `packaging/`; the Windows installer takes the version and architecture as
  parameters and includes both in the output file name.
- Packaging metadata (version, maintainer, description, URL) is read from
  `pyproject.toml` so it cannot drift from the project version.
- The `.xlsx` exports no longer contain eLabFTW's internal permission, booking,
  signing and bookkeeping columns. Both exports now share the same standard
  columns — `id`, `title`, `date`, `body`, `tags`, `category_title`,
  `status_title`, `fullname`, `team_name`, `modified_at`, `rating` — followed by
  the entry's extra fields.

### Fixed

- **Exports contained no extra fields and no main text.** eLabFTW's listing
  endpoints return a reduced record that carries neither `metadata` nor `body`,
  so the extra-field flattening silently produced nothing. Full records are now
  requested with the `full=1` query parameter.
- **Updating an entry that already had a main text did nothing at all.** The
  entry PATCH also re-sent the entire unchanged metadata — tens of kilobytes for
  template-based entries — and when the request was rejected the body update was
  lost with it, so the row was skipped without visible cause. The metadata is
  written separately, so it is no longer included, and a failing PATCH now logs
  the server's status and response.
- Entity links created through the API failed silently. eLabFTW requires an
  `{"action": "create"}` body on the links sub-endpoint; without it the API
  returned HTTP 500 and no link was created, while the import reported success.
- Link columns whose headers contained underscores were silently written into
  `metadata.extra_fields` instead of creating a link.
- The linked ID of an *items* / *experiments* extra field is stored as a JSON
  string. A numeric value was not rendered as a link by eLabFTW.
- `$delete_V` and `$delete_F` now modify the entry's stored metadata, so they
  actually clear a value or remove a field.
- The `Resource ID` / `Experiment ID` column is no longer written back as an
  extra field; it is only used to locate the entry being updated.
- The main-text column is matched on whole words, so a column such as
  `Antibody` is no longer mistaken for `body`.
- Attachment and file-path columns are matched regardless of underscores.
- The Windows build embeds the application icon, which was previously looked up
  at the wrong path and silently skipped.
- The macOS build names the `.dmg` as documented and tolerates either PyInstaller
  bundle layout when verifying the packaged `elapi` data files.
- The macOS build failed with `argument --add-data: Wrong syntax` when the
  project or interpreter path contained a space; the PyInstaller arguments are
  no longer word-split.
- `LICENSE` contained text copied from a GitHub project page; it now holds only
  the AGPL-3.0 licence text.

## [1.1.0] — 2026-05-05

### Added

- Download pre-filled CSV templates for a resource category or experiment
  template.

### Fixed

- Various import and export fixes.

## [1.0.1] — 2026-02-19

### Fixed

- Packaging and path-resolution fixes for the bundled applications.

## [1.0.0] — 2026-02-16

### Added

- First stable release: export resources and experiments to `.xlsx`, import
  entries from CSV, and a local web GUI.

[1.3.0]: https://github.com/sfb1638/elAPI_Plugins/compare/v1.2.0...v1.3.0
[1.3.0b1]: https://github.com/sfb1638/elAPI_Plugins/compare/v1.2.0...1.3.0b1
[1.2.0]: https://github.com/sfb1638/elAPI_Plugins/compare/v1.1.0...v1.2.0
[1.1.0]: https://github.com/sfb1638/elAPI_Plugins/compare/v1.0.1...v1.1.0
[1.0.1]: https://github.com/sfb1638/elAPI_Plugins/compare/v1.0.0...v1.0.1
[1.0.0]: https://github.com/sfb1638/elAPI_Plugins/releases/tag/v1.0.0
