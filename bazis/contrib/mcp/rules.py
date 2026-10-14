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
The rules of Bazis for an agent that builds or changes a Bazis project: `RULES` for every
project, `FRONTEND_RULES` for a product with a frontend made by bazis-front.
"""


#: the rules of every Bazis project
RULES = """\
# Bazis

You work on a Bazis project in the current directory. Bazis builds JSON:API services on
Django, FastAPI and Pydantic; the core is the package `bazis`, every other feature is a
separate package `bazis-<name>`. A project installs only the packages it needs.

- The MCP server `bazis` is the source of truth about Bazis, not your memory of it:
  `list_packages` (what each package solves and requires), `package_guide` (how to use a
  package, also `bazis` for the core), `guide_search` (the parts of the guides that answer a
  question, with their sections), `project_info` (the installed packages, settings, models
  and routes of this project) and `run_doctor` (the system checks). Read the guide
  of a package before you use it and follow it exactly: a long guide comes as its
  introduction with the titles of its sections; read the introduction, then a section
  (`package_guide(name, section)`) when a step needs it, never all of them in advance.
- The guides are the documentation of Bazis: do not read the sources of its packages (in
  `.venv`, the copies in `frontend/src/bazis/` and `frontend/e2e/bazis/`, checkouts) to
  find out how to use them. Only when the guide lacks a fact you need, read the source,
  and name the gap in "Guide gaps" of the summary.
- Read `AGENTS.md` (and `CLAUDE.md` if there is one) of the project first.
- Without a shell, with the tools of the MCP server `bazis` only, run the commands of these
  rules with `run_command` (`.venv/bin/python manage.py <command>` is
  `run_command("manage", ["<command>"])`; `"pytest"`, `"pip"`, and `"npm"` and `"npx"` in
  `frontend/`), start and stop the servers with `start_server` and `stop_server`, and add
  packages with `add_packages`.
- The Python environment is `.venv` (`.venv/bin/python`, on Windows
  `.venv\\Scripts\\python.exe`); `installed_version` of `list_packages` is the version in it.
  Add a package to `requirements.txt`, install it with `.venv/bin/python -m pip install -r
  requirements.txt`, then give it its installed release as the minimum: `<name>>=X.Y.Z`,
  the numbers of `installed_version` without a suffix such as `.post1.dev3` (its guide
  and your code follow that version). A requirement that the task gives is written as it
  is; never lower a minimum. List its app in `BS_INSTALLED_APPS` of `project.env` when its
  guide says so.
- After changing models run `.venv/bin/python manage.py makemigrations`. After a change run
  `run_doctor` and fix the errors and the warnings of the packages you used. With the
  database of `.env` it also checks the data against the declarations (`permit.W005`,
  `statusy.W003`: migrate); the info `bazis.database` says the database could not be
  reached and those checks did not run. The tests run with `.venv/bin/python -m pytest`
  when PostgreSQL and Redis are available (`.env`); if they are not, say so instead of
  skipping the tests silently.
- The tests (`tests/`, pytest, with `bazis_test_utils` as the guides show) cover the
  description: a test for every rule and invariant it states (a limit, a uniqueness, a rule
  of a status); for every role a test of what it may do and one of what it may not (403,
  404 or 422), as a user of the role (its `test_user` in a spec; for an anonymous role, a
  request without a token: 401 or 403); for every limit and uniqueness a test of parallel
  requests (`@pytest.mark.django_db(transaction=True)`; `parallel` of `bazis_test_utils`
  when its guide has it, else threads started together by a `threading.Barrier`, each
  closing its database connections): the invariant holds, the answers that succeed are 201
  or 200 (a change or a transit), the others 409 or 422, never a 5xx. At least 10 tests;
  none of the framework itself. The pytest plugin of `bazis_test_utils` installs the triggers of pgtrigger in the
  test database: never write a `django_db_setup`, a fixture that installs the triggers or
  one that creates the declared roles, statuses or transits.
- The tests share Redis (`BS_CACHES__DEFAULT__LOCATION`) with the running backend and other
  projects: never flush its database or call `cache.clear()`. The session fixture of
  `tests/conftest.py` gives the cache keys of the tests a prefix of their own and deletes
  only them at the end: keep it, and delete only those keys (`cache.delete_pattern('*')`).
  A test with `transaction=True` empties the tables after it; the flush applies the
  declarations again, the other data of a test is created by the test or its fixtures.
- The roles of bazis-permit (with their permission groups) are declared in `<app>/roles.py`
  and the statuses and transits of bazis-statusy in `<app>/workflow.py`, as their guides
  show, never created by data migrations, commands or fixtures: `migrate` applies them. A
  project whose data migrations already create them moves them into these modules and
  keeps those migrations as history without effect (`operations = []`, their
  dependencies kept): `migrate` takes over the existing rows.
