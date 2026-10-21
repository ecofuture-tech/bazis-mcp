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
The servers of the project: `start_server`, `stop_server` and `server_logs`, with servers
made of a small Python program in place of uvicorn and vite, and one real backend.
"""

import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
import types
import urllib.request

import pytest

from bazis.contrib.mcp import machine, processes, project, scaffold

from .support import SAMPLE_DIR, result
from .test_projects import error


pytestmark = pytest.mark.anyio

#: a server: listens on the port of its first argument and starts a child; `stubborn`
#: (second argument) ignores SIGTERM, as its child does
SERVE = """\
import signal, socket, subprocess, sys
if sys.argv[2] == 'stubborn':
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(120)'])
print('child', child.pid, flush=True)
server = socket.socket()
server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
server.bind(('127.0.0.1', int(sys.argv[1])))
server.listen()
print('serving', flush=True)
while True:
    server.accept()[0].close()
"""


def gone(pid: int) -> bool:
    """
    Whether the process `pid` has ended (waiting for it a little).
    """
    for _ in range(50):
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return True
        time.sleep(0.1)
    os.kill(pid, 9)
    return False


def child_of(log: str) -> int:
    return int(next(line for line in log.splitlines() if line.startswith('child ')).split()[1])


@pytest.fixture
def shop(monkeypatch, tmp_path):
    """
    A copy of the sample project with free ports, served; the servers left running are
    stopped after the test.
    """
    directory = tmp_path / 'shop'
    shutil.copytree(SAMPLE_DIR, directory, ignore=shutil.ignore_patterns('__pycache__'))
    backend, frontend, e2e = scaffold.free_ports(3)
    (directory / '.bazis').mkdir()
    (directory / '.bazis' / 'ports.json').write_text(
        json.dumps({'backend': backend, 'frontend': frontend, 'e2e': e2e})
    )
    monkeypatch.setattr(project, 'project_dir', directory)
    yield directory
    processes.stop_all()


@pytest.fixture
def fake_server(monkeypatch):
    """
    The servers are SERVE (`plain` or `stubborn`) on their port, else the `program` given.
    """
    def use(mode='plain', program=None):
        def server_command(which, directory):
            port = project.read_ports(directory)[which]
            command = [sys.executable, '-c', program] if program else [
                sys.executable, '-c', SERVE, str(port), mode
            ]
            return command, directory, dict(os.environ), port

        monkeypatch.setattr(processes, 'server_command', server_command)

    return use


async def test_start_and_stop_a_server(client, shop, fake_server):
    fake_server()

    started = result(await client.call_tool('start_server', {'which': 'backend'}))
    port = project.read_ports(shop)['backend']
    assert started['running'] is True and started['ready'] is True
    assert started['port'] == port and started['url'] == f'http://localhost:{port}'
    assert started['log'] == str(shop / '.bazis' / 'logs' / 'backend.log')
    assert (shop / '.bazis' / '.gitignore').read_text() == '*\n'  # never committed

    logs = result(await client.call_tool('server_logs', {'which': 'backend'}))
    assert logs['running'] is True and 'serving' in logs['output']
    child = child_of(logs['output'])
    last = result(await client.call_tool('server_logs', {'which': 'backend', 'lines': 1}))
    assert last['output'] == 'serving\n'

    # once at a time
    message = error(await client.call_tool('start_server', {'which': 'backend'}))
    assert message.startswith(f'The backend runs already (pid {started["pid"]}, port {port}')

    stopped = result(await client.call_tool('stop_server', {'which': 'backend'}))
    assert stopped == {'which': 'backend', 'stopped': True, 'exit_code': -15}
    assert gone(started['pid']) and gone(child)
    assert result(await client.call_tool('stop_server', {'which': 'backend'})) == {
        'which': 'backend', 'stopped': False, 'reason': 'The backend was not started.'
    }
    # the log stays to be read
    logs = result(await client.call_tool('server_logs', {'which': 'backend'}))
    assert logs['running'] is False and 'serving' in logs['output']


async def test_stop_kills_a_server_that_ignores_sigterm(client, shop, fake_server, monkeypatch):
    fake_server('stubborn')
    monkeypatch.setattr(processes, 'STOP_TIMEOUT', 1)

    started = result(await client.call_tool('start_server', {'which': 'frontend'}))
    assert started['ready'] is True
    child = child_of(result(await client.call_tool('server_logs', {'which': 'frontend'}))['output'])

    stopped = result(await client.call_tool('stop_server', {'which': 'frontend'}))
    assert stopped['stopped'] is True and stopped['exit_code'] == -9
    assert gone(started['pid']) and gone(child)


async def test_start_server_refuses_a_port_taken_by_another_process(client, shop, fake_server):
    fake_server()
    port = project.read_ports(shop)['backend']
    with socket.socket() as other:
        other.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        other.bind(('127.0.0.1', port))
        other.listen()
        message = error(await client.call_tool('start_server', {'which': 'backend'}))

    assert message.startswith(f'Port {port} of the backend is taken by a process that bazis-mcp did not start')
    assert processes.RUNNING == {}
    assert not (shop / '.bazis' / 'logs' / 'backend.log').exists()


async def test_a_server_that_ends_at_once(client, shop, fake_server):
    fake_server(program="print('broken settings'); raise SystemExit(3)")

    started = result(await client.call_tool('start_server', {'which': 'backend'}))

    assert started['running'] is False and started['ready'] is False
    assert started['exit_code'] == 3 and started['output'] == 'broken settings\n'
    # it can start again, and stopping it says that it ended
    assert result(await client.call_tool('start_server', {'which': 'backend'}))['exit_code'] == 3
    stopped = result(await client.call_tool('stop_server', {'which': 'backend'}))
    assert stopped['stopped'] is False and stopped['exit_code'] == 3


async def test_server_logs_without_a_log(client, shop):
    message = error(await client.call_tool('server_logs', {'which': 'frontend'}))
    assert message == 'The frontend has no log: start_server starts it.'
    tools = {it.name: it for it in (await client.list_tools()).tools}
    lines = tools['server_logs'].input_schema['properties']['lines']
    assert (lines['minimum'], lines['maximum']) == (1, 1000)


def test_the_commands_of_the_servers(shop, monkeypatch):
    ports = project.read_ports(shop)

    command, cwd, env, port = processes.server_command('backend', shop)
    assert command == [sys.executable, '-m', 'uvicorn', 'sample.main:app', '--port', str(ports['backend'])]
    assert cwd == shop and port == ports['backend']
    assert env['DJANGO_SETTINGS_MODULE'] == 'sample.settings'

    with pytest.raises(project.ProjectError, match='The project has no frontend/'):
        processes.server_command('frontend', shop)
    (shop / 'frontend').mkdir()
    monkeypatch.setattr(machine.shutil, 'which', {'npm': r'C:\node\npm.CMD'}.get)
    command, cwd, env, port = processes.server_command('frontend', shop)
    assert command == [r'C:\node\npm.CMD', 'run', 'dev', '--', '--port', str(ports['frontend']), '--strictPort']
    assert cwd == shop / 'frontend' and port == ports['frontend']

    (shop / '.bazis' / 'ports.json').unlink()
    with pytest.raises(project.ProjectError, match='The project has no ports'):
        processes.server_command('backend', shop)


async def test_the_backend_of_the_project(client, shop):
    """
    The real backend of the sample project: uvicorn with the Python of the project.
    """
    started = result(await client.call_tool('start_server', {'which': 'backend'}))
    try:
        assert started['ready'] is True, started
        # the schema of the routes of the project (BS_DEBUG of the tests)
        with urllib.request.urlopen(f'{started["url"]}/api/openapi.json', timeout=30) as response:
            schema = json.load(response)
    finally:
        stopped = result(await client.call_tool('stop_server', {'which': 'backend'}))
    assert any(path.startswith('/api/v1/') for path in schema['paths'])
    assert stopped['stopped'] is True and gone(started['pid'])


def test_the_servers_end_with_bazis_mcp(shop, tmp_path):
    """
    A server process that ends stops the servers it started (atexit), with their children.
    """
    port = project.read_ports(shop)['backend']
    script = f"""\
