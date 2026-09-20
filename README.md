# LSP-px

CK3 modding in Sublime Text 4, powered by [Paradox Language Server](https://github.com/JDeffner/paradox-modding-toolkit) and the [Sublime LSP client](https://lsp.sublimetext.io/).

[User documentation](https://github.com/JDeffner/px-toolkit-sublime/wiki) covers installation, projects, settings, authoring, and troubleshooting.

[Contributing](CONTRIBUTING.md) · [Support](SUPPORT.md) · [Security reporting](SECURITY.md) · [Code of Conduct](CODE_OF_CONDUCT.md)

This repository contains the native package. Event graphs, dynasty data and GUI layouts are presented as searchable lists and readable reports. An external graphical designer is outside this release.

## Maintenance and project takeover

I don't use Sublime Text regularly, so anyone interested is welcome to take over this project's maintenance. I'll still try to fix issues when I have time, but the [main Paradox Modding Toolkit](https://github.com/JDeffner/paradox-modding-toolkit) will always be my priority. If you'd like to take over, please [open an issue](https://github.com/JDeffner/px-toolkit-sublime/issues) so we can arrange the handover.

## Install and set up

1. Install **LSP** through Package Control. Use LSP **2.13 or newer** and Sublime Text **build 4200 or newer**. Restart Sublime if LSP was installed after this package.
2. Until a public Package Control listing exists, build with `python scripts/build_package.py` and copy `dist/LSP-px.sublime-package` into Sublime's **Installed Packages** directory. Use Preferences → Browse Packages to locate the adjacent directory. For development, clone into `Packages/LSP-px`; that exact package name is required. Do not install both forms.
3. Run **Paradox: Setup** from the command palette. Detect or set your CK3 `game/` folder and, optionally, the logs folder containing generated script documentation.
4. Open your mod folder, containing `descriptor.mod`, and open a script under `common/` or `events/`. The server downloads on first use, then indexes in the background. The status bar shows when it is ready.
5. Optionally run **Paradox: Enable Semantic Highlighting** and choose the **Paradox** color scheme. This toggle affects all LSP servers. Inlay hints are enabled for the CK3 window; use LSP's inlay-hint toggle to hide them.
6. Run **Paradox: Install Tiger**, save your changes, then **Paradox: Run Tiger Validation** for deep CK3 checks. This is separate from the LSP's lightweight diagnostics.

The managed server checks the upstream GitHub release on each startup or restart and installs newer stable px-lsp versions automatically. It verifies downloads against the release asset's SHA-256 digest and extracts each version into its own directory under `Package Storage/LSP-px`. Running sessions keep their current server until restarted. Offline, rate-limited, or failed updates keep the newest complete cached installation. A first install falls back to the pinned **px-lsp 0.3.4** bootstrap from toolkit **v0.4.3** if release discovery fails. Set `px.auto_update_server` to `false` to keep the cached version without update checks; with no cache, this installs the bootstrap version. Syntax grammars and descriptor metadata update with the Sublime package, separately from the server.

Node.js 18+ is the runtime minimum; use a maintained Node release. Windows x64 can download and update the upstream bundled runtime with the server when Node is absent. Linux/macOS need an installed Node runtime. Set `px.node_path` if Sublime cannot find it.

To use an earlier server, run **Paradox: Choose LSP Version** from the command palette, Setup, or Tools menu. Choose a supported stable version (0.3.4 or newer) to download, verify and pin it, then restart the server automatically. The choice is saved in the current `.sublime-project`, or in global package settings when no saved project is open. Cached versions remain selectable offline. A failed download leaves settings and the running session unchanged. Choose **Automatic updates** to clear the pin and enable updates again. You can also set `px.server_version` directly, for example `"0.3.4"`; a pin takes priority over `auto_update_server`. Custom `server_command` settings still take priority over managed versions.

Windows x64 has been exercised locally with the real editor and CK3 installation. CI checks are configured for Windows, Linux and macOS; consult the workflow results and [validation record](docs/VALIDATION.md) before treating another platform as verified. Automatic Tiger installation supports Windows/Linux x64. Other architectures and macOS require a separately installed `ck3-tiger` through `px.tiger_path`.

## Editing features

The LSP supplies context completion and snippets, hover documentation, signature help, definitions, references, document/workspace symbols, guarded rename, lightweight diagnostics and code actions, folding, full semantic tokens, inlay hints, hover source links, color swatches/presentation conversion, and document formatting where its providers support the file type.

Script, localization, GUI, descriptor, info and embedded datafunction grammars come from the matching upstream release. Syntax detection is restricted to recognized files in configured game/mod/dependency roots. Unrelated `.txt` and YAML files keep their syntax. Explicit syntax selections are respected; **Use Paradox Syntax** provides an override. The `_*.info` grammar does not imply script-provider parity.

Use standard **LSP:** commands for navigation, rename, formatting, references and code actions. All extra commands are under **Paradox:** and Tools → Paradox Modding:

| Area | Native tools |
| --- | --- |
| Documentation | Scope at cursor, contextual snippets, complete generated snippet catalog/export, searchable Examples Wiki |
| Index | Health and resolved settings, mod inventory, dependencies, override winners, localization coverage |
| Localization | Create/edit keys, choose duplicate editable sites, split source view, text preview, explicit alternate-language command argument |
| Events | Relationships, event details and vocabulary, definition value options, theme-banner paths |
| Dynasties | Dynasty/house/member data and source navigation |
| GUI | Widget outline, effective properties/provenance, dependency and static-layout reports, palette preview data, save-value snapshots |
| GUI editing | Set/remove property, insert child, duplicate/delete widget, copy widget source |
| Authoring | New mod scaffold, descriptor completion/hover/validation/creation, schema-driven definition templates and property edits |
| Configuration | Open/create mod calendar, dependency playset and schema overlay |
| Validation | Tiger install/run/cancel, optional debounced runs on save, separate underlines and F4 result navigation |

Project-level reports refresh after debounced index changes. Cursor and GUI snapshot reports should be reopened after editing. Quick panels remain searchable; large reports display the first 500 entries and link to source where the server supplies locations.

## Settings

Open Preferences → Package Settings → LSP-px → Settings. Server settings live under `settings`; adapter settings live under `px`. Project overrides belong under `settings.LSP.LSP-px` in your `.sublime-project`:

```json
{
  "folders": [{"path": "."}],
  "settings": {
    "LSP": {
      "LSP-px": {
        "settings": {
          "gamePath": "C:/Games/Crusader Kings III/game",
          "parentPaths": ["../base_mod"],
          "hoverDetail": "full",
          "scopeInlayHints": true
        },
        "px": {"tiger_run_on": "manual"}
      }
    }
  }
}
```

Project values override global values; defaults fill omitted server fields. Relative server paths resolve against the first project folder. `descriptor.mod` identifies editable mod roots; set `modPath`/`workspaceMods` explicitly for an unconventional layout. `modPath` remains the stable default root while commands select the mod containing the active document. One game is supported per window. Parent folders, including playset parents and nested dependencies, and vanilla are read-only context for package writers, though Sublime itself still allows opening/editing files normally.

| Server setting | Default / choices |
| --- | --- |
| `gameId` | `"ck3"`; this adapter currently supports CK3 only |
| `gamePath` | `null`; CK3 `game/` directory |
| `logsPath` | `null`; generated CK3 script-doc logs, otherwise bundled knowledge is used |
| `modPath` | `null`; detect default editable mod |
| `workspaceMods` | `[]`; detect editable roots from open folders |
| `parentPaths` | `[]`; dependency roots, base first |
| `locLanguage` | `"english"`; reference/display language |
| `completionMode` | `"minimal"`, `"examples"`, `"names"` |
| `hoverDetail` | `"compact"`, `"standard"` (default), `"full"` |
| `scopeInlayHints` | `false`; inferred scope annotations |
| `indexAssets` | `true`; graphics definition/reference indexing |
| `calendar` | `null`, or `{ "epoch": 1, "after": "AD", "before": "BC" }`; optional twelve `months` names |
| `diagnosticsIgnore` | `[]`; ignored diagnostic codes |
| `diagnosticsIgnorePatterns` | `[]`; ignored workspace-relative globs |
| `diagnosticsVanilla` | `false`; diagnostics on opened vanilla files |
| `tracePerf` | `false`; server timing logs |

All sixteen are forwarded as a complete resolved object through the server's custom configuration notification. Path, language and asset changes rebuild the index. Completion/hover/diagnostic preferences update live. Mod-local `.px-toolkit/calendar.json` takes precedence over calendar settings. Playsets require a JSON object whose `parents` value is an array of nonempty path strings. Invalid playsets are rejected before replacing a running watcher or restarting the session. Playset/schema changes restart the server even when an HTML report has focus; the package owns a cancellable polling watcher for external mod/dependency creates, edits and deletes. Vanilla is not polled. Increase `px.watch_interval_seconds` for a large dependency tree; it must be a finite number of at least 1.

| Adapter setting | Meaning |
| --- | --- |
| `server_command` | Exact argument array for a manual/offline server; bypass managed installation |
| `auto_update_server` | Default `true`: check for newer stable servers on startup/restart; `false` keeps the newest cached version |
| `server_version` | Default `null`: follow `auto_update_server`; an exact version such as `"0.3.4"` pins that server, including an older cached version |
| `node_path` | Explicit Node executable |
| `heap_mb` | `null`: upstream policy, half RAM bounded to 2048–4096 MiB; explicit range 512–32768 |
| `storage_dir` | Override server cache directory |
| `data_dir` | Override parent of the server's `ck3/` data directory |
| `detect_syntax` | Automatic scoped assignment, default true |
| `excluded_mods` | Excluded editable roots |
| `inlay_hints` | Enable hints when the server connects, default true |
| `watch_interval_seconds` | Mod/dependency polling interval, default 3 |
| `tiger_path` | Separately installed Tiger executable |
| `tiger_run_on` | `"manual"` (default) or `"save"` |
| `tiger_timeout_seconds` | Default 180 |
| `require_descriptor` | Show a missing-descriptor status for explicit roots, default false |

Semantic highlighting, completion presentation, signature help, diagnostics styling and formatting on save are LSP/editor settings. For example, set `lsp_format_on_save` in syntax/project preferences if desired. The package does not silently enable formatting on save.

## Writing and validation

Localization and definition/GUI edits stay in buffers until you save. Existing dirty buffers take precedence over disk. Localization finds exact definitions in the requested language, including replace files and unsaved new buffers, before selecting a new override destination. Multiple editable sites use a destination picker. Returned source edits are checked against the source snapshot, translated from UTF-16 offsets, applied as one undo operation, and refused when stale. Localization saves use UTF-8 with BOM, preserve existing versions/comments and reject malformed or duplicate keys within a target file. Parent/vanilla localization overrides go into the editable mod's `localization/replace/` folder. Matching sibling files are preferred for new keys.

To author another language, invoke `px_localization` with `language` or `choose_language: true`, or change `settings.locLanguage`. This edits localization text; it does not provide machine translation. Templates are schema/example-derived starting points: fill their placeholders and validate with Tiger.

Tiger validates **saved files**. Unsaved files prevent a new run. A rejected replacement leaves the current run active; a valid replacement cancels it. Results use their own output panel and underlines, are cancelled/superseded coherently, and preserve results for other editable mods. The adapter accepts `.px-toolkit/ck3-tiger.conf` or an existing root `ck3-tiger.conf`; otherwise it supplies configured parent descriptors. LSP and Tiger support code/glob suppression and `# px:ignore CODE` / `# px:ignore-next-line CODE` annotations. Neither validator guarantees in-game behavior.

## Limits

- Provider guards remain upstream: rename is restricted to supported mod-owned script identifiers. GUI/localization initiation, inherited/vanilla identifiers and named graphics assets are not made renameable by this package.
- Formatting is the server's script document formatter. No range/on-type formatter, broad style controls, or equivalent GUI/localization formatter is added.
- No call/type hierarchy, implementation/declaration/type-definition provider, semantic selection ranges, document highlights, document-link provider, code lenses, file-rename reference updates, or general refactoring provider exists in the bootstrap server. Later server releases may add providers independently of this package.
- GUI layouts and save values are static data. There is no native JavaScript/canvas designer, live game renderer, debugger, event execution, or runtime scope inspection. Ironman/binary saves remain unsupported.
- Theme-banner/texture paths are navigable. This package does not add DDS conversion, a graphical dynasty/event canvas, a coat-of-arms editor, Workshop publishing, or an arbitrary color picker. DDS image hover rendering still needs a visual acceptance check.
- Signature help, completion richness and localization resolution depend on the server's knowledge and the loaded game/mod context. Missing game/log paths reduce available information.

## Troubleshooting and development

Use **Paradox: Index Health**, **LSP: Troubleshoot Server**, **LSP: Toggle Log Panel**, and **Paradox: Restart Server / Rebuild Index**. If LSP was installed after this package, restart Sublime. Manual servers must report px-lsp 0.3.4 or newer. Automatic update failures are logged in Sublime's console and keep the cached server; a checksum failure does not replace an existing installation. For a damaged installation, close Sublime, move the specific version directory under `Package Storage/LSP-px` aside, and restart. Use **Paradox: Choose LSP Version** to roll back or return to automatic updates. An unavailable pinned version reports an error instead of silently starting a different version.

Build: `python scripts/build_package.py`. Pure tests: `python -m unittest discover -s tests -v`. Real wire tests: `python scripts/ci_protocol.py`. Native CI uses [SublimeText/UnitTesting](https://github.com/SublimeText/UnitTesting). See [development and validation](docs/VALIDATION.md), [release checklist](docs/RELEASING.md), and [source notices](THIRD-PARTY-NOTICES.md).

Licensed under **GPL-3.0-or-later**, matching the main Paradox Modding Toolkit. See [COPYRIGHT](COPYRIGHT) for the license grant, [LICENSE](LICENSE) for the full text, and [third-party notices](THIRD-PARTY-NOTICES.md) for attribution and separately installed components. Game data is read from the user's installation, not distributed in this package. This project is not affiliated with Paradox Interactive.
