"""Exercise the pinned release over real framed stdio, without Sublime.

Usage: python scripts/protocol_smoke.py --server PATH [--game PATH]
Writes .dev/protocol-results.json. Fixtures are disposable and contain no game data.
"""
import argparse
import json
import queue
import subprocess
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from lib import core


class Client:
    def __init__(self, command):
        self.process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.messages, self.errors, self.serial = queue.Queue(), [], 0
        self.notifications = []
        threading.Thread(target=self.read, daemon=True).start()
        threading.Thread(target=lambda: self.errors.extend(iter(self.process.stderr.readline, b'')), daemon=True).start()

    def read(self):
        while True:
            headers = {}
            while True:
                line = self.process.stdout.readline()
                if not line:
                    return
                if line in (b'\r\n', b'\n'):
                    break
                k, v = line.decode().split(':', 1)
                headers[k.lower()] = v.strip()
            self.messages.put(json.loads(self.process.stdout.read(int(headers['content-length']))))

    def send(self, method, params, identifier=None):
        message = {'jsonrpc': '2.0', 'method': method, 'params': params}
        if identifier is not None:
            message['id'] = identifier
        self.write(message)

    def write(self, message):
        body = json.dumps(message).encode()
        self.process.stdin.write(('Content-Length: %d\r\n\r\n' % len(body)).encode() + body)
        self.process.stdin.flush()

    def request(self, method, params, timeout=120):
        self.serial += 1
        serial = self.serial
        self.send(method, params, serial)
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            value = self.messages.get(timeout=max(.01, deadline-time.monotonic()))
            if value.get('id') == serial and 'method' not in value:
                if 'error' in value:
                    raise RuntimeError('%s: %s' % (method, value['error']))
                return value.get('result')
            if 'id' in value and 'method' in value:
                self.write({'jsonrpc': '2.0', 'id': value['id'], 'result': None})
            elif 'method' in value:
                self.notifications.append(value)
        raise TimeoutError(method)


