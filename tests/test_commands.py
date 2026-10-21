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
The commands of the project: `run_command` (the closed table, as argv without a shell) and
`add_packages` (the requirements and `.venv`).
"""

import json
import os
import shutil
import subprocess
import sys
import time
import types
from importlib import metadata

import pytest

from bazis.contrib.mcp import catalog, commands, machine, project, scaffold

from .support import SAMPLE_DIR, make_venv, result
from .test_projects import error


pytestmark = pytest.mark.anyio

PASSWORD = 'e2e-password-of-the-tests'
#: the programs of Node.js as `shutil.which` finds them (`npm.cmd` on Windows)
NODE = {'npm': '/node/bin/npm', 'npx': '/node/bin/npx'}


class FakePopen:
    """
    Records the commands instead of running them: `ran` has their argv and keyword
    arguments; they print `stdout` and end with `returncode`.
    """

    ran: list = []
    stdout = ''
    returncode = 0

    def __init__(self, command, **kwargs):
        self.ran.append((command, kwargs))
        self.pid = 0

    def communicate(self, timeout=None):
        return self.stdout, ''

    def wait(self, timeout=None):
        return self.returncode


@pytest.fixture
def fake_popen(monkeypatch):
    """
    FakePopen in place of the processes of `commands` only (the other modules, such as
    `scaffold`, run theirs).
    """
    monkeypatch.setattr(FakePopen, 'ran', [])
    monkeypatch.setattr(FakePopen, 'stdout', '')
    monkeypatch.setattr(FakePopen, 'returncode', 0)
    names = ('DEVNULL', 'PIPE', 'TimeoutExpired')
    module = types.SimpleNamespace(Popen=FakePopen, **{it: getattr(subprocess, it) for it in names})
    monkeypatch.setattr(commands, 'subprocess', module)
    return FakePopen


@pytest.fixture
def shop(monkeypatch, tmp_path):
    """
    A project with a frontend, its ports and a .env with the password of the end-to-end
    tests.
    """
    directory = tmp_path / 'shop'
    shutil.copytree(SAMPLE_DIR, directory, ignore=shutil.ignore_patterns('__pycache__'))
    (directory / 'frontend' / 'node_modules' / '.bin').mkdir(parents=True)
    for tool in ('tsc', 'playwright'):
        (directory / 'frontend' / 'node_modules' / '.bin' / tool).write_text('')
    (directory / '.bazis').mkdir()
    ports = {'backend': 8101, 'frontend': 5101, 'e2e': 5102}
    (directory / '.bazis' / 'ports.json').write_text(json.dumps(ports))
    (directory / '.env').write_text(f'BS_DEBUG=true\nE2E_PASSWORD={PASSWORD}\n')
    (directory / 'requirements.txt').write_text('bazis>=2.0.0\n')
    (directory / 'requirements-dev.txt').write_text(
        '-r requirements.txt\n# the tools\nbazis-test-utils>=2.5.2\n'
    )
    monkeypatch.setattr(project, 'project_dir', directory)
    monkeypatch.setattr(machine.shutil, 'which', lambda name: NODE.get(name))
    return directory


async def test_run_command_manage(client):
    done = result(await client.call_tool('run_command', {'kind': 'manage', 'args': ['check']}))

    assert done['ok'] is True and done['exit_code'] == 0 and done['timed_out'] is False
    assert done['command'] == f'{sys.executable} manage.py check'
    assert done['directory'] == str(SAMPLE_DIR)
    assert 'System check identified no issues' in done['stdout']


@pytest.mark.parametrize('kind, args, expected', [
    ('manage', ['check'], ['{python}', 'manage.py', 'check']),
    ('manage', ['migrate', '--noinput'], ['{python}', 'manage.py', 'migrate', '--noinput']),
    ('manage', ['bazis_front', 'contract'], ['{python}', 'manage.py', 'bazis_front', 'contract']),
    ('manage', ['bazis_front', 'shots'], ['{python}', 'manage.py', 'bazis_front', 'shots']),
    ('manage', ['bazis_front', 'screens'], ['{python}', 'manage.py', 'bazis_front', 'screens']),
    ('manage', ['bazis_front', 'screens', '--check'], ['{python}', 'manage.py', 'bazis_front', 'screens', '--check']),
    ('manage', ['bazis_front', 'shots', '--check'], ['{python}', 'manage.py', 'bazis_front', 'shots', '--check']),
    ('manage', ['bazis_messages', 'apply', 'locale/translations.json', '--check'],
     ['{python}', 'manage.py', 'bazis_messages', 'apply', 'locale/translations.json', '--check']),
    ('pytest', [], ['{python}', '-m', 'pytest']),
    ('pytest', ['tests/test_shop.py::test_list[2-items]', '-k', 'not slow'],
     ['{python}', '-m', 'pytest', 'tests/test_shop.py::test_list[2-items]', '-k', 'not slow']),
    ('pytest', ['-xvs', '-Werror', '-rA', '-kshop', '--co', '--tb=short', '--lf'],
     ['{python}', '-m', 'pytest', '-xvs', '-Werror', '-rA', '-kshop', '--co', '--tb=short', '--lf']),
    ('manage', ['migrate', '--noinput', '--skip-checks', '--plan'],
     ['{python}', 'manage.py', 'migrate', '--noinput', '--skip-checks', '--plan']),
    ('pip', ['install', '-r', 'requirements-dev.txt'],
     ['{python}', '-m', 'pip', 'install', '-r', 'requirements-dev.txt']),
    ('npm', ['build'], ['{npm}', 'run', 'build']),
    ('npm', ['e2e', '--', '--grep', 'login'], ['{npm}', 'run', 'e2e', '--', '--grep', 'login']),
    ('npm', ['e2e', '--', 'e2e/login.spec.ts', '--project=chromium', '--workers', '1'],
     ['{npm}', 'run', 'e2e', '--', 'e2e/login.spec.ts', '--project=chromium', '--workers', '1']),
    ('npm', ['test', '--', 'src/app.test.ts', '-t', 'renders'],
     ['{npm}', 'run', 'test', '--', 'src/app.test.ts', '-t', 'renders']),
    ('npm', ['install'], ['{npm}', 'install']),
    # `npm run e2e` written whole
    ('npm', ['run', 'e2e'], ['{npm}', 'run', 'e2e']),
    ('npm', ['run', 'test', '--', '-t', 'renders'], ['{npm}', 'run', 'test', '--', '-t', 'renders']),
    ('npm', ['ci'], ['{npm}', 'ci']),
    ('npx', ['tsc', '--noEmit'], ['{npx}', '--no', '--', 'tsc', '--noEmit']),
    ('npx', ['playwright', 'install', 'chromium'],
     ['{npx}', '--no', '--', 'playwright', 'install', 'chromium']),
])
async def test_run_command_table(client, shop, fake_popen, kind, args, expected):
    """
    The commands of the table as argv without a shell, in the project or in `frontend/`, in
    a new process group, with the settings of the project and the ports and the password
    of the end-to-end tests; the password never in the result.
    """
    fake_popen.stdout = f'logged in with {PASSWORD}\n'

    call_result = await client.call_tool('run_command', {'kind': kind, 'args': args})
    done = result(call_result)

    [(command, kwargs)] = fake_popen.ran
    programs = {'{python}': sys.executable, '{npm}': NODE['npm'], '{npx}': NODE['npx']}
    assert command == [programs.get(it, it) for it in expected]
    assert kwargs['cwd'] == (shop / 'frontend' if kind in ('npm', 'npx') else shop)
    assert 'shell' not in kwargs and kwargs['start_new_session'] is True
    assert kwargs['stdin'] == subprocess.DEVNULL
    env = kwargs['env']
    assert env['E2E_PORT'] == '5102' and env['E2E_PASSWORD'] == PASSWORD
    assert env['DJANGO_SETTINGS_MODULE'] == 'sample.settings'
    assert done['ok'] is True and done['stdout'] == 'logged in with ***\n'
    assert PASSWORD not in call_result.content[0].text


@pytest.mark.parametrize('kind, args, message', [
    ('manage', [], 'manage runs only:'),
    ('manage', ['runserver'], 'manage runs only:'),
    ('manage', ['shell', '-c', 'import os'], 'manage runs only:'),
    ('manage', ['dbshell'], 'manage runs only:'),
    ('manage', ['bazis_front'], 'manage bazis_front needs one of:'),
    ('manage', ['bazis_front', 'nuke'], 'manage bazis_front needs one of:'),
    # the edits of the generated screens are dropped only by the user
    ('manage', ['bazis_front', 'screens', '--force'], 'manage bazis_front screens never runs with --force'),
    ('manage', ['bazis_front', 'screens', '--check', '--force'], 'never runs with --force'),
    # also as the abbreviations that argparse expands
    ('manage', ['bazis_front', 'screens', '--forc'], 'never runs with --forc'),
    ('manage', ['bazis_front', 'screens', '--check', '--f'], 'never runs with --f'),
    ('manage', ['bazis_front', 'screens', '--fo=1'], 'never runs with --fo=1'),
    ('manage', ['bazis_messages', 'makemessages'], 'manage bazis_messages needs one of:'),
    ('npm', ['dev'], 'npm runs only the scripts:'),
    ('npm', ['run', 'dev'], 'args are the script and its arguments after --, such as ["e2e"]'),
    ('npm', ['run', 'install'], 'npm runs only the scripts:'),
    ('npm', ['install', 'left-pad'], 'npm install takes no arguments.'),
    ('npm', ['ci', '--ignore-scripts=false'], 'npm ci takes no arguments.'),
    ('npm', ['exec', 'left-pad'], 'npm runs only the scripts:'),
    ('npm', [], 'npm runs only the scripts:'),
    ('npm', ['build', '--', '--outDir', 'src'], 'only e2e and test take arguments, after --.'),
    ('npm', ['build', '--prefix', 'src'], 'only e2e and test take arguments, after --.'),
    ('npm', ['e2e', '--grep', 'login'], 'only e2e and test take arguments, after --.'),
    ('npm', ['e2e', '--', '--output=src'], 'npm never runs with --output'),
    ('npm', ['e2e', '--', '--output', 'e2e'], 'npm never runs with --output'),
    ('npx', ['tsc'], 'npx runs only:'),
    ('npx', ['prettier', '--write', '.'], 'npx runs only:'),
    ('pip', ['install', 'requests'], 'pip runs only:'),
    ('pip', ['install', '-r', 'requirements-dev.txt', '--index-url', 'x'], 'pip runs only:'),
    ('pytest', ['tests; rm -rf ~'], 'has a character of a shell'),
    ('pytest', ['$(whoami)'], 'has a character of a shell'),
    ('pytest', ['`id`'], 'has a character of a shell'),
    ('pytest', ['a|b'], 'has a character of a shell'),
    ('pytest', ['tests\nrm'], 'has a character of a shell'),
    ('pytest', ['~/tests'], 'has a character of a shell'),
    ('manage', ['check', '>', 'out.txt'], 'has a character of a shell'),
    ('pytest', ['../other/tests'], 'has ".."'),
    ('pytest', ['--basetemp=.'], 'pytest never runs with --basetemp'),
    ('pytest', ['--basetemp', 'tests'], 'pytest never runs with --basetemp'),
    ('npm', ['run', 'test', '--', '--fsModuleCachePath=src', '--clearCache'], 'npm never runs with --fsModuleCachePath'),
    ('npm', ['run', 'test', '--', '--fs-module-cache-path', 'src', '--clear-cache'], 'npm never runs with --fs-module-cache-path'),
    ('pytest', ['/etc/passwd'], 'is outside the project directory'),
    ('pytest', ['--rootdir=/etc'], 'is outside the project directory'),
    ('manage', ['bazis_messages', 'apply', '/etc/hosts'], 'is outside the project directory'),
    ('pytest', ['outside/test_x.py::test_a'], 'is outside the project directory'),
])
async def test_run_command_refusals(client, shop, fake_popen, tmp_path, kind, args, message):
    """
    A command or an argument out of the table, a character of a shell, a path out of the
    project (also through a symbolic link): refused, nothing runs.
    """
    (tmp_path / 'elsewhere').mkdir()
    (shop / 'outside').symlink_to(tmp_path / 'elsewhere')

    assert message in error(await client.call_tool('run_command', {'kind': kind, 'args': args}))
    assert fake_popen.ran == []


async def test_run_command_takes_only_the_kinds_of_the_table(client, shop, fake_popen):
    tools = {it.name: it for it in (await client.list_tools()).tools}
    schema = tools['run_command'].input_schema
    assert schema['properties']['kind']['enum'] == list(commands.KINDS)

    for kind in ('bash', 'sh', 'python', 'node'):
        call_result = await client.call_tool('run_command', {'kind': kind, 'args': ['-c', 'id']})
        assert call_result.is_error
    assert fake_popen.ran == []


async def test_run_command_needs_a_frontend_for_npm(client, shop, fake_popen):
    shutil.rmtree(shop / 'frontend')
    message = error(await client.call_tool('run_command', {'kind': 'npm', 'args': ['build']}))
    assert message == 'The project has no frontend/: `bazis_front init` creates it.'
    assert fake_popen.ran == []


async def test_npx_never_downloads(client, shop, fake_popen):
    """
    npx runs only a tool installed in `frontend/node_modules`: without it the command is
    refused before npx can download a package.
    """
    shutil.rmtree(shop / 'frontend' / 'node_modules')
    for args in (['tsc', '--noEmit'], ['playwright', 'install', 'chromium']):
        message = error(await client.call_tool('run_command', {'kind': 'npx', 'args': args}))
        assert message == (
            f'{args[0]} is not installed in frontend/node_modules: run_command("npm", ["install"]) '
            'installs the dependencies of the frontend (npx never downloads).'
        )
    assert fake_popen.ran == []


async def test_run_command_without_node(client, shop, fake_popen, monkeypatch):
    monkeypatch.setattr(machine.shutil, 'which', lambda name: None)
    for kind, args in (('npm', ['build']), ('npx', ['tsc', '--noEmit'])):
        message = error(await client.call_tool('run_command', {'kind': kind, 'args': args}))
        assert message == f'{kind} is not found: check_machine says how to install Node.js.'
    assert fake_popen.ran == []


async def test_run_command_without_ports_and_password(client, shop, fake_popen, monkeypatch):
    monkeypatch.delenv('E2E_PORT', raising=False)
    monkeypatch.delenv('E2E_PASSWORD', raising=False)
    (shop / '.bazis' / 'ports.json').unlink()
    (shop / '.env').write_text('BS_DEBUG=true\n')

    result(await client.call_tool('run_command', {'kind': 'npm', 'args': ['e2e']}))

    [(_, kwargs)] = fake_popen.ran
    assert 'E2E_PORT' not in kwargs['env'] and 'E2E_PASSWORD' not in kwargs['env']


async def test_run_command_timeout_kills_the_group(client, shop, monkeypatch):
    """
    A command over the timeout is killed with the processes it started, reporting its
    progress to the client meanwhile. The timeout falls once the test has started its child
    (its pid file), however long pytest takes to start.
    """
    monkeypatch.setattr(commands, 'TIMEOUT', 60)
    monkeypatch.setattr(commands, 'PROGRESS_INTERVAL', 0.5)
    (shop / 'tests').mkdir(exist_ok=True)
    (shop / 'tests' / 'test_slow.py').write_text(
        'import pathlib, subprocess, sys, time\n\n\n'
        'def test_slow():\n'
        "    child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])\n"
        "    pathlib.Path('child.pid').write_text(str(child.pid))\n"
        '    time.sleep(60)\n'
    )
    reports = []

    async def progress(value, total, message):
        reports.append(value)
        if (shop / 'child.pid').exists():
            monkeypatch.setattr(commands, 'TIMEOUT', value)

    started = time.monotonic()
    done = result(await client.call_tool(
        'run_command', {'kind': 'pytest', 'args': ['tests/test_slow.py']},
        progress_callback=progress,
    ))

    assert time.monotonic() - started < 60
    assert done['timed_out'] is True and done['ok'] is False and done['exit_code'] is None
    assert reports and reports == sorted(reports)
    child = int((shop / 'child.pid').read_text())
    for _ in range(50):
        try:
            os.kill(child, 0)
        except ProcessLookupError:
            break
        time.sleep(0.1)
    else:
        os.kill(child, 9)
        raise AssertionError('the child of the command is still running')


async def test_run_command_keeps_the_end_of_a_long_output(client, shop):
    (shop / 'tests').mkdir(exist_ok=True)
    (shop / 'tests' / 'test_loud.py').write_text(
        'def test_loud():\n'
        "    print('\\x1b[31mred\\x1b[0m ' + 'x' * 200 + '\\n' * 2, end='')\n"
        "    print(('é' * 100 + '\\n') * 5000)\n"
        "    print('the end')\n"
    )
    call_result = await client.call_tool(
        'run_command', {'kind': 'pytest', 'args': ['-s', 'tests/test_loud.py']}
    )
    done = result(call_result)

    assert done['ok'] is True
    assert len(done['stdout'].encode()) <= commands.OUTPUT_LIMIT
    assert 'the end' in done['stdout'] and '\x1b' not in done['stdout']
    assert len(call_result.content[0].text.encode()) < catalog.RESULT_LIMIT


def test_closure():
    """
    The packages and those they require, each once, the packages named first.
    """
    known = catalog.catalog()
    found = commands.closure(['bazis-permit', 'bazis-statusy'])

    assert found[0] == 'bazis-permit' and 'bazis-statusy' in found
    assert {'bazis-users', 'bazis'} <= set(found) and len(found) == len(set(found))
    for name in found:
        assert set(known[name]['manifest']['package'].get('requires', [])) <= set(found)
    with pytest.raises(project.ProjectError, match='Unknown package bazis-nope, requests;'):
        commands.closure(['bazis-nope', 'bazis', 'requests'])


async def test_add_packages(client, shop, fake_popen, monkeypatch):
    """
    The packages and those they require that the requirements do not name are added with
    the version of the catalog, then `requirements-dev.txt` is installed into `.venv` and
    the minimums are raised to the installed releases (bazis here).
    """
    monkeypatch.setattr(project, 'python', None)
    python = make_venv(shop)
    known = catalog.catalog()
    packages = commands.closure(['bazis-permit'])
    assert 'bazis-users' in packages and 'bazis' in packages

    done = result(await client.call_tool('add_packages', {'names': ['bazis-permit']}))

    expected = [f'{name}>={known[name]["version"]}' for name in packages if name != 'bazis']
    assert done['added'] == expected
    assert done['required'] == ['bazis']
    assert done['installed'] == {'bazis': metadata.version('bazis')}
    # bazis-users is added: the route set of the team is written (the users of the labels)
    assert done['files'] == ['users/__init__.py', 'users/routes.py', 'users/router.py']
    assert (shop / 'users' / 'routes.py').read_text() == scaffold.USERS_ROUTES_PY
    [(command, kwargs)] = fake_popen.ran
    assert command == [str(python), '-m', 'pip', 'install', '-r', 'requirements-dev.txt']
    assert kwargs['cwd'] == shop and 'shell' not in kwargs
    installed = scaffold.release(metadata.version('bazis'))
    assert (shop / 'requirements.txt').read_text().splitlines() == [
        f'bazis>={installed}', *expected
    ]

    # again: nothing to add, the requirements stay
    done = result(await client.call_tool('add_packages', {'names': ['bazis-permit']}))
    assert done['added'] == [] and set(done['required']) == set(packages) and done['files'] == []


async def test_add_packages_keeps_the_users_of_a_product_with_a_frontend(client, shop, fake_popen, monkeypatch):
    """
    The app `users/` that `create_project` wrote is the project's own: nothing is written
    over it. A link out of the project in its place is refused before anything is changed.
    """
    monkeypatch.setattr(project, 'python', None)
    make_venv(shop)
    scaffold.write_users(shop)
    (shop / 'users' / 'routes.py').write_text('# own\n')
    done = result(await client.call_tool('add_packages', {'names': ['bazis-users']}))
    assert done['added'] and done['files'] == []
    assert (shop / 'users' / 'routes.py').read_text() == '# own\n'

    (shop / 'requirements.txt').write_text('bazis>=2.19.1\n')
    outside = shop.parent / 'outside.py'
    (shop / 'users' / 'routes.py').unlink()
    (shop / 'users' / 'routes.py').symlink_to(outside)
    message = error(await client.call_tool('add_packages', {'names': ['bazis-users']}))
    assert 'is outside the project directory' in message
    assert (shop / 'requirements.txt').read_text() == 'bazis>=2.19.1\n' and not outside.exists()


async def test_add_packages_refusals(client, shop, fake_popen):
    before = (shop / 'requirements.txt').read_text()

    message = error(await client.call_tool('add_packages', {'names': ['bazis-permit', 'requests']}))
    assert message.startswith('Unknown package requests; the packages are: bazis, ')
    assert fake_popen.ran == [] and (shop / 'requirements.txt').read_text() == before

    # a failed installation leaves the requirements as they were
    fake_popen.returncode = 1
    fake_popen.stdout = 'ERROR: No matching distribution found for bazis-permit'
    done = result(await client.call_tool('add_packages', {'names': ['bazis-permit']}))
    assert done['added'] == [] and done['install']['ok'] is False and done['files'] == []
    assert not (shop / 'users').exists()
    assert 'No matching distribution' in done['install']['stdout']
    assert (shop / 'requirements.txt').read_text() == before


async def test_pip_only_into_the_python_of_the_project(client, shop, fake_popen, monkeypatch):
    """
    Without .venv nor --python, pip is refused: it never installs into the Python of the
    server.
    """
    monkeypatch.setattr(project, 'python', None)
    before = (shop / 'requirements.txt').read_text()
    for tool, args in (
        ('run_command', {'kind': 'pip', 'args': ['install', '-r', 'requirements-dev.txt']}),
        ('add_packages', {'names': ['bazis-permit']}),
    ):
        message = error(await client.call_tool(tool, args))
        assert message.startswith('The project has no .venv: pip installs only into the Python of '
                                  'the project, never into that of bazis-mcp.'), tool
    assert fake_popen.ran == [] and (shop / 'requirements.txt').read_text() == before


@pytest.mark.parametrize('file, line', [
    ('requirements.txt', 'git+https://example.com/bazis.git'),
    ('requirements.txt', 'bazis @ https://example.com/bazis-2.16.0-py3-none-any.whl'),
    ('requirements.txt', 'https://example.com/bazis-2.16.0-py3-none-any.whl'),
    ('requirements.txt', './wheels/bazis-2.16.0-py3-none-any.whl'),
    ('requirements.txt', '/srv/bazis'),
    ('requirements.txt', '.'),
    ('requirements.txt', '-e .'),
    # the file of an archive without a slash: pip installs it from the current directory
    ('requirements.txt', 'demo-0.1-py3-none-any.whl'),
    ('requirements.txt', 'demo-0.1.tar'),
    ('requirements.txt', 'demo-0.1.tar.gz'),
    ('requirements.txt', 'demo-0.1.zip'),
    ('requirements.txt', 'Demo-0.1.TGZ'),
    ('requirements-dev.txt', 'demo-0.1-py3-none-any.whl[test]'),
    ('requirements.txt', '-r requirements.txt'),
    ('requirements-dev.txt', '-r other.txt'),
    ('requirements-dev.txt', '--requirement requirements.txt'),
    ('requirements-dev.txt', '-c constraints.txt'),
    ('requirements-dev.txt', '--index-url https://example.com/simple'),
    ('requirements-dev.txt', '--extra-index-url=https://example.com/simple'),
    ('requirements-dev.txt', '--find-links ./wheels'),
    ('requirements-dev.txt', '-f wheels'),
    ('requirements-dev.txt', '--pre'),
    ('requirements-dev.txt', 'bazis-test-utils>=2.5.2 --hash=sha256:00'),
    ('requirements-dev.txt', 'bazis-test-utils>=${VERSION}'),
    ('requirements-dev.txt', 'bazis-test-utils; python_version < "4"'),
])
async def test_pip_only_from_pypi(client, shop, fake_popen, file, line):
    """
    A line of the requirements that is not a requirement of PyPI (a URL, a path, an option of
    pip) is refused before pip runs, by run_command and by add_packages.
    """
    with (shop / file).open('a') as requirements:
        requirements.write(line + '\n')
    before = (shop / 'requirements.txt').read_text()
    for tool, args in (
        ('run_command', {'kind': 'pip', 'args': ['install', '-r', 'requirements-dev.txt']}),
        ('add_packages', {'names': ['bazis-permit']}),
    ):
        message = error(await client.call_tool(tool, args))
        assert message.startswith(f'{file}, line ') and 'is not a requirement of PyPI' in message, tool
    assert fake_popen.ran == [] and (shop / 'requirements.txt').read_text() == before


async def test_pip_requirements_of_pypi(client, shop, fake_popen):
    (shop / 'requirements.txt').write_text(
        '# the project\n\nbazis[test] >= 2.16.0, <3  # the core\nDjango~=6.0\nbazis-front==0.1.*\n'
        # not files of archives: a name with `.tar` inside it, and one that begins with `zip`
        'backports.tarfile>=1.2\nzipp\n'
    )
    done = result(await client.call_tool(
        'run_command', {'kind': 'pip', 'args': ['install', '-r', 'requirements-dev.txt']}
    ))
    assert done['ok'] is True and len(fake_popen.ran) == 1
    assert commands.requirements() == {
        'bazis', 'django', 'bazis-front', 'backports-tarfile', 'zipp', 'bazis-test-utils'
    }


def test_an_exception_kills_the_command(shop, monkeypatch, tmp_path):
    """
    An exception while a command runs, such as one of its progress when the client is gone,
    kills the group of the command before it goes on.
    """
    monkeypatch.setattr(commands, 'PROGRESS_INTERVAL', 0.2)
    pid_file = tmp_path / 'child.pid'
    script = (
        'import pathlib, subprocess, sys, time\n'
        "child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])\n"
        'pathlib.Path(sys.argv[1]).write_text(str(child.pid))\n'
        'time.sleep(60)\n'
    )

    def progress(elapsed):
        if pid_file.exists():
            raise RuntimeError('the client is gone')

    started = time.monotonic()
    with pytest.raises(RuntimeError, match='the client is gone'):
        commands.execute([sys.executable, '-c', script, str(pid_file)], shop, dict(os.environ),
                         progress=progress)
    assert time.monotonic() - started < 20
    child = int(pid_file.read_text())
    for _ in range(50):
        try:
            os.kill(child, 0)
        except ProcessLookupError:
            break
        time.sleep(0.1)
    else:
        os.kill(child, 9)
        raise AssertionError('the child of the command is still running')


def test_add_packages_keeps_the_requirements_on_an_exception(shop, fake_popen, monkeypatch):
    """
    pip that cannot start or a progress that raises: the group killed, the requirements as
    they were.
    """
    before = (shop / 'requirements.txt').read_text()
    killed = []
    monkeypatch.setattr(commands.processes, 'signal_group', lambda process, kill=False: killed.append(kill))

    def cannot_start(command, **kwargs):
        raise FileNotFoundError(2, 'No such file or directory', command[0])

    monkeypatch.setattr(commands.subprocess, 'Popen', cannot_start)
    with pytest.raises(project.ProjectError, match='cannot be run'):
        commands.add_packages(['bazis-permit'])
    assert (shop / 'requirements.txt').read_text() == before

    class Cancelled(FakePopen):
        def communicate(self, timeout=None):
            if timeout is not None:
                raise subprocess.TimeoutExpired('pip', timeout)
            return '', ''

    def cancelled(elapsed):
        raise KeyboardInterrupt

    monkeypatch.setattr(commands.subprocess, 'Popen', Cancelled)
    with pytest.raises(KeyboardInterrupt):
        commands.add_packages(['bazis-permit'], progress=cancelled)
    assert killed == [True] and len(fake_popen.ran) == 1
    assert (shop / 'requirements.txt').read_text() == before
