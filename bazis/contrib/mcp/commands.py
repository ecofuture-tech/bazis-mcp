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
The commands of the project served: only those of the closed table of `KINDS` (`run`), as
argv without a shell in the project directory or its `frontend/`, and the Bazis packages
added to its requirements and installed into its `.venv` (`add_packages`).
"""

import os
import re
import shlex
import subprocess
import time
from collections.abc import Callable
from pathlib import Path

from . import catalog, processes, project, scaffold


#: the longest run of a command, in seconds
TIMEOUT = 600
#: the seconds between two reports of the progress of a command
PROGRESS_INTERVAL = 5
#: the end of stdout and of stderr kept in a result, in bytes
OUTPUT_LIMIT = 10_000

#: the management commands of `manage` (their options follow them), and those that need one
#: of their subcommands
MANAGE = {'makemigrations', 'migrate', 'check', 'bazis_doctor', 'collectstatic', 'e2e_data'}
MANAGE_SUBCOMMANDS = {
    'bazis_front': {'init', 'contract', 'check', 'add', 'design', 'e2e', 'update', 'status'},
    'bazis_messages': {'make', 'status', 'apply', 'compile'},
}
#: the scripts of `npm run` in `frontend/` (not `dev`: the dev server is `processes.start`)
NPM_SCRIPTS = {'build', 'lint', 'test', 'e2e', 'format'}
#: the commands of `npx` in `frontend/`, whole
NPX = [['tsc', '--noEmit'], ['playwright', 'install', 'chromium']]
#: the only command of `pip` in `.venv`, whole
PIP = ['install', '-r', 'requirements-dev.txt']
KINDS = ('manage', 'pytest', 'npm', 'npx', 'pip')

#: what a shell would read in an argument: never in one (there is no shell, the table is closed)
SHELL_RE = re.compile(r'[;&|$`<>(){}*?!~\'"\\\x00-\x1f\x7f]')
#: the escapes of the colors of a terminal
ANSI_RE = re.compile(r'\x1b\[[0-9;?]*[A-Za-z]')
#: the name of a requirement line
REQUIREMENT_RE = re.compile(r'\s*([A-Za-z0-9][A-Za-z0-9._-]*)')

Progress = Callable[[float], None]


def _check_args(args: list[str], cwd: Path) -> None:
    for arg in args:
        if SHELL_RE.search(arg):
            raise project.ProjectError(f'{arg!r} has a character of a shell: the arguments are plain words.')
        if '..' in arg:
            raise project.ProjectError(f'{arg!r} has "..": the paths stay in the project.')
        # a path, also that of an option (`--rootdir=<path>`) or of a test (`<path>::<test>`)
        for part in re.split('=|::', arg):
            project.inside(cwd / part)


def frontend_dir() -> Path:
    """
    `frontend/` of the project served, made by `bazis_front init`.
    """
    directory = project.inside('frontend')
    if not directory.is_dir():
        raise project.ProjectError('The project has no frontend/: `bazis_front init` creates it.')
    return directory


def argv(kind: str, args: list[str]) -> tuple[list[str], Path]:
    """
    The command of `kind` with `args` and its directory, from the closed table of `KINDS`;
    ProjectError for anything else.
    """
    if kind in ('npm', 'npx'):
        cwd = frontend_dir()
    else:
        cwd = project.inside('.')
    _check_args(args, cwd)
    python = project.find_python(project.project_dir, project.python)
    first = args[0] if args else None
    if kind == 'manage':
        if first in MANAGE_SUBCOMMANDS:
            choices = MANAGE_SUBCOMMANDS[first]
            if len(args) < 2 or args[1] not in choices:
                raise project.ProjectError(f'manage {first} needs one of: {", ".join(sorted(choices))}.')
        elif first not in MANAGE:
            known = sorted(MANAGE | set(MANAGE_SUBCOMMANDS))
            raise project.ProjectError(f'manage runs only: {", ".join(known)}.')
        return [python, 'manage.py', *args], cwd
    if kind == 'pytest':
        return [python, '-m', 'pytest', *args], cwd
    if kind == 'npm':
        if first not in NPM_SCRIPTS:
            raise project.ProjectError(f'npm runs only the scripts: {", ".join(sorted(NPM_SCRIPTS))}.')
        return ['npm', 'run', *args], cwd
    if kind == 'npx':
        if args not in NPX:
            raise project.ProjectError(f'npx runs only: {"; ".join(shlex.join(it) for it in NPX)}.')
        return ['npx', *args], cwd
    if kind == 'pip':
        if args != PIP:
            raise project.ProjectError(f'pip runs only: {shlex.join(PIP)}.')
        return [python, '-m', 'pip', *args], cwd
    raise project.ProjectError(f'Unknown kind {kind!r}: one of {", ".join(KINDS)}.')


def environment() -> tuple[dict[str, str], str | None]:
    """
    The environment of a command: that of the server with the settings module of the
    project, `E2E_PORT` of `.bazis/ports.json` and `E2E_PASSWORD` of `.env`, and the
    password, which never appears in a result.
    """
    env = dict(os.environ)
    if settings := project.settings_name():
        env['DJANGO_SETTINGS_MODULE'] = settings
    if ports := project.read_ports(project.project_dir):
        env['E2E_PORT'] = str(ports['e2e'])
    values, _ = project.env_values(project.project_dir)
    password = (values or {}).get('E2E_PASSWORD')
    if password:
        env['E2E_PASSWORD'] = password
    return env, password


def tail(text: str, secret: str | None = None) -> str:
    """
    The end of an output within OUTPUT_LIMIT bytes, without the colors of a terminal and the
    `secret`.
    """
    text = ANSI_RE.sub('', text)
    if secret:
        text = text.replace(secret, '***')
    return text.encode()[-OUTPUT_LIMIT:].decode(errors='ignore')


def execute(
    command: list[str], cwd: Path, env: dict[str, str], secret: str | None = None,
    progress: Progress | None = None,
) -> dict:
    """
    Runs `command` in `cwd` in a new process group, reporting the seconds it has run to
    `progress` every PROGRESS_INTERVAL, and kills the group after TIMEOUT seconds: the
    `exit_code` (null after the timeout), `ok`, `timed_out` and the ends of `stdout` and
    `stderr` (`tail`).
    """
    try:
        process = subprocess.Popen(
            command, cwd=cwd, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True, errors='replace', start_new_session=True,
        )
    except OSError as err:
        raise project.ProjectError(f'{command[0]} cannot be run: {err}') from err
    started = time.monotonic()
    timed_out = False
    while True:
        try:
            stdout, stderr = process.communicate(timeout=min(PROGRESS_INTERVAL, TIMEOUT))
            break
        except subprocess.TimeoutExpired:
            elapsed = time.monotonic() - started
            if elapsed >= TIMEOUT:
                timed_out = True
                processes.signal_group(process, kill=True)
                stdout, stderr = process.communicate()
                break
            if progress:
                progress(elapsed)
    return {
        'command': shlex.join(command),
        'directory': str(cwd),
        'exit_code': None if timed_out else process.returncode,
        'ok': not timed_out and process.returncode == 0,
        'timed_out': timed_out,
        'stdout': tail(stdout, secret),
        'stderr': tail(stderr, secret),
    }


def run(kind: str, args: list[str], progress: Progress | None = None) -> dict:
    """
    Runs the command of `kind` with `args` (`argv`) with the `environment` of the project.
    """
    command, cwd = argv(kind, args)
    env, password = environment()
    return execute(command, cwd, env, password, progress)


def _name(requirement: str) -> str:
    return re.sub(r'[-_.]+', '-', requirement).lower()


def closure(names: list[str]) -> list[str]:
    """
    The Bazis packages `names` and those they require (`requires` of their manifests in the
    catalog), each once; ProjectError for a name that is not in the catalog.
    """
    known = catalog.catalog()
    if unknown := [name for name in names if name not in known]:
        raise project.ProjectError(
            f'Unknown package {", ".join(unknown)}; the packages are: {", ".join(known)}.'
        )
    found: list[str] = []

    def visit(name):
        if name not in found:
            found.append(name)
            for required in known[name]['manifest']['package'].get('requires', []):
                visit(required)

    for name in names:
        visit(name)
    return found


def add_packages(names: list[str], progress: Progress | None = None) -> dict:
    """
    Adds the Bazis packages `names` and those they require (`closure`) that the requirements
    do not name yet to `requirements.txt`, with the version of the catalog as the minimum,
    installs `requirements-dev.txt` into `.venv` (`PIP`) and raises the minimums to the
    installed releases (`scaffold.raise_minimums`). When the installation fails,
    `requirements.txt` is written back as it was. The apps and the settings are left to
    the agent, as the guides say.
    """
    packages = closure(names)
    requirements = project.inside('requirements.txt')
    required = {
        _name(match[1])
        for file in (requirements, project.inside('requirements-dev.txt'))
        for line in file.read_text(encoding='utf-8').splitlines()
        if not line.lstrip().startswith(('#', '-')) and (match := REQUIREMENT_RE.match(line))
    }
    known = catalog.catalog()
    present = [name for name in packages if name in required]
    added = [f'{name}>={known[name]["version"]}' for name in packages if name not in required]
    before = requirements.read_text(encoding='utf-8')
    if added:
        requirements.write_text(
            before + ('' if before.endswith('\n') or not before else '\n') + '\n'.join(added) + '\n',
            encoding='utf-8',
        )
    command, cwd = argv('pip', PIP)
    env, password = environment()
    done = execute(command, cwd, env, password, progress)
    if not done['ok']:
        requirements.write_text(before, encoding='utf-8')
        return {'added': [], 'required': present, 'installed': {}, 'install': done}
    versions = scaffold.raise_minimums(
        project.project_dir, project.find_python(project.project_dir, project.python)
    )
    return {
        'added': added,
        'required': present,
        'installed': {name: versions[name] for name in packages if name in versions},
        'install': done,
    }
