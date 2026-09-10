"""CK3 integration through the public Sublime LSP helper API."""
from __future__ import annotations

import copy
import html
import json
import os
import re
import shutil
import threading
import weakref
from pathlib import Path
from urllib.parse import unquote, urlsplit

import sublime
import sublime_plugin

from .lib import core, authoring, install, tiger, ui
from .lib.watcher import ModWatcher, snapshot

try:
    from LSP.plugin import LspPlugin, PluginStartError, Notification, Request, Promise
    from LSP.plugin import command_handler, notification_handler, uri_handler
    from LSP.plugin import uri_from_view
    HAS_LSP = True
except ImportError:
    HAS_LSP = False

NAME = "LSP-px"
RESOURCE = "Packages/" + NAME + "/"
SYNTAXES = {"script": "Paradox Script", "loc": "Paradox Localization", "gui": "Paradox GUI",
            "mod": "Paradox Descriptor", "info": "Paradox Info"}
INSTANCES = {}
TIGER_RUNS = {}
TIGER_RESULTS = {}
SAVE_GENERATIONS = {}
DESCRIPTOR_DATA = {"fields": [], "tags": []}
UNLOADING = False


def configuration(window):
    settings = sublime.load_settings(NAME + ".sublime-settings").to_dict()
    project = (window.project_data() or {}).get("settings", {}).get("LSP", {}).get(NAME, {})
    for key, value in project.items():
        if isinstance(value, dict) and isinstance(settings.get(key), dict):
            settings[key] = dict(settings[key], **value)
        else:
            settings[key] = value
    return settings


def resolved(window, view=None):
    conf = configuration(window)
    options = conf.get("px", {})
    view = view or window.active_view()
    return core.resolve_settings(conf.get("settings", {}), window.folders(), view.file_name() if view else None,
                                 options.get("excluded_mods", []))


def instance(window):
    ref = INSTANCES.get(window.id())
    obj = ref() if ref else None
    return obj if obj and obj.weaksession() else None


def request(window, method, params, callback, view=None):
    obj = instance(window)
    if not obj:
        ui.error("Open a CK3 script in an editable mod first. If the server did not start, run Paradox: Setup or LSP: Troubleshoot Server.")
        return
    session = obj.weaksession()
    version = re.match(r"(\d+)\.(\d+)\.(\d+)", obj.version or "")
    if version and tuple(int(n) for n in version.groups()) < (0, 3, 4):
        ui.error("This package needs px-lsp 0.3.4 or newer; this server reports " + obj.version)
        return
    def receive(result):
        try:
            callback(result)
        except (ValueError, OSError, KeyError, TypeError) as exc:
            ui.error("{}: {}".format(method, exc))
    def send():
        session.send_request_async(Request("paradox/" + method, params, view),
            lambda result: ui.on_main(lambda: receive(result)),
            lambda err: ui.error("{}: {}".format(method, err)))
    sublime.set_timeout_async(send)


def document(view):
    if not view or not view.file_name():
        raise ValueError("Save the document inside your mod first")
    text = view.substr(sublime.Region(0, view.size()))
    return {"uri": uri_from_view(view) if HAS_LSP else core.file_uri(view.file_name()), "text": text}


def cursor_params(view):
    doc = document(view)
    return {"uri": doc["uri"], "position": core.position(doc["text"], view.sel()[0].begin())}


def active_root(window, view=None):
    settings = resolved(window, view)
    view = view or window.active_view()
    return core.editable_root(view.file_name() if view else None, settings) or settings["modPath"]


def require_editable(view):
    if not view or not core.editable_root(view.file_name(), resolved(view.window(), view)):
        raise ValueError("Choose a file inside an editable workspace mod; dependencies and vanilla are read-only context")


def restart(window):
    view = window.active_view()
    if view:
        view.run_command("lsp_restart_server", {"config_name": NAME})


def update_configuration():
    if UNLOADING:
        return
    for window in sublime.windows():
        for view in window.views():
            assign_language(view)
        obj = instance(window)
        if obj:
            sublime.set_timeout_async(obj.sync_settings)


def assign_language(view, force=None):
    window = view.window()
    if not window or view.settings().get("px_report") or view.is_scratch():
        return
    try:
        conf = configuration(window)
        if not conf.get("enabled", True) or (not force and not conf.get("px", {}).get("detect_syntax", True)):
            return
        settings = resolved(window, view)
        root = core.editable_root(view.file_name(), settings)
        missing = root and not os.path.isfile(os.path.join(root, "descriptor.mod"))
        if missing and conf.get("px", {}).get("require_descriptor") and "missing-descriptor" not in settings["diagnosticsIgnore"]:
            view.set_status("px_descriptor_missing", "Paradox: missing descriptor.mod — run Create Mod Descriptor")
        else:
            view.erase_status("px_descriptor_missing")
        mode = force or core.language_for(view.file_name(), settings)
        if not mode:
            return
        current = view.syntax()
        previous = view.settings().get("px_assigned_syntax")
        # Respect explicit syntax changes. Generic Text/YAML is safe to adopt.
        if not force and current and current.path != previous and current.scope not in ("text.plain", "source.yaml") and not current.scope.startswith("source.paradox"):
            return
        path = RESOURCE + "syntaxes/" + SYNTAXES[mode] + ".tmLanguage"
        if not current or current.path != path:
            view.assign_syntax(path)
            view.settings().set("px_assigned_syntax", path)
        view.settings().set("translate_tabs_to_spaces", mode == "loc")
        view.settings().set("tab_size", 4)
        if mode == "loc":
            view.settings().set("default_encoding", "UTF-8 with BOM")
    except ValueError as exc:
        view.set_status("px_config", str(exc))


