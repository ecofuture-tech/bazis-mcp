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
from typing import Annotated, Literal

from pydantic import Field

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ResourceError, ResourceNotFoundError, ToolError
from mcp.types import ToolAnnotations

from . import __version__, catalog, front, project, search


INSTRUCTIONS = """\
Bazis builds JSON:API services on Django, FastAPI and Pydantic. The core is the package
`bazis`; every other feature is a separate package `bazis-<name>`. Install only the
packages the project needs.

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
    that updates it (`contract`, `design`, `e2e`, `update`), each with the issues and their
    hints;
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

Read `package_guide("bazis-front")` and follow the steps of "Building the frontend of a
product" in its introduction, with the section of each step read when you reach it
(`guide_search` finds a section). If `front_check` says that bazis-front is missing,
install it as the guide says first. The tools of the frontend layer take the place of the
commands that only read: `front_check` is `bazis_front check`, `front_status` says what is
stale and the command that updates it, `front_catalog` lists the components. Run
`run_doctor` after a change of the backend, and finish with the checks of the last step of
the guide and the end-to-end tests against the running backend; fix every failure.
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
