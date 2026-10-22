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
The MCP server of a Bazis project: the catalog of the Bazis packages and the facts and
checks of the project, for AI agents, and the creation of a project or the choice of the
project during the conversation.

Run in the project directory, or anywhere to create a project: `bazis-mcp` (see the README).
"""

import argparse
import shlex
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, Field

import anyio.from_thread

from mcp.server.mcpserver import (
    AcceptedElicitation,
    Context,
    Elicit,
    ElicitationResult,
    Image,
    MCPServer,
    Resolve,
)
from mcp.server.mcpserver.exceptions import ResourceError, ResourceNotFoundError, ToolError
from mcp.types import ClientCapabilities, ElicitationCapability, ToolAnnotations

from . import (
    __version__,
    catalog,
    commands,
    files,
    front,
    machine,
    processes,
    project,
    prompts,
    rules,
    scaffold,
    search,
)


INSTRUCTIONS = """\
Bazis builds JSON:API services on Django, FastAPI and Pydantic. The core is the package
`bazis`; every other feature is a separate package `bazis-<name>`. Install only the
packages the project needs.

The tools work on one project, the one the server was started in or the one chosen in the
conversation (`project_status` says which); without one they answer "No project" with the
projects of the current directory to choose with `use_project`, and the catalog
(`list_packages`, `package_guide`, `guide_search`) describes the released packages.

- A new application: call `check_machine` first. If programs are `missing`, list them to
  the user with what each one is for and its `install_command`, and ask whether to install
  them; only after the user says yes in this conversation call `install_tools` with their
  names (`confirmed_by_user` true; the client may ask the user itself). Give the user the
  `run_yourself` commands it returns (sudo, or no package manager) to run, then call
  `check_machine` again. Never install anything in another way.
- Then ask for the directory of the application unless the user named one (a new
  directory, never a temporary one; else the current working directory of the
  conversation under a new name), and call `create_project` with it, the description of
  the user, the `name` of the product in Latin letters (it becomes the package:
  `master-na-chas` is `master_na_chas`), the `language` of the description (its code,
  such as `ru`; `frontend` false only for a backend without screens) and the PostgreSQL
  server the user chose as `database` (`host:port`; not when the environment of the server
  names one, the tool says so).
  It writes the skeleton, installs `.venv`, creates the database and serves the new
  project: do its `next_steps` following its `rules`.
- An existing project: `use_project(directory)`, then do what is asked following the
  `rules` it returns. The user goes on with the next changes in this conversation: each
  one on the same project, ending with the final checks of the rules.
- The rules speak of the current directory: it is the project directory. Change only the
  files in it (`read_file`, `write_file`, `delete_file`, `list_files`). Never read `.env`:
  `project_status` gives the names of its variables.
- Run the commands of the rules only with `run_command`: `.venv/bin/python manage.py
  <command> <options>` is `run_command("manage", ["<command>", "<options>"])`, the tests
  `run_command("pytest")`, the commands in `frontend/` `run_command("npm", ["build"])` and
  `run_command("npx", ["tsc", "--noEmit"])` (after `run_command("npm", ["install"])`); it
  sets `E2E_PORT` and `E2E_PASSWORD` itself.
  Start and stop the backend and the dev server of the frontend with `start_server` and
  `stop_server` (`server_logs` shows their output), add Bazis packages with
  `add_packages`. Never run a command in another way.
- End every task with the summary in the sections the rules name, with exactly their headings
  (Built, Packages, Run, Outside the files, Left for you, Guide gaps).

- Choose packages with `list_packages` (what each one solves and requires), then read the
  guide of each chosen package with `package_guide` before using it, also for the core
  (`bazis`). Follow the guides, not your memory of Bazis. A long guide comes as its
  introduction (`complete` false) with the titles of its `sections`: read a section with
  `package_guide(name, section)` when the step at hand needs it, not all of them up front.
