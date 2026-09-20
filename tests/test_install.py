"""Managed updates through the same entry point used by the Sublime adapter."""
import copy
import hashlib
import http.client
import io
import json
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest.mock import patch
import urllib.error
import zipfile

try:
    import sublime
except ImportError:
    from lib import install
else:
    import importlib
    install = importlib.import_module('LSP-px.lib.install')


def archive(version, bundled=False, runtime=True):
    files = {'px-lsp-' + version + '/dist/server.js': version.encode()}
    if bundled and runtime:
        files['px-lsp-' + version + '/node.exe'] = b'node runtime'
    output = io.BytesIO()
    if bundled:
        with zipfile.ZipFile(output, 'w') as bundle:
            for name, content in files.items():
                bundle.writestr(name, content)
    else:
        with tarfile.open(fileobj=output, mode='w:gz') as bundle:
            for name, content in files.items():
                entry = tarfile.TarInfo(name)
                entry.size = len(content)
                bundle.addfile(entry, io.BytesIO(content))
    return output.getvalue()


def release(version='0.3.5', bundled=False, runtime=True):
    content = archive(version, bundled, runtime)
    name = ('px-lsp-win-x64-' + version + '.zip' if bundled
            else 'px-lsp-server-' + version + '.tar.gz')
    asset = {'name': name, 'state': 'uploaded',
             'browser_download_url': install.DOWNLOADS + 'v0.4.4/' + name,
             'digest': 'sha256:' + hashlib.sha256(content).hexdigest()}
    return {'draft': False, 'prerelease': False, 'assets': [asset]}, content


class ManagedUpdateTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        # Normalize macOS /var aliases and Windows short temporary paths.
        self.storage = Path(self.tmp.name).resolve()
        self.options = {'heap_mb': 1024}
        self.node = patch.object(install, 'node_path', return_value='/node')
        self.node.start()
        self.addCleanup(self.node.stop)

    def seed(self, version='0.3.4', bundled=False):
        metadata, content = release(version, bundled)
        asset = metadata['assets'][0]
        with patch.object(install.urllib.request, 'urlopen', return_value=io.BytesIO(content)):
            return install.install_release(self.storage, 'server-' + version + ('-win' if bundled else ''),
                (asset['browser_download_url'], asset['digest'][7:]), 'server.js', bundled)

    def response(self, metadata, content, calls):
        def open_url(request, timeout):
            calls.append(request.full_url)
            if request.full_url == install.RELEASES:
                return io.BytesIO(json.dumps(metadata).encode())
            self.assertEqual(request.full_url, metadata['assets'][0]['browser_download_url'])
            return io.BytesIO(content)
        return open_url

    def test_first_start_installs_latest_verified_server(self):
        metadata, content = release()
        calls = []
        with patch.object(install.urllib.request, 'urlopen', side_effect=self.response(metadata, content, calls)):
            command = install.server_command(self.storage, self.options)
        self.assertEqual(command[:2], ['/node', '--max-old-space-size=1024'])
        self.assertEqual(command[-1], '--stdio')
        self.assertEqual(Path(command[-2]).read_text(), '0.3.5')
        self.assertEqual(len(calls), 2)
        self.assertFalse((self.storage / 'server-0.3.4').exists())

    def test_upgrade_preserves_old_install_and_reuses_latest_on_restart(self):
        old = self.seed()
        metadata, content = release()
        calls = []
        with patch.object(install.urllib.request, 'urlopen', side_effect=self.response(metadata, content, calls)):
            updated = install.server_command(self.storage, self.options)
            restarted = install.server_command(self.storage, self.options)
        self.assertEqual(old.read_text(), '0.3.4')
        self.assertEqual(Path(updated[-2]).read_text(), '0.3.5')
        self.assertEqual(updated, restarted)
        self.assertEqual(calls.count(install.RELEASES), 2)
        self.assertEqual(len(calls), 3)
        self.assertEqual(list(self.storage.glob('.install-*')), [])

    def test_updates_cross_minor_and_major_versions(self):
        self.seed()
        for version in ('0.4.0', '1.0.0', '1.10.0'):
            metadata, content = release(version)
            with patch.object(install.urllib.request, 'urlopen', side_effect=self.response(metadata, content, [])):
                command = install.server_command(self.storage, self.options)
            self.assertEqual(Path(command[-2]).read_text(), version)

    def test_offline_and_rate_limited_start_reuses_newest_cache(self):
        self.seed('0.3.4')
        newest = self.seed('0.3.10')
        self.seed('0.3.9')
        for error in (urllib.error.URLError('offline'), TimeoutError('timeout'),
                      urllib.error.HTTPError(install.RELEASES, 403, 'rate limited', {}, io.BytesIO())):
            if isinstance(error, urllib.error.HTTPError):
                self.addCleanup(error.close)
            with self.subTest(error=error), self.assertLogs(install.__name__, level='WARNING'), \
                    patch.object(install.urllib.request, 'urlopen', side_effect=error):
                command = install.server_command(self.storage, self.options)
            self.assertEqual(Path(command[-2]), newest)

    def test_bad_download_keeps_cache_and_cleans_staging(self):
        old = self.seed()
        metadata, content = release()
        with self.assertLogs(install.__name__, level='WARNING'), \
                patch.object(install.urllib.request, 'urlopen',
                             side_effect=self.response(metadata, content + b'tampered', [])):
            command = install.server_command(self.storage, self.options)
        self.assertEqual(Path(command[-2]), old)
        self.assertEqual(old.read_text(), '0.3.4')
        self.assertFalse((self.storage / 'server-0.3.5').exists())
        self.assertEqual(list(self.storage.glob('.install-*')), [])

    def test_invalid_metadata_keeps_cache(self):
        old = self.seed()
        for body in (b'{', b'null', b'[]', b'{}', b'x' * (2 * 1024 * 1024 + 1)):
            with self.subTest(body=body[:10]), self.assertLogs(install.__name__, level='WARNING'), \
                    patch.object(install.urllib.request, 'urlopen', return_value=io.BytesIO(body)):
                self.assertEqual(Path(install.server_command(self.storage, self.options)[-2]), old)

    def test_interrupted_download_and_invalid_archive_keep_cache(self):
        old = self.seed()
        metadata, _ = release()
        for error in (http.client.IncompleteRead(b'partial'), EOFError('truncated gzip')):
            def response(request, timeout):
                if request.full_url == install.RELEASES:
                    return io.BytesIO(json.dumps(metadata).encode())
                raise error
            with self.subTest(error=error), self.assertLogs(install.__name__, level='WARNING'), \
                    patch.object(install.urllib.request, 'urlopen', side_effect=response):
                self.assertEqual(Path(install.server_command(self.storage, self.options)[-2]), old)
        content = b'not an archive'
        metadata['assets'][0]['digest'] = 'sha256:' + hashlib.sha256(content).hexdigest()
        with self.assertLogs(install.__name__, level='WARNING'), \
                patch.object(install.urllib.request, 'urlopen', side_effect=self.response(metadata, content, [])):
            self.assertEqual(Path(install.server_command(self.storage, self.options)[-2]), old)
        self.assertEqual(list(self.storage.glob('.install-*')), [])

    def test_opt_out_keeps_newest_cache_without_network(self):
        self.seed()
        newest = self.seed('0.3.5')
        with patch.object(install.urllib.request, 'urlopen', side_effect=AssertionError('unexpected network')):
            command = install.server_command(self.storage, dict(self.options, auto_update_server=False))
        self.assertEqual(Path(command[-2]), newest)

    def test_manual_command_bypasses_update_and_runtime_detection(self):
        manual = ['/custom/node', '/custom/server.js', '--stdio']
        with patch.object(install, 'node_path', side_effect=AssertionError('unexpected runtime lookup')), \
                patch.object(install.urllib.request, 'urlopen', side_effect=AssertionError('unexpected network')):
            self.assertEqual(install.server_command(self.storage, {'server_command': manual}), manual)

    def test_old_remote_release_does_not_downgrade(self):
        newest = self.seed('0.3.10')
        metadata, content = release('0.3.5')
        calls = []
        with patch.object(install.urllib.request, 'urlopen', side_effect=self.response(metadata, content, calls)):
            command = install.server_command(self.storage, self.options)
        self.assertEqual(Path(command[-2]), newest)
        self.assertEqual(calls, [install.RELEASES])

    def test_bootstrap_install_when_discovery_fails_or_updates_disabled(self):
        metadata, content = release('0.3.4')
        asset = metadata['assets'][0]
        def response(request, timeout):
            if request.full_url == install.RELEASES:
                raise urllib.error.URLError('discovery unavailable')
            return io.BytesIO(content)
        with patch.object(install, 'SERVER', (asset['browser_download_url'], asset['digest'][7:])), \
                patch.object(install.urllib.request, 'urlopen', side_effect=response):
            with self.assertLogs(install.__name__, level='WARNING'):
                command = install.server_command(self.storage / 'automatic', self.options)
            disabled = install.server_command(self.storage / 'disabled', dict(self.options, auto_update_server=False))
        self.assertEqual(Path(command[-2]).read_text(), '0.3.4')
        self.assertEqual(Path(disabled[-2]).read_text(), '0.3.4')

    def test_windows_updates_bundled_runtime_together_with_server(self):
        old = self.seed(bundled=True)
        metadata, content = release(bundled=True)
        with patch.object(install, 'node_path', return_value=None), \
                patch.object(install.platform, 'system', return_value='Windows'), \
                patch.object(install.platform, 'machine', return_value='AMD64'), \
                patch.object(install.urllib.request, 'urlopen', side_effect=self.response(metadata, content, [])):
            command = install.server_command(self.storage, self.options)
        self.assertIn('server-0.3.5-win', command[0])
        self.assertTrue(Path(command[0]).is_file())
        self.assertEqual(Path(command[-2]).read_text(), '0.3.5')
        self.assertEqual(old.read_text(), '0.3.4')

    def test_missing_bundled_runtime_keeps_previous_install(self):
        old = self.seed(bundled=True)
        metadata, content = release(bundled=True, runtime=False)
        with self.assertLogs(install.__name__, level='WARNING'), \
                patch.object(install.urllib.request, 'urlopen', side_effect=self.response(metadata, content, [])):
            self.assertEqual(install.managed_server(self.storage, bundled_node=True), old)
        self.assertFalse((self.storage / 'server-0.3.5-win').exists())

    def test_partial_or_unsafe_cache_is_not_selected(self):
        old = self.seed()
        broken = self.storage / 'server-99.0.0'
        broken.mkdir()
        for marker in ('{', '[]', json.dumps({'entry': '../outside.js', 'sha256': 'a' * 64}),
                       json.dumps({'entry': 'missing/server.js', 'sha256': 'a' * 64})):
            (broken / 'installed.json').write_text(marker)
            self.assertEqual(install.managed_server(self.storage, auto_update=False), old)

    def test_update_setting_requires_boolean(self):
        for value in ('false', 0, None):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, 'auto_update_server'):
                install.server_command(self.storage, dict(self.options, auto_update_server=value))

    def test_pinned_older_cache_wins_without_network(self):
        old = self.seed('0.3.4')
        self.seed('0.3.5')
        with patch.object(install.urllib.request, 'urlopen', side_effect=AssertionError('unexpected network')):
            command = install.server_command(self.storage, dict(self.options, server_version='0.3.4'))
        self.assertEqual(Path(command[-2]), old)

    def test_downloads_exact_pin_even_with_a_newer_cache(self):
        newer = self.seed('0.3.6')
        metadata, content = release('0.3.5')
        def response(request, timeout):
            if request.full_url.startswith(install.RELEASE_HISTORY + '?'):
                return io.BytesIO(json.dumps([metadata]).encode())
            self.assertEqual(request.full_url, metadata['assets'][0]['browser_download_url'])
            return io.BytesIO(content)
        with patch.object(install.urllib.request, 'urlopen', side_effect=response):
            command = install.server_command(self.storage, dict(self.options, server_version='0.3.5'))
        self.assertEqual(Path(command[-2]).read_text(), '0.3.5')
        self.assertEqual(newer.read_text(), '0.3.6')

    def test_unavailable_pin_never_substitutes_another_version(self):
        old = self.seed()
        with patch.object(install, 'released_servers', return_value={}), \
                self.assertRaisesRegex(ValueError, '0.9.9'):
            install.server_command(self.storage, dict(self.options, server_version='0.9.9'))
        self.assertEqual(old.read_text(), '0.3.4')

    def test_pins_reject_unsupported_or_malformed_versions_before_network(self):
        with patch.object(install.urllib.request, 'urlopen', side_effect=AssertionError('unexpected network')):
            for version in ('0.3.3', '../server', 'latest', '', 4, '0.4.0-beta.1'):
                with self.subTest(version=version), self.assertRaises(ValueError):
                    install.server_command(self.storage, dict(self.options, server_version=version))

    def test_pinned_windows_server_uses_matching_bundled_node(self):
        old = self.seed('0.3.4', bundled=True)
        self.seed('0.3.5', bundled=True)
        with patch.object(install, 'node_path', return_value=None), \
                patch.object(install.platform, 'system', return_value='Windows'), \
                patch.object(install.platform, 'machine', return_value='AMD64'), \
                patch.object(install.urllib.request, 'urlopen', side_effect=AssertionError('unexpected network')):
            command = install.server_command(self.storage, dict(self.options, server_version='0.3.4'))
        self.assertEqual(Path(command[-2]), old)
        self.assertEqual(Path(command[0]), old.parent.parent / 'node.exe')

    def test_clearing_pin_resumes_automatic_updates(self):
        old = self.seed()
        pinned = dict(self.options, server_version='0.3.4')
        self.assertEqual(Path(install.server_command(self.storage, pinned)[-2]), old)
        metadata, content = release()
        with patch.object(install.urllib.request, 'urlopen', side_effect=self.response(metadata, content, [])):
            command = install.server_command(self.storage, dict(pinned, server_version=None))
        self.assertEqual(Path(command[-2]).read_text(), '0.3.5')


