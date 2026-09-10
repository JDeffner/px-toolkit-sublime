# LSP-px

CK3 modding in Sublime Text 4, powered by [Paradox Language Server](https://github.com/JDeffner/paradox-modding-toolkit) and the [Sublime LSP client](https://lsp.sublimetext.io/).

This repository contains the native package. Event graphs, dynasty data and GUI layouts are presented as searchable lists and readable reports. An external graphical designer is outside this release.

## Install and set up

1. Install **LSP** through Package Control. Use LSP **2.13 or newer** and Sublime Text **build 4200 or newer**. Restart Sublime if LSP was installed after this package.
2. Until a public Package Control listing exists, build with `python scripts/build_package.py` and copy `dist/LSP-px.sublime-package` into Sublime's **Installed Packages** directory. Use Preferences → Browse Packages to locate the adjacent directory. For development, clone into `Packages/LSP-px`; that exact package name is required. Do not install both forms.
3. Run **Paradox: Setup** from the command palette. Detect or set your CK3 `game/` folder and, optionally, the logs folder containing generated script documentation.
4. Open your mod folder, containing `descriptor.mod`, and open a script under `common/` or `events/`. The server downloads on first use, then indexes in the background. The status bar shows when it is ready.
5. Optionally run **Paradox: Enable Semantic Highlighting** and choose the **Paradox** color scheme. This toggle affects all LSP servers. Inlay hints are enabled for the CK3 window; use LSP's inlay-hint toggle to hide them.
6. Run **Paradox: Install Tiger**, save your changes, then **Paradox: Run Tiger Validation** for deep CK3 checks. This is separate from the LSP's lightweight diagnostics.

The managed server is pinned to **px-lsp 0.3.4**, from toolkit **v0.4.3**. Downloads are verified against SHA-256 hashes and extracted into `Package Storage/LSP-px`, never executed inside the packed package. Existing installations work offline. Node.js 18+ is the runtime minimum; use a maintained Node release. Windows x64 can download the upstream bundled runtime when Node is absent. Linux/macOS need an installed Node runtime. Set `px.node_path` if Sublime cannot find it.

Windows x64 has been exercised locally with the real editor and CK3 installation. CI checks are configured for Windows, Linux and macOS; consult the workflow results and [validation record](docs/VALIDATION.md) before treating another platform as verified. Automatic Tiger installation supports Windows/Linux x64. Other architectures and macOS require a separately installed `ck3-tiger` through `px.tiger_path`.

## Editing features

The LSP supplies context completion and snippets, hover documentation, signature help, definitions, references, document/workspace symbols, guarded rename, lightweight diagnostics and code actions, folding, full semantic tokens, inlay hints, document links, color swatches/presentation conversion, and document formatting where its providers support the file type.

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

Project values override global values; defaults fill omitted server fields. Relative server paths resolve against the first project folder. `descriptor.mod` identifies editable mod roots; set `modPath`/`workspaceMods` explicitly for an unconventional layout. `modPath` remains the stable default root while commands select the mod containing the active document. One game is supported per window. Parent folders and vanilla are read-only context for package writers, though Sublime itself still allows opening/editing files normally.

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

All sixteen are forwarded as a complete resolved object through the server's custom configuration notification. Path, language and asset changes rebuild the index. Completion/hover/diagnostic preferences update live. Mod-local `.px-toolkit/calendar.json` takes precedence over calendar settings. Playset/schema changes restart the server; the package owns a cancellable polling watcher for external mod/dependency creates, edits and deletes. Vanilla is not polled. Increase `px.watch_interval_seconds` for a large dependency tree.

| Adapter setting | Meaning |
| --- | --- |
| `server_command` | Exact argument array for a manual/offline server; bypass managed installation |
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

Localization and definition/GUI edits stay in buffers until you save. Existing dirty buffers take precedence over disk. Returned source edits are checked against the source snapshot, translated from UTF-16 offsets, applied as one undo operation, and refused when stale. Localization saves use UTF-8 with BOM, preserve existing versions/comments and reject malformed or duplicate keys within a target file. Parent/vanilla localization overrides go into the editable mod's `localization/replace/` folder. Matching sibling files are preferred for new keys.

To author another language, invoke `px_localization` with `language` or `choose_language: true`, or change `settings.locLanguage`. This edits localization text; it does not provide machine translation. Templates are schema/example-derived starting points: fill their placeholders and validate with Tiger.

Tiger validates **saved files**. Unsaved files prevent a run. Results use their own output panel and underlines, are cancelled/superseded coherently, and preserve results for other editable mods. The adapter accepts `.px-toolkit/ck3-tiger.conf` or an existing root `ck3-tiger.conf`; otherwise it supplies configured parent descriptors. LSP and Tiger support code/glob suppression and `# px:ignore CODE` / `# px:ignore-next-line CODE` annotations. Neither validator guarantees in-game behavior.

## Limits

- Provider guards remain upstream: rename is restricted to supported mod-owned script identifiers. GUI/localization initiation, inherited/vanilla identifiers and named graphics assets are not made renameable by this package.
- Formatting is the server's script document formatter. No range/on-type formatter, broad style controls, or equivalent GUI/localization formatter is added.
- No call/type hierarchy, implementation/declaration/type-definition provider, semantic selection ranges, document highlights, code lenses, file-rename reference updates, or general refactoring provider exists in the pinned server.
- GUI layouts and save values are static data. There is no native JavaScript/canvas designer, live game renderer, debugger, event execution, or runtime scope inspection. Ironman/binary saves remain unsupported.
- Theme-banner/texture paths are navigable. This package does not add DDS conversion, a graphical dynasty/event canvas, a coat-of-arms editor, Workshop publishing, or an arbitrary color picker. DDS image hover rendering still needs a visual acceptance check.
- Signature help, completion richness and localization resolution depend on the server's knowledge and the loaded game/mod context. Missing game/log paths reduce available information.

## Troubleshooting and development

Use **Paradox: Index Health**, **LSP: Troubleshoot Server**, **LSP: Toggle Log Panel**, and **Paradox: Restart Server / Rebuild Index**. If LSP was installed after this package, restart Sublime. If a manual server reports an older version, use the pinned release. If a download fails, inspect the error; a checksum failure does not replace an existing installation. For a damaged installation, close Sublime, move the specific version directory under `Package Storage/LSP-px` aside, and restart.

Build: `python scripts/build_package.py`. Pure tests: `python -m unittest discover -s tests -v`. Real wire tests: `python scripts/ci_protocol.py`. Native CI uses [SublimeText/UnitTesting](https://github.com/SublimeText/UnitTesting). See [development and validation](docs/VALIDATION.md), [release checklist](docs/RELEASING.md), and [source notices](THIRD-PARTY-NOTICES.md).

GPL-3.0; see [LICENSE](LICENSE). Game data is read from the user's installation, not distributed in this package. This project is not affiliated with Paradox Interactive.