- To find how to do something, or which package or section covers it, use
  `guide_search(query)` (optionally for one `package`): it returns the best matching parts
  of the guides and manifests, the short ones whole, with the `section` to read the rest.
  If the guides do not answer, say what was missing rather than guessing.
- Facts about this project (installed packages, settings, models, routes) come from
  `project_info`.
- After a change run `run_doctor` and fix what it reports; run the tests of the project
  once the change is done, and fix what they report.
- The frontend layer (bazis-front, guide `package_guide("bazis-front")`): check the specs
  with `front_check`, find what is stale with `front_status`, choose the components with
  `front_catalog`, and look at the screenshots of `bazis_front shots` with
  `front_screenshot`.
"""

SECTIONS = Literal['packages', 'settings', 'models', 'routes']
LAYERS = Literal['product', 'screens', 'design']
READ_ONLY = ToolAnnotations(readOnlyHint=True, openWorldHint=False)
#: writes a new directory and installs its packages from PyPI
CREATES = ToolAnnotations(
    readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=True
)
#: changes only which project the next calls serve
CHOOSES = ToolAnnotations(
    readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False
)
#: installs programs on the machine (from the package manager) and starts its servers, or the
#: packages of the project (from PyPI)
INSTALLS = ToolAnnotations(
    readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=True
)
#: runs a command of the closed table: it may change the files and the database of the project
#: (migrate, bazis_front) and download (npm, npx, pip)
RUNS = ToolAnnotations(
    readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=True
)
#: starts a server of the project in the background
STARTS = ToolAnnotations(
    readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False
)
#: stops a server that `start_server` started
STOPS = ToolAnnotations(
    readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False
)
#: writes a file of the project, replacing it, or deletes it (again: no other effect)
WRITES = ToolAnnotations(
    readOnlyHint=False, destructiveHint=True, idempotentHint=True, openWorldHint=False
)
PROGRAMS = Literal[tuple(machine.REQUIRED_FOR)]
KINDS = Literal[commands.KINDS]
SERVERS = Literal[processes.SERVERS]
CONFIRMED_BY_USER = (
    'True only after the user explicitly said yes in this conversation to installing these '
    'programs; never on your own'
)

server = MCPServer('bazis', instructions=INSTRUCTIONS, version=__version__)


def _package(name: str) -> dict:
    packages = _project_call(catalog.packages)
    if name not in packages:
        raise ToolError(f'Unknown package {name!r}; the packages are: {", ".join(packages)}.')
    return packages[name]


def _project_call(func, *args):
    try:
        return func(*args)
    except project.ProjectError as err:
        raise ToolError(str(err)) from err


class Confirmation(BaseModel):
    install: bool = Field(description='Run these commands on this machine')


@server.tool(annotations=READ_ONLY)
def check_machine() -> dict:
    """
    The programs a Bazis project needs on this machine, found without changing anything:
    `python` (that of the project, 3.12 or newer), `uv`, `node` (with npm, for the
    frontend), `postgresql` and `postgresql-service` (the server running on port 5432),
    `redis` and `redis-service` (port 6379), `gdal` and `gettext`. For each one: what it is
    `required_for`, its `status` (`ok`, `missing`, `old`, or `stopped` for a server), what
    was `found`, the `install_command` of the package `manager` of the machine (Homebrew,
    apt; null without one, and for the Python of a project: its `.venv` is created again
    with a newer Python) and whether it `needs_sudo`. `missing` names those not `ok`:
    list them to the user and ask before `install_tools`.
    """
    return machine.check()


def _confirmation(
    names: list[PROGRAMS], confirmed_by_user: bool, ctx: Context
) -> Confirmation | Elicit[Confirmation]:
    """
    Whether the user agrees to the commands of `install_tools`: asked by the client when it
    supports elicitation (on every protocol: a request during the call, or the input
    required by the call), else `confirmed_by_user`.
    """
    runs, _ = machine.plan(names)
    if runs and ctx.session.check_client_capability(
        ClientCapabilities(elicitation=ElicitationCapability())
    ):
        return Elicit(
            'bazis-mcp will run on this machine:\n'
            + '\n'.join(shlex.join(command) for _, command in runs),
            Confirmation,
        )
    return Confirmation(install=confirmed_by_user)


@server.tool(annotations=INSTALLS)
def install_tools(
    names: list[PROGRAMS],
    confirmation: Annotated[ElicitationResult[Confirmation], Resolve(_confirmation)],
    confirmed_by_user: Annotated[bool, Field(description=CONFIRMED_BY_USER)] = False,
) -> dict:
    """
    Installs or starts the programs `names` of `check_machine` with its `install_command`
    only, once the user agrees: the client asks the user when it can, else
    `confirmed_by_user` must be true, set only after the user said yes in the conversation.
    Without that nothing runs and `to_confirm` lists the commands to confirm. The commands
    run in the order of `check_machine` (a program before its server). `installed`
    has the result of each command run (`ok`, the end of its `output`); `run_yourself` the
    programs not installed here with the `reason` and the command for the user (one that
    needs sudo, or a Homebrew this user cannot run; null without a package manager).
    """
    runs, refused = machine.plan(names)
    if runs and not (isinstance(confirmation, AcceptedElicitation) and confirmation.data.install):
        commands = [{'name': name, 'command': shlex.join(command)} for name, command in runs]
        return {'installed': [], 'to_confirm': commands, 'run_yourself': refused}
    return {'installed': machine.install(runs), 'to_confirm': [], 'run_yourself': refused}


@server.tool(annotations=CREATES)
def create_project(
    directory: str,
    description: str,
    name: str | None = None,
    frontend: bool = True,
    language: str | None = None,
    database: str | None = None,
) -> dict:
    """
    Creates a Bazis project and serves it from now on. `directory` is an absolute path to a
    new or empty directory, not a temporary one nor inside another project. Pass `name`, the
    name of the product in Latin letters, normalized to the project package as a directory
    name is (`master-na-chas` is `master_na_chas`; the result says `name`; default: from the
    name of the directory; a directory such as `app`, `src`, `project`, `backend` or
    `service` names no product and is refused without it). `frontend` adds bazis-front
    (it needs Node.js; false: a backend only), `language` is the language of the product,
    a code such as `ru`, `pt-br` (default: English, until the agent sets the language of
    the description). `database` is the PostgreSQL server of the project, `host:port`, the
    one the user chose (`check_machine` finds one on port 5432): needed when the environment
    of bazis-mcp names none, and refused when it names another. It writes the skeleton,
    installs `.venv` from PyPI, checks the name and the language with the Python of the
    project, creates the database when that server is reachable and chooses the ports; when
    a step fails, the directory is left as it was.
    A database of the name that has data or cannot be opened is left as it is: the first
    free `<name>_N` is created instead and set in `.env`. A product with a frontend gets the app
    `users/` of the team (`users/routes.py`, `users/router.py`). The Redis of the environment of
    the server is the cache of `.env`. Returns the facts (`database` says what was done,
    `cache` is the Redis location), `rules` to follow and `next_steps`, the task of building the
    project.
    """
    return _project_call(project.create, directory, description, name, frontend, language, database)


@server.tool(annotations=CHOOSES)
def use_project(directory: str) -> dict:
    """
    Serves the existing project in `directory` (an absolute path, the directory of its
    manage.py) from now on: the facts of `project_status` and the `rules` to follow when
    changing it. The project served chosen again keeps its settings module and Python.
    """
    return _project_call(project.use, directory)


@server.tool(annotations=READ_ONLY)
def project_status() -> dict:
    """
    The project served: its `directory`, `settings` module, `python`, whether it has a
    `frontend` (made by `bazis_front init`), its `ports` (null until chosen),
    `database_name` (`BS_DATABASES__DEFAULT__NAME` of the environment of the server, else
    of the env file, `BS_ENV_FILE` of that environment or `.env`, else of `project.env`;
    null when none sets it or for an env file outside the project directory) and
    `env_keys`, the names of
    the variables of its `.env` (never their values; null without `.env` or for a `.env`
    outside the project directory, `env_reason` says which).
    """
    return _project_call(project.status)


def _progress(ctx: Context):
    """
    Reports to the client the seconds a command has run (from the worker thread of a tool).
    """
    def report(elapsed: float) -> None:
        anyio.from_thread.run(ctx.report_progress, elapsed, None, f'{int(elapsed)} s')

    return report


@server.tool(annotations=INSTALLS)
def add_packages(names: list[str], ctx: Context) -> dict:
    """
    Adds the Bazis packages `names` (names of `list_packages`) with the Bazis packages they
    require to `requirements.txt` of the project, those it does not name yet, with the
    version of the catalog as the minimum, installs `requirements-dev.txt` from PyPI into
    `.venv` and raises the minimums to the installed releases. `added` lists the lines
    written, `required` the packages named already, `installed` the installed versions and
    `install` the result of pip; when pip fails, `requirements.txt` stays as it was. With
    bazis-users newly added to a project without them it writes `users/routes.py` and
    `users/router.py` (the route set of the team, `files` lists them). Then add the apps and
    settings their guides name (`BS_INSTALLED_APPS`) yourself. Refused
    without `.venv` (pip never installs into the Python of bazis-mcp) and when a line of the
    requirements is not a requirement of PyPI (a URL, a path, the file of an archive such as
    `demo-0.1-py3-none-any.whl`, an option of pip).
    """
    return _project_call(commands.add_packages, names, _progress(ctx))


@server.tool(annotations=RUNS)
def run_command(kind: KINDS, ctx: Context, args: list[str] | None = None) -> dict:
    """
    Runs a command of the project from a closed table, as argv without a shell, with a
    timeout of 600 seconds. In the project directory: `manage` (`manage.py <args>`:
    makemigrations, migrate, check, bazis_doctor, collectstatic, e2e_data, or bazis_front or
    bazis_messages with their subcommand, never `bazis_front screens --force`), `pytest` (`-m pytest <args>`, never `--basetemp`)
    and `pip` (only `["install", "-r", "requirements-dev.txt"]`, from PyPI into `.venv`). In
    `frontend/`: `npm` (`["install"]` or `["ci"]`, else `npm run <script>` with args
    `["<script>", "--", ...]` such as `["e2e"]` (`["run", "e2e"]` too) of build, lint,
    test, e2e, format; test and e2e take arguments after `--`, never `--output`, `--fsModuleCachePath`, `--coverage.reportsDirectory`) and `npx` (only
    `["tsc", "--noEmit"]` or `["playwright", "install", "chromium"]`, never downloaded). The
    arguments are plain words in the project: no character of a shell, no `..`. No stdin:
    pass `--noinput` where Django asks. `E2E_PORT` and `E2E_PASSWORD` are set, the password
    never shown. Returns `exit_code`, `ok`, `timed_out` and the ends of `stdout` and
    `stderr`. The servers are started with `start_server`.
    """
    return _project_call(commands.run, kind, args or [], _progress(ctx))


@server.tool(annotations=STARTS)
def start_server(which: SERVERS) -> dict:
    """
    Starts in the background the `backend` (`uvicorn <project package>.main:app`) or the dev
    server of the `frontend` (`npm run dev` in `frontend/`) on its port of
    `.bazis/ports.json`, its output in `.bazis/logs/<which>.log`, and waits up to 60 seconds
    for its port: `pid`, `port`, `url`, `running`, `ready` (the port answers), and when it
    ended at once its `exit_code` and `output`. Refused when it runs already or another
    process has its port. Stop it with `stop_server`; the servers end with bazis-mcp.
    """
    return _project_call(processes.start, which)


@server.tool(annotations=STOPS)
def stop_server(which: SERVERS) -> dict:
    """
    Stops the server `which` started by `start_server`, with the processes it started
    (SIGTERM, then SIGKILL after 10 seconds): `stopped`, its `exit_code`, or the `reason`
    when it was not running.
    """
    return _project_call(processes.stop, which)


@server.tool(annotations=READ_ONLY)
def server_logs(which: SERVERS, lines: Annotated[int, Field(ge=1, le=1000)] = 100) -> dict:
    """
    The last `lines` lines of the log of the server `which` (at most 20,000 bytes) and
    whether it is `running`.
    """
    return _project_call(processes.logs, which, lines)


@server.tool(annotations=READ_ONLY)
def read_file(
    path: str,
    offset: Annotated[int, Field(ge=0)] = 0,
    limit: Annotated[int | None, Field(ge=1)] = None,
) -> dict:
    """
    The text of a file of the project (`path` relative to the project directory, or
    absolute in it): its lines from `offset` (the first is 0), at most `limit` of them
    (default: to the end), up to about 40,000 bytes; `next_offset` is the first line not
    read, null at the end. Read a longer file in parts. `.env` is never read
    (`project_status` gives the names of its variables), nor a path outside the project.
    """
    return _project_call(files.read, path, offset, limit)


@server.tool(annotations=WRITES)
def write_file(path: str, content: str) -> dict:
    """
    Writes `content` to a file of the project (`path` relative to the project directory),
    replacing it, with the missing directories; up to 1,000,000 bytes. Never `.env`,
    `.venv/`, `.git/`, `contract/` or a `generated/` directory (generated by the bazis_front
    commands), nor a path outside the project. Returns `path`, `bytes` and `created`.
    """
    return _project_call(files.write, path, content)


@server.tool(annotations=WRITES)
def delete_file(path: str) -> dict:
    """
    Deletes a file of the project (`path` relative to the project directory), such as one
    no longer needed; a symbolic link is deleted itself, never what it links to (a file of
    the project). Never a directory, what `write_file` never writes (`.env`, `.venv/`,
    `.git/`, `contract/`, a `generated/` directory) nor a path outside the project. Returns `path` and `link`.
    """
    return _project_call(files.delete, path)


@server.tool(annotations=WRITES)
def clean_project() -> dict:
    """
    Removes the temporary files and the outputs of the builds and the tests of the project,
    which the commands make again: `.scratch/`, `frontend/dist/`, `frontend/test-results/`,
    `frontend/playwright-report/` and `frontend/node_modules/.vite-e2e/`, those it has (a
    symbolic link itself, never what it links to). Returns them in `removed`. Nothing else:
    `delete_file` deletes a file.
    """
    return _project_call(files.clean)


@server.tool(annotations=READ_ONLY)
def list_files(subdir: str = '') -> dict:
    """
    The entries of a directory of the project (`subdir`, default the project directory):
    `name`, `type` (`directory`, `file`, `link`, `other`) and the `size` of a file, at most
    400 (`truncated`).
    """
    return _project_call(files.listing, subdir)


@server.tool(annotations=READ_ONLY)
def list_packages() -> dict:
    """
    The Bazis packages (`packages`): what each one is for (`summary`, `solves`), the Bazis packages it
    requires and pairs well with, and the installed and the latest known version
    (`installed_version` is null if the package is not installed in the Python of the project;
    without a project, for every package: the catalog of the released packages).
    """
    return {'packages': [catalog.summary(it) for it in _project_call(catalog.packages).values()]}


@server.tool(annotations=READ_ONLY)
def package_guide(name: str, section: str | None = None) -> dict:
    """
    How to use a Bazis package (`bazis` for the core): its AGENTS.md (setup, the classes
    to extend, the rules) and its manifest (`extension_points` with import paths,
    `pitfalls` with the ids of the checks that detect them). Read it before using the
    package. A package installed in the Python of the project is described by its installed
    version, read again at every call.

    `sections` lists the titles of the sections of the AGENTS.md. A long one (over about
    12 kB with its manifest) is not returned whole: `complete` is false and `agents_md` is its introduction; read the
    sections you need with `section` (a title of `sections`), which returns the text of
    that section only; `guide_search` finds the section that covers a question.
    """
    package = _package(name)
    try:
        return catalog.guide(package, section)
    except KeyError as error:
        titles = error.args[1]
        raise ToolError(
            f'No section {section!r} in the guide of {name}; the sections are: '
            f'{", ".join(titles) or "none"}.'
        ) from None


@server.tool(annotations=READ_ONLY)
def guide_search(
    query: str,
    package: str | None = None,
    limit: Annotated[int, Field(ge=1, le=search.LIMIT_MAX)] = 5,
) -> dict:
    """
    Searches the guides of the Bazis packages (their AGENTS.md and the extension points and
    pitfalls of their manifests), of all packages or of one `package`, for the words of the
    `query` (identifiers such as `validate_item` or `PermitRouteBase` work too). `results`
    are the `limit` best matches (at most 10), each with its `package` and `score` and
    either the `section` of the guide (a title for `package_guide(name, section)`), the
    `heading` it is under in that section (null at its top) and its `text` (an excerpt
    around the words when `complete` is false), or an `extension_point` or a `pitfall` of
    the manifest. The guides are those `package_guide` serves.
    """
    if package is None:
        packages = list(_project_call(catalog.packages).values())
    else:
        packages = [_package(package)]
    return {'query': query, 'results': search.search(packages, query, limit)}


@server.tool(annotations=READ_ONLY)
def project_info(sections: list[SECTIONS] | None = None) -> dict:
    """
    Facts about this project: the installed Bazis packages, the settings (secrets hidden,
    dynamic settings without a value), the JSON:API models with their relations, and the
    route classes with their routes. `sections` limits the result (default: all).
    """
    return _project_call(project.info, sections)


@server.tool(annotations=READ_ONLY)
def run_doctor(deploy: bool = False) -> dict:
    """
    Runs the Django system checks of this project, including the checks of the Bazis
    packages (`manage.py bazis_doctor`). `ok` is false if there is an error. `deploy` adds
    the deployment checks. From bazis 2.13 it also runs the database checks against the
    database `default` (such as the declared roles and workflows against the rows); when
    the database cannot be reached they are skipped with the info `bazis.database`, and the
    data is not checked. Run it after every change.
    """
    return _project_call(project.doctor, deploy)


@server.tool(annotations=READ_ONLY)
def front_check(layer: LAYERS | None = None) -> dict:
    """
    Validates the specs of the frontend (spec/: product, screens, design) against each other
    and the contract (`manage.py bazis_front check --json`): `issues` with stable `code`,
    `severity`, `file`, `path` and the fix in `hint`; `ok` is false if there is an error,
    `contract` false if they were not checked against contract/contract.json. `layer`
    reports one layer only. Without bazis-front (installed, in INSTALLED_APPS) or spec/,
    `checked` is false and `reason` says what to do.
    """
    return _project_call(front.check, layer)


@server.tool(annotations=READ_ONLY)
def front_status() -> dict:
    """
    What of the frontend is stale, without Node (the issues of
    `manage.py bazis_front status --json`): `stale` by the `manage.py bazis_front` command
    that updates it (`contract`, `design`, `screens`, `e2e`, `shots`, `update`), each with the
    issues and their hints; `spec_issues` counts the messages of the check of the specs
    (`front.W002`: one for each error and one for all the warnings, which `status` folds; the
    issues themselves are in `front_check`), `shot_errors` has `front.W009` when the report of the last screenshots has errors or there
    is no report, the screenshots not taken (not stale: the screens are fixed instead,
    `bazis_front shots` again), `reviewed` the number of the `screens` of that report and of
    those `looked` at, a screenshot of each given whole (every part) by `front_screenshot`
    since the report was written, with the screens `not_looked` (null without a report), and
    `messages` the other issues. Without bazis-front
    (installed, in INSTALLED_APPS), `checked` is false and `reason` says what to do.
    """
    return _project_call(front.status)


# images for the model, not data: mcp before 2.3 fails on an output schema of Image unless told
@server.tool(annotations=READ_ONLY, structured_output=False)
def front_screenshot(file: str, part: int = 1) -> list[str | Image]:
    """
    A screenshot of the last run of `bazis_front shots`, as an image: `file` is the name of a
    PNG of `frontend/.scratch/shots/`, the `file` of a shot of its `report.json` (such as
    `task-list-manager-dark-390.png`), never another file. A screenshot taller than 1568 px
    comes in parts of that height, from the top: the text "part 1 of 4 (390x1568 px each)"
    before the image says it, and `part` (from 1) gives each of them; a PNG it cannot cut
    comes whole, with a text that says so. Up to 3,000,000 bytes, and 40 screenshots or
    parts of a run: look first at those whose shots have errors, then at one of each screen,
    against the checklist of "The visual check" of the guide of bazis-front.
    """
    note, data = _project_call(front.screenshot, file, part)
    return [*([note] if note else []), Image(data=data, format='png')]


@server.tool(annotations=READ_ONLY)
def front_catalog() -> dict:
    """
    The assets that `manage.py bazis_front init` and `add` copy into the frontend (the
    components, the hooks, the shadcn/ui components): `kind`, `target` directory,
    `capabilities` the contract must have (packages such as statusy) and the assets it
    `requires` (copied with it). `init` copies the vendored assets, the `template` and the
    assets that the template `requires`; `add` the others. Read from the bazis-front
    installed in the project (`source` "installed"), else from the catalog of its latest
    release ("catalog").
    """
    return _project_call(front.assets)


@server.resource(
    'bazis://packages/{name}/agents.md',
    title='AGENTS.md of a Bazis package',
    mime_type='text/markdown',
)
def agents_md(name: str) -> str:
    try:
        package = catalog.packages().get(name)
    except project.ProjectError as err:
        raise ResourceError(str(err)) from err
    if not package or not package['agents_md']:
        raise ResourceNotFoundError(f'No AGENTS.md for {name!r}')
    return package['agents_md']


@server.resource(
    'bazis://rules', title='The rules of Bazis for an agent', mime_type='text/markdown'
)
def rules_md() -> str:
    return rules.RULES


@server.resource(
    'bazis://rules/frontend',
    title='The rules of a product with a frontend made by bazis-front',
    mime_type='text/markdown',
)
def frontend_rules_md() -> str:
    return rules.FRONTEND_RULES


@server.prompt(title='Create a Bazis project')
def new_project(description: str) -> str:
    """
    Creates a Bazis project from a description and builds it.
    """
    return f"""\