def fixture():
    root = ROOT / '.dev/fixture mod ü'
    files = {
        'descriptor.mod': 'name="PX integration"\nsupported_version="1.*"\n',
        'common/traits/px_traits.txt': 'px_test_trait = {\n\tprowess = 2\n}\n',
        'events/px_events.txt': 'namespace = px_test\npx_test.1 = {\n\ttype = character_event\n\ttitle = px_test_title\n\tdesc = px_test_desc\n\timmediate = { add_trait = px_test_trait }\n\toption = { name = px_test_option }\n}\n',
        'localization/english/px_test_l_english.yml': '\ufeffl_english:\n px_test_title:0 "Testing"\n px_test_desc:0 "A test"\n px_test_option:0 "Continue"\n px_test_trait:0 "Testing trait"\n px_test_trait_desc:0 "A trait"\n',
        'gui/px_test.gui': 'window = {\n\tname = "px_test_window"\n\tsize = { 600 400 }\n\ttext_single = {\n\t\tname = "px_label"\n\t\ttext = "px_test_title"\n\t}\n}\n',
    }
    for name, text in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding='utf-8')
    return root


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--server', required=True)
    parser.add_argument('--node', default='node')
    parser.add_argument('--game')
    args = parser.parse_args()
    root = fixture()
    storage = ROOT / '.dev/protocol-cache'
    storage.mkdir(exist_ok=True)
    settings = core.resolve_settings({'gamePath': args.game}, [str(root)])
    client = Client([args.node, '--max-old-space-size=4096', args.server, '--stdio'])
    results = {}
    def check(method, params):
        start = time.monotonic()
        value = client.request(method, params)
        results[method] = {'seconds': round(time.monotonic()-start, 3), 'result': value}
        print(method, 'OK', flush=True)
        return value
    try:
        init = check('initialize', {'processId': None, 'rootUri': root.as_uri(), 'workspaceFolders': [{'uri': root.as_uri(), 'name': root.name}],
            'capabilities': {'textDocument': {'completion': {'completionItem': {'snippetSupport': True}}}},
            'initializationOptions': {'settings': settings, 'storageDir': str(storage), 'client': {'ownFileWatcher': True, 'hoverHtml': False, 'hoverIcons': False, 'fileLinks': False, 'commands': []}}})
        assert init['serverInfo']['version'] == core.SERVER_VERSION
        client.send('initialized', {})
        event = root / 'events/px_events.txt'
        text = event.read_text(encoding='utf-8')
        doc = {'uri': event.as_uri()}
        client.send('textDocument/didOpen', {'textDocument': dict(doc, languageId='paradox', version=1, text=text)})
        for _ in range(600):
            inv = client.request('paradox/snippetCatalogue', {})
            if not inv.get('indexing') and inv.get('entries'):
                break
            time.sleep(.5)
        else:
            raise AssertionError('Full index never became ready')
        pos = core.position(text, text.index('px_test_trait')+3)
        for method, params in [
            ('textDocument/completion', {'textDocument': doc, 'position': core.position(text, text.index('add_trait')+3)}),
            ('textDocument/hover', {'textDocument': doc, 'position': pos}),
            ('textDocument/definition', {'textDocument': doc, 'position': pos}),
            ('textDocument/references', {'textDocument': doc, 'position': pos, 'context': {'includeDeclaration': True}}),
            ('textDocument/documentSymbol', {'textDocument': doc}),
            ('workspace/symbol', {'query': 'px_test'}),
            ('textDocument/foldingRange', {'textDocument': doc}),
            ('textDocument/semanticTokens/full', {'textDocument': doc}),
            ('textDocument/formatting', {'textDocument': doc, 'options': {'tabSize': 4, 'insertSpaces': False}}),
            ('textDocument/signatureHelp', {'textDocument': doc, 'position': pos}),
            ('textDocument/inlayHint', {'textDocument': doc, 'range': {'start': {'line': 0, 'character': 0}, 'end': core.position(text, len(text))}}),
            ('textDocument/documentColor', {'textDocument': doc}),
            ('textDocument/colorPresentation', {'textDocument': doc, 'range': {'start': pos, 'end': pos}, 'color': {'red': 1, 'green': 0, 'blue': 0, 'alpha': 1}}),
            ('textDocument/prepareRename', {'textDocument': doc, 'position': pos}),
            ('textDocument/rename', {'textDocument': doc, 'position': pos, 'newName': 'px_test_trait_renamed'}),
            ('textDocument/codeAction', {'textDocument': doc, 'range': {'start': pos, 'end': pos}, 'context': {'diagnostics': []}}),
            ('paradox/indexStats', None), ('paradox/modOverview', {'modRoot': str(root)}),
            ('paradox/locCoverage', {'modRoot': str(root)}), ('paradox/overrides', {'modRoot': str(root)}),
            ('paradox/scopeAt', {'uri': doc['uri'], 'position': pos}),
            ('paradox/dependencies', {'uri': doc['uri'], 'position': pos, 'guiUses': True}),
            ('paradox/snippets', {'uri': doc['uri'], 'position': pos}), ('paradox/snippetCatalogue', {}),
            ('paradox/exampleWiki', None), ('paradox/lookupLoc', {'key': 'px_test_title'}),
            ('paradox/locText', {'keys': ['px_test_title'], 'modRoot': str(root)}),
            ('paradox/eventGraph', {'modRoot': str(root), 'maxNodes': 50, 'connectedOnly': False}),
            ('paradox/eventDetail', {'id': 'px_test.1', 'modRoot': str(root)}),
            ('paradox/eventVocabulary', {'modRoot': str(root)}),
            ('paradox/eventValueOptions', {'value': 'px_test_trait', 'modRoot': str(root)}),
            ('paradox/eventBanner', {'theme': 'default'}), ('paradox/dynastyTree', {'modRoot': str(root)}),
            ('paradox/modifierFormats', {'modRoot': str(root)}),
            ('paradox/definitionForm', {'kind': 'trait', 'name': 'px_test_trait', 'modRoot': str(root)}),
        ]:
            check(method, params)
        assert results['textDocument/definition']['result'], 'Definition must resolve fixture trait'
        assert results['textDocument/rename']['result'].get('changes'), 'Rename must return workspace edits'
        wiki = results['paradox/exampleWiki']['result']
        entry = next(e for e in wiki['entries'] if e['name'] == 'add_trait')
        check('paradox/exampleWikiEntry', {'name': entry['name'], 'kind': entry['kind']})
        gui = root / 'gui/px_test.gui'
        gd = {'uri': gui.as_uri(), 'text': gui.read_text()}
        for method in ('guiTree', 'guiLayout', 'guiDependencies', 'guiVocabulary'):
            check('paradox/' + method, gd)
        check('paradox/guiWidgetInfo', dict(gd, line=0, placement=True))
        check('paradox/guiPreview', dict(gd, entries=[{'name': 'window', 'kind': 'builtin'}]))
        check('paradox/guiSaveValues', {'path': str(root / 'missing-test-save.ck3')})
        edit = check('paradox/guiSourceEdit', dict(gd, op={'kind': 'setProperties', 'line': 0, 'properties': [{'key': 'name', 'value': '"px_renamed"'}]}))
        assert edit.get('edits') and not edit.get('refused'), edit
        trait = root / 'common/traits/px_traits.txt'
        de = check('paradox/definitionEdit', {'uri': trait.as_uri(), 'text': trait.read_text(), 'ops': [{'op': 'setProperties', 'name': 'px_test_trait', 'properties': [{'key': 'prowess', 'value': '3'}]}]})
        assert de.get('edits'), de
        settings['hoverDetail'] = 'full'
        client.send('paradox/configChanged', settings)
        check('paradox/indexStats', None)
        client.notifications.clear()
        client.send('textDocument/didChange', {'textDocument': dict(doc, version=2), 'contentChanges': [{'text': 'px_broken = {\n'}]})
        for _ in range(30):
            time.sleep(.1)
            client.request('paradox/indexStats', None)
            ds = [n['params'] for n in client.notifications if n['method'] == 'textDocument/publishDiagnostics' and n['params']['uri'] == doc['uri']]
            if ds and ds[-1]['diagnostics']:
                results['diagnostic-push'] = ds[-1]
                break
        else:
            raise AssertionError('Malformed script did not publish diagnostics')
        check('shutdown', None)
        client.send('exit', None)
        client.process.wait(timeout=15)
        assert client.process.returncode == 0
    finally:
        if client.process.poll() is None:
            client.process.kill()
            client.process.wait()
        results['_stderr'] = b''.join(client.errors).decode(errors='replace')
        (ROOT / '.dev/protocol-results.json').write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding='utf-8')


if __name__ == '__main__':
    main()