- With bazis-ws, publish from the code of a write with `publish_changed(item)` of
  `bazis.contrib.ws.messages` (after the commit), never with a Redis client or `on_commit`
  of your own, and route the socket with `router.register('bazis.contrib.ws.router')` in
  the root router module. Notify a user with `notify` of bazis-notify when the project has
  it (stored, in his language, and delivered live by bazis-notify itself: never a second
  message of bazis-ws); without bazis-notify, with `notify(users, lambda user:
  notification(...))` of `bazis.contrib.ws.messages` (in the language of each user).
- A route set of bazis-permit that restricts its objects with its own `restrict_queryset`
  and applies it in its `get_queryset` (`FileUploadRouteSet` of bazis-uploadable, the
  routes of bazis-bg, their subclasses) needs no `permit_public = True`, which says that the data of the route is public: set it
  only on a route whose data is public (`permit.W002` names the routes that restrict
  nothing).
- A location is a `PointField` of `django.contrib.gis.db.models` (`geography=True` when the
  product measures distances, for the index of the distances), never two `FloatField`s.
  What is near is filtered and sorted by the core, `filter=<field>__near=<lon>,<lat>,5km`
  and `sort=<field>__distance(<lon>,<lat>)` with the point field in the LIST schema of the
  route, never by a distance computed in Python or SQL of your own; a distance in the code
  is `point_distance`/`point_within` of `bazis.core.utils.geo`, as the guide of the core
  shows.
- With bazis-users, the root router module imports `bazis.contrib.users.token` (the token
  endpoint) unless it registers the user routes (`users.E002`), and a user model of the
  project has `UserLanguageMixin`, so that the language of a user follows him.
- Temporary files (scripts, outputs, screenshots) go to `.scratch/` of the project, which
  Git ignores; never to `/tmp` or other directories outside the project.
- Never read, print or copy the values of `.env`. Never write a password, token or other
  secret, also of the test users, in your messages or the summary: say where it is set
  (such as `E2E_PASSWORD`). Never run git commands that change the repository (commit,
  push, reset): the user reviews and commits the changes.
- The database of `.env` is created by `bazis new` when PostgreSQL is reachable, with
  PostGIS (the task says what it did). Never drop or recreate it: after the first
  `migrate` add new migrations, never delete or generate again the applied ones. You may
  create it when it is missing (`CREATE DATABASE`, then `CREATE EXTENSION postgis` in it);
  report it. When the task says that the database already has data of another project or
  could not be inspected, it is not ready: never migrate it nor change its data, say that
  the user checks the access to it or sets another `BS_DATABASES__DEFAULT__NAME` in `.env`.
- The final checks are `run_doctor`, the tests and, with a frontend, the checks of its
  rules. Run the final checks once, after the last change: fix what fails and run again only
  the checks that failed, not the whole round.
- End with a short summary in these sections: Built (what you built or changed), Packages
  (the Bazis packages used), Run (how to run it), Outside the files (what you created
  outside them, such as the database), Left for you (what is left for the user, each with
  its reason) and Guide gaps (each fact a guide lacked: the package, the fact, the source
  you read instead; "none" when there was none).

# Languages

The languages of the product are `BS_LANGUAGES` and `BS_LANGUAGE_CODE` of `project.env`;
English, the language of the msgids, is always one of them.

- The texts of the code are English msgids through `gettext_lazy`
  (`from django.utils.translation import gettext_lazy as _`): `verbose_name`, `help_text`,
  the labels of `choices`, the titles and the messages. Keep them lazy (no `str()` or
  f-string of them). No text in another language in the code; the names of the declared
  roles, statuses and transits are English msgids too, which `migrate` translates into the
  column of each language with the catalog of the project.
- Translate them into every other language in the catalogs of the project
  (`locale/<language>/LC_MESSAGES/django.po` of the project and of its apps) with
  `.venv/bin/python manage.py bazis_messages`, run in the project root: `make` (it creates
  `locale/`, runs makemessages with the ignores of a project and prints what is
  `untranslated` or `fuzzy`), write the translations of those entries to
  `locale/translations.json` (`{"<language>": {"<msgid>": "<msgstr>"}}`, a plural with the
  list of its forms, as the guide of the core shows), then `apply locale/translations.json
  --check` (it compiles the catalogs). Remove from the file the msgids that `apply`
  reports as `unknown` (no longer in the code). Keep the JSON file in the project and add
  to it after every `make`; keep the `.po` and the `.mo` files. Never write a script that
  edits the `.po` files, never run `makemessages` or `compilemessages` yourself.
