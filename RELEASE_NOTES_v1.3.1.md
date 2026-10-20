# v1.3.1: Skipped-Rows Log and Fixes for Creating Entries

A maintenance release for 1.3.0. It fixes the main text and the permissions not being saved when an entry is created from a template, adds a log of skipped rows, and makes the Mac app start again when you click its icon.

## Please read before updating

- **On macOS the app no longer shows as running in the Dock.** macOS never starts a second copy of an app it believes is running, so a click on the Dock icon could not replace the old copy. The app now starts its program in the background and exits at once, so every click starts afresh. Close the browser tab to stop the app, or open it again to restart it. Windows and Linux already worked this way.
- **More rows are reported as skipped.** In update mode, a row whose ID is missing or invalid, or whose update failed, used to be only counted. It is now listed in the warning and in the log. The warning's heading reads "Skipped N rows:".

## New

- **A log of skipped rows.** Every skipped row is written to its own file, `skipped_rows.log`, with a header for each import (file name and mode). The warning in the GUI ends with a link, **Open the full log of skipped rows**, that shows it. The warning lists only the first ten rows; the log has all of them. The file is in the `logs` folder of the project, or for an installed app in `~/.local/state/elAPI_Plugins/logs` (Linux), `~/Library/Logs/elAPI_Plugins` (macOS) or `%LOCALAPPDATA%\elAPI_Plugins\logs` (Windows).
- **macOS: a click on the app icon replaces a running copy.** See the first point above.

## Fixes

- **The main text and the permission columns are saved when creating an entry from a template.** eLabFTW ignores them in its creating request whenever a template is used, so a new entry kept the template's text (not your HTML) and the default permissions. They are now set with a follow-up request, the first thing done to a new entry, so a later failure cannot leave it more widely visible than the CSV asked. Updating existing entries was not affected. If you created entries from a template with 1.3.0, check their text and permissions.
- **The Windows installer includes `chardet`**, which the CSV import needs to detect a file's encoding.
- **A template or link-target lookup no longer ends an import** when elapi cannot read its saved settings; the lookup is skipped and the row is checked without it.
- **A failed creation names the title of the row** instead of `<unknown title>`.
- The version in the footer of the setup page was out of date.

## Under the hood

- The tests no longer depend on saved eLabFTW settings or on the operating system. A CI workflow now runs them, with the lint and type checks, on Linux, Windows and macOS.

## Install

Download the file for your system from the assets below:

| System | File |
|---|---|
| **Windows** | `elAPI_Plugins_x64_1.3.1_installer.exe`: run it and follow the steps |
| **macOS, Apple Silicon** | `elAPI_Plugins_arm64.dmg`: drag the app into Applications |
| **macOS, Intel** | `elAPI_Plugins_x86_64.dmg`: same |
| **Linux (Debian/Ubuntu)** | `elapi-plugins_1.3.1_amd64.deb`: `sudo apt install ./elapi-plugins_1.3.1_amd64.deb` |

On first launch macOS may block the app: open **System Settings > Privacy & Security** and click **Open Anyway**.

**Updating:** install over your current version. Your eLabFTW connection settings are kept. If an earlier copy is still running, starting the new one closes it.
