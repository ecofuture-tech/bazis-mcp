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

#: prints the version of bazis-front in the Python of the project, its registry of the
#: assets (`assets/registry.json`) and whether its app is in the INSTALLED_APPS of the
#: settings (null when they cannot be read), without setting Django up
PROBE = """\
import json
from importlib import metadata, resources

try:
    version = metadata.version('bazis-front')
except metadata.PackageNotFoundError:
    version = registry = enabled = None
else:
    path = resources.files('bazis.contrib.front').joinpath('assets', 'registry.json')
    registry = json.loads(path.read_text(encoding='utf-8')) if path.is_file() else None
    try:
        from django.conf import settings

        enabled = any(
            it == 'bazis.contrib.front' or it.startswith('bazis.contrib.front.')
            for it in settings.INSTALLED_APPS
        )
    except Exception:
        enabled = None
print(json.dumps({'version': version, 'registry': registry, 'enabled': enabled}))
"""

PROBE_NAME = 'Reading bazis-front'

NOT_INSTALLED = (
    'bazis-front is not installed in the Python of the project: install it (`pip install '
    'bazis-front`), add "bazis.contrib.front" to BS_INSTALLED_APPS and create the frontend '
    'with `manage.py bazis_front init`.'
)
NOT_ENABLED = (
    '"bazis.contrib.front" is not in the INSTALLED_APPS of the project: add it to '
    'BS_INSTALLED_APPS and create the frontend with `manage.py bazis_front init`.'
)
#: the prefix of the message of a management command that refuses to run
COMMAND_ERROR = 'CommandError: '

#: the check of bazis-front that repeats the issues of the specs (`front_check`)
SPEC_CHECK = 'front.W002'
#: the check of bazis-front whose issue is the errors of the report of the last screenshots
#: (`bazis_front shots`): not stale, the screens are fixed instead
SHOTS_CHECK = 'front.W009'


def package() -> dict | None:
    """
    The version of bazis-front in the Python of the project, its registry (null for a
    version without one) and `enabled`, or None if it is not installed there.
    """
    settings = project.settings_name()
    env = {'DJANGO_SETTINGS_MODULE': settings} if settings else {}
    data = project.json_of(PROBE_NAME, project.run(PROBE_NAME, '-c', PROBE, **env))
    return data if data['version'] else None


def _unavailable(installed: dict | None) -> dict | None:
    """
    The result of a tool for a project whose bazis-front cannot run, else None. Settings
    that cannot be read (`enabled` null) are left to the command, which reports why.
    """
    if installed is None:
        return {'checked': False, 'reason': NOT_INSTALLED}
    if installed['enabled'] is False:
        return {'checked': False, 'reason': NOT_ENABLED}
    return None


def check(layer: str | None = None) -> dict:
    """
    The issues of the specs, as `manage.py bazis_front check --json` reports them (`ok`
    is false if there is an error), or why they are not checked.
    """
    if unavailable := _unavailable(package()):
        return unavailable
    done = project.django('bazis_front', 'check', '--json', *(['--layer', layer] if layer else []))
    data = project.parse_json(done.stdout)
    if data is not None:
        # the specs are checked; exit code 1 means they have errors
        return {'checked': True, 'ok': not data['errors'], **data}
    lines = done.stderr.strip().splitlines()
    if lines and lines[-1].startswith(COMMAND_ERROR):
        # the command refused to check, such as without spec/
        return {'checked': False, 'reason': lines[-1].removeprefix(COMMAND_ERROR)}
    raise project.failure('bazis_front check', done)


def status() -> dict:
    """
    The parts of the frontend that are stale, from the issues of
    `manage.py bazis_front status --json` (the checks of the state of the frontend, without
    Node), by the `command` of bazis-front that brings them up to date, and the errors of the
    report of the last screenshots (`shot_errors`), which no command updates.
    """
    installed = package()
    if unavailable := _unavailable(installed):
        return unavailable
    issues = project.manage('bazis_front', 'status', '--json')['issues']
    stale: dict[str, list[dict]] = {}
    other = []
    shot_errors = []
    spec_issues = 0
    for issue in issues:
        if issue['command']:
            stale.setdefault(issue['command'], []).append(issue)
        elif issue['id'] == SPEC_CHECK:
            spec_issues += 1
        elif issue['id'] == SHOTS_CHECK:
            shot_errors.append(issue)
        else:
            other.append(issue)
    return {
        'checked': True,
        'version': installed['version'],
        'up_to_date': not stale,
        'stale': stale,
        'spec_issues': spec_issues,
        'shot_errors': shot_errors,
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
    }
