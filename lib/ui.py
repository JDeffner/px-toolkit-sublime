"""Native quick panels, source navigation and readable reports."""
from __future__ import annotations

import html
import json
import os
import re

import sublime

LIVE_REPORTS = {}


def refresh_window(window):
    valid = {sheet.id() for sheet in window.sheets()}
    for key, (sheet, refresh) in list(LIVE_REPORTS.items()):
        if key[0] != window.id():
            continue
        if sheet.id() not in valid:
            LIVE_REPORTS.pop(key, None)
        else:
            refresh(sheet)


def on_main(callback):
    sublime.set_timeout(callback)


def message(text):
    on_main(lambda: sublime.status_message("Paradox: " + str(text)))


def error(text):
    on_main(lambda: sublime.error_message("Paradox: " + str(text)))


def label(key):
    return re.sub(r"(?<=[a-z])(?=[A-Z])", " ", str(key)).replace("_", " ").capitalize()


def summary(value):
    if isinstance(value, dict):
        title = value.get("label") or value.get("name") or value.get("key") or value.get("id") or value.get("type")
        detail = value.get("shortDoc") or value.get("detail") or value.get("message") or value.get("doc") or value.get("value")
        return str(title or "Details"), str(detail or (str(len(value)) + " fields"))[:300]
    if isinstance(value, list):
        return str(len(value)) + " entries", ""
    if value is None:
        return "Not available", ""
    if isinstance(value, bool):
        return "Yes" if value else "No", ""
    return str(value), ""


def source_of(value, context_file=None, one_based=False):
    if not isinstance(value, dict):
        return None
    file = value.get("file") or value.get("fsPath") or value.get("fullpath")
    if not file and "line" in value:
        file = context_file
    if not isinstance(file, str) or not os.path.isabs(file):
        return None
    line = value.get("line", 0)
    return {"file": file, "line": max(0, line - int(one_based)) if isinstance(line, int) else 0}


def open_source(window, file, line=0, column=0, side=False):
    if not os.path.isfile(file):
        error("Source file no longer exists: " + file)
        return None
    if side:
        if window.num_groups() < 2:
            window.set_layout({"cols": [0.0, 0.5, 1.0], "rows": [0.0, 1.0], "cells": [[0, 0, 1, 1], [1, 0, 2, 1]]})
        group = (window.active_group() + 1) % window.num_groups()
        return window.open_file("{}:{}:{}".format(file, line + 1, column + 1), sublime.ENCODED_POSITION, group=group)
    return window.open_file("{}:{}:{}".format(file, line + 1, column + 1), sublime.ENCODED_POSITION)


def report(window, title, data, context_file=None, one_based=False, sheet=None, refresh=None):
    body = []
    def render(value, depth=0):
        if depth > 12:
            return
        if isinstance(value, dict):
            site = source_of(value, context_file, one_based)
            if site:
                url = sublime.command_url("px_open_source", site)
                body.append('<p><a href="{}">{}:{}</a></p>'.format(html.escape(url, quote=True), html.escape(os.path.basename(site["file"])), site["line"] + 1))
            for key, child in value.items():
                if key in ("file", "fsPath", "fullpath") and site:
                    continue
                body.append('<div style="margin-left: {}px"><b>{}</b></div>'.format(depth * 10, html.escape(label(key))))
                render(child, depth + 1)
        elif isinstance(value, list):
            if not value:
                body.append("<p>None.</p>")
            for child in value[:500]:
                render(child, depth)
            if len(value) > 500:
                body.append("<p>Showing 500 of {} entries. Use the searchable browser to inspect the remainder.</p>".format(len(value)))
        else:
            body.append('<p style="margin-left: {}px">{}</p>'.format(depth * 10, html.escape(summary(value)[0]).replace("\n", "<br>")))
    render(data)
    content = '<body id="px-report"><h2>{}</h2>{}</body>'.format(html.escape(title), "".join(body))
    if sheet:
        sheet.set_contents(content)
    else:
        sheet = window.new_html_sheet("Paradox: " + title, content)
    if refresh:
        LIVE_REPORTS[(window.id(), sheet.id())] = (sheet, refresh)
    return sheet


def browse(window, title, data, context_file=None, one_based=False, previous=None, refresh=None):
    """All entries remain searchable; large documents render only on selection."""
    rows, actions = [], []
    if previous:
        rows.append(sublime.QuickPanelItem("Back", details="Return to the previous list"))
        actions.append(previous)
    rows.append(sublime.QuickPanelItem("Read report", details=title))
    actions.append(lambda: report(window, title, data, context_file, one_based, refresh=refresh))
    site = source_of(data, context_file, one_based)
    if site:
        rows.append(sublime.QuickPanelItem("Open source", details="{}:{}".format(site["file"], site["line"] + 1)))
        actions.append(lambda: open_source(window, **site))
    items = list(data.items()) if isinstance(data, dict) else list(enumerate(data)) if isinstance(data, list) else [(title, data)]
    back = lambda: browse(window, title, data, context_file, one_based, previous)
    for key, value in items:
        name, detail = summary(value)
        caption = name if isinstance(key, int) else label(key) + ": " + name
        rows.append(sublime.QuickPanelItem(caption[:150], details=html.escape(detail)))
        if isinstance(value, (dict, list)):
            actions.append(lambda v=value, t=caption: browse(window, t, v, context_file, one_based, back))
        else:
            actions.append(lambda v=value, t=caption: report(window, t, v, context_file, one_based))
    window.show_quick_panel(rows, lambda i: actions[i]() if i >= 0 else None, placeholder=title)


def pick(window, title, items, callback):
    if not items:
        message("No results for " + title)
        return
    rows = []
    for item in items:
        name, detail = summary(item)
        rows.append(sublime.QuickPanelItem(name, details=html.escape(detail)))
    window.show_quick_panel(rows, lambda i: callback(items[i]) if i >= 0 else None, placeholder=title)


def when_loaded(view, callback, attempts=100):
    if not view or not view.is_valid():
        return
    if view.is_loading() and attempts:
        sublime.set_timeout(lambda: when_loaded(view, callback, attempts - 1), 30)
    elif not view.is_loading():
        callback(view)
    else:
        error("Timed out opening the target file")
