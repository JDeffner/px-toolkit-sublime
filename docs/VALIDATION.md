# Validation record

This file distinguishes performed checks from configured or outstanding checks.

## Local environment

- Windows x64, Sublime Text build 4200, its embedded Python 3.8.12.
- Isolated portable profile under `.dev/sublime`; the normal user profile is not modified.
- LSP installed with Package Control 4.2.8. Runtime integration uses public LSP 2.13 APIs.
- px-lsp 0.3.4, toolkit v0.4.3; real installed CK3 data and synthetic scratch mod fixtures.
- Node 24.12.0; standalone pure tests also run on Python 3.14.
- ck3-tiger 1.19.0, real executable and game installation.

## Performed

- 28 pure tests: scoped roots/languages, exclusions/parents/vanilla boundaries, spaces/Unicode/percent URIs, stable default root, UTF-16 including surrogate pairs, stale/overlap boundaries, localization headers/duplicates/escaping/comments/line endings, new-mod overwrite refusal, descriptor strings, archive traversal/links, atomic failed installation, file snapshots and Tiger parsing/suppression/null coordinates.
- Real stdio protocol smoke against the release: initialization/version, standard editing/navigation/symbol/token/format requests, native custom read requests, GUI and definition source edits, live configuration notification, shutdown and process exit. The runner waits for the full index, not merely the first mod definitions.
- Real Sublime integration: package load, scoped syntax, one registered session, correct resolved roots/settings, completion, hover, definition, semantic tokens, snippet catalog, buffer edit/undo, stale-edit refusal, localization BOM saved bytes and Unicode, GUI server edit and undo, HTML report creation.
- Real Tiger output parsing with CK3 installed; file-level warnings with null positions exposed a bug, now fixed with a regression test.
- Real Tiger invalid-property → fix → diagnostic-clear cycle and cancellation passed through package commands.
- Guided definition creation inserted the chosen identifier using a server-generated template.
- Managed cold installation inside Sublime passed. The verified Windows runtime fallback downloaded and ran Node successfully. Manual and managed server sessions both reached a healthy state.
- Cached server reuse passed with the downloader replaced by a test function that fails on any download attempt.
- Live hover/scope settings, external file creation/deletion and debounced open-report refresh passed in the editor.
- Full installed CK3 index reached approximately 476,000 definitions across 6,876 indexed files.
- The latest packed candidate passed 22 local editor workflow checks with no errors, including definition creation, Tiger fix/clear/cancel and buffer undo.
- New Mod created a BOM-encoded descriptor and project file and opened the new project in a separate Sublime window.
- Closing the isolated Sublime instance removed its server process; a subsequent process inventory found no remaining server from this test profile.
- Deterministic packed-package build excludes development tooling, downloaded runtime, cache, test profile and fixtures.

## CI and remaining release acceptance

