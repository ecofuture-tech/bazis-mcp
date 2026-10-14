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
The servers of the project served, run in the background: the backend (uvicorn) and the dev
server of the frontend (vite), each on its port of `.bazis/ports.json`, in a new process
group with its output in `.bazis/logs/<server>.log`. The registry `RUNNING` has those this
server started: they are stopped by `stop` (the whole group, SIGTERM then SIGKILL) and when
the server ends (`atexit`).
"""

import atexit
import os
import signal
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from . import machine, project, scaffold


SERVERS = ('backend', 'frontend')
#: the seconds a start waits for the port of the server
READY_TIMEOUT = 60
#: the seconds a server has to end after SIGTERM, before SIGKILL
STOP_TIMEOUT = 10
#: the longest log of `logs`, in bytes
LOG_LIMIT = 20_000


@dataclass
class Server:
    process: subprocess.Popen
    directory: Path
    port: int
    log: Path


#: the servers started by this server, by name
RUNNING: dict[str, Server] = {}
#: one change of `RUNNING` at a time (the tools run in worker threads)
LOCK = threading.Lock()


def signal_group(process: subprocess.Popen, kill: bool = False) -> None:
    """
    Sends SIGTERM, or SIGKILL when `kill`, to the process group of `process` (started with
    `start_new_session`): also to the processes it started, such as the node of
    `npm run dev`. On Windows to the process only.
    """
    try:
        if os.name == 'posix':
            os.killpg(process.pid, signal.SIGKILL if kill else signal.SIGTERM)
        elif kill:
            process.kill()
        else:
            process.terminate()
    except ProcessLookupError:
        pass


def terminate(process: subprocess.Popen) -> int:
    """
    Stops the process group of `process`: SIGTERM, then SIGKILL to what is left after
    STOP_TIMEOUT seconds or after the process ended. Returns its exit code.
    """
    signal_group(process)
    try:
        process.wait(STOP_TIMEOUT)
    except subprocess.TimeoutExpired:
        pass
    signal_group(process, kill=True)
    return process.wait()


def server_command(which: str, directory: Path) -> tuple[list[str], Path, dict[str, str], int]:
    """
    The command of the server `which` of the project in `directory`, its directory, its
    environment and its port.
    """
    ports = project.read_ports(directory)
    if ports is None:
        raise project.ProjectError(
            'The project has no ports: .bazis/ports.json is missing or cannot be read.'
        )
    port = ports[which]
    env = dict(os.environ)
    if which == 'backend':
        settings = project.settings_name()
        if not settings:
            raise project.ProjectError(f'No settings module: {directory} has no manage.py that sets it.')
        python = project.find_python(directory, project.python)
        env['DJANGO_SETTINGS_MODULE'] = settings
        package = settings.split('.')[0]
        return [python, '-m', 'uvicorn', f'{package}.main:app', '--port', str(port)], directory, env, port
    frontend = project.inside('frontend')
    if not frontend.is_dir():
        raise project.ProjectError('The project has no frontend/: `bazis_front init` creates it.')
    npm = machine.node_program('npm')
    return [npm, 'run', 'dev', '--', '--port', str(port), '--strictPort'], frontend, env, port


def _running(which: str) -> Server | None:
    server = RUNNING.get(which)
    return server if server and server.process.poll() is None else None


def start(which: str) -> dict:
    """
    Starts the server `which` of the project served in the background and waits until its
    port accepts connections, at most READY_TIMEOUT seconds. Refused when it runs already
    or when another process has its port.
    """
    directory = project.inside('.')
    with LOCK:
        if server := _running(which):
            raise project.ProjectError(
                f'The {which} runs already (pid {server.process.pid}, port {server.port}, '
                f'project {server.directory}): stop_server first.'
            )
        command, cwd, env, port = server_command(which, directory)
        if machine.reachable(port):
            raise project.ProjectError(
                f'Port {port} of the {which} is taken by a process that bazis-mcp did not start: '
                'stop it, or choose other ports in .bazis/ports.json.'
            )
        log = scaffold.local_dir(directory) / 'logs' / f'{which}.log'
        log.parent.mkdir(exist_ok=True)
        with log.open('wb') as output:
            try:
                process = subprocess.Popen(
                    command, cwd=cwd, env=env, stdin=subprocess.DEVNULL, stdout=output,
                    stderr=subprocess.STDOUT, start_new_session=True,
                )
            except OSError as err:
                raise project.ProjectError(f'{command[0]} cannot be run: {err}') from err
        RUNNING[which] = Server(process, directory, port, log)
    deadline = time.monotonic() + READY_TIMEOUT
    while process.poll() is None and not machine.reachable(port):
        if time.monotonic() > deadline:
            break
        time.sleep(0.2)
    result = {'which': which, 'pid': process.pid, 'port': port, 'url': f'http://localhost:{port}',
              'log': str(log)}
    if process.poll() is not None:
        return {**result, 'running': False, 'ready': False, 'exit_code': process.returncode,
                'output': _tail(log, 30)}
    return {**result, 'running': True, 'ready': machine.reachable(port), 'exit_code': None}


def stop(which: str) -> dict:
    """
    Stops the server `which` started by `start`, with the processes it started.
    """
    with LOCK:
        server = RUNNING.pop(which, None)
    if server is None:
        return {'which': which, 'stopped': False, 'reason': f'The {which} was not started.'}
    if server.process.poll() is not None:
        return {'which': which, 'stopped': False, 'exit_code': server.process.returncode,
                'reason': f'The {which} had ended already.'}
    return {'which': which, 'stopped': True, 'exit_code': terminate(server.process)}


def stop_all() -> None:
    """
    Stops every server started by `start` (at the end of this server).
    """
    with LOCK:
        servers = list(RUNNING.values())
        RUNNING.clear()
    for server in servers:
        if server.process.poll() is None:
            terminate(server.process)


atexit.register(stop_all)


def _tail(log: Path, lines: int) -> str:
    text = log.read_bytes()[-LOG_LIMIT:].decode(errors='replace')
    return ''.join(text.splitlines(keepends=True)[-lines:])


def logs(which: str, lines: int = 100) -> dict:
    """
    The last `lines` lines of the log of the server `which` (at most LOG_LIMIT bytes): of the
    one started by `start`, else of the project served.
    """
    with LOCK:
        server = RUNNING.get(which)
    log = server.log if server else project.inside(Path(scaffold.LOCAL_DIR) / 'logs' / f'{which}.log')
    if not log.is_file():
        raise project.ProjectError(f'The {which} has no log: start_server starts it.')
    return {
        'which': which,
        'running': bool(server) and server.process.poll() is None,
        'log': str(log),
        'output': _tail(log, lines),
    }
