"""Generate the command palette and menus from one reviewed command inventory."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMMANDS = [
    ("Setup", "px_setup", {}), ("Restart Server / Rebuild Index", "px_restart", {}),
    ("Reload Script Docs", "px_report", {"feature": "reloadDocs"}),
    ("Index Health", "px_report", {"feature": "indexStats", "readable": True}),
    ("Use Paradox Syntax", "px_use_syntax", {}),
    ("Enable Semantic Highlighting (all LSP servers)", "px_enable_semantic", {}),
    ("Insert Snippet", "px_snippets", {}), ("Browse All Generated Snippets", "px_snippets", {"catalogue": True}),
    ("Export Generated Snippets", "px_snippets", {"export": True}),
    ("Examples Wiki", "px_examples", {}),
    ("Inspect Scope at Cursor", "px_report", {"feature": "scopeAt"}),
    ("Browse Definition Dependencies", "px_report", {"feature": "dependencies"}),
    ("Mod Inventory", "px_report", {"feature": "modOverview"}),
    ("Localization Coverage", "px_report", {"feature": "locCoverage"}),
    ("Override Winners", "px_report", {"feature": "overrides"}),
    ("Edit / Create Localization", "px_localization", {}),
    ("Open Localization Side by Side", "px_localization", {"side": True, "edit_value": False}),
    ("Preview Localization Text", "px_report", {"feature": "locText"}),
    ("Event Relationships", "px_report", {"feature": "eventGraph"}),
    ("Inspect Event", "px_report", {"feature": "eventDetail"}),
    ("Event Vocabulary", "px_report", {"feature": "eventVocabulary"}),
    ("Browse Values for a Definition", "px_report", {"feature": "eventValueOptions"}),
    ("Resolve Event Theme Banner", "px_report", {"feature": "eventBanner"}),
    ("Browse Dynasties", "px_dynasty", {}),
    ("Modifier Display Formats", "px_report", {"feature": "modifierFormats"}),
    ("GUI Widget Outline", "px_report", {"feature": "guiTree"}),
    ("Inspect GUI Widget", "px_gui", {}),
    ("GUI Dependencies", "px_report", {"feature": "guiDependencies"}),
    ("Inspect Static GUI Layout", "px_report", {"feature": "guiLayout"}),
    ("Browse GUI Widget Palette", "px_gui", {"action": "palette"}),
    ("Edit GUI Widget Property", "px_gui", {"action": "set"}),
    ("Insert Child GUI Widget", "px_gui", {"action": "insert"}),
    ("Duplicate GUI Widget", "px_gui", {"action": "duplicate"}),
    ("Delete GUI Widget", "px_gui", {"action": "delete"}),
    ("Copy GUI Widget Source", "px_gui", {"action": "blockText"}),
    ("Load Save Values for GUI Preview", "px_report", {"feature": "guiSaveValues"}),
    ("New Mod", "px_new_mod", {}),
    ("Create Definition", "px_definition", {}),
    ("Inspect Definition Schema", "px_definition", {"action": "inspect"}),
    ("Edit Definition Property", "px_definition", {"action": "property"}),
    ("Descriptor Validation Report", "px_descriptor_report", {}),
    ("Create Mod Descriptor", "px_create_descriptor", {}),
    ("Open Mod Calendar", "px_config_file", {"kind": "calendar"}),
    ("Open Dependency Playset", "px_config_file", {"kind": "playset"}),
    ("Open Schema Overlay", "px_config_file", {"kind": "schema"}),
    ("Install Tiger", "px_install_tiger", {}),
    ("Run Tiger Validation", "px_tiger", {}),
    ("Cancel Tiger Validation", "px_tiger", {"cancel": True}),
]


def write(name, value):
    (ROOT / name).write_text(json.dumps(value, ensure_ascii=False, indent=4) + "\n", encoding="utf-8")


def main():
    extra = [("Edit Localization in Another Language", "px_localization", {"choose_language": True})]
    write("Default.sublime-commands", [{"caption": "Paradox: " + title, "command": cmd, "args": args} for title, cmd, args in COMMANDS + extra])
    groups = [("Setup and server", 0, 6), ("Scripts and documentation", 6, 13), ("Localization", 13, 18),
              ("Events and dynasties", 18, 25), ("GUI tools", 25, 36), ("Authoring and validation", 36, len(COMMANDS))]
    write("Main.sublime-menu", [{"id": "tools", "children": [{"caption": "Paradox Modding", "children": [
        {"caption": group, "children": [{"caption": title, "command": cmd, "args": args} for title, cmd, args in COMMANDS[start:end]]}
        for group, start, end in groups]}]},
        {"id": "preferences", "children": [{"id": "package-settings", "children": [{"caption": "LSP-px", "children": [
            {"caption": "Settings", "command": "edit_settings", "args": {"base_file": "Packages/LSP-px/LSP-px.sublime-settings"}},
            {"caption": "Setup", "command": "px_setup"}]}]}]}])
    write("Context.sublime-menu", [{"caption": "Paradox", "children": [
        {"caption": title, "command": cmd, "args": args} for title, cmd, args in COMMANDS if cmd in ("px_localization", "px_snippets") or title in ("Inspect Scope at Cursor", "Run Tiger Validation")]}])


if __name__ == "__main__":
    main()