if HAS_LSP:
    class PxPlugin(LspPlugin):
        @classmethod
        def on_pre_start_async(cls, context):
            try:
                window = context.view.window()
                options = context.configuration.root_settings.get("px", {})
                settings = core.resolve_settings(context.configuration.settings.get(), window.folders(),
                    context.view.file_name(), options.get("excluded_mods", []))
                storage = cls.plugin_storage_path
                storage.mkdir(parents=True, exist_ok=True)
                context.configuration.command = install.server_command(str(storage), options)
                cache = core.expand_path(options.get("storage_dir")) or str(storage / "cache")
                Path(cache).mkdir(parents=True, exist_ok=True)
                init = context.configuration.initialization_options
                init.set("storageDir", cache)
                init.set("settings", settings)
                init.set("client", {"ownFileWatcher": True, "hoverHtml": False, "hoverIcons": False,
                                    "fileLinks": True, "commands": ["px.editLocalization", "px.openLocalizationSideBySide", "px.showReferences", "px.showExamplesWiki"]})
                if options.get("data_dir"):
                    init.set("dataDir", core.expand_path(options["data_dir"]))
                context.working_directory = settings["modPath"] or (window.folders()[0] if window.folders() else None)
            except (ValueError, OSError) as exc:
                raise PluginStartError(str(exc))

        def __init__(self, weaksession):
            super().__init__(weaksession)
            self.watcher = None
            self.settings = None
            self.health = {}
            self.version = None
            self.catalogue = None
            self.refresh_generation = 0

        def on_server_response_async(self, response):
            if response.get("method") == "initialize":
                self.version = response.get("result", {}).get("serverInfo", {}).get("version")

        def on_initialized_async(self):
            session = self.weaksession()
            if not session:
                return
            INSTANCES[session.window.id()] = weakref.ref(self)
            self.sync_settings()
            if configuration(session.window).get("px", {}).get("inlay_hints", True):
                ui.on_main(lambda: session.window.run_command("lsp_toggle_inlay_hints", {"enable": True}))

        def sync_settings(self):
            session = self.weaksession()
            if not session or UNLOADING:
                return
            try:
                new_settings = resolved(session.window)
            except ValueError as exc:
                ui.error(exc)
                return
            if new_settings == self.settings:
                return
            self.settings = new_settings
            session.send_notification(Notification("paradox/configChanged", self.settings))
            if self.watcher:
                self.watcher.stop()
            roots = core.unique_paths(self.settings["workspaceMods"] + [p for root in self.settings["workspaceMods"] for p in core.parents_for(self.settings, root)])
            interval = configuration(session.window).get("px", {}).get("watch_interval_seconds", 3)
            self.watcher = ModWatcher(roots, self.files_changed, interval)
            self.watcher.start()
            ui.on_main(lambda: session.window.run_command("lsp_toggle_inlay_hints", {"enable": bool(session.window.settings().get("lsp_show_inlay_hints", True))}))

        def on_pre_send_notification_async(self, notification):
            if notification.get("method") == "workspace/didChangeConfiguration":
                sublime.set_timeout_async(self.sync_settings)

        def files_changed(self, paths):
            sublime.set_timeout_async(lambda: self._files_changed_async(paths))

        def _files_changed_async(self, paths):
            session = self.weaksession()
            if not session or UNLOADING:
                return
            if any(os.path.basename(p) in ("schema.json", "playset.json") for p in paths):
                ui.on_main(lambda: restart(session.window))
            else:
                for file in paths:
                    session.send_notification(Notification("paradox/modFileChanged", {"fsPath": file}))

        @notification_handler("paradox/status")
        def status(self, params):
            self.health = params
            session = self.weaksession()
            if session:
                text = "PX: indexing…" if params.get("indexing") else "PX: {:,} definitions · {:,} tokens{}".format(params.get("definitions", 0), params.get("tokens", 0), " (bundled)" if params.get("tokensFromBundledDumps") else "")
                ui.on_main(lambda: [v.set_status("px_health", text) for v in session.window.views() if v.syntax() and v.syntax().scope.startswith("source.paradox")])

        @notification_handler("paradox/progress")
        def progress(self, params):
            if params.get("state") == "start":
                ui.message(params.get("detail", params.get("phase", "Loading")))

        @notification_handler("paradox/indexChanged")
        def index_changed(self, params):
            self.catalogue = None
            self.refresh_generation += 1
            session = self.weaksession()
            if session:
                generation = self.refresh_generation
                def refresh():
                    if generation == self.refresh_generation and not UNLOADING:
                        session.window.settings().set("px_index_revision", generation)
                        ui.refresh_window(session.window)
                sublime.set_timeout(refresh, 500)

        def client_command(self, name, arguments):
            session = self.weaksession()
            if session:
                args = arguments or []
                if name in ("px.editLocalization", "px.openLocalizationSideBySide") and args and isinstance(args[0], str):
                    ui.on_main(lambda: session.window.run_command("px_localization", {"key": args[0], "side": name.endswith("SideBySide"), "edit_value": name == "px.editLocalization"}))
                elif name == "px.showExamplesWiki":
                    entry = args[0] if args and isinstance(args[0], dict) else None
                    ui.on_main(lambda: session.window.run_command("px_examples", {"entry": entry}))
                elif name == "px.showReferences" and len(args) == 3:
                    uri, line, character = args
                    if isinstance(uri, str) and uri.startswith("file:") and isinstance(line, int) and isinstance(character, int):
                        params = {"textDocument": {"uri": uri}, "position": {"line": line, "character": character}, "context": {"includeDeclaration": True}}
                        session.send_request_async(Request("textDocument/references", params), lambda result: ui.on_main(lambda: show_locations(session.window, result)))
            return Promise.resolve(None)

        @command_handler("px.editLocalization")
        def edit_loc(self, args):
            return self.client_command("px.editLocalization", args)

        @command_handler("px.openLocalizationSideBySide")
        def side_loc(self, args):
            return self.client_command("px.openLocalizationSideBySide", args)

        @command_handler("px.showReferences")
        def references(self, args):
            return self.client_command("px.showReferences", args)

        @command_handler("px.showExamplesWiki")
        def examples(self, args):
            return self.client_command("px.showExamplesWiki", args)

        @uri_handler("command")
        def command_uri(self, uri, flags):
            parsed = urlsplit(uri)
            allowed = {"px.editLocalization", "px.openLocalizationSideBySide", "px.showReferences", "px.showExamplesWiki"}
            if parsed.path not in allowed:
                return Promise.resolve(None)
            try:
                args = json.loads(unquote(parsed.query)) if parsed.query else []
                if isinstance(args, list):
                    self.client_command(parsed.path, args)
            except (ValueError, TypeError):
                pass
            return Promise.resolve(None)

        def on_session_end_async(self, exit_code, exception):
            if self.watcher:
                self.watcher.stop()
            session = self.weaksession()
            if session and instance(session.window) is self:
                INSTANCES.pop(session.window.id(), None)
                ui.on_main(lambda: [v.erase_status("px_health") for v in session.window.views()])


def show_locations(window, locations):
    rows = []
    for loc in locations or []:
        try:
            file = core.uri_path(loc["uri"])
            pos = loc["range"]["start"]
            rows.append({"label": "{}:{}".format(os.path.basename(file), pos["line"] + 1), "detail": file,
                         "file": file, "line": pos["line"], "column": pos["character"]})
        except (KeyError, ValueError):
            continue
    ui.pick(window, "References", rows, lambda r: ui.open_source(window, r["file"], r["line"], r["column"], utf16=True))


class PxOpenSourceCommand(sublime_plugin.WindowCommand):
    def run(self, file, line=0, column=0, side=False):
        ui.open_source(self.window, file, line, column, side)


