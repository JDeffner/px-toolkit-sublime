"""Executed by PxTestHarness inside an isolated real Sublime process.

Copy to the test profile's Data/integration.py, then subl --command px_test_run.
The runner uses real views, commands and LSP sessions; it records failures.
"""
import importlib
import json
import os
import time
import traceback
from pathlib import Path
import sublime

module = importlib.import_module('LSP-px.plugin')
ROOT = DATA.parents[2]
fixture = ROOT / '.dev/fixture mod ü'
local = json.loads((DATA / 'editor-config.json').read_text(encoding='utf-8-sig'))
results = {'build': sublime.version(), 'checks': [], 'errors': []}
record('editor', results)


def check(name, condition, detail=None):
    results['checks'].append({'name': name, 'passed': bool(condition), 'detail': detail})
    record('editor', results)
    if not condition:
        raise AssertionError(name + ': ' + str(detail))


def protect(fn):
    def guarded(*args):
        try:
            return fn(*args)
        except Exception:
            results['errors'].append(traceback.format_exc())
            record('editor', results)
    return guarded


def wait_for(predicate, callback, remaining=120):
    if predicate():
        protect(callback)()
    elif remaining:
        sublime.set_timeout(protect(lambda: wait_for(predicate, callback, remaining-1)), 500)
    else:
        check('wait timeout', False)


check('LSP imports', module.HAS_LSP)
window.set_project_data({'folders': [{'path': str(fixture)}], 'settings': {'LSP': {'LSP-px': {
    'px': {'server_command': [local['node'], local['server'], '--stdio'], 'tiger_path': local.get('tiger')},
    'settings': {'gamePath': local.get('game')}
}}}})
event = window.open_file(str(fixture / 'events/px_events.txt'))


def begin():
    module.assign_language(event)
    check('scoped syntax', event.syntax().scope == 'source.paradox', event.syntax().scope)
    wait_for(lambda: module.instance(window), connected)


def connected():
    obj = module.instance(window)
    check('one LSP session', bool(obj.weaksession()))
    results['server_version'] = obj.version
    check('workspace settings', obj.settings['workspaceMods'] == [str(fixture)], obj.settings)
    text = event.substr(sublime.Region(0, event.size()))
    position = module.core.position(text, text.index('px_test_trait')+2)
    session = obj.weaksession()
    calls = [
        ('textDocument/completion', {'textDocument': {'uri': module.core.file_uri(event.file_name())}, 'position': module.core.position(text, text.index('add_trait')+3)}),
        ('textDocument/hover', {'textDocument': {'uri': module.core.file_uri(event.file_name())}, 'position': position}),
        ('textDocument/definition', {'textDocument': {'uri': module.core.file_uri(event.file_name())}, 'position': position}),
        ('textDocument/semanticTokens/full', {'textDocument': {'uri': module.core.file_uri(event.file_name())}}),
        ('paradox/snippetCatalogue', {})
    ]
    def step(index=0):
        if index == len(calls):
            sublime.set_timeout(protect(writers))
            return
        method, payload = calls[index]
        def done(value):
            check(method, bool(value), str(value)[:300])
            sublime.set_timeout_async(protect(lambda: step(index+1)))
        session.send_request_async(module.Request(method, payload, event), protect(done), protect(lambda err: check(method, False, err)))
    # Wait for full indexing so vocabulary-backed completions are meaningful.
    wait_for(lambda: obj.health.get('indexing') is False, lambda: sublime.set_timeout_async(protect(step)))


def writers():
    target = fixture / 'common/traits/px_undo.txt'
    target.write_text('px_undo = { prowess = 1 }\n', encoding='utf-8')
    view = window.open_file(str(target))
    def loaded():
        module.assign_language(view)
        before = view.substr(sublime.Region(0, view.size()))
        i = before.index('1')
        view.run_command('px_apply_source_edits', {'expected': before, 'edits': [{'start': i, 'end': i+1, 'newText': '2'}]})
        check('source edit applied', 'prowess = 2' in view.substr(sublime.Region(0, view.size())))
        view.run_command('undo')
        check('single undo restores source', view.substr(sublime.Region(0, view.size())) == before)
        # Record expected errors instead of opening modal dialogs in this test.
        original = module.ui.error
        captured = []
        module.ui.error = lambda message: captured.append(str(message))
        try:
            view.run_command('px_apply_source_edits', {'expected': 'stale', 'edits': [{'start': i, 'end': i+1, 'newText': '9'}]})
            check('stale edit refused', bool(captured) and view.substr(sublime.Region(0, view.size())) == before)
        finally:
            module.ui.error = original
        window.focus_view(event)
        window.run_command('px_localization', {'key': 'px_test_title', 'value': 'Testing ü 😀'})
        loc = str(fixture / 'localization/english/px_test_l_english.yml')
        wait_for(lambda: window.find_open_file(loc) and window.find_open_file(loc).is_dirty(), lambda: localization_done(loc))
    wait_for(lambda: not view.is_loading(), loaded)