Create a Bazis project: {description}

Call `check_machine` first; if programs are `missing`, list them to the user and call
`install_tools` only after the user agrees. Then ask for its directory unless it is named
above (a new directory, never a temporary one), and call `create_project` with it, this
description, the name of the product in Latin letters, the language of the description and the
PostgreSQL server of the user (`database`, unless the environment of the server names one).
Do its `next_steps` following its `rules` in the project directory, with the commands of
`run_command` and the servers of `start_server`.
"""


@server.prompt(title='Change the Bazis project')
def change_project(request: str) -> str:
    """
    Changes the Bazis project served (or the one named by the user) as requested.
    """
    if project.project_dir is None:
        return (
            'Call `use_project` with the directory of the project first (ask for it if it is '
            'not known), and follow the `rules` it returns.\n\n' + prompts.change_prompt(request)
        )
    directory = project.project_dir
    ports = scaffold.project_ports(directory) if prompts.has_frontend(directory) else None
    return prompts.change_prompt(request, ports=ports)


@server.prompt(title='Add a Bazis package')
def add_package(name: str) -> str:
    """
    Adds a Bazis package to the project and makes it work.
    """
    return f"""\
Add the Bazis package {name} to this project.

1. Read its guide with `package_guide("{name}")` and the guides of the Bazis packages it
   requires that are not installed yet (`list_packages` shows them).