class PxSetTextCommand(sublime_plugin.TextCommand):
    def run(self, edit, text, expected=None, bom=False):
        current = self.view.substr(sublime.Region(0, self.view.size()))
        if expected is not None and expected != current:
            ui.error("The document changed while the operation was running. Retry against the current text.")
            return
        if self.view.is_read_only():
            ui.error("This view is read-only")
            return
        self.view.replace(edit, sublime.Region(0, self.view.size()), text)
        if bom:
            self.view.set_encoding("UTF-8 with BOM")


class PxApplySourceEditsCommand(sublime_plugin.TextCommand):
    def run(self, edit, expected, edits):
        try:
            require_editable(self.view)
            current = self.view.substr(sublime.Region(0, self.view.size()))
            if current != expected:
                raise ValueError("The source changed. Retry the operation; no edits were applied.")
            # Validate the entire edit set before touching the buffer.
            core.offset_edits(current, edits)
            for item in sorted(edits, key=lambda e: e["start"], reverse=True):
                a, b = core.utf16_offset(current, item["start"]), core.utf16_offset(current, item["end"])
                self.view.replace(edit, sublime.Region(a, b), item["newText"])
        except ValueError as exc:
            ui.error(exc)


class PxRestartCommand(sublime_plugin.WindowCommand):
    def run(self):
        restart(self.window)


class PxUseSyntaxCommand(sublime_plugin.TextCommand):
    def run(self, edit, mode=None):
        if mode:
            assign_language(self.view, mode)
        else:
            modes = list(SYNTAXES)
            self.view.window().show_quick_panel([SYNTAXES[m] for m in modes], lambda i: assign_language(self.view, modes[i]) if i >= 0 else None)


class PxEnableSemanticCommand(sublime_plugin.WindowCommand):
    def run(self):
        settings = sublime.load_settings("LSP.sublime-settings")
        settings.set("semantic_highlighting", True)
        sublime.save_settings("LSP.sublime-settings")
        ui.message("Semantic highlighting enabled for LSP. Color scheme support is required; the bundled Paradox scheme is available.")


class PxSetupCommand(sublime_plugin.WindowCommand):
    def run(self, action=None, value=None):
        if action is None:
            options = [("detect", "Detect CK3 and script-doc paths"), ("gamePath", "Set CK3 game folder"),
                       ("logsPath", "Set CK3 script-doc logs folder"), ("settings", "Open all package settings"),
                       ("semantic", "Enable semantic highlighting (all LSP servers)"),
                       ("tiger", "Install ck3-tiger"), ("help", "Read setup and feature guide")]
            if not HAS_LSP:
                ui.error("Install the LSP package using Package Control, then restart Sublime. LSP-px requires LSP 2.13 or newer.")
            self.window.show_quick_panel([v for _, v in options], lambda i: self.run(options[i][0]) if i >= 0 else None, placeholder="Paradox setup")
            return
        if action == "settings":
            self.window.run_command("edit_settings", {"base_file": RESOURCE + NAME + ".sublime-settings", "default": "{\n\t\"settings\": {\n\t}\n}\n"})
        elif action == "semantic":
            self.window.run_command("px_enable_semantic")
        elif action == "help":
            view = self.window.new_file()
            view.set_name("LSP-px Guide")
            view.set_scratch(True)
            view.run_command("px_set_text", {"text": sublime.load_resource(RESOURCE + "README.md")})
            view.assign_syntax("Packages/Markdown/Markdown.sublime-syntax")
        elif action == "tiger":
            self.window.run_command("px_install_tiger")
        elif action == "detect":
            game, logs = core.detect_game()
            values = {k: v for k, v in (("gamePath", game), ("logsPath", logs)) if v}
            self.save(values)
            ui.report(self.window, "Detected paths", values or {"status": "No installation found. Set paths manually in Setup."})
        elif action in ("gamePath", "logsPath"):
            if value is None:
                current = resolved(self.window).get(action) or ""
                self.window.show_input_panel(core.SETTINGS.get(action) or action, current, lambda text: self.run(action, text), None, None)
            elif os.path.isdir(os.path.expanduser(value)):
                self.save({action: str(Path(value).expanduser().resolve())})
            else:
                ui.error("That folder does not exist")

    def save(self, values):
        settings = sublime.load_settings(NAME + ".sublime-settings")
        merged = dict(settings.get("settings", {}), **values)
        settings.set("settings", merged)
        sublime.save_settings(NAME + ".sublime-settings")
        update_configuration()


REPORTS = {
    "modOverview": "Mod inventory", "indexStats": "Index health", "locCoverage": "Localization coverage",
    "overrides": "Override winners", "scopeAt": "Scope inspector", "dependencies": "Definition dependencies",
    "eventGraph": "Event relationships", "eventDetail": "Event inspector", "eventVocabulary": "Event vocabulary",
    "eventValueOptions": "Values for this definition", "eventBanner": "Event theme banner",
    "modifierFormats": "Modifier display formats", "locText": "Localization text preview",
    "guiTree": "Widget outline", "guiLayout": "Static GUI layout", "guiDependencies": "GUI dependencies",
    "guiVocabulary": "Widget vocabulary", "guiSaveValues": "Save preview values",
}


