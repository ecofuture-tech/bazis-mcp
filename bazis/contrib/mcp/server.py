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
checks of the project, for AI agents. All tools only read.

Run in the project directory: `bazis-mcp` (see the README).
"""

import argparse
import contextlib
import sys
from pathlib import Path
from typing import Literal

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ResourceNotFoundError, ToolError
from mcp.types import ToolAnnotations

from . import __version__, catalog, project


INSTRUCTIONS = """\
Bazis builds JSON:API services on Django, FastAPI and Pydantic. The core is the package
`bazis`; every other feature is a separate package `bazis-<name>`. Install only the
packages the project needs.

- Choose packages with `list_packages` (what each one solves and requires), then read the
  guide of each chosen package with `package_guide` before using it, also for the core
  (`bazis`). Follow the guides, not your memory of Bazis.
- Facts about this project (installed packages, settings, models, routes) come from
  `project_info`.
- After every change run `run_doctor` and the tests of the project, and fix what they
  report.
"""

SECTIONS = Literal['packages', 'settings', 'models', 'routes']
READ_ONLY = ToolAnnotations(readOnlyHint=True, openWorldHint=False)

server = MCPServer('bazis', instructions=INSTRUCTIONS, version=__version__)


def _package(name: str) -> dict:
    packages = catalog.packages()
    if name not in packages:
        raise ToolError(f'Unknown package {name!r}; the packages are: {", ".join(packages)}.')
    return packages[name]


def _project_call(func, *args):
    try:
        return func(*args)
    except project.ProjectError as err:
        raise ToolError(str(err)) from err


@server.tool(annotations=READ_ONLY)
def list_packages() -> dict:
    """
    The Bazis packages (`packages`): what each one is for (`summary`, `solves`), the Bazis packages it
    requires and pairs well with, and the installed and the latest known version
    (`installed_version` is null if the package is not installed).
    """
    return {'packages': [catalog.summary(it) for it in catalog.packages().values()]}


@server.tool(annotations=READ_ONLY)
def package_guide(name: str) -> dict:
    """
    How to use a Bazis package (`bazis` for the core): its AGENTS.md (setup, the classes
    to extend, the rules) and its manifest (`extension_points` with import paths,
    `pitfalls` with the ids of the checks that detect them). Read it before using the
    package. An installed package is described by its installed version.
    """
    return _package(name)


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
    the deployment checks. Run it after every change.
    """
    return _project_call(project.doctor, deploy)


@server.resource(
    'bazis://packages/{name}/agents.md',
    title='AGENTS.md of a Bazis package',
    mime_type='text/markdown',
)
def agents_md(name: str) -> str:
    package = catalog.packages().get(name)
    if not package or not package['agents_md']:
        raise ResourceNotFoundError(f'No AGENTS.md for {name!r}')
    return package['agents_md']


@server.prompt(title='Add a Bazis package')
def add_package(name: str) -> str:
    """
    Adds a Bazis package to the project and makes it work.
    """
    return f"""\
Add the Bazis package {name} to this project.

1. Read its guide with `package_guide("{name}")` and the guides of the Bazis packages it
   requires that are not installed yet (`list_packages` shows them).
2. Add the packages to the dependencies of the project, and the apps and settings the
   guides name (`BS_INSTALLED_APPS`, `BS_BAZIS_APPS` if the project sets it).
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


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog='bazis-mcp', description='The MCP server of a Bazis project (stdio).'
    )
    parser.add_argument(
        '--project-dir',
        type=Path,
        default=Path.cwd(),
        help='The directory of manage.py and project.env (default: the current directory).',
    )
    parser.add_argument(
        '--settings',
        help='The settings module (default: DJANGO_SETTINGS_MODULE or the one of manage.py).',
    )
    args = parser.parse_args(argv)

    # stdout is the protocol channel: anything the project prints while loading goes to stderr
    with contextlib.redirect_stdout(sys.stderr):
        project.setup(args.project_dir.resolve(), args.settings)
    server.run()


if __name__ == '__main__':
    main()
