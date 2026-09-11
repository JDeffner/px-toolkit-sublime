"""Real Sublime API tests; skipped by normal CPython, run in UnitTesting CI."""
import importlib
import json
import unittest
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
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

    def test_script_comment_toggle(self):
        self.view.assign_syntax('Packages/LSP-px/syntaxes/Paradox Script.tmLanguage')
        self.view.run_command('px_set_text', {'text': 'test = yes'})
        self.view.run_command('toggle_comment', {'block': False})
        self.assertTrue(self.view.substr(sublime.Region(0, self.view.size())).startswith('#'))

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


@unittest.skipIf(sublime is None, 'requires Sublime Text')
class AuditRegressionTest(unittest.TestCase):
    def setUp(self):
        self.module = importlib.import_module('LSP-px.plugin')
        self.window = sublime.active_window()
        self.old_project = self.window.project_data()
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / 'mod'
        self.root.mkdir()
        (self.root / 'descriptor.mod').write_text('name="Test"')
        self.project = {'folders': [{'path': str(self.root)}], 'settings': {'LSP': {'LSP-px': {
            'enabled': False, 'settings': {}}}}}
        self.window.set_project_data(self.project)
        self.views = []
        self.errors = patch.object(self.module.ui, 'error').start()
        self.addCleanup(patch.stopall)

    def tearDown(self):
        self.module.TIGER_RUNS.pop(self.window.id(), None)
        for view in self.views:
            view.set_scratch(True)
            view.close()
        self.window.set_project_data(self.old_project)
        self.tmp.cleanup()

    def buffer(self, file, text):
        view = self.window.new_file()
        view.retarget(str(file))
        view.run_command('px_set_text', {'text': text})
        self.views.append(view)
        return view

    def test_writer_refuses_nested_and_playset_parents(self):
        parent = self.root / 'dependencies/base'
        parent.mkdir(parents=True)
        self.project['settings']['LSP']['LSP-px']['settings']['parentPaths'] = [str(parent)]
        self.window.set_project_data(self.project)
        view = self.buffer(parent / 'events/a.txt', 'original = 1')
        args = {'expected': 'original = 1', 'edits': [{'start': 0, 'end': 8, 'newText': 'changed'}]}
        view.run_command('px_apply_source_edits', args)
        self.assertEqual(view.substr(sublime.Region(0, view.size())), 'original = 1')
        self.errors.assert_called_once()
        (parent / 'descriptor.mod').write_text('name="Parent"')
        config = self.root / '.px-toolkit/playset.json'
        config.parent.mkdir()
        config.write_text(json.dumps({'parents': [str(parent)]}))
        self.project['folders'].append({'path': str(parent)})
        self.project['settings']['LSP']['LSP-px']['settings'] = {}
        self.window.set_project_data(self.project)
        view.run_command('px_apply_source_edits', args)
        self.assertEqual(view.substr(sublime.Region(0, view.size())), 'original = 1')
        view.retarget(str(self.root / 'events/own.txt'))
        view.run_command('px_apply_source_edits', args)
        self.assertEqual(view.substr(sublime.Region(0, view.size())), 'changed = 1')

    def test_localization_command_updates_unsaved_french_buffer(self):
        file = self.root / 'localization/french/custom_l_french.yml'
        text = 'l_french:\n shared_key:3 "Old" # keep\n other:0 "Unsaved"\n'
        view = self.buffer(file, text)
        entries = [{'source': 'vanilla', 'file': str(Path(self.tmp.name) / 'base_l_english.yml'), 'value': 'English', 'line': 0}]
        with patch.object(self.module, 'request', side_effect=lambda w, m, p, callback, v: callback(entries)), \
                patch.object(self.module.ui, 'when_loaded', side_effect=lambda v, callback: callback(v)):
            self.window.run_command('px_localization', {'key': 'shared_key', 'language': 'french', 'value': 'New'})
        self.assertEqual(view.substr(sublime.Region(0, view.size())), text.replace('"Old"', '"New"'))
        self.assertEqual(view.encoding(), 'UTF-8 with BOM')
        self.assertFalse(file.exists())
        self.assertFalse((self.root / 'localization/replace').exists())
        self.errors.assert_not_called()

    def test_localization_command_offers_all_exact_sites(self):
        files = [self.root / 'localization/french/a_l_french.yml', self.root / 'localization/replace/b_l_french.yml']
        for file in files:
            self.buffer(file, 'l_french:\n shared_key:0 "Old"\n')
        with patch.object(self.module, 'request', side_effect=lambda w, m, p, callback, v: callback([])), \
                patch.object(self.module.ui, 'pick') as picker:
            self.window.run_command('px_localization', {'key': 'shared_key', 'language': 'french', 'value': 'New'})
        self.assertEqual({r['file'] for r in picker.call_args[0][2]}, {str(f) for f in files})
        self.assertTrue(all('"Old"' in v.substr(sublime.Region(0, v.size())) for v in self.views))

    def test_localization_explicit_dependency_target_is_refused(self):
        parent = self.root / 'localization/french/parent'
        parent.mkdir(parents=True)
        self.project['settings']['LSP']['LSP-px']['settings']['parentPaths'] = [str(parent)]
        self.window.set_project_data(self.project)
        view = self.buffer(parent / 'a_l_french.yml', 'l_french:\n key:0 "Parent"\n')
        with patch.object(self.module, 'request', side_effect=lambda w, m, p, callback, v: callback([])):
            self.window.run_command('px_localization', {'key': 'key', 'language': 'french', 'value': 'New', 'target': view.file_name()})
        self.assertIn('"Parent"', view.substr(sublime.Region(0, view.size())))
        self.errors.assert_called_once()

    def test_rejected_tiger_replacement_keeps_active_run(self):
        view = self.buffer(self.root / 'events/a.txt', 'dirty = yes')
        previous = self.module.tiger.TigerRun()
        self.module.TIGER_RUNS[self.window.id()] = previous
        view.set_status('px_tiger', 'Tiger: running')
        self.window.run_command('px_tiger', {'manual': False})
        self.assertFalse(previous.cancelled.is_set())
        self.assertIs(self.module.TIGER_RUNS[self.window.id()], previous)
        (self.root / 'descriptor.mod').unlink()
        self.window.run_command('px_tiger', {'manual': False})
        self.assertFalse(previous.cancelled.is_set())
        self.assertEqual(view.get_status('px_tiger'), 'Tiger: running')
        self.window.run_command('px_tiger', {'cancel': True})
        self.assertTrue(previous.cancelled.is_set())
        self.assertNotIn(self.window.id(), self.module.TIGER_RUNS)
        self.assertFalse(view.get_status('px_tiger'))

    def test_invalid_playset_preserves_watcher_and_session(self):
        view = self.buffer(self.root / 'descriptor.mod', '')
        view.assign_syntax('Packages/LSP-px/syntaxes/Paradox Descriptor.tmLanguage')
        session = SimpleNamespace(window=self.window, send_notification=Mock())
        obj = self.module.PxPlugin(lambda: session)
        obj.settings = self.module.resolved(self.window)
        old_settings = obj.settings
        obj.watcher = Mock()
        config = self.root / '.px-toolkit/playset.json'
        config.parent.mkdir()
        with patch.object(self.module, 'ModWatcher') as watcher, patch.object(self.module, 'restart') as restart:
            for value in ('../parent', None, 42):
                config.write_text(json.dumps({'parents': value}))
                obj.sync_settings()
                obj._files_changed_async([str(config)])
                self.module.PxEvents().on_post_save(view)
                self.assertIn('Playset', view.get_status('px_config'))
            watcher.assert_not_called()
            restart.assert_not_called()
        obj.watcher.stop.assert_not_called()
        session.send_notification.assert_not_called()
        self.assertIs(obj.settings, old_settings)

    def test_tiger_failure_cannot_clear_a_newer_run(self):
        view = self.buffer(self.root / 'events/a.txt', '')
        view.run_command('undo')
        self.assertFalse(view.is_dirty())
        previous = self.module.tiger.TigerRun()
        self.module.TIGER_RUNS[self.window.id()] = previous
        pending = []
        with patch.object(self.module.threading, 'Thread') as thread, \
                patch.object(self.module, 'tiger_executable', side_effect=ValueError('test failure')), \
                patch.object(self.module.ui, 'on_main', side_effect=pending.append):
            self.window.run_command('px_tiger')
            first = self.module.TIGER_RUNS[self.window.id()]
            self.assertTrue(previous.cancelled.is_set())
            self.assertIsNot(first, previous)
            thread.call_args[1]['target']()
            self.window.run_command('px_tiger')
            replacement = self.module.TIGER_RUNS[self.window.id()]
            self.assertIsNot(replacement, first)
            for callback in pending:
                callback()
        self.assertIs(self.module.TIGER_RUNS[self.window.id()], replacement)
        self.assertIn('running', view.get_status('px_tiger'))
        self.errors.assert_not_called()
        self.window.run_command('px_tiger', {'cancel': True})

    def test_restart_dispatches_from_html_sheet(self):
        self.buffer(self.root / 'events/a.txt', '')
        sheet = self.window.new_html_sheet('Regression', '<body>Report</body>')
        self.window.focus_sheet(sheet)
        try:
            self.assertIsNone(self.window.active_view())
            with patch.object(sublime.View, 'run_command') as dispatch:
                self.window.run_command('px_restart')
                dispatch.assert_called_once_with('lsp_restart_server', {'config_name': 'LSP-px'})
        finally:
            sheet.close()
