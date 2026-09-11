# Contributing to LSP-px

Contributions and new maintainers are welcome. Joël does not regularly use Sublime Text and works on this package when time allows. The [main Paradox Modding Toolkit](https://github.com/JDeffner/paradox-modding-toolkit) remains his priority. Reviews and fixes have no guaranteed turnaround. To take over maintenance, open an issue to arrange a handover.

## Where to start

- Report an editor problem with the [bug form](https://github.com/JDeffner/px-toolkit-sublime/issues/new/choose) and a small example.
- Propose a workflow improvement or help test Sublime on Windows, Linux, or macOS.
- Improve documentation or verify completion, hover, inlay hints, colors, and image hovers in the real editor.
- Report vulnerabilities privately using [SECURITY.md](SECURITY.md). Follow the [Code of Conduct](CODE_OF_CONDUCT.md) in project discussions.

This repository owns the Sublime adapter, configuration, source writers, package installation, and native commands. The toolkit owns the language server and game knowledge. If a problem also occurs in another client using the same server, include that evidence and link an upstream issue when appropriate.

## Development setup

Use Python 3.12 or newer for repository scripts, a maintained Node.js release for server checks, Sublime Text 4 build 4200 or newer, and LSP 2.13 or newer. Plugin code must remain compatible with Sublime's Python 3.8 runtime. Most tests use synthetic fixtures and do not need CK3. The full local editor/Tiger workflow needs your own CK3 installation.

```text
git clone https://github.com/JDeffner/px-toolkit-sublime.git
cd px-toolkit-sublime
git switch -c fix/describe-the-change
python -m unittest discover -s tests -v
python -m compileall -q lib plugin.py
python scripts/ci_protocol.py
python scripts/build_package.py
```

The protocol check downloads the pinned, hash-verified server on first use. Later runs reuse the cached installation. No JavaScript dependency install is needed for ordinary adapter work. Use pnpm for the upstream generation tools when needed; see [third-party notices](THIRD-PARTY-NOTICES.md).

For live source development, clone into a folder named exactly `LSP-px` under an isolated Sublime profile's `Packages` directory. For packed testing, install `dist/LSP-px.sublime-package` in that profile's `Installed Packages` directory. Do not install both forms. Install the separate LSP package before testing, then restart Sublime.

The [validation guide](docs/VALIDATION.md) describes the Windows portable test profile and native harness. Keep game, server, and Tiger paths in the ignored local configuration. Do not put the harness in your normal editor profile.

## Code map

| Path | Responsibility |
| --- | --- |
| `plugin.py` | LSP lifecycle, commands, editor events, and guarded writes |
| `lib/core.py` | Settings, roots, file ownership, URIs, and UTF-16 coordinates |
| `lib/authoring.py` | Localization targets/writes and descriptor helpers |
| `lib/install.py`, `lib/tiger.py`, `lib/watcher.py` | Downloads, validator processes, and external changes |
| `lib/ui.py` | Native reports, pickers, and source navigation |
| `syntaxes/`, `data/`, `vendor/` | Resources derived from pinned upstream source |
| `scripts/` | Generation, packaging, and local integration checks |
| `tests/` | Pure tests and tests requiring the real Sublime API |

## Changes and verification

Keep changes focused and inspect callers before changing an interface. Derive game knowledge from the toolkit or game data rather than inventing vocabulary in the adapter. Use supported LSP APIs. Preserve upstream attribution when regenerating resources.

Package writers must protect parent and vanilla files, preserve unsaved text, reject stale edits, and maintain CK3 encoding rules. Validate configuration, archive paths, downloads, and subprocess inputs at their boundaries. Do not bypass checksums to work around a download failure.

Add regression tests for changed behavior. Test through the relevant editor command when behavior depends on Sublime. Standalone Python skips native tests; report those skips. A successful server request does not by itself establish that a feature works visually. Record what you actually tested and any limits. The existing CI workflow runs pure/protocol and native editor checks on three operating systems.

If menus or settings change, update their generator and regenerate the checked-in output:

```text
python scripts/generate_menus.py
python scripts/generate_schema.py
```

For packaging changes, inspect the archive and verify that builds remain repeatable. Do not commit `.dev`, `dist`, caches, credentials, machine-specific paths, game assets, or private mod/save data. Use minimal samples you have permission to share.

## Pull requests

Open a branch and PR against `main`. Explain the problem, resulting behavior, and verification. Update relevant documentation and add a changelog entry under Unreleased for user-facing changes. For substantial new behavior, discuss the intended workflow first. Maintainers decide when to merge or release; do not publish a release as part of an ordinary fix.

Wiki corrections can be proposed as exact text in an issue or PR. Maintainers synchronize the [wiki](https://github.com/JDeffner/px-toolkit-sublime/wiki) with accepted changes. See [SUPPORT.md](SUPPORT.md) for questions and [the release guide](docs/RELEASING.md) for maintainer procedures.

## License

This project uses **GPL-3.0-or-later**, matching the main toolkit. Contributions are submitted under that license. Only submit work you have permission to contribute, preserve required notices, and identify any external source and its license. No separate contributor license agreement or copyright transfer is required. See [COPYRIGHT](COPYRIGHT), [LICENSE](LICENSE), and [third-party notices](THIRD-PARTY-NOTICES.md).
