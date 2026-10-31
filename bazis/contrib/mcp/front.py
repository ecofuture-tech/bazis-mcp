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

import json
import struct
import zlib

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

#: the lint of a file of the specs (bazis-front 0.11), run by `write_file` on the files of
#: `spec/` with SPEC_SUFFIXES
LINT = 'bazis.contrib.front.spec.lint'
SPEC_SUFFIXES = ('.yaml', '.json')

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
#: the start of the message of the check of the contract (`front.W001`, `command`
#: `contract`) when contract/contract.json differs from the backend; the files generated
#: from it for the frontend, which the specs are not checked against, have another
STALE_PREFIX = 'The contract in '
#: what `check` says first when the specs were checked against a stale contract/contract.json:
#: the issues of a field or a route added since come from it (P012, S032); the contract
#: depends on the migrations and the database, so the tool never exports it itself
STALE_CONTRACT = (
    'The contract is stale: run `bazis_front contract` (from the migrated database), then '
    '`front_check` again; the issues below may come from the old contract.'
)


def package() -> dict | None:
    """
    The version of bazis-front in the Python of the project, its registry (null for a
    version without one) and `enabled`, or None if it is not installed there.
    """
    settings = project.settings_name()
    env = {'DJANGO_SETTINGS_MODULE': settings} if settings else {}
    data = project.json_of(PROBE_NAME, project.run(PROBE_NAME, '-c', PROBE, **env))
    return data if data['version'] else None


def lint(path: str) -> dict | None:
    """
    The YAML and the shape of the spec file `path` (relative to the project) as
    `python -m bazis.contrib.front.spec.lint --json` of bazis-front 0.11 reports them, without
    Django: `ok` (false if it has an error) and its `issues`. None when the lint says
    nothing: bazis-front not installed or older, a file of no layer of the specs.
    """
    try:
        done = project.run('Linting the spec', '-m', LINT, path, '--json')
    except project.ProjectError:
        return None
    data = project.parse_json(done.stdout)
    if data is None:
        return None
    return {'ok': not data['errors'], 'issues': data['issues']}


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
    is false if there is an error), first a `notice` when they were checked against a
    contract that is stale (`stale_contract`), or why they are not checked.
    """
    if unavailable := _unavailable(package()):
        return unavailable
    done = project.django('bazis_front', 'check', '--json', *(['--layer', layer] if layer else []))
    data = project.parse_json(done.stdout)
    if data is not None:
        # the specs are checked; exit code 1 means they have errors
        notice = {'notice': STALE_CONTRACT} if data['contract'] and stale_contract() else {}
        return {**notice, 'checked': True, 'ok': not data['errors'], **data}
    lines = done.stderr.strip().splitlines()
    if lines and lines[-1].startswith(COMMAND_ERROR):
        # the command refused to check, such as without spec/
        return {'checked': False, 'reason': lines[-1].removeprefix(COMMAND_ERROR)}
    raise project.failure('bazis_front check', done)


def stale_contract() -> bool:
    """
    Whether `manage.py bazis_front status --json` reports contract/contract.json stale
    (STALE_PREFIX), `bazis_front contract` exports it again. False when the status cannot be
    read, such as while a route of the backend fails to import: the specs, which need no
    route, are checked all the same.
    """
    try:
        issues = project.manage('bazis_front', 'status', '--json')['issues']
    except project.ProjectError:
        return False
    return any(
        issue['command'] == 'contract' and issue['message'].startswith(STALE_PREFIX)
        for issue in issues
    )


def status() -> dict:
    """
    The parts of the frontend that are stale, from the issues of
    `manage.py bazis_front status --json` (the checks of the state of the frontend, without
    Node), by the `command` of bazis-front that brings them up to date, the errors of the
    report of the last screenshots (`shot_errors`), which no command updates, and its screens
    looked at (`reviewed`).
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
        'reviewed': reviewed(),
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


#: the screenshots of `bazis_front shots` and their report, in the project
SHOTS_DIR = 'frontend/.scratch/shots'
SHOTS_REPORT = 'report.json'
#: the largest screenshot given, in bytes: a client sends it to its model in base64, a third
#: larger, under a limit of about 4 MB
SHOT_LIMIT = 3_000_000
#: the screenshots given for one run of `shots` (one report), each part of one counted
SHOTS_PER_RUN = 40
#: the longest side of an image that a client gives its model whole (it scales a longer one
#: down, unreadable): a taller screenshot is given in parts of this height
PART_HEIGHT = 1568
PNG = b'\x89PNG\r\n\x1a\n'
#: by run (the time of its report, None without one): the screenshots and parts given
_given: dict[int | None, int] = {}
#: by run: the parts of each screenshot given, with the number of its parts
_looked: dict[int | None, dict[str, tuple[int, set[int]]]] = {}