All six jobs passed in [run 34536817440](https://github.com/JDeffner/px-toolkit-sublime/actions/runs/34536817440): pure/wire checks and real Sublime UnitTesting on Windows, Linux and macOS. The suite has 28 pure tests and 5 editor tests (33 run inside Sublime); the wire runner records 48 results including diagnostics. CI editor tests check API loading, syntax resources, comment toggling, command registration, real buffer undo/encoding and HTML sheets; the broader end-to-end CK3/Tiger workflows were performed locally on Windows.

Before a stable public tag, visually review completion/hover presentation, color swatches, inlay layout, DDS image hovers and source-link navigation. The native screenshot helper was unavailable during this session (`failed to connect native pipe`, OS error 2). No public listing or stable tag is claimed by the candidate build. The final artifact is built twice and its hash checked for equality; `dist/SHA256SUMS` records the resulting checksum.

There is no test here claiming in-game correctness, graphical designer parity, a multi-million-definition load test, macOS Tiger installation, or Package Control maintainer acceptance.

## Reproduce

```text
python -m unittest discover -s tests -v
python scripts/ci_protocol.py
python scripts/build_package.py
```

For local Windows editor integration:

1. `python scripts/setup_sublime_test.py` copies an installed Sublime into `.dev/sublime`.
2. Build with `--install ".dev/sublime/Data/Installed Packages"`.
3. Start the portable executable; wait for the harness to install LSP and its libraries. Restart the portable instance after dependencies finish installing. The harness records bootstrap results under `Data/`.
4. `scripts/protocol_smoke.py` creates `.dev/fixture mod ü`. Its fixture includes intentionally incomplete game content suitable for navigation and diagnostics tests.
5. Create portable `Data/editor-config.json` with absolute `node`, `server`, `game`, and optional `tiger` paths. Copy `scripts/editor_integration.py` to portable `Data/integration.py`; run portable `subl.exe --command px_test_run`. Inspect `Data/editor.json` for `complete: true` and no failures.

The test harness and scripts are excluded from the public `.sublime-package`. Do not install the harness into a normal profile. CI uses the separate UnitTesting tests in `tests/test_editor.py` and requires no CK3 game assets.

## Audit fixes, 11 September 2026

The local audit-fix suite has 33 pure tests and 13 native editor tests. All 46 passed inside Sublime Text 4200; standalone Python skips the 13 native tests. Regression coverage includes nested/playset dependency edit guards, malformed playsets retaining the current watcher and session, alternate-language and unsaved localization destinations, rejected Tiger replacements, and restart dispatch from HTML reports.

The broader local workflow passed 26 checks with the real server and CK3/Tiger installation. The added checks verify a playset-triggered restart while a report has focus, indexing of a new parent definition, and manual restart from a report. These results were recorded locally. Remote checks for this revision are listed on the pull request; earlier successful runs do not validate later changes.

## Automatic server updates, 20 September 2026

- Added 17 updater tests covering first install, upgrades, numeric version ordering, offline/rate-limited startup, metadata validation, checksum and archive failures, interrupted downloads, opt-out, manual commands, cache validation and Windows bundled-runtime updates.
- All 63 tests passed inside Sublime Text 4200 with Python 3.8.12, including the 13 native editor tests. Standalone Python passed the 50 non-editor tests and skipped those 13 native tests.
- The real protocol smoke passed against both bootstrap px-lsp 0.3.4 and the discovered stable px-lsp 0.3.5 from toolkit v0.4.4. `python scripts/ci_protocol.py --latest` exercises the updater and checks the selected server's reported version; CI now runs this alongside the bootstrap check.
- The packed package started a managed 0.3.5 session in the isolated Sublime Text 4200 profile, without a manual server command. It retained the 0.3.4 installation and completed indexing 476,077 definitions from the installed CK3 game and local fixtures.
- Live update verification was performed on Windows x64. The automated Windows bundled-runtime cases use synthetic archives; no new claim is made for a live bundled-runtime, Linux or macOS update in this revision.

Updates take effect at server startup/restart. Cached fallback covers discovery, download and extraction failures; it is not an automatic rollback after a server starts and later encounters a protocol or runtime error.

## Server version selection, 20 September 2026

- The suite now has 25 installer tests and 21 native editor tests, including eight version-picker tests. All 79 tests passed inside Sublime Text 4200 with Python 3.8.12. Standalone Python passed 58 tests and skipped the 21 native tests.
- Added coverage for exact version pins, cached downgrades without network access, unavailable versions, release-history pagination, matching Windows runtimes, project/global persistence, failed installation preserving settings, and returning to automatic updates.
- In the isolated editor, selecting 0.3.4 saved the project pin and started that server. A manual restart retained 0.3.4. Choosing Automatic updates cleared the saved pin, enabled updates, and started a healthy 0.3.5 session.
- The live upstream release list offered supported versions 0.3.4 and 0.3.5. Real protocol checks passed against both versions. No new live platform claim is made beyond Windows x64.