class PxReportCommand(sublime_plugin.WindowCommand):
    def run(self, feature="modOverview", query=None, params=None, readable=False):
        if feature == "reloadDocs":
            request(self.window, feature, {"force": True}, lambda r: ui.message("Reloaded {:,} engine tokens".format(r.get("tokens", 0))))
            return
        if feature not in REPORTS:
            return
        view = self.window.active_view()
        try:
            title = REPORTS[feature]
            payload = {"modRoot": active_root(self.window)}
            if feature == "indexStats":
                payload = None
            elif feature in ("scopeAt", "dependencies"):
                payload = cursor_params(view)
                if feature == "dependencies":
                    payload["guiUses"] = True
            elif feature.startswith("gui") and feature != "guiSaveValues":
                if not view or not view.syntax() or view.syntax().scope != "source.paradox-gui":
                    raise ValueError("Open a Paradox GUI file for this command")
                payload = document(view)
                if feature == "guiLayout":
                    payload["previewValues"] = self.window.settings().get("px_preview_values", {})
            elif feature in ("eventDetail", "eventBanner", "eventValueOptions", "locText", "guiSaveValues"):
                key = {"eventDetail": "id", "eventBanner": "theme", "eventValueOptions": "value", "locText": "keys", "guiSaveValues": "path"}[feature]
                if query is None:
                    self.window.show_input_panel(title + (" (comma-separated keys)" if feature == "locText" else ""), "",
                        lambda text: self.run(feature, text, readable=readable), None, None)
                    return
                if feature == "guiSaveValues" and not os.path.isfile(os.path.expanduser(query)):
                    raise ValueError("Save file does not exist")
                payload[key] = [k.strip() for k in query.split(",") if k.strip()] if key == "keys" else core.expand_path(query) if key == "path" else query
            elif feature == "eventGraph":
                payload.update({"maxNodes": 500, "connectedOnly": False})
                if query:
                    payload["root"] = query
            if params:
                payload = dict(payload or {}, **params)
            context_file = view.file_name() if view else None
            generation = [0]
            refreshable = feature not in ("scopeAt", "dependencies") and not feature.startswith("gui")
            def refresh(sheet):
                generation[0] += 1
                current = generation[0]
                request(self.window, feature, payload, lambda data: done(data, sheet) if current == generation[0] and sheet in self.window.sheets() else None)
            def done(data, sheet=None):
                if feature == "guiSaveValues" and data and not data.get("error"):
                    self.window.settings().set("px_preview_values", data.get("values", {}))
                if feature == "indexStats":
                    obj = instance(self.window)
                    data = {"serverVersion": obj.version if obj else "unknown", "health": obj.health if obj else {},
                            "index": data, "settings": resolved(self.window), "watcher": "Mod folders and dependencies; active"}
                if readable or sheet:
                    ui.report(self.window, title, data, context_file, sheet=sheet, refresh=refresh if refreshable else None)
                else:
                    ui.browse(self.window, title, data, context_file, refresh=refresh if refreshable else None)
            request(self.window, feature, payload, done, view)
        except (ValueError, OSError) as exc:
            ui.error(exc)


class PxSnippetsCommand(sublime_plugin.WindowCommand):
    def run(self, catalogue=False, export=False):
        view = self.window.active_view()
        try:
            doc = document(view)
            selection = [(r.a, r.b) for r in view.sel()]
            def insert(item):
                if view.substr(sublime.Region(0, view.size())) != doc["text"] or [(r.a, r.b) for r in view.sel()] != selection:
                    ui.error("The document or selection changed; reopen the snippet picker.")
                    return
                self.window.focus_view(view)
                view.run_command("insert_snippet", {"contents": item["snippet"]})
            def done(result):
                if result.get("indexing"):
                    ui.message("The index is still loading. Reopen the snippet catalog when the status bar is ready.")
                    return
                if export:
                    output = self.window.new_file()
                    output.set_name("Paradox generated snippets.json")
                    output.assign_syntax("Packages/JSON/JSON.sublime-syntax")
                    output.run_command("px_set_text", {"text": json.dumps(result, ensure_ascii=False, indent=2) + "\n"})
                    return
                if catalogue:
                    ui.pick(self.window, "Generated snippet catalog", result.get("entries", []),
                            lambda entry: ui.pick(self.window, entry["label"], entry["variants"], insert))
                else:
                    ui.pick(self.window, "Insert CK3 snippet", result.get("snippets", []), insert)
            request(self.window, "snippetCatalogue" if catalogue or export else "snippets",
                    {} if catalogue or export else cursor_params(view), done, view)
        except ValueError as exc:
            ui.error(exc)


class PxExamplesCommand(sublime_plugin.WindowCommand):
    def run(self, entry=None):
        if entry:
            request(self.window, "exampleWikiEntry", {"name": entry["name"], "kind": entry["kind"]},
                    lambda data: ui.browse(self.window, entry["name"], data, one_based=True))
        else:
            obj = instance(self.window)
            def show(data):
                if obj:
                    obj.catalogue = data
                rows = [dict(item, label=item["name"] + " · " + item["kind"], detail=item.get("shortDoc", "")) for item in data.get("entries", [])]
                ui.pick(self.window, "Examples Wiki · search name or kind", rows, lambda selected: self.run(selected))
            if obj and obj.catalogue:
                show(obj.catalogue)
            else:
                request(self.window, "exampleWiki", None, show)


class PxDynastyCommand(sublime_plugin.WindowCommand):
    def run(self, dynasty=None):
        params = {"modRoot": active_root(self.window)}
        if dynasty:
            params["dynasty"] = dynasty
        def done(data):
            if not data.get("supported", True):
                ui.message("Dynasty history is not supported for this workspace")
            elif dynasty:
                ui.browse(self.window, "Dynasty " + dynasty, data)
            else:
                rows = [dict(d, label=str(d.get("name", d.get("id"))), detail="Dynasty " + str(d.get("id"))) for d in data.get("dynasties", [])]
                ui.pick(self.window, "Choose a dynasty", rows, lambda d: self.run(d["id"]))
        request(self.window, "dynastyTree", params, done)


class PxLocalizationCommand(sublime_plugin.WindowCommand):
    def run(self, key=None, side=False, edit_value=True, value=None, language=None, target=None, choose_language=False):
        view = self.window.active_view()
        if choose_language:
            self.window.show_input_panel("Localization language", resolved(self.window)["locLanguage"],
                lambda lang: self.run(key, side, edit_value, value, lang), None, None)
            return
        if key is None:
            selected = view.substr(view.word(view.sel()[0])) if view and view.sel() else ""
            self.window.show_input_panel("Localization key", selected, lambda text: self.run(text, side, edit_value, value, language), None, None)
            return
        try:
            if not authoring.KEY.fullmatch(key):
                raise ValueError("Invalid localization key")
            settings = resolved(self.window)
            lang = language or settings["locLanguage"]
            root = active_root(self.window)
            if not root:
                raise ValueError("Open an editable mod first")
            def done(entries):
                def read(file):
                    opened = self.window.find_open_file(file)
                    return opened.substr(sublime.Region(0, opened.size())) if opened else Path(file).read_text(encoding="utf-8-sig")
                candidates = core.unique_paths(e["file"] for e in entries if core.under(e["file"], root) and e["file"].endswith("_l_" + lang + ".yml"))
                if target is None and edit_value and len(candidates) > 1:
                    ui.pick(self.window, "Choose the localization definition to edit",
                        [{"label": os.path.basename(file), "detail": file, "file": file} for file in candidates],
                        lambda item: self.run(key, side, edit_value, value, lang, item["file"]))
                    return
                destination = target or authoring.localization_target(root, lang, key, entries, read)
                authoring.validate_loc_target(destination, root, lang)
                target_before = read(destination) if os.path.isfile(destination) or self.window.find_open_file(destination) else ""
                if not edit_value and entries:
                    ui.pick(self.window, "Localization: " + key,
                            [dict(e, label=e.get("value", key), detail=e["file"]) for e in entries],
                            lambda e: ui.open_source(self.window, e["file"], e["line"], side=side))
                    return
                def apply(text):
                    # Opening a missing path creates a dirty buffer; save stays explicit.
                    Path(destination).parent.mkdir(parents=True, exist_ok=True)
                    if side:
                        if self.window.num_groups() < 2:
                            self.window.set_layout({"cols": [0, 0.5, 1], "rows": [0, 1], "cells": [[0, 0, 1, 1], [1, 0, 2, 1]]})
                        opened = self.window.open_file(destination, group=(self.window.active_group() + 1) % self.window.num_groups())
                    else:
                        opened = self.window.open_file(destination)
                    def write(buffer):
                        try:
                            old = buffer.substr(sublime.Region(0, buffer.size()))
                            if old != target_before:
                                raise ValueError("Localization changed while the editor was open. Retry against the latest text.")
                            new = authoring.upsert_localization(old, key, text, lang)
                            buffer.run_command("px_set_text", {"expected": old, "text": new, "bom": True})
                            assign_language(buffer)
                            match = buffer.find(r"(?m)^\s*" + re.escape(key) + ":", 0)
                            if match:
                                buffer.sel().clear()
                                buffer.sel().add(match)
                                buffer.show(match)
                            ui.message("Localization updated in the buffer; save to write it to disk")
                        except ValueError as exc:
                            ui.error(exc)
                    ui.when_loaded(opened, write)
                if value is None:
                    initial = next((e.get("value", "") for e in entries if e.get("source") == "mod"), entries[0].get("value", "") if entries else "")
                    for line in target_before.splitlines():
                        match = authoring.LOC_ENTRY.match(line)
                        if match and match.group(2) == key:
                            try:
                                initial = json.loads('"' + match.group(4) + '"')
                            except ValueError:
                                initial = match.group(4)
                            break
                    self.window.show_input_panel("Text for " + key + " (" + lang + ")", initial, apply, None, None)
                else:
                    apply(value)
            request(self.window, "lookupLoc", {"key": key}, done, view)
        except (ValueError, OSError) as exc:
            ui.error(exc)


