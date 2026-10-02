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
The Bazis project the server serves. Its facts and checks come from the management
commands `bazis_introspect` and `bazis_doctor`, run in a new process at every call: the
result reflects the code as it is now (an agent changes it while the server runs), and a
project that fails to load cannot break the server.
"""

import json
import os
import re
import subprocess
import sys
from pathlib import Path


SETTINGS_RE = re.compile(r"""DJANGO_SETTINGS_MODULE['"]\s*,\s*['"]([\w.]+)['"]""")
TIMEOUT = 300

#: the project directory (the directory of manage.py and project.env)
project_dir: Path = Path.cwd()
#: the settings module given on the command line, if any
settings_module: str | None = None


class ProjectError(Exception):
    """
    The project cannot be loaded; the message says why.
    """


def configure(directory: Path, settings: str | None = None) -> None:
    global project_dir, settings_module
    project_dir = directory.resolve()
    settings_module = settings


def find_settings(directory: Path) -> str | None:
    """
    The settings module of the project: `DJANGO_SETTINGS_MODULE`, or the default that
    `manage.py` sets.
    """
    if module := os.environ.get('DJANGO_SETTINGS_MODULE'):
        return module
    manage = directory / 'manage.py'
    if manage.is_file():
        match = SETTINGS_RE.search(manage.read_text(encoding='utf-8', errors='replace'))
        if match:
            return match.group(1)
    return None


def manage(command: str, *args: str):
    """
    The JSON printed by `python -m django <command> <args>` in the project directory, run
    with the Python of the server (the environment of the project).
    """
    if not project_dir.is_dir():
        raise ProjectError(f'The project directory {project_dir} does not exist.')
    settings = settings_module or find_settings(project_dir)
    if not settings:
        raise ProjectError(
            f'No settings module: {project_dir} has no manage.py that sets '
            'DJANGO_SETTINGS_MODULE. Pass --project-dir, --settings or set DJANGO_SETTINGS_MODULE.'
        )
    env = dict(os.environ, DJANGO_SETTINGS_MODULE=settings)
    env['PYTHONPATH'] = os.pathsep.join(filter(None, [str(project_dir), env.get('PYTHONPATH')]))
    try:
        done = subprocess.run(
            [sys.executable, '-m', 'django', command, *args],
            cwd=project_dir, env=env, capture_output=True, text=True, timeout=TIMEOUT,
            stdin=subprocess.DEVNULL,
        )
    except subprocess.TimeoutExpired as err:
        raise ProjectError(f'{command} did not finish in {TIMEOUT} seconds.') from err
    data = _json(done.stdout)
    if data is None:
        # the end of a traceback says what went wrong
        error = '\n'.join((done.stderr.strip() or done.stdout.strip()).splitlines()[-15:])
        raise ProjectError(f'{command} failed (exit code {done.returncode}):\n{error}')
    return data


def _json(text: str):
    """
    The JSON document in the output: the first line that starts one (the project may print
    other lines before it).
    """
    for match in re.finditer(r'^[\[{]', text, re.MULTILINE):
        try:
            return json.JSONDecoder().raw_decode(text, match.start())[0]
        except ValueError:
            continue
    return None


def info(sections: list[str] | None = None) -> dict:
    """
    The requested sections of `manage.py bazis_introspect` (default: all). The installed
    packages are read without loading the project.
    """
    from bazis.core import introspect

    sections = sections or ['packages', 'settings', 'models', 'routes']
    data = {}
    if 'packages' in sections:
        data['packages'] = introspect.packages()
    rest = [it for it in sections if it != 'packages']
    if rest:
        data.update(manage('bazis_introspect', *rest))
    return data


def doctor(deploy: bool = False) -> dict:
    """
    The system checks of the project, as `manage.py bazis_doctor --json` reports them.
    """
    messages = manage('bazis_doctor', '--json', *(['--deploy'] if deploy else []))
    return {
        'ok': not any(it['level'] in ('error', 'critical') for it in messages),
        'messages': messages,
    }
