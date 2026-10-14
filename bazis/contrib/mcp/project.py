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
The Bazis project the server serves: the one it was started in, else the one that
`use_project` or `create_project` chose during the conversation. Its facts and checks come
from the management commands `bazis_introspect` and `bazis_doctor`, run in a new process at
every call: the result reflects the code as it is now (an agent changes it while the server
runs), and a project that fails to load cannot break the server.
"""

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

from dotenv import dotenv_values

from . import prompts, rules, scaffold


SETTINGS_RE = re.compile(r"""DJANGO_SETTINGS_MODULE['"]\s*,\s*['"]([\w.]+)['"]""")
#: the name of a variable of .env: python-dotenv also takes a line without `=`, such as a
#: line of a value on several lines without quotes or a pasted token, for a name
ENV_NAME_RE = re.compile(r'[A-Za-z_][A-Za-z0-9_]*')
TIMEOUT = 300
NO_PROJECT = 'No project: call create_project or use_project.'

#: the project directory (the directory of manage.py and project.env), None without a project
project_dir: Path | None = None
#: the settings module given on the command line, if any
settings_module: str | None = None
#: the Python of the project given on the command line, if any
python: str | None = None
#: the project directory of the command line (resolved), with its settings module and Python:
#: kept when `use` chooses that directory again
launched: tuple[Path, str | None, str | None] | None = None
#: `create` and `use` one at a time: they change the project served, and a creation removes
#: what it wrote when it fails
CHANGE_LOCK = threading.Lock()


class ProjectError(Exception):
    """
    The project cannot be loaded; the message says why.
    """


def configure(directory: Path, settings: str | None = None, interpreter: str | None = None):
    global project_dir, settings_module, python
    project_dir = directory.resolve()
    settings_module = settings
    python = interpreter


def launch(directory: Path, settings: str | None = None, interpreter: str | None = None):
    """
    Serves the project of the command line (`configure`), whose settings module and Python
    `use` keeps when it chooses that directory again.
    """
    global launched
    configure(directory, settings, interpreter)
    launched = (project_dir, settings, interpreter)


def is_project(directory: Path) -> bool:
    """
    Whether a directory is that of a project: it has `manage.py`.
    """
    return (directory / 'manage.py').is_file()


def find_python(directory: Path, interpreter: str | None = None) -> str:
    """
    The Python of the project: `interpreter` (given with --python), else the virtual
    environment `.venv` of the project directory or of its parent, else the Python of the
    server.
    """
    if interpreter:
        return interpreter
    for base in (directory, directory.parent):
        for path in (base / '.venv' / 'bin' / 'python', base / '.venv' / 'Scripts' / 'python.exe'):
            if path.is_file():
                return str(path)
    return sys.executable


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


def run(name: str, *args: str, **env: str) -> subprocess.CompletedProcess:
    """
    `<python> <args>` in the project directory, with the Python of the project
    (`find_python`), the project directory on the path and the variables `env`. `name`
    names the call in the errors.
    """
    _check_dir()
    env = dict(os.environ, **env)
    env['PYTHONPATH'] = os.pathsep.join(filter(None, [str(project_dir), env.get('PYTHONPATH')]))
    interpreter = find_python(project_dir, python)
    try:
        return subprocess.run(
            [interpreter, *args],
            cwd=project_dir, env=env, capture_output=True, text=True, timeout=TIMEOUT,
            stdin=subprocess.DEVNULL,
        )
    except subprocess.TimeoutExpired as err:
        raise ProjectError(f'{name} did not finish in {TIMEOUT} seconds.') from err
    except OSError as err:
        raise ProjectError(f'{name} cannot run the Python of the project {interpreter}: {err}') from err


def _check_dir():
    if project_dir is None:
        raise ProjectError(NO_PROJECT)
    if not project_dir.is_dir():
        raise ProjectError(f'The project directory {project_dir} does not exist.')


def inside(path: Path | str) -> Path:
    """
    A path of the project, relative to its directory or absolute, resolved with its symbolic
    links: the boundary of what the tools read and write. ProjectError if it is outside.
    """
    _check_dir()
    resolved = _resolve(project_dir, path)
    if resolved is None:
        raise ProjectError(f'{path} is outside the project directory {project_dir}.')
    return resolved


def _resolve(directory: Path, path: Path | str) -> Path | None:
    resolved = (directory / path).resolve()
    return resolved if resolved.is_relative_to(directory) else None


def settings_name() -> str | None:
    """
    The settings module of the project: the one given with --settings, else `find_settings`.
    """
    _check_dir()
    return settings_module or find_settings(project_dir)


def django(command: str, *args: str) -> subprocess.CompletedProcess:
    """
    `python -m django <command> <args>` with the settings of the project.
    """
    settings = settings_name()
    if not settings:
        raise ProjectError(
            f'No settings module: {project_dir} has no manage.py that sets '
            'DJANGO_SETTINGS_MODULE. Pass --project-dir, --settings or set DJANGO_SETTINGS_MODULE.'
        )
    return run(command, '-m', 'django', command, *args, DJANGO_SETTINGS_MODULE=settings)


def manage(command: str, *args: str):
    """
    The JSON printed by `python -m django <command> <args>` (`django`).
    """
    return json_of(command, django(command, *args))


def failure(name: str, done: subprocess.CompletedProcess) -> ProjectError:
    """
    The error of a call that printed no JSON: the end of its output (of a traceback) says
    what went wrong.
    """
    error = '\n'.join((done.stderr.strip() or done.stdout.strip()).splitlines()[-15:])
    return ProjectError(f'{name} failed (exit code {done.returncode}):\n{error}')


def json_of(name: str, done: subprocess.CompletedProcess):
    """
    The JSON that a call printed (`parse_json`); its `failure` when it printed none.
    """
    data = parse_json(done.stdout)
    if data is None:
        raise failure(name, done)
    return data


def parse_json(text: str):
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


#: prints the Bazis packages installed in the Python of the project as
#: `bazis.core.introspect.packages()` lists them, without setting Django up; with a Bazis
#: older than `introspect` (2.4) only their names and versions, so that the catalog gives
#: their guides, and none without Bazis
PACKAGES_PROBE = """\
import json
import re
from importlib import metadata