import os, sys
from pathlib import Path
from bazis.contrib.mcp import processes, project

project.configure(Path({str(shop)!r}))
processes.server_command = lambda which, directory: (
    [sys.executable, '-c', {SERVE!r}, '{port}', 'plain'], directory, dict(os.environ), {port}
)
print(processes.start('backend')['pid'], flush=True)
"""
    done = subprocess.run([sys.executable, '-c', script], capture_output=True, text=True, timeout=60)

    assert done.returncode == 0, done.stderr
    pid = int(done.stdout.strip())
    child = child_of((shop / '.bazis' / 'logs' / 'backend.log').read_text())
    assert gone(pid) and gone(child)


@pytest.mark.parametrize('signum', [signal.SIGTERM, signal.SIGINT])
def test_the_servers_end_with_a_signal(shop, signum):
    """
    bazis-mcp ended by SIGTERM (as a client ends its server) or SIGINT stops the servers it
    started, with their children, and ends by that signal.
    """
    port = project.read_ports(shop)['backend']
    script = f"""\
import os, sys, time
from pathlib import Path
from bazis.contrib.mcp import processes, project

project.configure(Path({str(shop)!r}))
processes.server_command = lambda which, directory: (
    [sys.executable, '-c', {SERVE!r}, '{port}', 'plain'], directory, dict(os.environ), {port}
)
processes.stop_on_signals()
print(processes.start('backend')['pid'], flush=True)
time.sleep(60)
"""
    bazis_mcp = subprocess.Popen([sys.executable, '-c', script], stdout=subprocess.PIPE, text=True)
    pid = int(bazis_mcp.stdout.readline())
    child = child_of((shop / '.bazis' / 'logs' / 'backend.log').read_text())

    bazis_mcp.send_signal(signum)

    assert bazis_mcp.wait(30) == -signum
    assert gone(pid) and gone(child)


def test_the_servers_end_together_and_a_repeated_signal_waits(shop):
    """
    SIGTERM goes to all the servers before SIGKILL to any of them; a signal that comes
    meanwhile does not end bazis-mcp before all of them are stopped. The signals of
    `signal_group` are printed in their order.
    """
    ports = project.read_ports(shop)
    script = f"""\