class PxGuiCommand(sublime_plugin.WindowCommand):
    def run(self, action="inspect", line=None, key=None, value=None, source=None):
        view = next((v for v in self.window.views() if v.id() == source["view"]), None) if source else self.window.active_view()
        try:
            doc = document(view)
            if source and doc["text"] != source["text"]:
                raise ValueError("The GUI source changed while choosing an operation. Reopen the widget picker.")
            source = {"view": view.id(), "text": doc["text"]}
            def resume(*args):
                self.run(*args, source=source)
            if not view.syntax() or view.syntax().scope != "source.paradox-gui":
                raise ValueError("Open a Paradox GUI document")
            if action == "palette":
                def palette(data):
                    def selected(entry):
                        request(self.window, "guiPreview", dict(doc, entries=[{"name": entry["name"], "kind": entry["kind"]}]),
                                lambda result: ui.browse(self.window, "Widget preview: " + entry["name"], result, view.file_name()), view)
                    ui.pick(self.window, "Widget palette · static layout preview", data.get("entries", []), selected)
                request(self.window, "guiVocabulary", doc, palette, view)
                return
            if line is None:
                def tree(data):
                    rows = []
                    def walk(nodes, depth=0):
                        for node in nodes:
                            rows.append(dict(node, label="  " * depth + node.get("key", "widget") + " " + node.get("name", ""), detail="Line " + str(node["line"] + 1)))
                            walk(node.get("children", []), depth + 1)
                    walk(data.get("nodes", []))
                    ui.pick(self.window, "Choose a source widget", rows, lambda node: resume(action, node["line"], key, value))
                request(self.window, "guiTree", doc, tree, view)
                return
            if action == "inspect":
                request(self.window, "guiWidgetInfo", dict(doc, line=line, placement=True),
                        lambda result: ui.browse(self.window, "Widget properties and layout", result, view.file_name()), view)
                return
            require_editable(view)
            if action == "set":
                if key is None:
                    def vocabulary(data):
                        names = sorted(set(k for keys in data.get("properties", {}).values() for k in keys))
                        rows = [{"label": "Enter another property", "key": None}] + [{"label": k, "key": k} for k in names]
                        def selected(item):
                            if item["key"] is None:
                                self.window.show_input_panel("Property", "", lambda text: resume(action, line, text, value), None, None)
                            else:
                                resume(action, line, item["key"], value)
                        ui.pick(self.window, "Property to change", rows, selected)
                    request(self.window, "guiVocabulary", doc, vocabulary, view)
                    return
                if value is None:
                    self.window.show_input_panel("Raw GUI value for " + key + " (empty removes property)", "",
                        lambda text: resume(action, line, key, text), None, None)
                    return
                op = {"kind": "setProperties", "line": line, "properties": [{"key": key, "value": value or None}]}
            elif action == "insert":
                if key is None:
                    request(self.window, "guiVocabulary", doc,
                        lambda data: ui.pick(self.window, "Insert a child widget", data.get("entries", []), lambda e: resume(action, line, e["name"])), view)
                    return
                op = {"kind": "insert", "line": line, "widget": {"type": key}}
            elif action in ("duplicate", "delete", "blockText"):
                op = {"kind": action, "line": line}
            else:
                raise ValueError("Unsupported widget operation")
            def edited(result):
                if not result or result.get("refused"):
                    ui.error((result or {}).get("refused", "The server could not edit this widget"))
                    return
                if "blockText" in result:
                    sublime.set_clipboard(result["blockText"])
                    ui.message("Widget source copied")
                else:
                    view.run_command("px_apply_source_edits", {"expected": doc["text"], "edits": result.get("edits", [])})
                if result.get("warning"):
                    ui.message(result["warning"])
            request(self.window, "guiSourceEdit", dict(doc, op=op), edited, view)
        except ValueError as exc:
            ui.error(exc)


