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

from . import catalog, machine, processes, project, scaffold


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
#: the scripts of `npm run` in `frontend/` (not `dev`: the dev server is `processes.start`), and
#: those that take arguments, after `--`
NPM_SCRIPTS = {'build', 'lint', 'test', 'e2e', 'format'}
NPM_ARGUMENTS = {'test', 'e2e'}
#: the commands of `npm` without arguments: the dependencies of `frontend/` (after
#: `bazis_front add` or `update`)
NPM_COMMANDS = {'install', 'ci'}
#: the commands of `npx` in `frontend/`, whole, run only from `frontend/node_modules` (`--no`:
#: npx never downloads a package)
NPX = [['tsc', '--noEmit'], ['playwright', 'install', 'chromium']]
#: the only command of `pip` in `.venv`, whole
PIP = ['install', '-r', 'requirements-dev.txt']
KINDS = ('manage', 'pytest', 'npm', 'npx', 'pip')
#: the options that remove the directory they name, never run: `--basetemp` of pytest and
#: `--output` of Playwright (`npm run e2e`), as `--option=<dir>` or `--option <dir>` (neither
#: takes an abbreviation of a long option)
REMOVING = {'pytest': '--basetemp', 'npm': '--output'}

#: what a shell would read in an argument: never in one (there is no shell, the table is closed)
SHELL_RE = re.compile(r'[;&|$`<>(){}*?!~\'"\\\x00-\x1f\x7f]')
#: the escapes of the colors of a terminal
ANSI_RE = re.compile(r'\x1b\[[0-9;?]*[A-Za-z]')
_NAME = r'[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?'
_VERSION = r'(?:~=|===?|!=|<=?|>=?)\s*[A-Za-z0-9.*+!_-]+'
#: a requirement of PyPI: its name, extras and versions (`bazis[test]>=2.16, <3`), nothing else
REQUIREMENT_RE = re.compile(
    rf'({_NAME})\s*(?:\[\s*{_NAME}(?:\s*,\s*{_NAME})*\s*\])?\s*(?:{_VERSION}(?:\s*,\s*{_VERSION})*)?'
)
#: the extensions of the archives of pip (`ARCHIVE_EXTENSIONS`, in any case): a name ending
#: with one of them, such as `demo-0.1-py3-none-any.whl`, pip installs as a local file
ARCHIVES = (
    '.whl', '.zip', '.tar', '.tar.gz', '.tgz', '.tar.bz2', '.tbz', '.tar.xz', '.txz', '.tlz',
    '.tar.lz', '.tar.lzma',
)
#: a comment of a requirements file, as pip strips it
COMMENT_RE = re.compile(r'(^|\s)#.*')
#: the requirements files of a project, and the only line of them that is not a requirement:
#: the include of `requirements.txt` in `requirements-dev.txt`, as the skeleton writes it
REQUIREMENTS = ('requirements.txt', 'requirements-dev.txt')
INCLUDE = ['-r', 'requirements.txt']

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


def _npm(args: list[str]) -> list[str]:
    first = args[0] if args else None
    if first in NPM_COMMANDS:
        if len(args) > 1:
            raise project.ProjectError(f'npm {first} takes no arguments.')
        return [machine.node_program('npm'), first]
    if first not in NPM_SCRIPTS:
        raise project.ProjectError(
            f'npm runs only the scripts: {", ".join(sorted(NPM_SCRIPTS))}, and '
            f'{" and ".join(sorted(NPM_COMMANDS))} without arguments.'
        )
    if args[1:] and (first not in NPM_ARGUMENTS or args[1] != '--'):
        raise project.ProjectError(
            f'npm run {first}: only {" and ".join(sorted(NPM_ARGUMENTS))} take arguments, after --.'
        )
    return [machine.node_program('npm'), 'run', *args]


