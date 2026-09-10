"""Real Sublime API tests; skipped by normal CPython, run in UnitTesting CI."""
import importlib
import json
import unittest
try:
    import sublime
except ImportError:
    sublime = None


@unittest.skipIf(sublime is None, 'requires Sublime Text')
class EditorTest(unittest.TestCase):
    def setUp(self):
        self.module = importlib.import_module('LSP-px.plugin')
        self.view = sublime.active_window().new_file()
        self.view.set_scratch(True)

    def tearDown(self):
        self.view.close()

    def test_helper_api_and_all_syntax_resources(self):
        self.assertTrue(self.module.HAS_LSP)
        for name in self.module.SYNTAXES.values():
            self.view.assign_syntax('Packages/LSP-px/syntaxes/' + name + '.tmLanguage')
            self.assertTrue(self.view.syntax().scope.startswith('source.paradox'))

    def test_buffer_writer_undo_and_encoding(self):
        self.view.run_command('px_set_text', {'expected': '', 'text': 'l_english:\n key:0 "ü 😀"\n', 'bom': True})
        self.assertEqual(self.view.encoding(), 'UTF-8 with BOM')
        self.assertIn('ü 😀', self.view.substr(sublime.Region(0, self.view.size())))
        self.view.run_command('undo')
        self.assertEqual(self.view.size(), 0)

    def test_menu_commands_exist(self):
        import sublime_plugin
        classes = sublime_plugin.window_command_classes + sublime_plugin.text_command_classes
        commands = {c(None).name() for c in classes if c.__module__ == self.module.__name__}
        entries = json.loads(sublime.load_resource('Packages/LSP-px/Default.sublime-commands'))
        for entry in entries:
            self.assertIn(entry['command'], commands)

    def test_report_is_real_html_sheet(self):
        sheet = self.module.ui.report(self.view.window(), 'Test', {'file': '', 'count': 1})
        self.assertIsInstance(sheet, sublime.HtmlSheet)
        sheet.close()