class PxDefinitionCommand(sublime_plugin.WindowCommand):
    def run(self, kind=None, name=None, action="create", key=None, value=None, source=None):
        view = next((v for v in self.window.views() if v.id() == source["view"]), None) if source else self.window.active_view()
        try:
            root = source["root"] if source else active_root(self.window)
            if not root:
                raise ValueError("Open an editable mod first")
            text = view.substr(sublime.Region(0, view.size())) if view else None
            if source and text != source["text"]:
                raise ValueError("The source changed while choosing definition properties. Reopen the command.")
            source = {"root": root, "view": view.id() if view else None, "text": text}
            def resume(*args):
                self.run(*args, source=source)
            if kind is None:
                def kinds(result):
                    rows = [{"label": "Enter definition kind", "id": None}] + [e for e in result.get("entries", []) if e.get("category") == "Definitions"]
                    def chosen(entry):
                        if entry.get("id"):
                            resume(entry["id"].split(":", 1)[-1], name, action, key, value)
                        else:
                            self.window.show_input_panel("Definition kind", "", lambda text: resume(text, name, action, key, value), None, None)
                    ui.pick(self.window, "Definition kind", rows, chosen)
                request(self.window, "snippetCatalogue", {}, kinds)
                return
            if name is None:
                self.window.show_input_panel("Definition identifier", "", lambda text: resume(kind, text, action, key, value), None, None)
                return
            if not authoring.KEY.fullmatch(name):
                raise ValueError("Use a script identifier for the name")
            def form(data):
                if view and (not view.is_valid() or view.substr(sublime.Region(0, view.size())) != source["text"]):
                    raise ValueError("The source changed while the definition form loaded. Reopen the command.")
                if not data:
                    ui.error("The server has no schema for definition kind " + kind)
                    return
                if action == "inspect":
                    ui.browse(self.window, kind + ": " + name, data)
                    return
                if action == "property":
                    require_editable(view)
                    if key is None:
                        rows = [dict(k, label=k["key"], detail=k.get("doc", k.get("values", ""))) for k in data.get("keys", [])]
                        ui.pick(self.window, "Property", rows, lambda k: resume(kind, name, action, k["key"], value))
                        return
                    if value is None:
                        field = next((k for k in data["keys"] if k["key"] == key), {})
                        options = []
                        if field.get("values") == "bool":
                            options = [{"label": "yes", "value": "yes"}, {"label": "no", "value": "no"}]
                        elif field.get("values", "").startswith("enum:"):
                            options = [{"label": x, "value": x} for x in field["values"][5:].split("|")]
                        for ref_kind in field.get("refKinds", []):
                            options += [dict(o, value=o.get("name", o.get("value", ""))) for o in data.get("options", {}).get(ref_kind, [])]
                        def custom():
                            self.window.show_input_panel("Raw script value (empty removes " + key + ")", field.get("example", ""),
                                lambda text: resume(kind, name, action, key, text), None, None)
                        if options:
                            ui.pick(self.window, key, [{"label": "Enter a value", "custom": True}] + options,
                                    lambda option: custom() if option.get("custom") else resume(kind, name, action, key, option["value"]))
                        else:
                            custom()
                        return
                    doc = document(view)
                    op = {"op": "setProperties", "name": name, "properties": [{"key": key, "value": value or None}]}
                    request(self.window, "definitionEdit", dict(doc, ops=[op]), lambda result: self.apply(view, doc, result), view)
                    return
                target = os.path.join(root, data["folder"], "px_" + name + ".txt")
                if not core.under(target, root):
                    raise ValueError("The definition folder escapes the mod")
                if os.path.exists(target) or self.window.find_open_file(target):
                    ui.error("The target already exists. Open it and use Edit Definition Property: " + target)
                    return
                Path(target).parent.mkdir(parents=True, exist_ok=True)
                created = self.window.open_file(target)
                def start(buffer):
                    assign_language(buffer)
                    buffer.set_encoding("UTF-8 with BOM")
                    if kind == "event":
                        if "." not in name:
                            ui.error("An event identifier needs namespace.number")
                            return
                        buffer.run_command("px_set_text", {"expected": "", "text": "namespace = " + name.split(".", 1)[0] + "\n\n", "bom": True})
                    doc = document(buffer)
                    # Use the server's measured skeleton, not a handwritten game template.
                    def snippet_result(result):
                        if buffer.substr(sublime.Region(0, buffer.size())) != doc["text"]:
                            ui.error("The new definition changed while its template loaded. Reopen the snippet picker.")
                            return
                        template = next((s for s in result.get("snippets", []) if s.get("form") == "definition"), None)
                        if template:
                            self.window.focus_view(buffer)
                            buffer.sel().clear()
                            buffer.sel().add(sublime.Region(buffer.size()))
                            contents = re.sub(r"^\$\{\d+:[^}]+\}(?=\s*=)", name, template["snippet"], count=1)
                            buffer.run_command("insert_snippet", {"contents": contents})
                            ui.message("Definition template inserted. Fill the fields, then save.")
                        else:
                            op = {"op": "upsertBlock", "name": name, "text": name + " = {\n}\n"}
                            request(self.window, "definitionEdit", dict(doc, ops=[op]), lambda result: self.apply(buffer, doc, result), buffer)
                    # Allow the new document to attach before cursor-based requests.
                    sublime.set_timeout(lambda: request(self.window, "snippets", {"uri": doc["uri"], "position": core.position(doc["text"], len(doc["text"]))}, snippet_result, buffer), 300)
                ui.when_loaded(created, start)
            request(self.window, "definitionForm", {"kind": kind, "name": name, "modRoot": root}, form, view)
        except (ValueError, OSError) as exc:
            ui.error(exc)

    def apply(self, view, doc, result):
        refused = [op["refused"] for op in (result or {}).get("ops", []) if op.get("refused")]
        if refused:
            ui.error("; ".join(refused))
        elif result:
            view.run_command("px_apply_source_edits", {"expected": doc["text"], "edits": result.get("edits", [])})


class PxNewModCommand(sublime_plugin.WindowCommand):
    def run(self, parent=None, folder=None, name=None, version=None):
        if parent is None:
            self.window.show_input_panel("Parent folder for the new mod", str(Path.home() / "Documents"), lambda text: self.run(parent=text), None, None)
        elif folder is None:
            self.window.show_input_panel("Mod folder name", "", lambda text: self.run(parent, text), None, None)
        elif name is None:
            self.window.show_input_panel("Mod display name", folder.replace("_", " "), lambda text: self.run(parent, folder, text), None, None)
        elif version is None:
            game = resolved(self.window).get("gamePath")
            metadata = core.read_json(os.path.join(os.path.dirname(game), "launcher", "launcher-settings.json"), {}) if game else {}
            raw = str(metadata.get("rawVersion", ""))
            match = re.match(r"(\d+\.\d+)\.", raw)
            self.window.show_input_panel("Supported CK3 version (for example major.minor.*)", match.group(1) + ".*" if match else "",
                lambda text: self.run(parent, folder, name, text), None, None)
        else:
            try:
                if not re.fullmatch(r"\d+\.\d+\.(?:\d+|\*)", version):
                    raise ValueError("Use major.minor.patch or major.minor.*")
                root = authoring.new_mod(core.expand_path(parent), folder, name, version)
                self.window.run_command("open_project_or_workspace", {"file": os.path.join(root, folder + ".sublime-project"), "new_window": True})
                ui.message("Mod created. Add it to the CK3 launcher separately when ready to playtest.")
            except (ValueError, OSError) as exc:
                ui.error(exc)