def localization_done(loc):
    view = window.find_open_file(loc)
    check('localization preserves existing keys', 'px_test_desc' in view.substr(sublime.Region(0, view.size())))
    check('localization UTF-8 BOM selected', view.encoding() == 'UTF-8 with BOM', view.encoding())
    view.run_command('save')
    wait_for(lambda: not view.is_dirty(), lambda: after_save(loc))


def after_save(loc):
    check('localization saved bytes BOM', Path(loc).read_bytes().startswith(b'\xef\xbb\xbf'))
    check('non-ASCII text saved', 'Testing ü 😀' in Path(loc).read_text(encoding='utf-8-sig'))
    window.focus_view(event)
    window.run_command('px_report', {'feature': 'indexStats', 'readable': True})
    gui = window.open_file(str(fixture / 'gui/px_test.gui'))
    def edit_gui():
        module.assign_language(gui)
        window.focus_view(gui)
        window.run_command('px_gui', {'action': 'set', 'line': 0, 'key': 'name', 'value': '"px_edited"'})
        wait_for(lambda: 'px_edited' in gui.substr(sublime.Region(0, gui.size())), lambda: gui_done(gui))
    wait_for(lambda: not gui.is_loading(), edit_gui)


def gui_done(gui):
    check('GUI command applies server edits', gui.is_dirty())
    gui.run_command('undo')
    check('GUI undo', 'px_test_window' in gui.substr(sublime.Region(0, gui.size())))
    window.focus_view(event)
    window.run_command('px_definition', {'kind': 'trait', 'name': 'px_created_by_test'})
    file = str(fixture / 'common/traits/px_px_created_by_test.txt')
    def created():
        view = window.find_open_file(file)
        check('definition generated with chosen identifier', 'px_created_by_test = {' in view.substr(sublime.Region(0, view.size())))
        view.run_command('save')
        wait_for(lambda: not view.is_dirty(), tiger_bad)
    wait_for(lambda: window.find_open_file(file) and window.find_open_file(file).is_dirty(), created)


def tiger_bad():
    if not local.get('tiger'):
        finish()
        return
    path = fixture / 'common/traits/px_tiger_test.txt'
    path.write_text('px_tiger_test = {\n this_is_not_a_trait_property = 123\n}\n', encoding='utf-8-sig')
    window.focus_view(event)
    window.run_command('px_tiger')
    def bad_done():
        rows = module.TIGER_RESULTS.get(window.id(), [])
        bad = [r for r in rows if r['file'] == str(path) and 'this_is_not_a_trait_property' in r['message']]
        check('Tiger reports invalid property', bool(bad), [r for r in rows if r['file'] == str(path)])
        path.write_text('px_tiger_test = {\n prowess = 1\n}\n', encoding='utf-8-sig')
        window.run_command('px_tiger')
        wait_for(lambda: window.id() not in module.TIGER_RUNS, lambda: tiger_fixed(path), 600)
    wait_for(lambda: window.id() not in module.TIGER_RUNS, bad_done, 600)


def tiger_fixed(path):
    rows = module.TIGER_RESULTS.get(window.id(), [])
    check('Tiger clears fixed diagnostic', not any(r['file'] == str(path) and 'this_is_not_a_trait_property' in r['message'] for r in rows))
    window.run_command('px_tiger')
    run = module.TIGER_RUNS.get(window.id())
    window.run_command('px_tiger', {'cancel': True})
    check('Tiger cancellation', run is not None and run.cancelled.is_set() and window.id() not in module.TIGER_RUNS)
    finish()


def finish():
    results['complete'] = True
    record('editor', results)


wait_for(lambda: not event.is_loading(), begin)
