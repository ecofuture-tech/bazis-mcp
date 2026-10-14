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
The programs a Bazis project needs on this machine: `check` finds them without changing
anything, `plan` and `install` install or start them with the commands of `COMMANDS` only,
the closed table of the package manager of the machine, never with a command of the caller.
"""

import os
import re
import shlex
import shutil
import socket
import subprocess
import sys
from pathlib import Path

from . import project, scaffold


#: the oldest Python of a project (`requires-python` of the Bazis packages)
PYTHON_VERSION = (3, 12)
POSTGRESQL_PORT = 5432
REDIS_PORT = 6379
VERSION_TIMEOUT = 30
INSTALL_TIMEOUT = 1800
#: the end of the output of a command kept in a result
OUTPUT_LIMIT = 2000

#: the programs, in the order of `check`, and what each one is for; `-service` is a server
#: running on this machine, started apart from its installation
REQUIRED_FOR = {
    'python': 'the Python of the project, 3.12 or newer',
    'uv': 'installing .venv faster (pip is used without it)',
    'node': 'the frontend (bazis-front): Node.js {}.{} or newer with npm'.format(*scaffold.NODE_VERSION),
    'postgresql': 'the database of the project: PostgreSQL with PostGIS',
    'postgresql-service': f'the PostgreSQL server of the project, on port {POSTGRESQL_PORT}',
    'redis': 'the cache of the project',
    'redis-service': f'the Redis server of the project, on port {REDIS_PORT}',
    'gdal': 'the PostGIS backend of Django (GeoDjango)',
    'gettext': 'the translations of the product (makemessages, compilemessages)',
}

#: the formula of PostgreSQL that `COMMANDS` installs with Homebrew: keg-only, its programs
#: are in `<prefix>/opt/postgresql@18/bin`, not on the PATH
BREW_POSTGRESQL = 'postgresql@18'
#: why `install_tools` does not install the Python of a project
PROJECT_PYTHON = (
    'A new Python does not change the Python of the project, that of its .venv: create .venv '
    'again with Python {}.{} or newer, then install requirements-dev.txt into it.'
).format(*PYTHON_VERSION)

#: the only commands `install` runs, by package manager: Homebrew on macOS, apt on Debian
#: and Ubuntu (its commands need sudo: the user runs them). A program without a command
#: there is installed by the user as its site says.
COMMANDS = {
    'brew': {
        'python': ['brew', 'install', 'python@3.13'],
        'uv': ['brew', 'install', 'uv'],
        'node': ['brew', 'install', 'node'],
        'postgresql': ['brew', 'install', BREW_POSTGRESQL, 'postgis'],
        'postgresql-service': ['brew', 'services', 'start', BREW_POSTGRESQL],
        'redis': ['brew', 'install', 'redis'],
        'redis-service': ['brew', 'services', 'start', 'redis'],
        'gdal': ['brew', 'install', 'gdal'],
        'gettext': ['brew', 'install', 'gettext'],
    },
    'apt': {
        'python': ['sudo', 'apt-get', 'install', '-y', 'python3', 'python3-venv'],
        'postgresql': ['sudo', 'apt-get', 'install', '-y', 'postgresql', 'postgis'],
        'postgresql-service': ['sudo', 'systemctl', 'start', 'postgresql'],
        'redis': ['sudo', 'apt-get', 'install', '-y', 'redis-server'],
        'redis-service': ['sudo', 'systemctl', 'start', 'redis-server'],
        'gdal': ['sudo', 'apt-get', 'install', '-y', 'gdal-bin'],
        'gettext': ['sudo', 'apt-get', 'install', '-y', 'gettext'],
    },
}


def package_manager() -> str | None:
    """
    The package manager of this machine that `COMMANDS` knows, or None.
    """
    if sys.platform == 'darwin' and shutil.which('brew'):
        return 'brew'
    if sys.platform.startswith('linux') and shutil.which('apt-get'):
        return 'apt'
    return None


def reachable(port: int) -> bool:
    """
    Whether a server accepts connections on `port` of this machine.
    """
    try:
        with socket.create_connection(('localhost', port), timeout=1):
            return True
    except OSError:
        return False


def version(*command: str) -> str | None:
    """
    The first line that `command` (such as `node --version`) prints, None when it fails.
    """
    try:
        done = subprocess.run(
            command, capture_output=True, text=True, timeout=VERSION_TIMEOUT,
            stdin=subprocess.DEVNULL,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    lines = (done.stdout.strip() or done.stderr.strip()).splitlines()
    return lines[0] if not done.returncode and lines else None


def _python() -> tuple[str, str | None]:
    interpreter = (
        project.find_python(project.project_dir, project.python) if project.project_dir
        else sys.executable
    )
    found = version(interpreter, '-c', 'import platform; print(platform.python_version())')
    numbers = re.match(r'(\d+)\.(\d+)', found or '')
    if not numbers:
        return 'missing', None
    status = 'ok' if tuple(map(int, numbers.groups())) >= PYTHON_VERSION else 'old'
    return status, f'{found} ({interpreter})'


def _program(*names: str) -> tuple[str, str | None]:
    paths = [shutil.which(name) for name in names]
    if not all(paths):
        return 'missing', None
    return 'ok', version(paths[0], '--version') or paths[0]


def _node() -> tuple[str, str | None]:
    status, found = _program('node', 'npm')
    if status == 'ok' and scaffold.node_problem():
        status = 'old'
    return status, found


def _server(name: str, port: int, running: bool) -> tuple[str, str | None]:
    status, found = _program(name)
    if status == 'missing' and running:
        return 'ok', f'a server on port {port}'
    return status, found


def _postgresql(manager: str | None, running: bool) -> tuple[str, str | None]:
    status, found = _server('postgres', POSTGRESQL_PORT, running)
    if status == 'missing' and manager == 'brew':
        # the prefix of Homebrew (`brew --prefix`) is the parent of the directory of its command
        keg = Path(shutil.which('brew')).parent.parent / 'opt' / BREW_POSTGRESQL / 'bin' / 'postgres'
        if keg.is_file():
            return 'ok', version(str(keg), '--version') or str(keg)
    return status, found


def table_command(manager: str | None, name: str) -> list[str] | None:
    """
    The command of `COMMANDS` that installs or starts the program `name` with `manager`;
    None without one, and for the Python of a project served (`PROJECT_PYTHON`).
    """
    if name == 'python' and project.project_dir is not None:
        return None
    return COMMANDS.get(manager, {}).get(name)


def _command(manager: str | None, name: str) -> dict:
    command = table_command(manager, name)
    return {
        'install_command': shlex.join(command) if command else None,
        'needs_sudo': bool(command) and command[0] == 'sudo',
    }


def check() -> dict:
    """
    The programs of `REQUIRED_FOR` on this machine, read without changing anything: for
    each one its `status` (`ok`; `missing`; `old`, older than a project needs; `stopped`,
    a server not running), what was `found` (its version), the command that installs or
    starts it with the `manager` of the machine (`install_command`, null without one) and
    whether it `needs_sudo`. The Python is that of the project served (without a command:
    its `.venv` is created again, `PROJECT_PYTHON`), else that of the server (which creates
    the `.venv` of a new project). The PostgreSQL of Homebrew is found in its keg too.
    `missing` names the programs not `ok`.
    """
    manager = package_manager()
    postgresql, redis = reachable(POSTGRESQL_PORT), reachable(REDIS_PORT)
    statuses = {
        'python': _python(),
        'uv': _program('uv'),
        'node': _node(),
        'postgresql': _postgresql(manager, postgresql),
        'postgresql-service': ('ok', f'port {POSTGRESQL_PORT}') if postgresql else ('stopped', None),
        'redis': _server('redis-server', REDIS_PORT, redis),
        'redis-service': ('ok', f'port {REDIS_PORT}') if redis else ('stopped', None),
        'gdal': _program('gdalinfo'),
        'gettext': _program('msgfmt', 'xgettext'),
    }
    tools = [
        {'name': name, 'required_for': REQUIRED_FOR[name], 'status': status, 'found': found,
         **_command(manager, name)}
        for name, (status, found) in statuses.items()
    ]
    return {
        'manager': manager,
        'tools': tools,
        'missing': [it['name'] for it in tools if it['status'] != 'ok'],
    }


def _brew_usable() -> bool:
    # Homebrew refuses root and installs into the directory of its command
    brew = shutil.which('brew')
    return bool(brew) and os.geteuid() != 0 and os.access(Path(brew).parent, os.W_OK)


def plan(names: list[str]) -> tuple[list[tuple[str, list[str]]], list[dict]]:
    """
    The commands of `COMMANDS` that `install` may run for the programs `names` (names of
    `REQUIRED_FOR`), and the programs it may not install, each with the `reason` and the
    command the user runs (`run_yourself`, null without one): a command with sudo, a
    Homebrew this user cannot run, no package manager or no command in it, the Python of a
    project. Both in the order of `REQUIRED_FOR`, whatever the order of `names`: a program
    is installed before its server is started.
    """
    manager = package_manager()
    runs, refused = [], []
    for name in [it for it in REQUIRED_FOR if it in names]:
        command = table_command(manager, name)
        if command is None:
            if name == 'python' and project.project_dir is not None:
                reason = PROJECT_PYTHON
            elif manager:
                reason = f'{manager} has no command for it here: install it yourself.'
            else:
                reason = ('No known package manager on this machine (Homebrew on macOS, apt on '
                          'Debian and Ubuntu): install it yourself.')
            refused.append({'name': name, 'reason': reason, 'run_yourself': None})
        elif command[0] == 'sudo':
            refused.append({'name': name, 'reason': 'The command needs sudo: run it yourself.',
                            'run_yourself': shlex.join(command)})
        elif manager == 'brew' and not _brew_usable():
            refused.append({
                'name': name,
                'reason': 'Homebrew cannot be run by this user (root, or no right to write to '
                          'it): run the command yourself as its owner.',
                'run_yourself': shlex.join(command),
            })
        else:
            runs.append((name, command))
    return runs, refused


def install(runs: list[tuple[str, list[str]]]) -> list[dict]:
    """
    Runs the commands of `plan`, one after the other: for each one the `name`, the
    `command`, whether it succeeded (`ok`) and the end of its `output`.
    """
    results = []
    for name, command in runs:
        try:
            done = subprocess.run(
                command, capture_output=True, text=True, timeout=INSTALL_TIMEOUT,
                stdin=subprocess.DEVNULL,
            )
            ok, output = not done.returncode, f'{done.stdout}{done.stderr}'.strip()
        except subprocess.TimeoutExpired:
            ok, output = False, f'It did not finish in {INSTALL_TIMEOUT} seconds.'
        except OSError as err:
            ok, output = False, str(err)
        results.append({'name': name, 'command': shlex.join(command), 'ok': ok,
                        'output': output[-OUTPUT_LIMIT:]})
    return results