class PxConfigFileCommand(sublime_plugin.WindowCommand):
    def run(self, kind="calendar"):
        templates = {
            "calendar": {"epoch": 1, "after": "AD", "before": "BC"},
            "playset": {"parents": []},
            "schema": {"entries": []},
        }
        if kind not in templates:
            return
        root = active_root(self.window)
        if not root:
            ui.error("Open an editable mod first")
            return
        file = os.path.join(root, ".px-toolkit", kind + ".json")
        Path(file).parent.mkdir(parents=True, exist_ok=True)
        existed = os.path.exists(file) or self.window.find_open_file(file)
        view = self.window.open_file(file)
        if not existed:
            ui.when_loaded(view, lambda v: v.run_command("px_set_text", {"expected": "", "text": json.dumps(templates[kind], indent=2) + "\n"}))


def tiger_executable(window):
    configured = configuration(window).get("px", {}).get("tiger_path")
    if configured:
        path = core.expand_path(configured)
        if not os.path.isfile(path):
            raise ValueError("Configured tiger_path does not exist")
        return path
    found = shutil.which("ck3-tiger")
    if found:
        return found
    storage = str(Path(sublime.packages_path()).parent / "Package Storage" / NAME)
    return install.install_tiger(storage)


class PxInstallTigerCommand(sublime_plugin.WindowCommand):
    def run(self):
        ui.message("Installing verified ck3-tiger release…")
        def worker():
            try:
                executable = tiger_executable(self.window)
                ui.message("Tiger ready: " + executable)
            except (ValueError, OSError) as exc:
                ui.error(exc)
        threading.Thread(target=worker, daemon=True).start()


def paint_tiger(view):
    window = view.window()
    if not window or not view.file_name():
        return
    rows = TIGER_RESULTS.get(window.id(), [])
    for scope, severities in (("invalid", ("error", "fatal")), ("markup.warning", ("warning",)), ("markup.info", ("info", "untidy", "tips"))):
        regions = []
        for row in rows:
            if os.path.normcase(row["file"]) == os.path.normcase(view.file_name()) and row["severity"] in severities:
                point = view.text_point(row["line"], row["column"])
                regions.append(sublime.Region(point, min(view.line(point).end(), point + row["length"])))
        view.add_regions("px_tiger_" + scope, regions, scope, "dot", sublime.DRAW_SQUIGGLY_UNDERLINE | sublime.DRAW_NO_FILL | sublime.DRAW_NO_OUTLINE)


class PxTigerCommand(sublime_plugin.WindowCommand):
    def run(self, cancel=False, manual=True):
        window_id = self.window.id()
        previous = TIGER_RUNS.get(window_id)
        if previous:
            previous.cancel()
        if cancel:
            TIGER_RUNS.pop(window_id, None)
            for view in self.window.views():
                view.erase_status("px_tiger")
            ui.message("Tiger cancelled")
            return
        try:
            root = active_root(self.window)
            settings = resolved(self.window)
            if not root or not os.path.isfile(os.path.join(root, "descriptor.mod")):
                raise ValueError("Tiger needs an editable mod with descriptor.mod")
            if any(v.is_dirty() and core.under(v.file_name(), root) for v in self.window.views()):
                if manual:
                    ui.error("Save the mod's changed files before running Tiger. It validates files on disk.")
                return
            run = tiger.TigerRun()
            TIGER_RUNS[window_id] = run
            ui.message("Tiger validating " + os.path.basename(root) + "…")
            for v in self.window.views():
                v.set_status("px_tiger", "Tiger: running…")
            def worker():
                try:
                    executable = tiger_executable(self.window)
                    cache = str(Path(sublime.cache_path()) / NAME / ("tiger-" + str(window_id)))
                    args = tiger.command(executable, root, settings, cache)
                    before = snapshot([root])
                    reports = run.run(args, root, configuration(self.window).get("px", {}).get("tiger_timeout_seconds", 180))
                    if reports is None:
                        return
                    rows = tiger.diagnostics(reports, root, settings)
                    unchanged = before == snapshot([root])
                    def publish():
                        if TIGER_RUNS.get(window_id) is not run or UNLOADING:
                            return
                        TIGER_RUNS.pop(window_id, None)
                        if not unchanged or any(v.is_dirty() and core.under(v.file_name(), root) for v in self.window.views()):
                            for view in self.window.views():
                                view.set_status("px_tiger", "Tiger: source changed; rerun validation")
                            return
                        # Preserve results from other editable mods in this window.
                        TIGER_RESULTS[window_id] = [r for r in TIGER_RESULTS.get(window_id, []) if not core.under(r["file"], root)] + rows
                        output = self.window.create_output_panel("px_tiger")
                        output.settings().set("result_file_regex", r"^(.+?):(\d+):(\d+):")
                        output.settings().set("result_base_dir", root)
                        lines = ["ck3-tiger · {} · {} diagnostics".format(os.path.basename(root), len(rows)), ""]
                        lines += ["{}:{}:{}: {} [{}] {}".format(r["file"], r["line"] + 1, r["column"] + 1, r["severity"], r["code"], r["message"]) for r in rows]
                        # File-less reports explain global/config failures and must stay visible.
                        lines += ["{} [{}] {}".format(r.get("severity", "warning"), r.get("key", "unknown"), r["message"]) for r in reports if not r.get("locations")]
                        output.run_command("px_set_text", {"text": "\n".join(lines) + "\n"})
                        for view in self.window.views():
                            paint_tiger(view)
                            view.set_status("px_tiger", "Tiger: {} diagnostics".format(len(rows)))
                        if manual or rows:
                            self.window.run_command("show_panel", {"panel": "output.px_tiger"})
                    ui.on_main(publish)
                except (ValueError, OSError) as exc:
                    if TIGER_RUNS.get(window_id) is run:
                        TIGER_RUNS.pop(window_id, None)
                        ui.error(exc)
                        ui.on_main(lambda: [v.set_status("px_tiger", "Tiger: failed; see error") for v in self.window.views()])
            threading.Thread(target=worker, name="LSP-px Tiger", daemon=True).start()
        except ValueError as exc:
            if manual:
                ui.error(exc)


def validate_descriptor(view):
    if not view.is_valid() or not view.syntax() or view.syntax().scope != "source.paradox-mod":
        return
    text = view.substr(sublime.Region(0, view.size()))
    issues = authoring.descriptor_issues(text, DESCRIPTOR_DATA["fields"], os.path.basename(view.file_name() or "") == "descriptor.mod")
    settings = resolved(view.window(), view)
    root = core.editable_root(view.file_name(), settings)
    if not root:
        issues = []
    else:
        issues = [i for i in issues if not tiger.suppressed(text, i["line"], i["code"], os.path.relpath(view.file_name(), root), settings)]
    view.settings().set("px_descriptor_issues", issues)
    regions = [sublime.Region(view.text_point(i["line"], i["startCol"]), view.text_point(i["line"], max(i["endCol"], i["startCol"] + 1))) for i in issues]
    view.add_regions("px_descriptor", regions, "invalid", "dot", sublime.DRAW_SQUIGGLY_UNDERLINE | sublime.DRAW_NO_FILL | sublime.DRAW_NO_OUTLINE)
    view.set_status("px_descriptor", "Descriptor: {} issues".format(len(issues)))