def _npx(args: list[str], cwd: Path) -> list[str]:
    if args not in NPX:
        raise project.ProjectError(f'npx runs only: {"; ".join(shlex.join(it) for it in NPX)}.')
    if not (cwd / 'node_modules' / '.bin' / args[0]).exists():
        raise project.ProjectError(
            f'{args[0]} is not installed in frontend/node_modules: run_command("npm", '
            '["install"]) installs the dependencies of the frontend (npx never downloads).'
        )
    return [machine.node_program('npx'), '--no', '--', *args]


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
    if (option := REMOVING.get(kind)) and any(arg.split('=', 1)[0] == option for arg in args):
        raise project.ProjectError(f'{kind} never runs with {option}: it removes the directory it names.')
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
        return _npm(args), cwd
    if kind == 'npx':
        return _npx(args, cwd), cwd
    if kind == 'pip':
        if args != PIP:
            raise project.ProjectError(f'pip runs only: {shlex.join(PIP)}.')
        requirements()
        return [venv_python(), '-m', 'pip', *args], cwd
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
    `stderr` (`tail`). On an exception, such as one of `progress`, the group is killed too.
    While it runs, the command is in `processes.COMMANDS`, stopped with the servers when this
    server ends.
    """
    with processes.LOCK:
        try:
            process = subprocess.Popen(
                command, cwd=cwd, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, text=True, errors='replace', start_new_session=True,
            )
        except OSError as err:
            raise project.ProjectError(f'{command[0]} cannot be run: {err}') from err
        processes.COMMANDS.add(process)
    started = time.monotonic()
    timed_out = False
    try:
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
    except BaseException:
        processes.signal_group(process, kill=True)
        process.wait()
        raise
    finally:
        with processes.LOCK:
            processes.COMMANDS.discard(process)
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


def venv_python() -> str:
    """
    The Python of the project that pip installs into (`project.project_python`: --python or
    `.venv`), never that of the server; ProjectError without one.
    """
    python = project.project_python(project.project_dir, project.python)
    if python is None:
        raise project.ProjectError(
            'The project has no .venv: pip installs only into the Python of the project, never '
            'into that of bazis-mcp. Create .venv in the project directory (python3 -m venv '
            '.venv) or start bazis-mcp with --python, then install requirements-dev.txt.'
        )
    return python


def requirements() -> set[str]:
    """
    The names of the requirements of the project (REQUIREMENTS); ProjectError for a line that
    is not a requirement of PyPI (`REQUIREMENT_RE`, a name that is not the file of an archive
    of `ARCHIVES`) nor INCLUDE: a URL, a path, an option of pip (`-e`, `-r`,
    `--index-url`...). pip installs here only from PyPI.
    """
    names = set()
    for file in REQUIREMENTS:
        path = project.inside(file)
        if not path.is_file():
            raise project.ProjectError(f'The project has no {file}.')
        for number, line in enumerate(path.read_text(encoding='utf-8').splitlines(), 1):
            line = COMMENT_RE.sub('', line).strip()
            if not line or (file == 'requirements-dev.txt' and line.split() == INCLUDE):
                continue
            match = REQUIREMENT_RE.fullmatch(line)
            if not match or match[1].lower().endswith(ARCHIVES):
                raise project.ProjectError(
                    f'{file}, line {number}: {line!r} is not a requirement of PyPI (a name, its '
                    '[extras] and versions): pip installs here only from PyPI, never from a '
                    'URL, a path, the file of an archive or with an option of pip.'
                )
            names.add(_name(match[1]))
    return names


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
    installed releases (`scaffold.raise_minimums`). When the installation fails or raises,
    `requirements.txt` is written back as it was. The apps and the settings are left to
    the agent, as the guides say.
    """
    packages = closure(names)
    required = requirements()
    python = venv_python()
    requirements_txt = project.inside('requirements.txt')
    known = catalog.catalog()
    present = [name for name in packages if name in required]
    added = [f'{name}>={known[name]["version"]}' for name in packages if name not in required]
    before = requirements_txt.read_text(encoding='utf-8')
    if added:
        requirements_txt.write_text(
            before + ('' if before.endswith('\n') or not before else '\n') + '\n'.join(added) + '\n',
            encoding='utf-8',
        )
    installed = False
    try:
        command, cwd = argv('pip', PIP)
        env, password = environment()
        done = execute(command, cwd, env, password, progress)
        installed = done['ok']
    finally:
        if not installed:
            requirements_txt.write_text(before, encoding='utf-8')
    if not installed:
        return {'added': [], 'required': present, 'installed': {}, 'install': done}
    versions = scaffold.raise_minimums(project.project_dir, python)
    return {
        'added': added,
        'required': present,
        'installed': {name: versions[name] for name in packages if name in versions},
        'install': done,
    }
