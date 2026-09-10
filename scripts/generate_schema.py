"""Generate JSON validation for every exposed server and adapter setting."""
import json
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from lib.core import SETTINGS

properties = {}
for key, value in SETTINGS.items():
    kind = 'boolean' if isinstance(value, bool) else 'array' if isinstance(value, list) else 'string'
    properties[key] = {'type': kind, 'default': value}
    if kind == 'array':
        properties[key]['items'] = {'type': 'string'}
    if value is None:
        properties[key]['type'] = ['string', 'null']
properties['gameId']['enum'] = ['ck3']
properties['completionMode']['enum'] = ['minimal', 'examples', 'names']
properties['hoverDetail']['enum'] = ['compact', 'standard', 'full']
properties['locLanguage']['pattern'] = '^[a-z_]+$'
properties['calendar'] = {'type': ['object', 'null'], 'required': ['epoch', 'after'], 'additionalProperties': False,
    'properties': {'epoch': {'type': 'integer'}, 'after': {'type': 'string'}, 'before': {'type': 'string'},
                   'months': {'type': 'array', 'minItems': 12, 'maxItems': 12, 'items': {'type': 'string'}}}}
px = {
    'server_command': {'type': 'array', 'items': {'type': 'string'}},
    'heap_mb': {'type': ['integer', 'null'], 'minimum': 512, 'maximum': 32768},
    'excluded_mods': {'type': 'array', 'items': {'type': 'string'}},
    'watch_interval_seconds': {'type': 'number', 'minimum': 1},
    'tiger_timeout_seconds': {'type': 'number', 'minimum': 1},
    'tiger_run_on': {'enum': ['manual', 'save']}
}
for key in ('node_path', 'storage_dir', 'data_dir', 'tiger_path'):
    px[key] = {'type': ['string', 'null']}
for key in ('detect_syntax', 'inlay_hints', 'require_descriptor'):
    px[key] = {'type': 'boolean'}
schema = {'type': 'object', 'properties': {
    'enabled': {'type': 'boolean'}, 'settings': {'type': 'object', 'additionalProperties': False, 'properties': properties},
    'px': {'type': 'object', 'additionalProperties': False, 'properties': px}}}
schema['$id'] = 'sublime://settings/LSP-px'
result = {'contributions': {'settings': [{'file_patterns': ['LSP-px.sublime-settings'], 'schema': schema}]}}
(ROOT / 'sublime-package.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
