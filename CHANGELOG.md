# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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

[1.2.0]: https://github.com/sfb1638/elAPI_Plugins/compare/v1.1.0...v1.2.0
[1.1.0]: https://github.com/sfb1638/elAPI_Plugins/compare/v1.0.1...v1.1.0
[1.0.1]: https://github.com/sfb1638/elAPI_Plugins/compare/v1.0.0...v1.0.1
[1.0.0]: https://github.com/sfb1638/elAPI_Plugins/releases/tag/v1.0.0
