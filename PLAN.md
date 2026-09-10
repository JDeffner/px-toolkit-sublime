# Paradox Modding Toolkit for Sublime Text: implementation plan

Drafted 2026-09-10. This is a source audit and implementation proposal, not a claim of a working or tested Sublime integration.

**Recommendation:** publish one discoverable package, provisionally `LSP-px`, that includes CK3 syntaxes, an LSP helper, and native modding commands. Use the existing Sublime `LSP` package for protocol transport and standard editor features. Keep language knowledge in `@px-lsp/server`; implement editor integration in Python. Target Sublime Text 4, with Windows, macOS and Linux as release targets subject to platform verification.

The server can already supply almost all the desired language intelligence. The substantial work is installation, correct file/root detection, settings propagation, localization writers, Tiger integration, and presenting the custom protocol in Sublime's UI.

**Evidence baseline**

- Local toolkit checkout: clean, commit `f517501e0edb83fb0473a5db1c2a9c42afb06886`, tag `v0.4.3`.
- Server package: `@px-lsp/server` **0.3.4**. Protocol package: `@px-lsp/protocol` **0.2.4**. These versions are independent of the toolkit tag and the future Sublime package version.
- Server implementation and handlers: [server.ts](https://github.com/JDeffner/paradox-modding-toolkit/blob/f517501e0edb83fb0473a5db1c2a9c42afb06886/packages/server/src/server.ts).
- Settings, methods and client capabilities: [protocol.ts](https://github.com/JDeffner/paradox-modding-toolkit/blob/f517501e0edb83fb0473a5db1c2a9c42afb06886/packages/protocol/src/protocol.ts).
- Process/distribution contract: [Embedding](https://github.com/JDeffner/paradox-modding-toolkit/blob/f517501e0edb83fb0473a5db1c2a9c42afb06886/docs/EMBEDDING.md).
- Sublime LSP release inspected: `4070-2.13.0`, including its public plugin API, hover navigation, color presentation, folding and session capabilities. [Release source](https://github.com/sublimelsp/LSP/tree/4070-2.13.0).
- Some toolkit prose is behind the implementation: folding now covers localization and GUI; colors are implemented; `tracePerf` exists; calendar month normalization is more restrictive than the VS Code settings description suggests. Prefer the pinned implementation and contract tests when they disagree.

**1. Standard editor features available from the current server**

“Available” means the server implements the operation and Sublime has a suitable client surface. Installation and integration verification are still required.

| Feature | Script / graphics script | Localization | GUI | Implementation and limits |
|---|---|---|---|---|
| Ranked completion and completion details | Yes | Expressions and format tags | Widgets, properties, templates, expressions | Preserve server order and snippet support. Include documentation and insertion previews from completion resolve. Do not promise identical VS Code popup ranking: the editors have different filtering behavior. |
| Completion insertion modes | Yes | Not a general loc-authoring mode | Not a general GUI template mode | Expose `minimal`, `examples`, `names`; the setting controls ordinary script keyword insertion. Explicit snippet templates retain their own bodies. |
| Hover documentation | Yes | Datafunctions and format tags | Yes | Plain Markdown works. Engine docs, scope context, indexed definitions and local constants depend on the context. |
| Go to definition | Yes | Names within supported expressions | Types, templates, block overrides and supported references | Mod, parent and vanilla navigation. Graphics navigation is limited to indexed/resolved reference forms. |
| Find references | Yes | From loc-key lines | No standard handler | GUI dependencies can be inspected through custom methods, but that is not a complete replacement for GUI Find References. |
| Rename symbol / prepare rename | Restricted yes | Cannot initiate here | Cannot initiate here | Only indexed names defined exclusively in editable mod content. Vanilla/parent definitions and overrides are refused. Named graphics asset rename is explicitly refused because not every reference form is indexed. A rename initiated in script can update indexed localization sites. |
| Signature help | Yes | Supported expression calls | Supported expression calls | Use existing client popup. |
| Document symbols | Yes | Yes | Yes | LSP symbol picker; optional package outline view later. |
| Workspace symbols | Yes, across the index | Included in index search | Included where indexed | One searchable symbol interface, independent of the active document language. |
| Folding | Braces, comment runs, `###` sections | Language body, comment runs, sections | Braces, comments, sections | Use LSP fold commands. Fold-gutter presentation is an editor integration detail, not an identical VS Code UI guarantee. Descriptor and info files can also use server folding if routed. |
| Document formatting | Yes | No | No | Current formatter adjusts leading indentation to tabs only. It ignores configurable spaces/tab width and does not perform general reformatting. No server range-formatting or on-type-formatting handler. |
| Semantic highlighting | Yes | No | Yes | Eight standard token types plus `defaultLibrary`: engine effects/triggers, targets, modifiers, reusable scripts, events, values and loc references. Actual coverage follows classifier/index coverage. |
| Inlay hints | Loc previews, local constants, optional scopes and calendar dates | Reference-language overlay | Loc previews and local constants; shared provider handles applicable hints | Turn on client rendering. Scope inference is advisory. Translation overlay displays existing reference text; it does not translate. |
| Structural diagnostics | Yes | Yes | Parser structural checks | Braces/syntax and layout traps; script adds conservative event-reference and required-loc checks. Localization adds header, filename, BOM and entry-format checks. |
| Localization quick fix | Yes, from missing-required-loc diagnostic | No general code-action provider | No general code-action provider | Existing fallback creates/appends a localization entry through `WorkspaceEdit`; richer edit/open commands require the adapter. No generic “fix every error” provider. |
| Color swatches and notation conversion | Yes | No | Yes | `documentColor` + `colorPresentation`. Server handles RGB, HSV, HSV360, hex and supported untagged values. Sublime's existing command changes representation of the current color; arbitrary visual color selection needs an additional picker UI/integration. |
| Indexing progress and logs | Yes | Same session | Same session | Standard work progress/log messages plus custom health notifications. |

Script language includes `.asset` files routed as `paradox`, with classification from their game-relative path. This does not turn binary `.mesh`, `.anim` or `.dds` files into editable language documents. Use `paradox-loc` for CK3 localization, not a generic YAML language id, and `paradox-gui` for GUI.

Reference behavior: [rename guards](https://github.com/JDeffner/paradox-modding-toolkit/blob/f517501e0edb83fb0473a5db1c2a9c42afb06886/packages/server/src/features/rename.ts), [folding](https://github.com/JDeffner/paradox-modding-toolkit/blob/f517501e0edb83fb0473a5db1c2a9c42afb06886/packages/server/src/features/folding.ts), [formatter](https://github.com/JDeffner/paradox-modding-toolkit/blob/f517501e0edb83fb0473a5db1c2a9c42afb06886/packages/server/src/features/formatting.ts), [Sublime color presentation](https://github.com/sublimelsp/LSP/blob/4070-2.13.0/plugin/color.py).

**2. Custom protocol coverage: implement native Sublime interfaces**

All names below have the `paradox/` prefix. These operations already exist; they need Python request handlers and UI, not a second language engine. Larger visual presentations remain optional.

| Methods | Proposed feature | Feasibility / boundary |
|---|---|---|
| `indexStats`, `reloadDocs` | Health report, index counts by kind/source, reload script docs | Straightforward commands and output panel. Reload Docs reparses existing dumps; it does not make CK3 generate them. |
| `modOverview` | Mod inventory with counts and source navigation | Native quick panel and linked report. |
| `locCoverage` | Missing, orphaned and untranslated-key report | Native report with language/mod filters. Classification is the server's, not proof of translation quality. |
| `overrides` | Override report showing winning mod/parent/vanilla definitions | Native report, open both sources, optional diff. Preserve first/last-wins distinctions. |
| `lookupLoc`, `locText` | Find/edit localization, side-by-side language editing, readable text preview | Native commands and minihtml. `locText` can return partially resolved expressions; display that state. Actual writing is client work. |
| `scopeAt` | Scope inspector at cursor, including chain and saved scopes | Status summary plus popup/report. Preserve arrays/uncertainty rather than claiming one certain scope. |
| `dependencies` | Definition dependency and usage browser, including GUI uses | Native picker drill-down. Do not label as standard LSP call hierarchy. |
| `exampleWiki`, `exampleWikiEntry` | Searchable in-editor documentation and corpus examples | Quick panel catalog, rich article view, click to source. Cache the compact catalog and fetch detail only on selection. |
| `snippets` | Insert a context-aware definition, child block or documented engine template | Quick panel with preview and Sublime snippet insertion. |
| `snippetCatalogue` | Search/export every generated script template and variant | Catalog/export command. If `indexing` is true, wait for index completion before presenting an empty catalog. |
| `eventGraph`, `eventDetail` | Event/on_action relationship browser and event inspector | Native incoming/outgoing lists and structured detail are feasible. A pan/zoom node canvas requires a separate visual frontend. |
| `eventVocabulary`, `eventValueOptions` | Guided event property/value editing and condition/effect pickers | Native multi-step commands feasible. Vocabulary does not itself implement the entire editor or runtime semantics. |
| `eventBanner` | Resolve event-theme banner asset | Show path/open target immediately. Image display needs texture decoding where the asset is DDS; method returns a path, not decoded pixels. |
| `dynastyTree` | Dynasty/house/member picker with relatives and jump-to-history | Native navigation feasible; graphical tree is additional UI work. Static history, not live genealogy simulation. |
| `definitionForm`, `definitionEdit` | Schema-driven creation and property editing of supported definitions | Quick-panel/input-panel wizard. Apply returned edits against the exact source snapshot. Client owns file creation, localization, icon selection and encoding. |
| `modifierFormats` | Player-facing modifier labels, signs, percentage display and available icon references | Text presentation feasible. Cropped texture icons require image handling. |
| `guiTree`, `guiWidgetInfo` | Widget outline; effective properties and template provenance; layout explanation | Native inspector with source navigation. |
| `guiDependencies`, `guiVocabulary` | Jump to scripted GUI/localization dependencies; insert widgets/properties | Native picker and command workflow. |
| `guiSourceEdit` | Source-preserving widget changes exposed as commands | Numeric move/resize and other supported operations can be implemented without a canvas. Honor refusal results, batch verdicts and source-version checks. |
| `guiLayout`, `guiPreview` | Layout inspection and palette previews | Inspect rectangles/data natively. Pixel previews need a renderer; fully interactive design needs a separate browser UI. |
| `guiSaveValues` | Load supported values from a CK3 save for static previews | Native file-selection command. Supported text/zip-packed saves only; ironman/binary rejection remains a server limit. Values are a snapshot. |
| `guiWidgetEdit` | None in new implementation | Deprecated: use `guiSourceEdit`. |

Also implement the protocol plumbing:

- Send `configChanged` with the **complete resolved settings object**, initially through `initializationOptions.settings` and subsequently when preferences/project configuration change. The server does not implement ordinary `workspace/didChangeConfiguration` as its settings path.
- Handle `status`, `progress`, `indexChanged`; keep health in the status bar and refresh open reports only when needed.
- Prefer standard watched-file notifications with a real watcher backend. `modFileChanged` is available if the package deliberately owns watching. Do not enable both paths for the same events.
- Register `px.editLocalization`, `px.openLocalizationSideBySide`, `px.showReferences`, `px.showExamplesWiki` once their implementations exist. Bridge code-action commands and allowlisted `command:` hover URLs separately; command links are not automatically VS Code-compatible.
- Enable `fileLinks` after verifying source/fragment navigation. Leave `hoverHtml` and `hoverIcons` false initially. Sublime does not implement VS Code theme variables, codicons or disclosure HTML verbatim.

Contract reference: [custom methods and capabilities](https://github.com/JDeffner/paradox-modding-toolkit/blob/f517501e0edb83fb0473a5db1c2a9c42afb06886/docs/PROTOCOL.md). Sublime has a public helper API for custom notifications, commands and URI handlers: [LspPlugin migration/API guide](https://lsp.sublimetext.io/migrating_to_lsp_plugin/).

**3. Complete server settings exposure**

Use the wire names below in the package's documented server-settings object. Do not forward VS Code's `px.*` names verbatim. Offer global defaults and `.sublime-project` overrides, with user/project path selection and documented precedence.

| Setting | Value/default to expose | Meaning / update behavior |
|---|---|---|
| `gameId` | `"ck3"` | Explicit CK3 default. One game per server instance. Other games are future package scope even though the engine supports them. |
| `gamePath` | Path or null | CK3 `game/` directory. Change reloads data/index. |
| `logsPath` | Path or null | CK3 logs containing generated script docs/data dumps. Change reloads data/index. |
| `modPath` | Auto-resolved root, explicit override allowed | Active/default editable mod. Change rebuilds. |
| `parentPaths` | Ordered array, default `[]` | Dependency context, base first. Change rebuilds. |
| `workspaceMods` | Auto-resolved editable roots, explicit override allowed | Distinguish edited mods from read-only dependencies. Change rebuilds. |
| `locLanguage` | `"english"` | Indexed/display/reference localization language. Change rebuilds. |
| `completionMode` | `"minimal"`, `"examples"`, `"names"` | Default minimal. Hot update; no reindex needed. |
| `hoverDetail` | `"compact"`, `"standard"`, `"full"` | Default standard. Hot update; reopen hover. Plain Markdown has no disclosure expansion, so expose Full explicitly. |
| `scopeInlayHints` | `false` | Optional inferred scopes. Update settings and ensure visible hints re-request. |
| `indexAssets` | `true` | Graphics asset definition/reference indexing. Toggle rebuilds the index. |
| `calendar` | Unset, or `{epoch, after, before?, months?}` | Display calendar, not a change to CK3 time simulation. Prefer twelve month-name strings; fixed engine month lengths apply. Mod-local calendar file takes precedence. Re-request hints/hover after change. |
| `diagnosticsIgnore` | `[]` | Suppress codes. Immediate revalidation. |
| `diagnosticsIgnorePatterns` | `[]` | Workspace-relative suppression globs. Immediate revalidation. |
| `diagnosticsVanilla` | `false` | Optional diagnostics on opened game files. Does not imply validating every vanilla file or authorizing edits. |
| `tracePerf` | `false` | Server request/index timing logs. Hot update. |

Initialization/process options also need support:

- `storageDir`: create a persistent directory in package storage before launch; expose an advanced override.
- `dataDir`: optional advanced override pointing to the parent of `ck3/`, not to `ck3/` itself. Normally preserve the release's `dist/` and `data/` sibling layout.
- `client`: adapter-controlled capability declarations, not user-facing toggles that can claim unimplemented features.
- Skip deprecated `wikidocsDir` and `clientCommands` in new configuration; document migration only if needed.
- Package-owned options: managed/manual server selection, command/path override, runtime path, compatible pinned server version, heap limit, diagnostics/log access, restart/reload commands, enabled/root detection and editable-root exclusions.
- Editor-owned options: semantic highlighting, inlay-hint visibility/length, signature help, completion behavior, diagnostics display, formatting on save and theme rules. Keep them distinct from server settings. `semantic_highlighting` and `show_inlay_hints` are both false in the inspected LSP defaults; provide an explicit CK3 setup preset/toggle and explain scope without silently changing other languages.

The server also consumes mod-local `.px-toolkit/schema.json`, `playset.json` and `calendar.json`. Preserve those workflows; add commands to open/create validated templates. Parent load order is not merely filesystem sidebar order. Edits to playsets/schema must trigger a known reload/reindex path; do not assume the server's default watcher globs cover these configuration files.

The VS Code settings `px.parentMods`, `px.excludedMods`, `px.enableForWorkspace`, `px.diagnostics.requireDescriptor`, `px.tigerPath`, `px.tigerRunOn`, `px.modProjectsDir`, workshop settings, `px.coaLibraryDir`, sidebar controls and webview-development settings are **not additional LSP settings**. Some can have Sublime equivalents; each needs client implementation. `px.trace.server` maps to client logging controls; `px.trace.perf` maps to server `tracePerf`.

**4. Features possible with additional client tooling**

| Feature | What must be built |
|---|---|
| Deep CK3 validation | Run `ck3-tiger` as a separate process. Add executable discovery/install, manual run, debounced optional on-save run, cancellation, report parsing and separate diagnostics. Apply code/glob/inline suppression consistently. Do not inject fake server-origin diagnostics through private LSP internals; use a package-owned diagnostics presentation or a documented integration. |
| Rich localization workflow | Port editor-independent rules for key placement, UTF-8 BOM, matching filename/header, conflict checks and multi-language editing. Existing keys/new sibling keys/vanilla overrides require different target selection. Keep dirty buffers authoritative and do not overwrite them from disk. |
| Descriptor support | Add descriptor syntax, field completion/hover/validation and optional missing-descriptor creation. Current rich implementation is in the VS Code client/shared modules, not the main LSP providers. Syntax and folding alone do not provide full parity. |
| `_*.info` support | Syntax, comments, folding and source browsing first. Do not advertise engine completion/hover parity for the `paradox-info` id. |
| New mod / definition scaffolds | Root setup and file writing in Python; reuse `definitionForm`, `definitionEdit` and snippet requests where appropriate. Complete mod scaffolding is not one existing server request. |
| Calendar insertion / localization generation | Date-display hints are already server-side. Date-entry commands and generation of game localization need client-side/shared-library logic. |
| DDS preview and conversion | Hover texture previews already arrive as data images and may render in Sublime; verify mdpopups. A standalone viewer/converter needs a decoder/encoder bridge or external tool. The server package exports DDS modules but has no general DDS decode/encode wire request. |
| Arbitrary color picker | Build a picker/input command and send the selected RGBA through `colorPresentation`; the standard Sublime format-change action is not a full picker. |
| Advanced graphical tools | Event canvas, dynasty canvas, GUI designer, coat-of-arms designer, map/3D tools and Workshop management need their own frontend/workflow and, in several cases, additional backend APIs. They do not arrive by connecting to LSP. |

**5. What cannot be delivered as a configuration-only wrapper**

- Standard call/type hierarchy, go-to implementation/declaration/type-definition, semantic selection ranges, document highlights, code lenses, file-rename reference updates, range/on-type formatting and general refactorings: the current server advertises no corresponding providers. Sublime supporting them does not make the server supply them. Add server work if these become requirements; dependency/event browsing can cover some user needs meanwhile.
- Safe rename for GUI/localization initiation, inherited/vanilla identifiers and named graphics assets: unavailable under the current server's guards. A naive text rename is not equivalent.
- General configurable formatting or localization/GUI formatting: requires an upstream formatter/provider extension or a separate formatter.
- Deep semantic validation from this LSP alone: Tiger remains the intended validator. No blanket correctness guarantee for CK3 script, even with both tools.
- Existing VS Code React/JavaScript webviews inside native Sublime panels: no equivalent browser runtime. Sublime minihtml has a restricted tag/layout system and no supported webview JavaScript/canvas environment. Build native reports/commands or an optional external browser companion. [minihtml reference](https://www.sublimetext.com/docs/minihtml.html).
- Exact in-game rendering, live event execution/stepping, breakpoints, live scopes, or complete dynamic localization evaluation: neither ordinary LSP nor the current custom API supplies a game runtime/debugger. Static layout/save snapshots do not remove that limit.
- Ironman/binary save support through `guiSaveValues`: explicitly unsupported by the current server.
- Identical VS Code visuals, completion filtering, arbitrary theme colors or folding affordances: adapt to Sublime and verify the user workflow.
- A guarantee of automatic public Package Control acceptance: submission has maintainer review. Build and validate the release, then submit through the documented channel process.

None of the native language features require rewriting the server in Python. Additional wire methods are justified only where reusable existing logic is not exposed (for example generic DDS operations or descriptor validation).

**6. Ordered delivery plan**

1. **Foundation and a real editor proof.** Create `LSP-px` package metadata, Python 3.8 plugin entry point compatible with the inspected LSP release, CK3 script/localization/GUI/descriptor/info syntaxes and settings/help commands. Detect mod roots from `descriptor.mod`, explicit settings and configured game/parent roots. Avoid taking every `.txt` or `.yml` on the machine; preserve explicit syntax choices and offer a manual Paradox mode. Connect one stdio server per compatible window/project context. Verify a real script completion, hover, definition jump and diagnostic in Sublime before expanding the UI.

2. **Complete standard LSP and settings.** Map syntax scopes to exact language ids, enable snippet support via LSP, handle full settings initialization/live changes, configure Markdown syntax blocks, semantic tokens, hints, folding and color conversions. Add workspace-root/parent distinction, watcher installation/health check, server health panel, persistent cache and logs. Support all sixteen current server settings. This is the first usable alpha.

3. **Native extended tools.** Add scope inspector, snippet insertion/catalog export, Examples Wiki, localization lookup/edit/split view, coverage, overrides, dependency browser and mod inventory. Bridge the four client commands and hover source links. Refresh views on index changes with caching, debouncing and request-generation checks. Add native event/dynasty/widget inspectors and property commands to cover the remaining useful read/edit endpoints.

4. **Validation and authoring quality.** Integrate Tiger, encoding-safe localization creation/editing, descriptor support, and guided definition creation. Validate source-version checks and undo behavior. Make this the public beta with both lightweight structural feedback and explicit deep-validation commands.

5. **Public release hardening.** Test clean installs and upgrades on each advertised platform, root detection, missing dependencies, parent mods, large workspaces, external edits, spaces/non-ASCII paths, dirty documents and process cleanup. Ship setup instructions, feature limitations, changelog, issue templates, compatible server-version mapping and matching source/license notices. Put the Sublime package at repository root and tag semantic releases for Package Control. [Submission requirements](https://packagecontrol.io/docs/submitting_a_package).

6. **Optional visual companion after native release.** If graphical parity matters, build an external browser frontend for the event/dynasty canvases and GUI designer. Feed it data from the existing server session through a narrow local bridge, preserve source-buffer ownership, and apply edits back through Sublime. Rendering and asset transport are additional components. This should not delay the useful native package.

**Distribution decision**

Use a package-managed, version-pinned server installation in writable package storage, with a manual `node + server.js --stdio` override for development/offline use. The current release offers a generic server payload and a self-contained Windows x64 payload; the other platforms require a suitable Node runtime or separately implemented managed-runtime provisioning. Preserve data layout, verify downloads, use atomic replacement and retain a working version on failed update. Check `serverInfo.version` before enabling newer custom methods.

The current server requires Node 18 or newer; choose a maintained compatible runtime when packaging rather than treating the minimum as the preferred runtime. Pass a configurable heap limit before the script path, defaulting to the upstream host's memory-aware policy. Capture stderr, keep stdout as protocol-only, and rely on proper LSP process id/shutdown handling to avoid orphaned index processes. No executable should be launched from inside a packed `.sublime-package`; install it into package storage.

For watching, use an installed LSP watcher backend such as `LSP-file-watcher-rust`, with compatibility checks and clear setup status. Merely requesting dynamic watcher registration is insufficient when no backend exists. A package-owned fallback is possible but must cover external create/change/delete events and deliberately advertise `ownFileWatcher`. [Watcher project](https://github.com/sublimelsp/LSP-file-watcher-rust), [client backend gate](https://github.com/sublimelsp/LSP/blob/4070-2.13.0/plugin/core/sessions.py).

**Release acceptance criteria**

- A fresh user can install the package, configure CK3 once, open a mod and obtain completions/navigation without changing unrelated text/YAML files.
- All settings reach the correct instance. Changes to paths, language and asset indexing rebuild; hover/completion/diagnostic options update without unnecessary restart. Hints refresh visibly.
- Every declared capability and advertised menu action has a verified working path or an explicit unavailable state; no dead VS Code command URLs.
- Multi-file edits preserve unsaved content, use UTF-16 LSP positions correctly, reject stale snapshots and support undo. BOM is verified from saved bytes, including newly created localization files.
- Parent/vanilla content remains context for normal editing operations. Rename refusal is preserved; writer commands select an editable target.
- New, deleted and externally edited files update references/diagnostics. Schema/playset/calendar updates have a tested reload path. Reopening a window does not leave old server processes alive.
- Tiger diagnostics remain distinguishable from structural LSP diagnostics, do not flicker between concurrent runs and clear after fixes. Test on a scratch CK3 mod with the real validator.
- Test complete workflows for script, loc, GUI and graphics files, including incomplete code, unsupported references, missing game/log paths, inherited overrides and large dependency chains.
- Use protocol smoke tests for adapter requests/settings and focused Python tests for path/root detection, URI/offset conversion, version checks and writers. Use real Sublime sessions for UI integration, packed-package installation and upgrade checks; existing server unit tests alone cannot establish client compatibility.

The recommended first public release is phases 1–5: complete standard editing, all server settings, broad native custom-protocol coverage, reliable localization and Tiger. A graphical companion is a separately scoped enhancement.
