import io
import json
import os
from pathlib import Path
import shutil
import stat
import tarfile
import tempfile
import unittest
from unittest.mock import patch
import zipfile

try:
    import sublime
except ImportError:
    from lib import core, authoring, install, tiger
    from lib.watcher import changes, snapshot
else:
    import importlib
    core, authoring, install, tiger = [importlib.import_module('LSP-px.lib.' + name) for name in ('core', 'authoring', 'install', 'tiger')]
    watcher = importlib.import_module('LSP-px.lib.watcher')
    changes, snapshot = watcher.changes, watcher.snapshot


class WorkspaceTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "mod with ünicode"
        self.root.mkdir()
        (self.root / "descriptor.mod").write_text('name="Test"')
        self.other = Path(self.tmp.name) / "parent"
        self.other.mkdir()
        (self.other / "descriptor.mod").write_text('name="Parent"')

    def settings(self, **options):
        return core.resolve_settings(options, [str(self.root)])

    def test_mod_detection_and_language_routing(self):
        settings = self.settings()
        self.assertEqual(settings["modPath"], str(self.root))
        cases = {"events/a.txt": "script", "common/traits/a.txt": "script", "gfx/models/a.asset": "script",
                 "localization/english/a_l_english.yml": "loc", "localisation/a.yml": "loc", "gui/a.gui": "gui",
                 "descriptor.mod": "mod", "common/traits/_traits.info": "info", "README.txt": None, "config.yml": None,
                 "gfx/a.dds": None, "gfx/a.mesh": None}
        for file, mode in cases.items():
            with self.subTest(file=file):
                self.assertEqual(core.language_for(str(self.root / file), settings), mode)
        self.assertIsNone(core.language_for(str(self.other / "events/a.txt"), settings))

    def test_prefix_sibling_does_not_count_as_contained(self):
        self.assertFalse(core.under(str(self.root) + "_outside/file", str(self.root)))
        self.assertTrue(core.under(self.root / "events/a.txt", self.root))

    def test_parent_is_never_editable(self):
        result = core.resolve_settings({"parentPaths": [str(self.other)]}, [str(self.root), str(self.other)])
        self.assertEqual(result["workspaceMods"], [str(self.root)])
        self.assertIsNone(core.editable_root(str(self.other / "events/a.txt"), result))
        self.assertEqual(core.language_for(str(self.other / "events/a.txt"), result), "script")

    def test_active_file_does_not_change_default_root(self):
        raw = {"workspaceMods": [str(self.root), str(self.other)]}
        a = core.resolve_settings(raw, [str(self.root)], str(self.other / "events/a.txt"))
        self.assertEqual(a["modPath"], str(self.root))

    def test_excluded_root_and_vanilla_are_not_editable(self):
        result = core.resolve_settings({"gamePath": str(self.other)}, [str(self.root), str(self.other)], excluded=[str(self.root)])
        self.assertEqual(result["workspaceMods"], [])
        self.assertIsNone(result["modPath"])

    def test_settings_do_not_mutate_defaults(self):
        a = self.settings()
        a["diagnosticsIgnore"].append("one")
        self.assertEqual(self.settings()["diagnosticsIgnore"], [])

    def test_invalid_settings_rejected(self):
        for key, val in (("gameId", "vic3"), ("completionMode", "magic"), ("hoverDetail", "all"),
                         ("parentPaths", "bad"), ("tracePerf", "false"), ("locLanguage", "../evil")):
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.settings(**{key: val})

    def test_uri_roundtrip_and_percent_characters(self):
        path = str(self.root / "events/100% #é.txt")
        self.assertEqual(core.uri_path(core.file_uri(path)), os.path.normpath(path))

    def test_playset_paths_resolve_against_mod(self):
        folder = self.root / ".px-toolkit"
        folder.mkdir()
        (folder / "playset.json").write_text(json.dumps({"parents": ["../parent"]}))
        self.assertEqual(core.parents_for(self.settings(), str(self.root)), [str(self.other)])

    def test_watcher_create_edit_delete_and_config(self):
        before = snapshot([str(self.root)])
        file = self.root / "events/a.txt"
        file.parent.mkdir()
        file.write_text("one")
        after = snapshot([str(self.root)])
        self.assertEqual(changes(before, after), [str(file)])
        file.write_text("two longer")
        self.assertEqual(changes(after, snapshot([str(self.root)])), [str(file)])
        file.unlink()
        self.assertEqual(changes(after, snapshot([str(self.root)])), [str(file)])
        (self.root / ".git").mkdir()
        (self.root / ".git/ignored.txt").write_text("ignore")
        self.assertNotIn(str(self.root / ".git/ignored.txt"), snapshot([str(self.root)]))

    def test_localization_target_siblings_and_overrides(self):
        loc = self.root / "localization/english"
        loc.mkdir(parents=True)
        sibling = loc / "events_l_english.yml"
        sibling.write_text('l_english:\n px_event_title:0 "Title"\n', encoding="utf-8-sig")
        target = authoring.localization_target(str(self.root), "english", "px_event_desc", [])
        self.assertEqual(target, str(sibling))
        inherited = authoring.localization_target(str(self.root), "english", "vanilla_key", [{"file": "vanilla", "source": "vanilla"}])
        self.assertIn("replace", Path(inherited).parts)
        self.assertNotIn("replace", Path(authoring.localization_target(str(self.root), "english", "new_key", [])).parts)

    def test_localization_cannot_escape_mod(self):
        with self.assertRaises(ValueError):
            authoring.validate_loc_target(str(self.other / "x_l_english.yml"), str(self.root), "english")
        with self.assertRaises(ValueError):
            authoring.validate_loc_target(str(self.root / "localization/x_l_french.yml"), str(self.root), "english")

    def test_new_mod_refuses_overwrite(self):
        root = authoring.new_mod(self.tmp.name, "new_mod", "My Mod", "1.19.*")
        self.assertTrue((Path(root) / "descriptor.mod").read_bytes().startswith(b"\xef\xbb\xbf"))
        with self.assertRaises(FileExistsError):
            authoring.new_mod(self.tmp.name, "new_mod", "My Mod", "1.19.*")
        with self.assertRaises(ValueError):
            authoring.new_mod(self.tmp.name, "../escape", "My Mod", "1.19.*")