try:
    from bazis.core import introspect
except ImportError:
    names = {
        re.sub(r'[-_.]+', '-', dist.metadata['Name'] or '').lower()
        for dist in metadata.distributions()
    }
    packages = [
        {'name': name, 'version': metadata.version(name), 'module': None, 'manifest': None,
         'agents_md': None}
        for name in sorted(names) if name == 'bazis' or name.startswith('bazis-')
    ]
else:
    packages = introspect.packages()
print(json.dumps(packages))
"""

PACKAGES_NAME = 'Reading the installed packages'


def packages() -> list[dict]:
    """
    The Bazis packages installed in the Python of the project (`find_python`), with their
    versions, modules, manifests and the paths of their AGENTS.md, read in a new process at
    every call: never those of the Python of the server (bazis-cli runs the server with its
    own), and the packages installed or upgraded while the server runs are seen.
    """
    return json_of(PACKAGES_NAME, run(PACKAGES_NAME, '-c', PACKAGES_PROBE))


def info(sections: list[str] | None = None) -> dict:
    """
    The requested sections of `manage.py bazis_introspect` (default: all). The installed
    packages are read without loading the project (`packages`).
    """
    sections = sections or ['packages', 'settings', 'models', 'routes']
    data = {}
    if 'packages' in sections:
        data['packages'] = packages()
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


def project_rules(frontend: bool) -> str:
    """
    The rules of Bazis for the agent of a project: `rules.RULES`, and `rules.FRONTEND_RULES`
    for a product with a frontend.
    """
    return '\n'.join([rules.RULES, *([rules.FRONTEND_RULES] if frontend else [])])


def status() -> dict:
    """
    The facts of the project served (`facts`).
    """
    _check_dir()
    return facts(project_dir, settings_module, python)


def facts(directory: Path, settings: str | None = None, interpreter: str | None = None) -> dict:
    """
    The facts of the project in `directory` (resolved) with the settings module and the
    Python given on the command line: its directory, settings module, Python, whether it
    has a frontend (made by `bazis_front init`), its ports (null until chosen or when
    `.bazis/ports.json` cannot be read) and the names of the variables of its `.env`, never
    their values nor a line without `=` (`ENV_NAME_RE`): `env_keys` is null without `.env`
    or for a `.env` outside the project
    directory (a symbolic link), and `env_reason` says why.
    """
    try:
        values, reason = env_values(directory)
        return {
            'directory': str(directory),
            'settings': settings or find_settings(directory),
            'python': find_python(directory, interpreter),
            'frontend': prompts.has_frontend(directory),
            'ports': read_ports(directory),
            'env_keys': None if values is None else list(values),
            'env_reason': reason,
        }
    except OSError as err:
        raise ProjectError(f'The files of the project {directory} cannot be read: {err}') from err


def read_ports(directory: Path) -> dict[str, int] | None:
    """
    The ports of the project in `directory` (resolved), `scaffold.read_ports`: None until
    chosen, when `.bazis/ports.json` cannot be read or links outside the project directory.
    """
    if _resolve(directory, Path(scaffold.LOCAL_DIR) / 'ports.json') is None:
        return None
    return scaffold.read_ports(directory)


def env_values(directory: Path) -> tuple[dict[str, str] | None, str | None]:
    """
    The variables of `.env` of the project in `directory` (resolved), as python-dotenv reads
    them without the lines that are no variables (`ENV_NAME_RE`), for the server only: never
    in a result. None without `.env` or for a `.env` outside the project directory (a
    symbolic link), with the reason.
    """
    env = _resolve(directory, '.env')
    if env is None:
        return None, '.env links outside the project directory: it is not read.'
    if not env.is_file():
        return None, 'The project has no .env.'
    values = dotenv_values(env, interpolate=False)
    return {
        key: value for key, value in values.items()
        if value is not None and ENV_NAME_RE.fullmatch(key)
    }, None


def use(directory: str) -> dict:
    """
    Serves the project in `directory` (an absolute path) from now on: its `facts` and its
    rules. The settings module and the Python of the command line are kept for its
    directory. The project served changes only once its facts are read.
    """
    path = Path(directory)
    if not path.is_absolute():
        raise ProjectError(f'{directory} is not an absolute path.')
    if not is_project(path):
        raise ProjectError(
            f'{path} is not a project: it has no manage.py. Call create_project for a new one.'
        )
    path = path.resolve()
    settings, interpreter = launched[1:] if launched and launched[0] == path else (None, None)
    with CHANGE_LOCK:
        found = facts(path, settings, interpreter)
        configure(path, settings, interpreter)
    return {**found, 'rules': project_rules(found['frontend'])}


def temp_dirs() -> list[Path]:
    """
    The temporary directories of this machine, which the system empties.
    """
    names = [tempfile.gettempdir(), *(['/tmp'] if os.name == 'posix' else [])]
    return [Path(it).resolve() for it in names]


def refusal(directory: Path) -> str | None:
    """
    Why a new project cannot be created in `directory` (absolute, resolved), or None.
    """
    if any(directory.is_relative_to(it) for it in temp_dirs()):
        return f'{directory} is in a temporary directory, which the system empties.'
    if directory == Path.home().resolve():
        return 'The home directory cannot be a project: choose a new directory in it.'
    if directory.exists() and (not directory.is_dir() or any(directory.iterdir())):
        return f'{directory} is not an empty directory: choose a new one.'
    if owner := next((it for it in directory.parents if is_project(it)), None):
        return f'{directory} is inside the project {owner}: choose a directory outside it.'
    return None


def create(
    directory: str,
    description: str,
    name: str | None = None,
    frontend: bool = True,
    language: str | None = None,
) -> dict:
    """
    Creates a project in `directory` (an absolute path to a missing or empty directory) and
    serves it: the skeleton, `.venv` with its packages, the language of the product, the
    database, the ports. Either all of it is done or the directory is left as it was. Returns
    the facts, the rules and the task of the agent (`next_steps`).
    """
    path = Path(directory)
    if not path.is_absolute():
        raise ProjectError(f'{directory} is not an absolute path.')
    with CHANGE_LOCK:
        return _create(path.resolve(), description, name, frontend, language)


def _create(
    path: Path, description: str, name: str | None, frontend: bool, language: str | None
) -> dict:
    if problem := refusal(path):
        raise ProjectError(problem)
    if frontend and (problem := scaffold.node_problem()):
        raise ProjectError(f'{problem}. Install it, or pass frontend false for a backend only.')
    name = name or scaffold.package_name(path)
    # what is removed when the creation fails: the directory, or the first of its missing parents
    top = path
    while not top.parent.exists():
        top = top.parent
    existed = path.exists()
    try:
        scaffold.write_files(path, name, frontend=frontend)
        python = scaffold.create_venv(path)
        if not scaffold.valid_package_name(name, python):
            raise ProjectError(
                f'{name!r} cannot be the project package: it would hide a module installed in '
                'the Python of the project. Pass another name.'
            )
        product = scaffold.product_language(language, python) if language else None
        if product:
            scaffold.set_language(path, product)
    except Exception as err:
        if existed:
            for child in path.iterdir():
                if child.is_dir() and not child.is_symlink():
                    shutil.rmtree(child)
                else:
                    child.unlink()
        elif top.exists():
            shutil.rmtree(top)
        if isinstance(err, scaffold.ScaffoldError):
            raise ProjectError(str(err)) from err
        raise
    database = scaffold.create_database(path, name, python)
    ports = scaffold.project_ports(path)
    configure(path)
    return {
        'directory': str(path),
        'name': name,
        'frontend': frontend,
        'language': list(product) if product else None,
        'database': database,
        'ports': ports,
        'rules': project_rules(frontend),
        'next_steps': prompts.new_prompt(description, name, frontend, product, database, ports),
    }
