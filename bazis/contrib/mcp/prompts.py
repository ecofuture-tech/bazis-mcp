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
The tasks of an agent that builds a Bazis project (`new_prompt`), adds a package to it
(`add_prompt`) or changes it (`change_prompt`), with the rules of `rules`.
"""

from pathlib import Path

from . import scaffold


#: the order of the work on a product with a frontend made by bazis-front: the steps of the
#: guide of bazis-front, with what the tasks add to them (the packages, `.venv`, the
#: description, the ports, the rounds of the screenshots, the final checks of the rules)
FRONTEND_STEPS = """\
Follow the steps of "Building the frontend of a product" in the introduction of the guide
of bazis-front (`package_guide("bazis-front")`), with the section of each step read when
you reach it, and with what this product adds to them:

- Before step 1, read the introduction of the guide of the core (`package_guide("bazis")`)
  and choose the Bazis packages the product needs with `list_packages` (the frontend logs in
  with bazis-users, roles and access need bazis-permit, statuses and transits
  bazis-statusy, files bazis-uploadable). The commands of `manage.py` run with
  `.venv/bin/python manage.py`.
- Step 2: the specs describe {source}, with scenarios for the main tasks of every role,
  including what a role may not do, and the `languages` and `language` of the backend; run
  `front_check` and fix the errors of the shape and of the references before the backend.
- Step 3: the backend also has the tests and the translations that the rules require,
  `makemigrations` and `run_doctor` without errors.
- Step 5 is `front_check`; step 6 chooses the components with `front_catalog`, and the texts
  of the screens go through `t()`.
- Step 7: the palette, the fonts, the shape and the surface of the design fit {source}.
- Step 8: install the browser once (`npx playwright install chromium` in `frontend/`), and
  fix the screens, the specs or the backend until the tests pass.
- Step 9: with the backend running as for `npm run e2e` (its test data,
  `.venv/bin/uvicorn {name}.main:app --port <backend>`), run `bazis_front shots` with
  `run_command`, read `frontend/.scratch/shots/report.json` and open the screenshots
  against the checklist of "The visual check"; fix every error in the specs, the screens,
  the design or the backend and run `shots` again until the report has no error, at most
  three rounds; after the third, list each error left (`shot_errors` of `front_status`) in
  Left for you, with its screen and code. Exit 2 means nothing was shot: start the backend,
  or install the browser.
- Step 10 is a part of the final checks of the rules: run them once, at the end. Say how to
  run the backend (`.venv/bin/uvicorn {name}.main:app --port <backend>`) and the frontend
  (`npm run dev -- --port <frontend>` in `frontend/`) with the ports of the project.
"""


def language_step(language: tuple[str, str] | None) -> str:
    """
    What the task of a new product says about its language: the `language` chosen for it
    (`scaffold.product_language`, written by `scaffold.set_language`), else the agent finds
    it from the description.
    """
    if language:
        code, own_name = language
        languages = ' and English' if code != 'en' else ''
        return f"""\
The product is in {own_name} (`{code}`){languages}: `BS_LANGUAGES` and `BS_LANGUAGE_CODE` of
`project.env` are set. Follow the rules of the languages."""
    return """\
The language of the product is the language of the description, and English is always one
of its languages (the language of the msgids). `project.env` has English only: if the
description is not in English, first set there
`BS_LANGUAGES='[["<code>", "<its own name>"], ["en", "English"]]'` and
`BS_LANGUAGE_CODE=<code>` with the code of Django of that language (`ru`, `de`, `pt-br`).
Follow the rules of the languages."""


def ports_text(ports: dict[str, int]) -> str:
    """
    What a task says about the ports of the project (`scaffold.project_ports`).
    """
    return (
        f'The ports of this project on this machine (`.bazis/ports.json`): the backend '
        f'{ports["backend"]}, the dev server of the frontend {ports["frontend"]}, the dev '
        f'server of the end-to-end tests {ports["e2e"]}.'
    )


def new_prompt(
    description: str,
    name: str,
    frontend: bool = False,
    language: tuple[str, str] | None = None,
    database: str | None = None,
    ports: dict[str, int] | None = None,
) -> str:
    """
    The task of building a new project (`bazis new`, the evals of bazis-cli): the backend,
    and with a `frontend` the whole product with its frontend made by bazis-front, in the
    `language` of `scaffold.product_language`, else in the language of the description;
    `database` is what `scaffold.create_database` did, `ports` those of
    `scaffold.project_ports`.
    """
    database = f'\n{database}\n' if database else ''
    ports = f'\n{ports_text(ports)}\n' if ports else ''
    skeleton = f"""\