def screenshot(name: str, part: int = 1) -> tuple[str | None, bytes]:
    """
    The PNG of a screenshot of the last run of `bazis_front shots`, `name` a file of
    `frontend/.scratch/shots/` (`file` of a shot of its `report.json`), at most SHOTS_PER_RUN
    of a run, and a note: a screenshot taller than PART_HEIGHT is given in parts, `part`
    of them. ProjectError for another file, a larger one, a part it has not or one more.
    """
    directory = project.inside(SHOTS_DIR)
    if '/' in name or '\\' in name or not name.endswith('.png'):
        raise project.ProjectError(
            f'{name!r} is not a screenshot: the name of a .png file of {SHOTS_DIR}/ (the `file` of '
            f'a shot of its {SHOTS_REPORT}).'
        )
    label = f'{SHOTS_DIR}/{name}'
    path = project.inside(directory / name)
    if path.parent != directory or not path.is_file():
        raise project.ProjectError(f'{label} is not a screenshot of the last run of `bazis_front shots`.')
    size = path.stat().st_size
    if size > SHOT_LIMIT:
        raise project.ProjectError(f'{label} has {size} bytes, over the limit of {SHOT_LIMIT}.')
    report = directory / SHOTS_REPORT
    run = report.stat().st_mtime_ns if report.is_file() else None
    if _given.get(run, 0) >= SHOTS_PER_RUN:
        raise project.ProjectError(
            f'{SHOTS_PER_RUN} screenshots of this run were read already: read the errors of '
            f'{SHOTS_REPORT}, fix them and take the screenshots again (`bazis_front shots`).'
        )
    data = path.read_bytes()
    if not data.startswith(PNG):
        raise project.ProjectError(f'{label} is not a PNG image.')
    try:
        note, data, parts = _part(data, part, label)
    except (struct.error, zlib.error, IndexError, ValueError) as exc:
        raise project.ProjectError(f'{label} is not a PNG image it can read: {exc}.') from exc
    _given[run] = _given.get(run, 0) + 1
    _looked.setdefault(run, {}).setdefault(name, (parts, set()))[1].add(part)
    return note, data


def reviewed() -> dict | None:
    """
    The screens of the report of the last screenshots that were looked at with `screenshot`
    in its run: those with a screenshot given whole (each of its parts); None without a
    report that can be read.
    """
    report = project.inside(SHOTS_DIR) / SHOTS_REPORT
    try:
        shots = json.loads(report.read_text(encoding='utf-8'))['shots']
        run = report.stat().st_mtime_ns
    except (OSError, ValueError):
        return None
    files = {name for name, (parts, given) in _looked.get(run, {}).items() if len(given) == parts}
    screens = sorted({it['screen'] for it in shots if it['file']})
    looked = {it['screen'] for it in shots if it['file'] in files}
    return {
        'screens': len(screens),
        'looked': len(looked),
        'not_looked': [it for it in screens if it not in looked],
    }


def _part(data: bytes, part: int, label: str) -> tuple[str | None, bytes, int]:
    """
    The note and the PNG of `part` of the image `data`, and the number of the parts it is given
    in: the whole image (one part) when it is not taller than PART_HEIGHT or not of 8-bit RGB
    or RGBA without interlace (said by the note).
    """
    chunks = list(_chunks(data))
    width, height, depth, colour, _, _, interlace = struct.unpack('>IIBBBBB', chunks[0][1])
    parts = -(-height // PART_HEIGHT)
    if not 1 <= part <= parts:
        raise project.ProjectError(f'{label} has {parts} part(s): `part` is 1 to {parts}.')
    if parts == 1:
        return None, data, 1
    if depth != 8 or colour not in (2, 6) or interlace:
        return (
            f'{label} is given whole, {width}x{height} px, and the client may scale it down: only a '
            'PNG of 8-bit RGB or RGBA without interlace is cut into parts.'
        ), data, 1
    bpp = 3 if colour == 2 else 4
    line = width * bpp + 1
    raw = zlib.decompress(b''.join(body for kind, body in chunks if kind == b'IDAT'))
    first, last = (part - 1) * PART_HEIGHT, min(part * PART_HEIGHT, height)
    rows = [raw[row * line:(row + 1) * line] for row in range(last)]
    # the rows of the part keep their filters but the first, which depends on the rows above:
    # unfiltered from the last row above it that depends on none (filter None or Sub)
    top = first
    while top and rows[top][0] > 1:
        top -= 1
    pixels = bytes(line - 1)
    for row in rows[top:first + 1]:
        pixels = _unfilter(row, pixels, bpp)
    body = b'\0' + pixels + b''.join(rows[first + 1:last])
    header = struct.pack('>IIBBBBB', width, last - first, 8, colour, 0, 0, 0)
    image = PNG + _chunk(b'IHDR', header) + _chunk(b'IDAT', zlib.compress(body)) + _chunk(b'IEND', b'')
    return f'part {part} of {parts} ({width}x{PART_HEIGHT} px each)', image, parts


def _chunks(data: bytes):
    """
    The type and the data of each chunk of the PNG `data`, IHDR first.
    """
    offset = len(PNG)
    while offset < len(data):
        (size,) = struct.unpack('>I', data[offset:offset + 4])
        kind = data[offset + 4:offset + 8]
        if offset == len(PNG) and kind != b'IHDR':
            raise ValueError('no IHDR first')
        yield kind, data[offset + 8:offset + 8 + size]
        offset += size + 12


def _chunk(kind: bytes, body: bytes) -> bytes:
    return struct.pack('>I', len(body)) + kind + body + struct.pack('>I', zlib.crc32(kind + body))


def _unfilter(row: bytes, above: bytes, bpp: int) -> bytes:
    """
    The pixels of the filtered `row` of a PNG (its filter byte first), `above` those of the
    row above it.
    """
    kind, pixels = row[0], bytearray(row[1:])
    if kind > 4:
        raise ValueError(f'filter {kind}')
    for i in range(len(pixels)) if kind else ():
        left = pixels[i - bpp] if i >= bpp else 0
        up = above[i]
        if kind == 1:
            pixels[i] = (pixels[i] + left) & 255
        elif kind == 2:
            pixels[i] = (pixels[i] + up) & 255
        elif kind == 3:
            pixels[i] = (pixels[i] + (left + up) // 2) & 255
        else:
            corner = above[i - bpp] if i >= bpp else 0
            estimate = left + up - corner
            near = min((abs(estimate - left), 0, left), (abs(estimate - up), 1, up), (abs(estimate - corner), 2, corner))
            pixels[i] = (pixels[i] + near[2]) & 255
    return bytes(pixels)
