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
from pathlib import Path
from typing import Literal

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ResourceError, ResourceNotFoundError, ToolError
from mcp.types import ToolAnnotations

from . import __version__, catalog, front, project


INSTRUCTIONS = """\
Bazis builds JSON:API services on Django, FastAPI and Pydantic. The core is the package
`bazis`; every other feature is a separate package `bazis-<name>`. Install only the
packages the project needs.

- Choose packages with `list_packages` (what each one solves and requires), then read the
  guide of each chosen package with `package_guide` before using it, also for the core
  (`bazis`). Follow the guides, not your memory of Bazis. A long guide comes as its
  introduction (`complete` false) with the titles of its `sections`: read them with
  `package_guide(name, section)`.
- Facts about this project (installed packages, settings, models, routes) come from
  `project_info`.
- After every change run `run_doctor` and the tests of the project, and fix what they
  report.
- The frontend layer (bazis-front, guide `package_guide("bazis-front")`): check the specs
  with `front_check`, find what is stale with `front_status`, and choose the components
  with `front_catalog`.
"""

SECTIONS = Literal['packages', 'settings', 'models', 'routes']
LAYERS = Literal['product', 'screens', 'design']
READ_ONLY = ToolAnnotations(readOnlyHint=True, openWorldHint=False)

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


@server.tool(annotations=READ_ONLY)
def list_packages() -> dict:
    """
    The Bazis packages (`packages`): what each one is for (`summary`, `solves`), the Bazis packages it
    requires and pairs well with, and the installed and the latest known version
    (`installed_version` is null if the package is not installed in the Python of the project).
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

    `sections` lists the titles of the sections of the AGENTS.md. A long one is not
    returned whole: `complete` is false and `agents_md` is its introduction; read the
    sections you need with `section` (a title of `sections`), which returns the text of
    that section only.
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
    What of the frontend is stale, without Node (the system checks `front.*` of
    `manage.py bazis_doctor`): `stale` by the `manage.py bazis_front` command that updates
    it (`contract`, `design`, `e2e`, `update`), each with the messages and their hints;
    `spec_issues` counts the issues of the specs (see `front_check`). Without bazis-front
    (installed, in INSTALLED_APPS), `checked` is false and `reason` says what to do.
    """
    return _project_call(front.status)


@server.tool(annotations=READ_ONLY)
def front_catalog() -> dict:
    """
    The assets that `manage.py bazis_front init` and `add` copy into the frontend (the
    components, the hooks, the shadcn/ui components): `kind`, `target` directory,
    `capabilities` the contract must have (packages such as statusy), the assets it
    `requires` (copied with it) and `init` (copied by `init`). Read from the bazis-front
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


@server.prompt(title='Build the frontend')
def build_frontend() -> str:
    """
    Builds the frontend of the project with bazis-front, from its specs to the end-to-end
    tests.
    """
    return """\
Build the frontend of this Bazis project with bazis-front.

1. Read `package_guide("bazis-front")` with all its sections, and `front_catalog`. If
   `front_check` says that bazis-front is missing, install it, add "bazis.contrib.front" to
   BS_INSTALLED_APPS and run `manage.py bazis_front init` (frontend/ and the starters of
   spec/).
2. Describe the product in spec/product.yaml (roles, entities, access, scenarios), its
   screens in spec/screens/ and its design in spec/design/, as the guide says; run
   `front_check` after each layer.
3. Build the backend the specs need (models, route sets, roles with their permissions,
   statuses and transits, migrations), run `run_doctor` and the tests, migrate, and
   export the contract with `manage.py bazis_front contract`.
4. Run `front_check` until it reports no errors; fix the spec or the backend as each
   `hint` says.
5. Copy the components the screens need with `manage.py bazis_front add`, write the
   screens in frontend/src/screens/ from them, and generate the theme
   (`manage.py bazis_front design`) and the end-to-end tests (`manage.py bazis_front e2e`).
6. Run `front_status` and update what is stale, then in frontend/ `npx tsc --noEmit`,
   `npm run lint`, `npm test` and `npm run e2e` against the running backend, with the
   test users of the roles (`test_user` in spec/product.yaml) in its data and their
   password in E2E_PASSWORD; fix every failure.
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
    parser.add_argument(
        '--python',
        help='The Python of the project (default: .venv of the project directory or of its '
        'parent, else the Python of the server).',
    )
    args = parser.parse_args(argv)

    project.configure(args.project_dir, args.settings, args.python)
    server.run()


if __name__ == '__main__':
    main()