class EditsTest(unittest.TestCase):
    def test_utf16_positions_roundtrip(self):
        text = "# 🐯\r\nname = { café }\n"
        for point in range(len(text) + 1):
            if point and text[point - 1] == "\r":
                continue
            self.assertEqual(core.point_at(text, core.position(text, point)), point)

    def test_utf16_edits_preserve_emoji_comments_and_crlf(self):
        text = "# 🐯\r\na = 1\r\nb = 2\r\n"
        start = len(text[:text.index("1")].encode("utf-16-le")) // 2
        result = core.offset_edits(text, [{"start": start, "end": start + 1, "newText": "42"}])
        self.assertEqual(result, text.replace("1", "42"))

    def test_invalid_and_overlapping_edits_refused(self):
        for edits in ([{"start": 1, "end": 2, "newText": ""}],
                      [{"start": 0, "end": 5, "newText": ""}, {"start": 2, "end": 3, "newText": ""}],
                      [{"start": 0, "end": 100, "newText": ""}]):
            with self.assertRaises(ValueError):
                core.offset_edits("🐯abc", edits)

    def test_loc_preserves_version_comments_eol_and_unicode(self):
        text = 'l_english:\r\n key:42 "old" # note\r\n other:0 "Stay"\r\n'
        result = authoring.upsert_localization(text, "key", 'New "quote" 🐯', "english")
        self.assertEqual(result, 'l_english:\r\n key:42 "New \\"quote\\" 🐯" # note\r\n other:0 "Stay"\r\n'.replace('\\\\"', '\\"'))

    def test_loc_new_file_and_no_final_newline(self):
        self.assertEqual(authoring.upsert_localization("", "key", "Text", "english"), 'l_english:\n key:0 "Text"\n')
        result = authoring.upsert_localization('l_english:\n a:0 "A"', "b", "B", "english")
        self.assertIn('"A"\n b:', result)

    def test_loc_duplicate_malformed_or_wrong_header_refused(self):
        for text in ('l_french:\n key:0 "A"\n', 'l_english:\n key:0 "A"\n key:0 "B"\n', 'l_english:\n key:0 "broken'):
            with self.subTest(text=text), self.assertRaises(ValueError):
                authoring.upsert_localization(text, "key", "New", "english")

    def test_descriptor_quotes_do_not_change_structure(self):
        fields = json.loads((Path(__file__).parents[1] / "data/descriptor.json").read_text(encoding="utf-8"))["fields"]
        text = 'name="Mod # { Test }"\nversion="1"\nsupported_version="1.19.*"\nreplace_path="history"\nreplace_path="common"\n'
        self.assertEqual(authoring.descriptor_issues(text, fields), [])
        issues = authoring.descriptor_issues(text + 'name="Again"\npath="a"\nunknown=1\n', fields)
        self.assertEqual({i["code"] for i in issues}, {"descriptor-duplicate-key", "descriptor-path-ignored", "descriptor-unknown-key"})