Build this Bazis project: {description}

The skeleton is ready: the project package `{name}` (settings, root router, ASGI app in
`{name}/main.py`), `project.env`, `.env`, `requirements.txt`, `tests/` (its `conftest.py`
keeps the cache keys of the tests apart), and `.venv` with Bazis installed.
{database}{ports}
{language_step(language)}
"""
    if not frontend:
        return skeleton + f"""
Read the introduction of the guide of the core (`package_guide("bazis")`), choose the
Bazis packages the project needs with `list_packages`, read the introductions of their
guides and the sections you need, then create the apps with their models, routes,
translations and tests, and register the routers in `{name}/router.py`. Finish with one
run of the final checks.
"""
    return skeleton + f"""
bazis-front is in `requirements.txt` and `BS_INSTALLED_APPS`.

Build the whole product, the backend and its frontend, in this order; register the
routers of the apps in `{name}/router.py`.

{FRONTEND_STEPS.format(source='the description', name=name)}"""


def has_frontend(project_dir: Path) -> bool:
    """
    Whether the project has a frontend made by `bazis_front init` (its lock).
    """
    return (project_dir / 'frontend' / 'bazis-front.lock.json').is_file()


def frontend_change(change: str) -> str:
    """
    What a task says about a change of a product with a frontend made by bazis-front:
    `change` names what changes it (`the package`, `the change`).
    """
    return f"""
The product has a frontend (bazis-front). Describe in `spec/` what {change} changes in the
product (fields, workflows, access, scenarios, screens). After the backend: migrate,
export the contract (`.venv/bin/python manage.py bazis_front contract`) and fix the spec
or the backend until `front_check` reports no errors. With `front_catalog` find the
components of what {change} adds and copy those the screens need (`bazis_front add`), use
them in the screens, generate the end-to-end tests again (`bazis_front e2e`), extend
`e2e_data`, and finish with the final checks of the rules.
"""


def add_prompt(
    package: str,
    goal: str | None = None,
    frontend: bool = False,
    ports: dict[str, int] | None = None,
) -> str:
    """
    The task of adding the Bazis `package` to a project, for a `goal`: in a project with a
    `frontend` (`has_frontend`) the frontend follows the change, and bazis-front added to
    a backend builds its frontend; `ports` are those of the project when it has or gets a
    frontend (`scaffold.project_ports`).
    """
    goal = f' The project needs it for: {goal}' if goal else ''
    prompt = f"""\
Add the Bazis package {package} to this project and use it.{goal}

Read its guide with `package_guide("{package}")` and the guides of the Bazis packages
it requires that are not installed (`list_packages`), install them, follow the setup of the
guides, change the models and routes they concern, create the migrations, add tests, and
make `run_doctor` pass without the warnings of the new packages.
"""
    if package == 'bazis-front':
        prompt += (
            f'\nInstall bazis-front from the requirement `{scaffold.frontend_requirement()}`: '
            'add this line to `requirements.txt` as it is.\n'
        )
    if frontend:
        prompt += frontend_change('the package')
    elif package == 'bazis-front':
        source = 'the backend' + (' and what the project needs it for' if goal else '')
        steps = FRONTEND_STEPS.format(source=source, name='<project package>')
        prompt += f'\nThen build the frontend of the product in this order:\n\n{steps}'
    if ports:
        prompt += f'\n{ports_text(ports)}\n'
    return prompt


def change_prompt(
    request: str, resumed: bool = False, ports: dict[str, int] | None = None
) -> str:
    """
    The task of a change of a project: in a `resumed` session, which has the project and
    the steps already, the `request` as it is; in a new one, with the preparation, and the
    steps of the frontend in a product with a frontend, whose `ports` it is given
    (`scaffold.project_ports`).
    """
    if resumed:
        return f'{request}\n\nAfter the change, run the final checks of the rules once.\n'
    prompt = f"""\
Change this Bazis project: {request}

The project exists: read `project_info` and the guides of the packages the change concerns
(`package_guide`; `list_packages` for a package it needs that is not installed). Change the
models, routes, translations and tests it concerns, with new migrations, and test the
rules it adds.
"""
    if ports:
        prompt += frontend_change('the change')
        prompt += f'\n{ports_text(ports)}\n'
    else:
        prompt += '\nFinish with the final checks of the rules.\n'
    return prompt
