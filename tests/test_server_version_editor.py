"""Version picker behavior using the real adapter inside Sublime."""
import copy
import importlib
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

try:
    import sublime
except ImportError:
    sublime = None


@unittest.skipIf(sublime is None, 'requires Sublime Text')
class ServerVersionCommandTest(unittest.TestCase):
    def setUp(self):
        self.module = importlib.import_module('LSP-px.plugin')
        self.global_data = {'px': {'heap_mb': 1024, 'auto_update_server': True, 'server_version': None}}
        self.project = {'folders': [{'path': '/mod'}], 'settings': {'LSP': {'LSP-px': {'px': {}}}}}
        self.window = Mock()
        self.window.project_data.side_effect = lambda: copy.deepcopy(self.project)
        self.window.set_project_data.side_effect = lambda value: setattr(self, 'project', value)
        self.window.project_file_name.return_value = '/mod/demo.sublime-project'
        self.window.is_valid.return_value = True
        settings = Mock()
        settings.get.side_effect = self.global_data.get
        settings.set.side_effect = self.global_data.__setitem__
        settings.to_dict.side_effect = lambda: copy.deepcopy(self.global_data)
        self.patch(self.module.sublime, 'load_settings', return_value=settings)
        self.save = self.patch(self.module.sublime, 'save_settings')
        self.restart = self.patch(self.module, 'restart')
        self.error = self.patch(self.module.ui, 'error')
        self.message = self.patch(self.module.ui, 'message')
        self.pick = self.patch(self.module.ui, 'pick')
        self.patch(self.module.ui, 'on_main', side_effect=lambda fn: fn())
        self.patch(self.module.threading, 'Thread',
                   side_effect=lambda **kwargs: SimpleNamespace(start=lambda: kwargs['target']()))
        self.prepare = self.patch(self.module.install, 'server_command', return_value=['node', 'server.js'])
        self.command = self.module.PxServerVersionCommand(self.window)

    def patch(self, target, name, **kwargs):
        context = patch.object(target, name, **kwargs)
        result = context.start()
        self.addCleanup(context.stop)
        return result

    def project_options(self):
        return self.project['settings']['LSP']['LSP-px']['px']

    def test_installs_before_persisting_project_pin_and_restarting(self):
        def prepare(storage, options):
            self.assertNotIn('server_version', self.project_options())
            self.restart.assert_not_called()
            self.assertEqual(options['server_version'], '0.3.4')
        self.prepare.side_effect = prepare
        self.command.run(version='0.3.4')
        self.assertEqual(self.project_options()['server_version'], '0.3.4')
        self.assertIsNone(self.global_data['px']['server_version'])
        self.save.assert_not_called()
        self.restart.assert_called_once_with(self.window)

    def test_failed_install_preserves_settings_and_current_session(self):
        original = copy.deepcopy(self.project)
        self.prepare.side_effect = ValueError('bad checksum')
        self.command.run(version='0.3.4')
        self.assertEqual(self.project, original)
        self.assertIsNone(self.global_data['px']['server_version'])
        self.restart.assert_not_called()
        self.save.assert_not_called()
        self.error.assert_called_once()

    def test_invalid_command_version_preserves_settings_and_session(self):
        self.command.run(version=4)
        self.assertEqual(self.project_options(), {})
        self.prepare.assert_not_called()
        self.restart.assert_not_called()
        self.error.assert_called_once()

    def test_automatic_choice_clears_pin_and_enables_updates(self):
        self.project_options().update({'server_version': '0.3.4', 'auto_update_server': False})
        self.command.run(automatic=True)
        self.assertIsNone(self.project_options()['server_version'])
        self.assertTrue(self.project_options()['auto_update_server'])
        chosen = self.prepare.call_args[0][1]
        self.assertIsNone(chosen['server_version'])
        self.assertTrue(chosen['auto_update_server'])
        self.restart.assert_called_once()

    def test_folder_window_persists_global_default_and_updates_local_override(self):
        self.window.project_file_name.return_value = None
        self.project_options()['server_version'] = '0.3.5'
        self.command.run(version='0.3.4')
        self.assertEqual(self.global_data['px']['server_version'], '0.3.4')
        self.assertEqual(self.project_options()['server_version'], '0.3.4')
        self.assertEqual(self.global_data['px']['heap_mb'], 1024)
        self.save.assert_called_once_with('LSP-px.sublime-settings')

    def test_offline_picker_still_offers_cached_versions_and_automatic(self):
        self.patch(self.module.install, 'server_runtime', return_value='node')
        self.patch(self.module.install, 'cached_servers', return_value={'0.3.5': '/cached/server.js'})
        self.patch(self.module.install, 'released_servers', side_effect=OSError('offline'))
        self.command.run()
        rows = self.pick.call_args[0][2]
        self.assertEqual([row['version'] for row in rows], [None, '0.3.5', '0.3.4'])
        self.assertIn('Cached', rows[1]['detail'])
        self.prepare.assert_not_called()
        self.restart.assert_not_called()
        self.assertEqual(self.project_options(), {})

    def test_manual_server_command_is_not_overwritten(self):
        self.project_options()['server_command'] = ['node', '/custom/server.js']
        original = copy.deepcopy(self.project)
        self.command.run(version='0.3.4')
        self.assertEqual(self.project, original)
        self.prepare.assert_not_called()
        self.restart.assert_not_called()
        self.error.assert_called_once()

    def test_settings_changed_during_download_are_not_overwritten(self):
        def change_settings(storage, options):
            self.project_options()['server_version'] = '0.3.6'
        self.prepare.side_effect = change_settings
        self.command.run(version='0.3.4')
        self.assertEqual(self.project_options()['server_version'], '0.3.6')
        self.restart.assert_not_called()
        self.save.assert_not_called()