class ArchiveTest(unittest.TestCase):
    def test_zip_slip_and_symlink_refused(self):
        for name, mode in (("../escape", 0), ("C:/escape", 0), ("a\\..\\escape", 0), ("link", stat.S_IFLNK << 16)):
            content = io.BytesIO()
            with zipfile.ZipFile(content, "w") as z:
                entry = zipfile.ZipInfo(name)
                entry.external_attr = mode
                z.writestr(entry, "no")
            with tempfile.TemporaryDirectory() as tmp, self.assertRaises(ValueError):
                install.safe_extract(content.getvalue(), tmp, True)

    def test_tar_link_refused(self):
        content = io.BytesIO()
        with tarfile.open(fileobj=content, mode="w:gz") as archive:
            entry = tarfile.TarInfo("link")
            entry.type = tarfile.SYMTYPE
            entry.linkname = "../outside"
            archive.addfile(entry)
        with tempfile.TemporaryDirectory() as tmp, self.assertRaises(ValueError):
            install.safe_extract(content.getvalue(), tmp)

    def test_atomic_install_preserves_previous_version_on_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            old = Path(tmp) / "server-old"
            old.mkdir()
            (old / "server.js").write_text("working")
            with patch.object(install, "download", side_effect=ValueError("bad checksum")), self.assertRaises(ValueError):
                install.install_release(tmp, "server-new", ("https://example.com/file", "hash"), "server.js")
            self.assertEqual((old / "server.js").read_text(), "working")
            self.assertFalse((Path(tmp) / "server-new").exists())
            self.assertEqual(list(Path(tmp).glob(".install-*")), [])


class TigerTest(unittest.TestCase):
    def test_file_level_report_with_null_coordinates(self):
        with tempfile.TemporaryDirectory() as tmp:
            reports = [{"message": "Expected UTF-8 BOM encoding", "key": "encoding", "locations": [
                {"fullpath": str(Path(tmp) / "a.txt"), "linenr": None, "line": None, "column": None, "length": None}]}]
            result = tiger.diagnostics(reports, tmp, core.SETTINGS)
            self.assertEqual((result[0]["line"], result[0]["column"], result[0]["length"]), (0, 0, 1))

    def test_noise_and_unknown_fields(self):
        reports = tiger.parse_reports('Loading [progress]\n[{"message":"bad", "key":"unknown", "newField": 1}]')
        self.assertEqual(len(reports), 1)
        with self.assertRaises(ValueError):
            tiger.parse_reports("failed")

    def test_suppression_same_line_next_line_and_reason(self):
        settings = {"diagnosticsIgnore": ["global"], "diagnosticsIgnorePatterns": ["common/**/vendor/*.txt"]}
        self.assertTrue(tiger.suppressed("", 0, "global", "a.txt", settings))
        self.assertTrue(tiger.suppressed("", 0, "code", "common/vendor/a.txt", settings))
        self.assertTrue(tiger.suppressed("# px:ignore-next-line code -- reason\na = 1", 1, "code", "a.txt", settings))
        self.assertFalse(tiger.suppressed("# px:ignore-next-line code\na = 1", 1, "other", "a.txt", settings))
        self.assertTrue(tiger.suppressed("a = 1 # px:ignore -- reason", 0, "all", "a.txt", settings))

    def test_glob_semantics(self):
        self.assertTrue(tiger.glob_match("*.txt", "common/a.TXT"))
        self.assertTrue(tiger.glob_match("common/**/a.txt", "common/a.txt"))
        self.assertTrue(tiger.glob_match("common/**/a.txt", "common/nested/a.txt"))
        self.assertFalse(tiger.glob_match("common/*.txt", "common/nested/a.txt"))

    def test_reports_do_not_diagnose_parent_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "mod"
            root.mkdir()
            reports = [{"message": "bad", "locations": [{"fullpath": str(root / "a.txt"), "linenr": 2}, {"fullpath": str(Path(tmp) / "vanilla.txt")}]}]
            rows = tiger.diagnostics(reports, str(root), core.SETTINGS)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["line"], 1)


if __name__ == "__main__":
    unittest.main()
