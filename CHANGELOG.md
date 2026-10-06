# Changelog

## 0.1.0, 6 October 2026

- Publish the verified 0.1.0-rc.3 functionality as a normal release. Keep the tested px-lsp 0.3.8 baseline from toolkit v0.5.5, which upstream marks as a prerelease.

## 0.1.0-rc.3, 6 October 2026

- Use px-lsp 0.3.8 from toolkit v0.5.5 (prerelease) as the tested baseline, while keeping version pins and cached rollback to 0.3.4 or newer.
- Refresh the script grammar from v0.5.5 and expose the DDS hover background setting.
- Check versioned rename edits against saved and unsaved buffers.
- Fix the Paradox color scheme and opening an existing source beside the current file. Install test packages with an atomic archive replacement.
- Add PX/ST branding, screenshot-based wiki guides, and a clear notice of limited future development.
- Automatically install newer stable language servers on startup/restart, verify GitHub asset digests, retain cached servers on failed updates, and provide an update opt-out.
- Add **Choose LSP Version** to pin an earlier supported stable server per project or globally, reuse cached versions offline, and return to automatic updates.
- Clarify the GPL-3.0-or-later license grant, add contribution/security/support/conduct policies and GitHub templates, and document maintainer handover.
- Protect nested and playset dependencies, validate playsets before watcher changes, preserve alternate-language localization targets, and fix Tiger replacement and report-focused restart behavior.

## 0.1.0 release candidate

- Native Sublime LSP helper pinned to px-lsp 0.3.4 (toolkit v0.4.3).
- Scoped CK3 syntax support and all sixteen server settings.
- Documentation, snippets, localization, dependency, event, dynasty and GUI tools.
- Buffer-safe source edits, localization BOM handling, descriptor and definition authoring.
- Verified server/Tiger installation, external-file polling, native validation diagnostics.
- Deterministic package builds, protocol tests, editor tests and platform CI.