import os, sys, time
from pathlib import Path
from bazis.contrib.mcp import processes, project

project.configure(Path({str(shop)!r}))
processes.STOP_TIMEOUT = 4
ports = {ports!r}
processes.server_command = lambda which, directory: (
    [sys.executable, '-c', {SERVE!r}, str(ports[which]), 'stubborn'], directory,
    dict(os.environ), ports[which],
)
signal_group = processes.signal_group

def printed(process, kill=False):
    # called by the signal handler: a print could interrupt the print of the main thread
    # (RuntimeError: reentrant call inside BufferedWriter), os.write cannot
    os.write(1, f"{{'kill' if kill else 'term'}} {{process.pid}}\\n".encode())
    signal_group(process, kill)

processes.signal_group = printed
processes.stop_on_signals()
print(*(processes.start(which)['pid'] for which in processes.SERVERS), flush=True)
time.sleep(60)
"""
    bazis_mcp = subprocess.Popen([sys.executable, '-c', script], stdout=subprocess.PIPE, text=True)
    pids = [int(pid) for pid in bazis_mcp.stdout.readline().split()]
    children = [child_of((shop / '.bazis' / 'logs' / f'{which}.log').read_text())
                for which in processes.SERVERS]

    bazis_mcp.send_signal(signal.SIGTERM)
    terms = [bazis_mcp.stdout.readline() for _ in pids]
    bazis_mcp.send_signal(signal.SIGINT)  # while it waits for the servers

    assert len(pids) == 2 and terms == [f'term {pid}\n' for pid in pids]
    assert bazis_mcp.stdout.read().splitlines() == [f'kill {pid}' for pid in pids]
    assert bazis_mcp.wait(30) == -signal.SIGTERM
    assert all([gone(pid) for pid in [*pids, *children]])


@pytest.mark.skipif(os.name != 'posix', reason='process groups')
@pytest.mark.parametrize('error', [ProcessLookupError, PermissionError])
def test_a_group_that_has_ended_is_not_an_error(monkeypatch, error):
    """
    `os.killpg` of a group that has ended raises ESRCH, or EPERM on macOS: stopping it goes on.
    """
    def killpg(pid, signum):
        raise error

    monkeypatch.setattr(processes.os, 'killpg', killpg)
    process = types.SimpleNamespace(pid=1, wait=lambda timeout=None: 0)

    processes.signal_group(process)
    processes.terminate(process)


def test_the_groups_are_waited_for_until_one_deadline(monkeypatch):
    """
    `terminate` waits for the groups until one deadline, STOP_TIMEOUT after the SIGTERMs:
    two that ignore it are killed after STOP_TIMEOUT once, not after their sum (on a clock
    of the test, without the load of the machine).
    """
    now = [0.0]

    class Stubborn:
        def __init__(self):
            self.waits = []

        def wait(self, timeout=None):
            self.waits.append(timeout)
            if timeout is not None:
                now[0] += timeout
                raise subprocess.TimeoutExpired('server', timeout)

    monkeypatch.setattr(processes, 'time', types.SimpleNamespace(monotonic=lambda: now[0]))
    monkeypatch.setattr(processes, 'signal_group', lambda process, kill=False: None)
    group = [Stubborn(), Stubborn()]

    processes.terminate(*group)

    assert [it.waits for it in group] == [[processes.STOP_TIMEOUT, None], [0, None]]


#: a command: starts a child, writes its pid and that of the child to the file of its
#: argument, and runs a minute
COMMAND = """\
import os, pathlib, subprocess, sys, time
child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])
pathlib.Path(sys.argv[1] + '.part').write_text(f'{os.getpid()} {child.pid}')
os.replace(sys.argv[1] + '.part', sys.argv[1])
time.sleep(60)
"""


@pytest.mark.parametrize('end', ['signal', 'exit'])
def test_the_commands_end_with_bazis_mcp(tmp_path, end):
    """
    A command that runs (`run_command`, `add_packages`) is stopped with its children when
    bazis-mcp ends by SIGTERM or by itself (atexit), as the servers are.
    """
    pid_file = tmp_path / 'command.pid'
    script = f"""\
import os, sys, threading, time
from pathlib import Path
from bazis.contrib.mcp import commands, processes

processes.stop_on_signals()
command = [sys.executable, '-c', {COMMAND!r}, {str(pid_file)!r}]
threading.Thread(
    target=commands.execute, args=(command, Path.cwd(), dict(os.environ)), daemon=True
).start()
while not Path({str(pid_file)!r}).exists():
    time.sleep(0.1)
print('running', flush=True)
if {end!r} == 'signal':
    time.sleep(60)
"""
    bazis_mcp = subprocess.Popen([sys.executable, '-c', script], cwd=tmp_path,
                                 stdout=subprocess.PIPE, text=True)
    assert bazis_mcp.stdout.readline() == 'running\n'
    pids = [int(pid) for pid in pid_file.read_text().split()]

    if end == 'signal':
        bazis_mcp.send_signal(signal.SIGTERM)
    assert bazis_mcp.wait(30) == (-signal.SIGTERM if end == 'signal' else 0)
    assert all([gone(pid) for pid in pids])