class PxDescriptorReportCommand(sublime_plugin.WindowCommand):
    def run(self):
        view = self.window.active_view()
        if view:
            validate_descriptor(view)
            ui.browse(self.window, "Descriptor validation", view.settings().get("px_descriptor_issues", []), view.file_name())


class PxCreateDescriptorCommand(sublime_plugin.WindowCommand):
    def run(self, name=None, version=None):
        root = active_root(self.window)
        if not root:
            ui.error("Set settings.modPath to the intended mod folder first, or use New Mod.")
            return
        target = os.path.join(root, "descriptor.mod")
        if os.path.isfile(target) or self.window.find_open_file(target):
            self.window.open_file(target)
            return
        if name is None:
            self.window.show_input_panel("Mod display name", os.path.basename(root), lambda value: self.run(value, version), None, None)
        elif version is None:
            self.window.show_input_panel("Supported CK3 version (major.minor.*)", "", lambda value: self.run(name, value), None, None)
        elif not re.fullmatch(r"\d+\.\d+\.(?:\d+|\*)", version):
            ui.error("Use major.minor.patch or major.minor.*")
        else:
            try:
                content = authoring.scaffold_descriptor(name, version)
                view = self.window.open_file(target)
                ui.when_loaded(view, lambda v: v.run_command("px_set_text", {"expected": "", "text": content}))
            except ValueError as exc:
                ui.error(exc)


class PxEvents(sublime_plugin.EventListener):
    def on_load(self, view):
        assign_language(view)
        paint_tiger(view)
        validate_descriptor(view)

    def on_activated(self, view):
        assign_language(view)
        window = view.window()
        if window:
            signature = json.dumps({"folders": window.folders(), "config": configuration(window)}, sort_keys=True)
            if window.settings().get("px_config_signature") != signature:
                window.settings().set("px_config_signature", signature)
                obj = instance(window)
                if obj:
                    sublime.set_timeout_async(obj.sync_settings)

    def on_load_project(self, window):
        update_configuration()

    def on_post_save_project(self, window):
        update_configuration()

    def on_modified(self, view):
        generation = view.change_count()
        sublime.set_timeout(lambda: validate_descriptor(view) if view.is_valid() and view.change_count() == generation else None, 400)
        # Validation is for saved text; remove stale underlines while editing.
        for scope in ("invalid", "markup.warning", "markup.info"):
            view.erase_regions("px_tiger_" + scope)

    def on_post_save(self, view):
        assign_language(view)
        validate_descriptor(view)
        window = view.window()
        if not window or not core.editable_root(view.file_name(), resolved(window, view)):
            return
        obj = instance(window)
        if obj:
            sublime.set_timeout_async(lambda: obj.files_changed([view.file_name()]))
        if configuration(window).get("px", {}).get("tiger_run_on") == "save":
            generation = SAVE_GENERATIONS.get(window.id(), 0) + 1
            SAVE_GENERATIONS[window.id()] = generation
            sublime.set_timeout(lambda: window.run_command("px_tiger", {"manual": False}) if SAVE_GENERATIONS.get(window.id()) == generation and not UNLOADING else None, 1500)

    def on_query_completions(self, view, prefix, locations):
        if not view.syntax() or view.syntax().scope != "source.paradox-mod":
            return None
        before = view.substr(sublime.Region(0, locations[0]))
        in_tags = re.search(r"tags\s*=\s*\{[^}]*$", before)
        if in_tags:
            return [sublime.CompletionItem(trigger=tag, completion='"' + tag + '"', kind=sublime.KIND_KEYWORD) for tag in DESCRIPTOR_DATA["tags"]]
        return [sublime.CompletionItem(trigger=f["key"], annotation=f["summary"], completion=f["snippet"], completion_format=sublime.COMPLETION_FORMAT_SNIPPET,
                    kind=sublime.KIND_KEYWORD, details=html.escape(f["doc"])) for f in DESCRIPTOR_DATA["fields"]]

    def on_hover(self, view, point, hover_zone):
        if hover_zone != sublime.HOVER_TEXT:
            return
        issues = view.settings().get("px_descriptor_issues", [])
        line = view.rowcol(point)[0]
        messages = [i["message"] for i in issues if i["line"] == line]
        if view.syntax() and view.syntax().scope == "source.paradox-mod":
            word = view.substr(view.word(point))
            field = next((f for f in DESCRIPTOR_DATA["fields"] if f["key"] == word), None)
            if field:
                messages.append(field["doc"])
        if view.window():
            messages += ["Tiger [{}]: {}".format(r["code"], r["message"]) for r in TIGER_RESULTS.get(view.window().id(), [])
                         if os.path.normcase(r["file"]) == os.path.normcase(view.file_name() or "") and r["line"] == line and not view.is_dirty()]
        if messages:
            view.show_popup("<body><p>" + "</p><p>".join(html.escape(m).replace("\n", "<br>") for m in messages) + "</p></body>", location=point, max_width=700)

    def on_pre_close_window(self, window):
        run = TIGER_RUNS.pop(window.id(), None)
        if run:
            run.cancel()
        TIGER_RESULTS.pop(window.id(), None)
        for key in list(ui.LIVE_REPORTS):
            if key[0] == window.id():
                ui.LIVE_REPORTS.pop(key, None)


def plugin_loaded():
    global UNLOADING, DESCRIPTOR_DATA
    UNLOADING = False
    DESCRIPTOR_DATA = json.loads(sublime.load_resource(RESOURCE + "data/descriptor.json"))
    if HAS_LSP:
        PxPlugin.register()
    sublime.load_settings(NAME + ".sublime-settings").add_on_change(NAME, lambda: sublime.set_timeout(update_configuration, 100))
    sublime.set_timeout(update_configuration, 200)


def plugin_unloaded():
    global UNLOADING
    UNLOADING = True
    sublime.load_settings(NAME + ".sublime-settings").clear_on_change(NAME)
    for ref in list(INSTANCES.values()):
        obj = ref()
        if obj and obj.watcher:
            obj.watcher.stop()
    for run in TIGER_RUNS.values():
        run.cancel()
    TIGER_RUNS.clear()
    INSTANCES.clear()
    ui.LIVE_REPORTS.clear()
    if HAS_LSP:
        PxPlugin.unregister()