- `bazis_messages` needs GNU gettext (`xgettext`, `msgmerge`, `msgfmt`). Without it, say
  in the summary that the catalogs were not made and that the user installs gettext; never
  work around it (no `.po` or `.mo` written another way).
- `bazis.W004` of `run_doctor` (two Bazis packages translate a msgid differently): the
  project translates the msgid itself. Declare it in `<project>/translations.py` (the
  package of the settings) with `gettext_noop` (`from django.utils.translation import
  gettext_noop`), so that `make` keeps it, and translate it through `bazis_messages` like
  the other texts: the catalog of the project wins. `bazis.W005` (a language without the
  translations of the texts of a Bazis package): report it in the summary.
"""

#: the rules of a product with a frontend made by bazis-front, added to RULES
FRONTEND_RULES = """\
# The frontend (bazis-front)

The product has a frontend made by bazis-front: the specs of the product in `spec/`, the
contract generated from the backend in `contract/`, the React app in `frontend/`. The
guide is `package_guide("bazis-front")` (`frontend/AGENTS.md` only points to its
sections): read its introduction before you change the frontend, then the section of a
step when you reach it, and follow it exactly. All the frontend logic is in bazis-front: use its commands,
do not write generators or frontends of your own.

- The frontend is changed with the subcommands of `.venv/bin/python manage.py bazis_front`
  (`init`, `contract`, `check`, `add`, `design`, `e2e`, `update`; `status` only shows its
  state). The MCP tools read it: `front_check` (the issues of the specs
  against the contract, with a `hint` each), `front_status` (what is stale and the command
  that updates it) and `front_catalog` (the components, the capabilities and the assets
  they require).
- The specs describe the product and the backend is built to satisfy them. After every
  change of the models, routes, roles, statuses or transits: migrate, export the contract
  (`bazis_front contract`), then fix the spec or the backend until `front_check` reports
  no errors.
- Never edit `contract/`, `frontend/src/bazis/generated/`, `frontend/e2e/generated/`, the
  copies of `frontend/src/bazis/client/`, `frontend/src/bazis/react/`,
  `frontend/src/bazis/i18n/`, `frontend/e2e/bazis/`, `frontend/bazis-front.lock.json` or
  `frontend/.bazis/`: generate them again with the commands, and wrap the copies in the
  product code (the texts of the product are in its own dictionaries).
- The backend decides the permissions (bazis-permit): never encode roles or permission
  rules in the frontend. The screens use the tokens of the design, never literal colors.
- The frontend is in the languages of the backend (`languages` and `language` of
  `spec/product.yaml` as `BS_LANGUAGES` and `BS_LANGUAGE_CODE`): every text of a screen
  goes through `t()` with a key in the dictionaries of the product,
  `frontend/src/i18n/<language>.ts`, one for each language (listed in
  `frontend/src/i18n/index.ts`); never a text in the JSX.
- The contract is exported from the migrated database, with the permit roles and the
  statuses and transits of the workflows that `migrate` applied from their declarations
  (the rules above). The test
  data of the end-to-end tests is the e2e data command recommended by bazis-front,
  `.venv/bin/python manage.py e2e_data`: on top of the migrations it creates only a user
  per `test_user` of the roles, with its role and the password of the environment
  variable `E2E_PASSWORD`, and the records the scenarios need (the items they open). It
  can run again (it sets the passwords again).
- The servers use the ports of the project on this machine, `.bazis/ports.json`
  (`backend`, `frontend`, `e2e`), never the defaults 8000 and 5173 that other projects
  use. After `bazis_front init` write `BAZIS_API_URL=http://localhost:<backend>` in
  `frontend/.env.local` (not committed), which `npm run dev` and `npm run e2e` read; the
  dev server is `npm run dev -- --port <frontend>`.
- After a change of the frontend run `npx tsc --noEmit` in `frontend/` and fix what it
  reports; format only with `npm run format` (the prettier pinned in its `package.json`,
  which leaves the copies alone), never `npx prettier`.
- The final checks of the frontend: `front_check` without errors, `front_status` with
  nothing stale, and in `frontend/` `npx tsc --noEmit`, `npm run lint`, `npm test` and
  `npm run build`; after a change of the specs or the screens also `bazis_front e2e` and
  `npm run e2e` against the running backend: migrate, run `e2e_data`, start
  `.venv/bin/uvicorn <project package>.main:app --port <backend>` in the background, run
  `E2E_PORT=<e2e> E2E_PASSWORD=<the same password> npm run e2e`, then stop the backend.
  A test that fails only sometimes gets one attempt at a fix, then goes to Left for you.
- Node.js with npm is needed by `npm install`, the TypeScript of the contract
  (`schema.d.ts`), the build and the tests of the frontend, and the contract by a migrated
  database. Without them do the other steps and say which ones did not run.
"""
