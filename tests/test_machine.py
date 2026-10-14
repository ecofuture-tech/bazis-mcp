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
The programs of the machine: `check_machine` and `install_tools`, on a machine made of
fakes (the programs found, the ports open, the commands run).
"""

import subprocess
import sys
from pathlib import Path

import pytest
from mcp import Client
from mcp.types import ElicitResult

from bazis.contrib.mcp import machine, project, scaffold
from bazis.contrib.mcp.server import server

from .support import result


pytestmark = pytest.mark.anyio

#: the version lines of every program of a complete machine
EVERYTHING = {
    'python': '3.13.1',
    'uv': 'uv 0.9.6',
    'node': 'v22.14.0',
    'npm': '10.9.2',
    'postgres': 'postgres (PostgreSQL) 18.0',
    'redis-server': 'Redis server v=8.2.1',
    'gdalinfo': 'GDAL 3.12.0',
    'msgfmt': 'msgfmt (GNU gettext-tools) 0.26',
    'xgettext': 'xgettext (GNU gettext-tools) 0.26',
}


class FakeMachine:
    """
    The programs of `versions` (name: the first line of `--version`) are found in `bin`,
    the servers listen on `ports`, `node_problem` is that of the Node.js found, and the
    commands of the package managers are recorded in `runs` (failing for `fail`).
    """

    def __init__(self, monkeypatch, tmp_path, platform='darwin', manager='brew'):
        self.bin = tmp_path / 'bin'
        self.bin.mkdir()
        self.versions = {manager: f'{manager} 1.0'} if manager else {}
        self.ports = set()
        self.node_problem = None
        self.runs = []
        self.fail = False
        monkeypatch.setattr(machine.sys, 'platform', platform)
        monkeypatch.setattr(machine.shutil, 'which', self.which)
        monkeypatch.setattr(machine.subprocess, 'run', self.run)
        monkeypatch.setattr(machine, 'reachable', lambda port: port in self.ports)
        monkeypatch.setattr(scaffold, 'node_problem', lambda: self.node_problem)

    def which(self, name):
        return str(self.bin / name) if name in self.versions else None

    def run(self, command, **kwargs):
        name = Path(command[0]).name
        if name in ('brew', 'sudo', 'apt-get'):
            self.runs.append((list(command), kwargs))
            return subprocess.CompletedProcess(
                command, 1 if self.fail else 0, 'the output\n', 'Error: no bottle' if self.fail else ''
            )
        if command[1:2] == ('-c',):  # the version of a Python
            return subprocess.CompletedProcess(command, 0, self.versions.get('python', '') + '\n', '')
        return subprocess.CompletedProcess(command, 0, self.versions[name] + '\n', '')


@pytest.fixture
def fake(monkeypatch, tmp_path):
    return FakeMachine(monkeypatch, tmp_path)


def by_name(checked) -> dict:
    return {it['name']: it for it in checked['tools']}


async def test_check_machine_with_everything(client, fake):
    fake.versions.update(EVERYTHING)
    fake.ports.update({machine.POSTGRESQL_PORT, machine.REDIS_PORT})

    checked = result(await client.call_tool('check_machine', {}))

    assert checked['manager'] == 'brew' and checked['missing'] == []
    tools = by_name(checked)
    assert list(tools) == list(machine.REQUIRED_FOR)
    assert all(it['status'] == 'ok' and it['needs_sudo'] is False for it in tools.values())
    assert tools['python']['found'] == f'3.13.1 ({sys.executable})'
    assert tools['node']['found'] == 'v22.14.0'
    assert tools['postgresql']['found'] == 'postgres (PostgreSQL) 18.0'
    assert tools['postgresql-service']['found'] == 'port 5432'
    assert tools['postgresql']['install_command'] == 'brew install postgresql@18 postgis'
    assert tools['redis-service']['install_command'] == 'brew services start redis'
    assert tools['gdal']['required_for'] == machine.REQUIRED_FOR['gdal']
    assert fake.runs == []  # nothing installed


async def test_check_machine_with_nothing(client, fake):
    fake.versions.update(python='3.11.9', msgfmt='msgfmt 0.26')  # no xgettext

    checked = result(await client.call_tool('check_machine', {}))

    statuses = {name: it['status'] for name, it in by_name(checked).items()}
    assert statuses == {
        'python': 'old', 'uv': 'missing', 'node': 'missing', 'postgresql': 'missing',
        'postgresql-service': 'stopped', 'redis': 'missing', 'redis-service': 'stopped',
        'gdal': 'missing', 'gettext': 'missing',
    }
    assert checked['missing'] == list(machine.REQUIRED_FOR)
    assert by_name(checked)['uv']['found'] is None


async def test_check_machine_old_node_and_servers_without_programs(client, fake):
    """
    A Node.js older than the frontend needs is old; a server that listens is found
    without its program (such as PostgreSQL in a container).
    """
    fake.versions.update(node='v20.1.0', npm='10.0.0')
    fake.node_problem = 'Node.js v20.1.0 is too old'
    fake.ports.add(machine.POSTGRESQL_PORT)

    tools = by_name(result(await client.call_tool('check_machine', {})))

    assert tools['node']['status'] == 'old' and tools['node']['found'] == 'v20.1.0'
    assert tools['postgresql']['status'] == 'ok'
    assert tools['postgresql']['found'] == 'a server on port 5432'
    assert tools['postgresql-service']['status'] == 'ok'
    assert tools['redis']['status'] == 'missing'


async def test_check_machine_reads_the_python_of_the_project(client, fake, monkeypatch):
    fake.versions['python'] = '3.12.4'
    monkeypatch.setattr(project, 'python', '/opt/project/bin/python')
    tools = by_name(result(await client.call_tool('check_machine', {})))
    assert tools['python']['found'] == '3.12.4 (/opt/project/bin/python)'

    # without a project: the Python of the server, which creates the .venv of a new one
    monkeypatch.setattr(project, 'project_dir', None)
    tools = by_name(result(await client.call_tool('check_machine', {})))
    assert tools['python']['found'] == f'3.12.4 ({sys.executable})'


@pytest.mark.parametrize('platform, manager, expected', [
    ('linux', 'apt-get', 'apt'),
    ('linux', None, None),
    ('darwin', None, None),
    ('win32', 'brew', None),
])
async def test_check_machine_commands_by_manager(
    client, monkeypatch, tmp_path, platform, manager, expected
):
    FakeMachine(monkeypatch, tmp_path, platform, manager)

    checked = result(await client.call_tool('check_machine', {}))

    assert checked['manager'] == expected
    commands = {name: (it['install_command'], it['needs_sudo']) for name, it in by_name(checked).items()}
    if expected is None:
        assert set(commands.values()) == {(None, False)}
        return
    assert commands['redis'] == ('sudo apt-get install -y redis-server', True)
    assert commands['postgresql-service'] == ('sudo systemctl start postgresql', True)
    assert commands['uv'] == commands['node'] == (None, False)  # not in apt


async def test_install_tools_needs_the_confirmation_of_the_user(client, fake):
    """
    A client without elicitation: nothing runs until `confirmed_by_user`, then the commands
    of the table only, as argv without a shell.
    """
    names = {'names': ['redis', 'redis-service', 'redis']}

    waiting = result(await client.call_tool('install_tools', names))
    assert waiting == {
        'installed': [],
        'to_confirm': [
            {'name': 'redis', 'command': 'brew install redis'},
            {'name': 'redis-service', 'command': 'brew services start redis'},
        ],
        'run_yourself': [],
    }
    assert fake.runs == []

    done = result(await client.call_tool('install_tools', {**names, 'confirmed_by_user': True}))
    assert [command for command, _ in fake.runs] == [
        ['brew', 'install', 'redis'], ['brew', 'services', 'start', 'redis'],
    ]
    for _, kwargs in fake.runs:
        assert 'shell' not in kwargs and kwargs['timeout'] == machine.INSTALL_TIMEOUT
    assert done['installed'] == [
        {'name': 'redis', 'command': 'brew install redis', 'ok': True, 'output': 'the output'},
        {'name': 'redis-service', 'command': 'brew services start redis', 'ok': True,
         'output': 'the output'},
    ]
    assert done['to_confirm'] == [] and done['run_yourself'] == []


async def test_install_tools_reports_a_failed_command(client, fake):
    fake.fail = True
    done = result(await client.call_tool(
        'install_tools', {'names': ['gdal'], 'confirmed_by_user': True}
    ))
    assert done['installed'] == [{
        'name': 'gdal', 'command': 'brew install gdal', 'ok': False,
        'output': 'the output\nError: no bottle',
    }]


async def test_install_tools_runs_only_the_programs_of_the_table(client, fake):
    call_result = await client.call_tool(
        'install_tools', {'names': ['curl; rm -rf ~'], 'confirmed_by_user': True}
    )
    assert call_result.is_error
    assert fake.runs == []


@pytest.mark.parametrize('platform, manager, expected', [
    ('linux', 'apt-get', [
        {'name': 'redis', 'reason': 'The command needs sudo: run it yourself.',
         'run_yourself': 'sudo apt-get install -y redis-server'},
        {'name': 'uv', 'reason': 'apt has no command for it here: install it yourself.',
         'run_yourself': None},
    ]),
    ('win32', None, [
        {'name': name, 'reason': 'No known package manager on this machine (Homebrew on macOS, '
         'apt on Debian and Ubuntu): install it yourself.', 'run_yourself': None}
        for name in ('redis', 'uv')
    ]),
])
async def test_install_tools_leaves_sudo_to_the_user(
    client, monkeypatch, tmp_path, platform, manager, expected
):
    fake = FakeMachine(monkeypatch, tmp_path, platform, manager)

    done = result(await client.call_tool(
        'install_tools', {'names': ['redis', 'uv'], 'confirmed_by_user': True}
    ))

    assert done == {'installed': [], 'to_confirm': [], 'run_yourself': expected}
    assert fake.runs == []


async def test_install_tools_without_the_right_to_run_homebrew(client, fake):
    fake.bin.chmod(0o555)
    try:
        done = result(await client.call_tool(
            'install_tools', {'names': ['redis'], 'confirmed_by_user': True}
        ))
    finally:
        fake.bin.chmod(0o755)
    assert done['run_yourself'] == [{
        'name': 'redis',
        'reason': 'Homebrew cannot be run by this user (root, or no right to write to it): '
                  'run the command yourself as its owner.',
        'run_yourself': 'brew install redis',
    }]
    assert fake.runs == []


@pytest.mark.parametrize('mode', ['legacy', 'auto'])
@pytest.mark.parametrize('answer, confirmed_by_user, runs', [
    (ElicitResult(action='accept', content={'install': True}), False, True),
    (ElicitResult(action='accept', content={'install': False}), True, False),
    (ElicitResult(action='decline'), True, False),
    (ElicitResult(action='cancel'), True, False),
])
async def test_install_tools_asks_the_user_through_the_client(
    fake, mode, answer, confirmed_by_user, runs
):
    """
    A client with elicitation asks the user, by a request during the call (`legacy`, the
    protocols before 2026-07-28) or by the input the call requires (`auto`): the answer
    decides, not `confirmed_by_user`.
    """
    asked = []

    async def elicitation(context, params):
        asked.append(params.message)
        return answer

    async with Client(
        server, raise_exceptions=True, mode=mode, elicitation_callback=elicitation
    ) as client:
        done = result(await client.call_tool(
            'install_tools',
            {'names': ['postgresql', 'postgresql-service'], 'confirmed_by_user': confirmed_by_user},
        ))

    assert asked == [
        'bazis-mcp will run on this machine:\nbrew install postgresql@18 postgis\n'
        'brew services start postgresql@18'
    ]
    assert bool(fake.runs) is runs
    assert bool(done['installed']) is runs and bool(done['to_confirm']) is not runs


async def test_install_tools_asks_nothing_without_a_command_to_run(monkeypatch, tmp_path):
    fake = FakeMachine(monkeypatch, tmp_path, 'linux', 'apt-get')

    async def elicitation(context, params):
        raise AssertionError('asked')

    async with Client(server, raise_exceptions=True, elicitation_callback=elicitation) as client:
        done = result(await client.call_tool('install_tools', {'names': ['gettext']}))

    assert done['run_yourself'][0]['run_yourself'] == 'sudo apt-get install -y gettext'
    assert fake.runs == []


async def test_install_tools_takes_the_names_of_check_machine(client):
    tools = {it.name: it for it in (await client.list_tools()).tools}
    schema = tools['install_tools'].input_schema
    assert schema['properties']['names']['items']['enum'] == list(machine.REQUIRED_FOR)
    assert set(schema['properties']) == {'names', 'confirmed_by_user'}
