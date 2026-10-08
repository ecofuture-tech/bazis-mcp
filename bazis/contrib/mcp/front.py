# Copyright 2026 EcoFuture Technology Services LLC and contributors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
The frontend layer of the project, made by bazis-front (`manage.py bazis_front`): the
issues of its specs, what of it is stale, and the assets bazis-front copies into it. Like
the other project tools, everything is read in a new process with the Python of the
project: the server never imports bazis-front.

A project without bazis-front gets a result that says so (`checked` false, `reason`), not
an error: the frontend layer is optional.
"""

from . import catalog, project


FRONT = 'bazis-front'

#: prints the version of bazis-front in the Python of the project and its registry of the
#: assets (`assets/registry.json`), without Django
PROBE = """\
import json
from importlib import metadata, resources

try:
    version = metadata.version('bazis-front')
except metadata.PackageNotFoundError:
    version = registry = None
else:
    path = resources.files('bazis.contrib.front').joinpath('assets', 'registry.json')
    registry = json.loads(path.read_text(encoding='utf-8')) if path.is_file() else None
print(json.dumps({'version': version, 'registry': registry}))
"""

PROBE_NAME = 'Reading bazis-front'

SETUP = (
    'install it in the project (`pip install bazis-front`), add "bazis.contrib.front" to '
    'BS_INSTALLED_APPS and create the frontend with `manage.py bazis_front init`.'
)
NOT_INSTALLED = f'bazis-front is not installed in the Python of the project: {SETUP}'
NOT_ENABLED = (
    'The project has no command bazis_front: bazis-front is not installed in its Python or '
    f'"bazis.contrib.front" is not in its INSTALLED_APPS; {SETUP}'
)
#: what Django prints for a management command that no app of the project provides
UNKNOWN_COMMAND = "Unknown command: 'bazis_front'"
#: the prefix of the message of a management command that refuses to run
COMMAND_ERROR = 'CommandError: '

#: the system checks of bazis-front that compare a generated or copied part of the frontend
#: with its source without Node, as `bazis_front <command> --check` does: the command that
#: brings each part up to date
STALE_CHECKS = {
    'front.W001': 'contract',
    'front.W005': 'design',
    'front.W003': 'e2e',
    'front.W004': 'update',
}
#: the system check that repeats the issues of the specs (`front_check`)
SPEC_CHECK = 'front.W002'


def package() -> dict | None:
    """
    The version of bazis-front in the Python of the project and its registry (null for a
    version without one), or None if it is not installed there.
    """
    done = project.run(PROBE_NAME, '-c', PROBE)
    data = project.parse_json(done.stdout)
    if data is None:
        raise project.failure(PROBE_NAME, done)
    return data if data['version'] else None


def check(layer: str | None = None) -> dict:
    """
    The issues of the specs, as `manage.py bazis_front check --json` reports them (`ok`
    is false if there is an error), or why they are not checked.
    """
    done = project.django('bazis_front', 'check', '--json', *(['--layer', layer] if layer else []))
    data = project.parse_json(done.stdout)
    if data is not None:
        # the specs are checked; exit code 1 means they have errors
        return {'checked': True, 'ok': not data['errors'], **data}
    lines = done.stderr.strip().splitlines()
    if any(it.startswith(UNKNOWN_COMMAND) for it in lines):
        return {'checked': False, 'reason': NOT_ENABLED}
    if lines and lines[-1].startswith(COMMAND_ERROR):
        # the command refused to check, such as without spec/
        return {'checked': False, 'reason': lines[-1].removeprefix(COMMAND_ERROR)}
    raise project.failure('bazis_front check', done)


def status() -> dict:
    """
    The parts of the frontend that are stale, from the system checks of bazis-front run by
    `manage.py bazis_doctor --json` (without Node and the database), by the command that
    updates them.
    """
    installed = package()
    if installed is None:
        return {'checked': False, 'reason': NOT_INSTALLED}
    messages = project.manage('bazis_doctor', '--json')
    if failed := [it for it in messages if it['id'] == 'bazis.app']:
        # the application did not load: the checks did not run
        raise project.ProjectError(failed[0]['message'])
    stale: dict[str, list[dict]] = {}
    other = []
    spec_issues = 0
    for message in messages:
        if message['id'] in STALE_CHECKS:
            stale.setdefault(STALE_CHECKS[message['id']], []).append(message)
        elif message['id'] == SPEC_CHECK:
            spec_issues += 1
        elif message['id'].startswith('front.'):
            other.append(message)
    return {
        'checked': True,
        'version': installed['version'],
        'up_to_date': not stale,
        'stale': stale,
        'spec_issues': spec_issues,
        'messages': other,
    }


def assets() -> dict:
    """
    The assets that bazis-front copies into the frontend, from the registry of the version
    installed in the project, else of the release in the catalog.
    """
    installed = package()
    if installed and installed['registry'] is not None:
        source, version, registry = 'installed', installed['version'], installed['registry']
    elif (entry := catalog.catalog().get(FRONT)) and entry.get('registry') is not None:
        source, version, registry = 'catalog', entry['version'], entry['registry']
    else:
        return {
            'source': None,
            'version': None,
            'assets': [],
            'reason': f'{NOT_INSTALLED} The catalog of this bazis-mcp has no release of it.',
        }
    return {
        'source': source,
        'version': version,
        'installed_version': installed['version'] if installed else None,
        'assets': [_asset(it) for it in registry['assets']],
    }


def _asset(entry: dict) -> dict:
    requires = entry.get('requires', {})
    return {
        'name': entry['name'],
        'kind': entry['kind'],
        'target': entry['target'],
        'capabilities': requires.get('capabilities', []),
        'requires': requires.get('assets', []),
        'init': entry.get('init', False),
    }