2. Install it with `add_packages(["{name}"])` (it adds the packages it requires too), then
   add the apps and settings the guides name (`BS_INSTALLED_APPS`, `BS_BAZIS_APPS` if the
   project sets it).
3. Change the models and routes as the guide says, then create the migrations.
4. Run `run_doctor` and the tests of the project; fix every error and every warning of
   the new package, or explain why a warning stays.
"""


@server.prompt(title='Audit the Bazis project')
def audit_project() -> str:
    """
    Reviews the project against the guides and checks of its Bazis packages.
    """
    return """\
Audit this Bazis project.

1. Run `run_doctor` with `deploy=true` and `project_info`.
2. For every installed Bazis package read `package_guide` and compare the project with
   its rules and pitfalls: routes that bypass permissions or the update checks, settings
   that are unsafe in production, packages that are installed but not used, needs that a
   package solves but the project implements by hand.
3. Report the problems ordered by severity, each with the file to change and the fix.
   Change nothing until the report is confirmed.
"""


@server.prompt(title='Build the frontend')
def build_frontend() -> str:
    """
    Builds the frontend of the project with bazis-front, from its specs to the end-to-end
    tests and the screenshots of its screens.
    """
    return """\
Build the frontend of this Bazis project with bazis-front.

Read `package_guide("bazis-front")` and follow the steps of "Building the frontend of a
product" in its introduction, with the section of each step read when you reach it
(`guide_search` finds a section). If `front_check` says that bazis-front is missing,
install it as the guide says first. The tools of the frontend layer take the place of the
commands that only read: `front_check` is `bazis_front check`, `front_status` says what is
stale and the command that updates it, `front_catalog` lists the components. Run
`run_doctor` after a change of the backend, and finish with the checks of the last step of
the guide and the end-to-end tests against the running backend (`start_server("backend")`,
then `run_command("npm", ["e2e"])`); fix every failure. With the backend still running,
take the screenshots, `run_command("manage", ["bazis_front", "shots"])`, and fix every
error of `frontend/.scratch/shots/report.json` and what the screenshots show
(`front_screenshot`, a tall one part by part, one of each screen while the limit of
40 images of a run lasts, those with errors or warnings and the main ones first; those
not looked at go to Left for you in one line, their number and their ids, and without a
shell `reviewed` of `front_status` names them `not_looked`) against the checklist of
"The visual check" of the guide,
then take them again, at most three rounds; fix each warning of the report too, or list it
in Left for you with why it stays.
"""


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog='bazis-mcp', description='The MCP server of a Bazis project (stdio).'
    )
    parser.add_argument(
        '--project-dir',
        type=Path,
        help='The directory of manage.py and project.env (default: the current directory when '
        'it has manage.py, else none until create_project or use_project).',
    )
    parser.add_argument(
        '--settings',
        help='The settings module (default: DJANGO_SETTINGS_MODULE or the one of manage.py).',
    )
    parser.add_argument(
        '--python',
        help='The Python of the project (default: .venv of the project directory or of its '
        'parent, else the Python of the server).',
    )
    args = parser.parse_args(argv)

    directory = args.project_dir or (Path.cwd() if project.is_project(Path.cwd()) else None)
    if directory:
        project.configure(directory, args.settings, args.python)
    processes.stop_on_signals()
    server.run()


if __name__ == '__main__':
    main()
