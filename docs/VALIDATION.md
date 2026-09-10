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
- Deterministic packed-package build excludes development tooling, downloaded runtime, cache, test profile and fixtures.

## CI and remaining release acceptance

`.github/workflows/test.yml` runs pure/wire checks and Sublime UnitTesting on Windows, Linux and macOS. Configuration of a job is not evidence that it passed; inspect the branch's actual run.

Before a stable public tag, complete the latest packed build's integration run, Tiger fix/clear and cancellation checks, report refresh/settings/external-watch checks, managed cold/warm installation, and review platform CI. A visual check of completion/hover presentation, color swatches, inlay layout, DDS image hovers and source links remains necessary: the native screenshot helper was unavailable during this session (`failed to connect native pipe`, OS error 2).

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