class ReleaseMetadataTest(unittest.TestCase):
    def test_history_filters_and_deduplicates_supported_stable_versions(self):
        latest, _ = release('0.3.5')
        old, _ = release('0.3.4')
        unsupported, _ = release('0.3.3')
        prerelease, _ = release('0.4.0')
        prerelease['prerelease'] = True
        unhashed, _ = release('0.3.6')
        unhashed['assets'][0]['digest'] = None
        with patch.object(install, 'release_metadata', return_value=[latest, latest, old, unsupported, prerelease, unhashed]):
            versions = install.released_servers()
        self.assertEqual(set(versions), {'0.3.4', '0.3.5'})

    def test_history_reads_older_pages_and_selects_platform_assets(self):
        latest, _ = release('0.3.5', bundled=True)
        old, _ = release('0.3.4', bundled=True)
        with patch.object(install, 'release_metadata', side_effect=[[latest] * 100, [old]]) as request:
            versions = install.released_servers(bundled_node=True)
        self.assertEqual(set(versions), {'0.3.4', '0.3.5'})
        self.assertEqual(request.call_args_list[1][0][0], install.RELEASE_HISTORY + '?per_page=100&page=2')
        self.assertTrue(versions['0.3.4'][0].endswith('.zip'))

    def test_rejects_prereleases_missing_hashes_and_other_download_hosts(self):
        metadata, _ = release()
        invalid = []
        for key in ('prerelease', 'draft'):
            item = copy.deepcopy(metadata)
            item[key] = True
            invalid.append(item)
        for key, value in (('digest', None), ('digest', 'sha256:invalid'),
                           ('browser_download_url', 'https://example.com/server.tar.gz'),
                           ('state', 'new'), ('name', 'px-lsp-server-0.4.0-beta.1.tar.gz'),
                           ('name', 'px-lsp-server-0.3.3.tar.gz')):
            item = copy.deepcopy(metadata)
            item['assets'][0][key] = value
            invalid.append(item)
        for item in invalid:
            with self.subTest(metadata=item), self.assertRaises(ValueError), \
                    patch.object(install.urllib.request, 'urlopen', return_value=io.BytesIO(json.dumps(item).encode())):
                install.latest_server()

    def test_selects_server_version_from_asset_not_toolkit_tag(self):
        metadata, _ = release('0.3.10')
        older, _ = release('0.3.9')
        metadata['tag_name'] = 'v9.0.0'
        metadata['assets'].extend(older['assets'])
        with patch.object(install.urllib.request, 'urlopen', return_value=io.BytesIO(json.dumps(metadata).encode())):
            version, artifact = install.latest_server()
        self.assertEqual(version, '0.3.10')
        self.assertEqual(artifact[0], metadata['assets'][0]['browser_download_url'])


if __name__ == '__main__':
    unittest.main()
