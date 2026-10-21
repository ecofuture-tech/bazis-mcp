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
  `frontend/`), start and stop the servers with `start_server` and `stop_server`, add
  packages with `add_packages`, and look at the screenshots of the frontend with
  `front_screenshot`.
- The Python environment is `.venv` (`.venv/bin/python`, on Windows
  `.venv\\Scripts\\python.exe`); `installed_version` of `list_packages` is the version in it.
  Add a package to `requirements.txt`, install it with `.venv/bin/python -m pip install -r
  requirements.txt`, then give it its installed release as the minimum: `<name>>=X.Y.Z`,
  the numbers of `installed_version` without a suffix such as `.post1.dev3` (its guide
  and your code follow that version). A requirement that the task gives is written as it
  is; never lower a minimum. List its app in `BS_INSTALLED_APPS` of `project.env` when its
  guide says so. A package the project no longer uses leaves `requirements.txt`, its app
  and its imports, but stays installed in `.venv` (nothing here uninstalls): say so in
  Left for you, with `.venv/bin/python -m pip uninstall <name>` for the user, never as a
  step of yours.
- After changing models run `.venv/bin/python manage.py makemigrations`. After a change run
  `run_doctor` and fix the errors and the warnings of the packages you used, but
  `front.W009` (the screenshots of the frontend not taken, or their errors) in a task that
  changes no screen, spec or design of the frontend: they need the backend and a browser,
  and the rules of the frontend say when to take them. With the
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
- The app `users/` with the route set of the team, `users/routes.py` and `users/router.py`,
  is in the skeleton of a product with a frontend (`create_project`; `add_packages` writes
  it when bazis-users is added to a project without it). With bazis-users, add the package,
  the app `users` to `BS_INSTALLED_APPS` and `router.register('users.router')` to the root
  router module: the user app of the project is named `users` and keeps these two files (a
  user model of its own goes to `users/models.py`, with `UserLanguageMixin`, so that the
  language of a user follows him). That registration also declares the token endpoint
  (`users.E002`): never register the bundled `bazis.contrib.users.router`, and never only
  import `bazis.contrib.users.token`. A frontend labels by that route the author of a
  status, the assignee and the watchers by name, and picks the users with a search; without
  it they are the start of an id, and `front_check` warns P036 for a field related to the
  users of a project without a route of them. Widen only its `restrict_queryset` for
  `view`, never remove it.
- With bazis-statusy, the payload type of a transit is the classmethod
  `Model.get_transit_payload_type(transit)` (bazis-statusy 2.15; 2.14 does not call it, its
  payload type is `item.transit_payload_type(transit)`): override it, never
  `transit_payload_type` of an item (its old name). The validated payload is kept in the
  history record of the transit, and whoever has the permission `history` of the item reads
  it with `GET /{item_id}/status_history/` (bazis-statusy 2.15): grant `history` only to the
  roles that may read the payloads, and mark a secret field of a payload model `Annotated[...,
  NOT_IN_HISTORY]` (`bazis.contrib.statusy.schemas`, on the field or a member of its
  `Optional`, never inside a list or a nested model): it is validated and given to the
  methods, not kept. The calculated field `status_history` is the compact history under
  `view`, without the payloads.
- With bazis-authing, the Google login of a browser is `POST /google-auth-init/` with the
  store token as the bearer token and the credentials of the browser, then a window of the
  same browser at the `url` of its answer (bazis-authing 2.8): never a URL with the store
  token. Its one-time ticket is bound to the browser by a SameSite=Lax cookie, so the page
  is same-site with the API (an API of another origin also answers CORS with credentials).
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
  report it. When the task says that the database of `.env` already has data of another
  project or could not be inspected, it is not ready: never migrate it nor change its data,
  say that the user checks the access to it or sets another `BS_DATABASES__DEFAULT__NAME`
  in `.env` (`project_status` gives `database_name`, the name the project uses). When it
  says that databases were taken and left as they are and that `.env` sets another one,
  only the taken ones are not ready (never change them): the one `.env` sets is the
  database of the project, migrate it.
- The final checks are `run_doctor`, the tests and, with a frontend, the checks of its
  rules. Run the final checks once, after the last change: fix what fails and run again only
  the checks that failed, not the whole round. A next change asked in the conversation ends
  with the whole round again, also the checks of the parts it did not change.
- Your last message is a short summary with exactly these section headings, in this order,
  none left out and none of your own instead: Built (what you built or changed), Packages
  (the Bazis packages used), Run (how to run it), Outside the files (what you created
  outside them, such as the database), Left for you (what is left for the user, each with
  its reason) and Guide gaps (each fact a guide lacked: the package, the fact, the source
  you read instead; "none" when there was none). A section with nothing to say says
  "none".

# Languages

The languages of the product are `BS_LANGUAGES` and `BS_LANGUAGE_CODE` of `project.env`:
those of the request, one unless it asks for more. Never add English, the language of
the msgids, for its own sake: bazis-front and Django fall back to it by themselves, while a
second language is one nobody asked for, with all its texts to translate and a switch of
languages in the interface.

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
  (`init`, `contract`, `check`, `add`, `design`, `screens`, `e2e`, `shots`, `update`;
  `status` only shows its state). The MCP tools read it: `front_check` (the issues of the specs
  against the contract, with a `hint` each), `front_status` (what is stale and the command
  that updates it) and `front_catalog` (the components, the capabilities and the assets
  they require).
- The specs describe the product and the backend is built to satisfy them. After every
  change of the models, routes, roles, statuses or transits: migrate, export the contract
  (`bazis_front contract`), then fix the spec or the backend until `front_check` reports
  no errors.
- With more than five links, the navigation is `navigation` of `spec/product.yaml` with
  groups of related screens (`{group, title, items}`), a `label` shorter than the title of
  a screen where it is long, and an `icon` (a name of lucide, D013) where that of its
  entity does not fit: "The specs" of the guide of bazis-front. The top bar shows the
  links it has room for, one by one, and moves the others, from the first that does not
  fit, into its menu `nav:more` (More) by itself; a group is shared by the row and the
  menu, so a group does not need to fit whole: choose `navigation` of the
  theme by the look of the product, never drop or hide links for their number, and never
  give a screen the id `more`, the mark of that menu (S055). The link of
  the form of a custom action requires its action by itself (a public one is shown to all):
  give it no `requires` (S030).
- The screens are generated from their specs, never written as TSX: describe each in
  `spec/screens/<id>.yaml` and run `bazis_front screens` after every change of `spec/`. What
  a spec cannot say goes to the extension of its screen (`extend: true`,
  `frontend/src/screens/<id>/extend.tsx`), a screen that the generated one does not fit is
  written by hand (`custom: true`, `frontend/src/screens/<id>/index.tsx`); never into
  `frontend/src/screens/generated/`. A page that only sends a custom action (a sign-up, a
  request) is a spec too, `primitive: form` with `form.action`, never a custom screen.
  `screens` refuses to overwrite an edited generated file (`front.W010`): move the edit to
  the extension and leave `--force`, which drops it, to the user.
- The numbers of a dashboard are the aggregates of the core (`meta=aggregates`): a sum, an
  average, a minimum or a maximum is the `value` of a tile (`{sum: <field>}`, `avg`, `min`,
  `max`) or of a chart (`sum`, `avg`). Never count or sum items in the browser: what a tile
  or a chart cannot say (a sum by a category or a related item) is `useList` with
  `meta: ['aggregates']`, `aggregate` and `group` in an extension. A sum or an average of
  an amount or a quantity with a fraction is of a `DecimalField` (the format `decimal` in
  the contract, S049), and the route set of the entity filters by the field (S050). The
  core answers 400 `ERR_AGGREGATE` over more groups than `BAZIS_API_AGGREGATE_GROUPS_MAX`
  (1000 by default, `BS_BAZIS_API_AGGREGATE_GROUPS_MAX`): a chart by day or by week groups
  the days of its periods, so a long one is by `month` or has a smaller `last`. The axis of
  a chart is in the time zone of the backend (`TIME_ZONE`), not of the browser. A tile of a
  `value` takes the whole row of a phone, and an average shows the decimal places of its
  field (`decimal_places`, `places` of the contract): no extension for them.
- A field of the payload of a transit or of the body of a custom action has a type that a
  form asks for: an amount or a quantity with a fraction is a `Decimal` (as a `DecimalField`
  of a model, typed with a point or the comma of the language and sent as `"2.5"`), else a
  text, a number, a date, a choice, the id of a related item or a list of them; another
  union, an object or another array is typed as JSON (S054). A decimal in an extension or a
  custom screen is the `FieldInput` of its field (its `DecimalInput`), never an input or a
  parse of your own. In the spec the type of such a decimal is `string` (`number` is
  allowed too, P017), and an Enum or a Literal of strings is `string` as well, never `json` (an `IntEnum` is `integer`).
- The YAML of the specs follows YAML 1.2: a text with `: ` or a special first character
  goes in quotes (`summary: "Tasks: of the team"`), and `summary` of `product` is a text
  or a map of the languages of the product (`{en: ..., ru: ...}`).
- A file that a scenario uploads (`upload`) is a file of `frontend/e2e/fixtures/`, which
  `npm run format` leaves byte for byte: put it there, never in a generated directory.
- With bazis-authing, the login screen of the template offers Google only with
  bazis-authing 2.8 or newer (the `POST` of its init): `check` warns of the `GET` of an older
  one (C005): upgrade bazis-authing to 2.8.0 (it requires bazis 2.19) and export the
  contract again. The template is same-site with the API through its proxy of `/api`; a
  login screen of your own opens Google with `loginInWindow` of
  `frontend/src/app/session.ts`.
- The screens are done when `bazis_front shots` (the backend running as for `npm run e2e`)
  reports no error in `frontend/.scratch/shots/report.json` and its screenshots pass the
  checklist of "The visual check" of the guide (without a shell, `front_screenshot` shows
  the `file` of a shot of the report, a tall one in parts, each `part` of which is looked
  at): fix the specs, the screens, the design or
  the backend and take them again, at most three rounds. Each warning of the report is
  fixed as well, or listed in Left for you with its screen, its code and why it stays. The
  errors left after the third are `shot_errors` of `front_status` (not stale): the work is
  not done while it has one that Left for you does not list with its screen, its code and
  why it is left. The screenshots are looked at, one of each screen while the limit of the
  client lasts (`front_screenshot` gives 40 images of a run), the screens with errors or
  warnings and the main ones first, then the others: the screens not looked at go to
  Left for you in one line, their number and their ids, not one by one with a reason.
  Without a shell, `reviewed` of `front_status` counts those looked at whole with
  `front_screenshot` and names the others (`not_looked`), and the work is not done while it
  names one that that line does not list. Never commit `frontend/.scratch/`.
- Never edit `contract/`, `frontend/src/bazis/generated/`, `frontend/src/screens/generated/`,
  `frontend/e2e/generated/`, the
  copies of `frontend/src/bazis/client/`, `frontend/src/bazis/react/`,
  `frontend/src/bazis/i18n/`, `frontend/e2e/bazis/`, `frontend/bazis-front.lock.json` or
  `frontend/.bazis/`: generate them again with the commands, and wrap the copies in the
  product code (the texts of the product are in its own dictionaries).
- The backend decides the permissions (bazis-permit): never encode roles or permission
  rules in the frontend. The screens use the tokens of the design, never literal colors.
- The users who do not log in (the guests of a public site) are an anonymous role of
  `spec/product.yaml` (`anonymous: true`, without a `test_user`). Its permit role is
  `Role(for_anonymous=True)` with permissions of the selector `all` only (anonymous users
  match no other), or none when the guests use only the public actions (no `access`
  then): never create a role for anonymous users that views the entities when the guests
  do not read them, it opens their data to anyone (P030). A screen is public when its `roles` lists that role, and only
  then: `bazis_front screens` routes it outside the session (`PUBLIC_ROUTES`), never a
  route or a layout of your own in `frontend/src/app/router.tsx`. Every anonymous role is
  in `roles` of a screen (S047), a scenario of the role opens only public screens (P035)
  and a public screen leads only to public screens (S045).
- A guest only reads through the routes of the entities: bazis-permit refuses him every
  create, change and deletion, so a public screen has no form of the items, deletion, bulk
  action or move (S044). He writes only through a custom action of the route set declared
  `public=True` (S046), limited by a throttle (`BAZIS_THROTTLE_PUBLIC`, or a `throttle` of
  its own), whose code restricts what it writes and returns; a transit of a guest is a
  route set of its own with `action_transit =
  route_declare(StatusyRouteSetBase.action_transit, public=True)`. `run_doctor` names an
  action that declares neither `access_action` nor `public` (`permit.W007`) and one whose
  `access_action` a role for anonymous users has (`permit.W008`): fix both. The sign-up or
  the request of a guest is the form of its action on a public screen ("The form of a
  custom action" of the guide): name the properties of the body as the fields of the
  entity (a relationship is then the picker of its items, which the anonymous role must
  view, S052; a title is translated), label the others with `labels`, and show what the
  action returns (a number) with `result`, `{title, message}`, whose `{name}` are the
  properties of its `response_model` (S053). Its end-to-end test calls the action at every
  run: give the throttle room for the runs of the tests (`20/hour` answers 429 after a few
  runs), and say in Left for you that it is the only guard of the form against spam. Set
  `BS_BAZIS_WS_ANONYMOUS_COMMON_CHANNEL=true` only when what the common channel says is
  public. No package registers a user or resets a password: a guest who needs an account
  is given one, say so in Left for you.
- After `pip install -U bazis-front`, `bazis_front update` merges the copies and the
  template: a conflict of `frontend/src/app/router.tsx` is resolved by taking the file of
  the template, its pristine copy `frontend/.bazis/base/template@<version>/src/app/router.tsx`,
  and applying the changes of the product to it again (taking the side of the product
  alone drops the public routes, S048). A product of bazis-front 0.3 that routed the
  screens of its guests by hand lists their anonymous role in `roles` of their specs and
  removes its routes and layout. Then `contract`, `check`, `screens`, `e2e` and `shots`
  again: after the update to 0.7 the contract is of format 10, and `check` reports C002 until
  `bazis_front contract` exports it again; with the capability `statusy`, the frontend needs
  `bazis-statusy>=2.13.0` (C004, `front.W006`). A custom screen that only sends a custom
  action becomes the form of the action (delete `frontend/src/screens/<id>/` and its own
  end-to-end tests, remove `custom: true`), an extension that only widened a tile of a
  sum on a phone is removed, a screen with the id `more` is renamed (S055), and code that
  read `CAPABILITIES.authing.token_param` (gone in format 10) uses `loginInWindow`.
  `useTransitsOf` and the message
  `board.no_moves` are gone since 0.5: never write code on them (the transits of the items
  of a list are `meta: ['for_transit']` of the list, those of an item `useTransits`).
- The frontend is in the languages of the backend (`languages` and `language` of
  `spec/product.yaml` list exactly the codes of `BS_LANGUAGES` and the one of
  `BS_LANGUAGE_CODE`, only the language of the request, P029): a text of a spec is a map
  of those languages or a key of the dictionaries, and every text of an extension or a
  custom screen goes through `t()` with a key in the dictionaries of the product,
  `frontend/src/i18n/<language>.ts`, one for each language (listed in
  `frontend/src/i18n/index.ts`); never a text in the JSX.
- The contract is exported from the migrated database, with the permit roles and the
  statuses and transits of the workflows that `migrate` applied from their declarations
  (the rules above). The test
  data of the end-to-end tests is the e2e data command recommended by bazis-front,
  `.venv/bin/python manage.py e2e_data`: on top of the migrations it creates only a user
  per `test_user` of the roles, with its role and the password of the environment
  variable `E2E_PASSWORD`, and the records the scenarios need (the items they open). It
  can run again (it sets the passwords again). It only adds: never remove the test users
  or the records it made, with an option of your own (`--clean`) or a delete, also at the
  end of a phase: they stay for the user to log in and for the next `npm run e2e`.
  Its dates are relative to the day of the
  run (`timezone.now() + timedelta(days=3)`, its date in UTC, the day that `expectDay`
  counts, never `timezone.localdate()`; some of them in the current month and the next
  days), never fixed (`2030-03-04`): the calendars, the boards and the dashboards of the
  screenshots show its records.
- The servers use the ports of the project on this machine, `.bazis/ports.json`
  (`backend`, `frontend`, `e2e`), never the defaults 8000 and 5173 that other projects
  use. After `bazis_front init` write `BAZIS_API_URL=http://localhost:<backend>` in
  `frontend/.env.local` (not committed), which `npm run dev` and `npm run e2e` read; the
  dev server is `npm run dev -- --port <frontend>`.
- After a change of the frontend run `npx tsc --noEmit` in `frontend/` and fix what it
  reports; format only with `npm run format` (the prettier pinned in its `package.json`,
  which leaves the copies alone), never `npx prettier`. After the last edit of any file of
  `frontend/` (also of an extension or a custom screen, also one made to fix a later check)
  run `npm run format` and `npm run lint` again: a file edited after them is unformatted.
- The final checks of the frontend: `front_check` without errors, `front_status` with
  nothing stale and no `shot_errors` (or each of them in Left for you, after the three
  rounds of the screenshots), and in `frontend/` `npm run format`, `npx tsc --noEmit`,
  `npm run lint`, `npm test`, `npm run build`, `bazis_front screens --check` and `bazis_front shots
  --check`; after a change of the specs
  or the screens also `bazis_front e2e` and `npm run e2e` against the running backend:
  migrate, run `e2e_data`, start `.venv/bin/uvicorn <project package>.main:app --port
  <backend>` in the background, run `E2E_PORT=<e2e> E2E_PASSWORD=<the same password> npm
  run e2e` and `bazis_front shots`, then stop the backend.
  A test that fails only sometimes gets one attempt at a fix, then goes to Left for you.
- Node.js with npm is needed by `npm install`, the TypeScript of the contract
  (`schema.d.ts`), the build and the tests of the frontend, and the contract by a migrated
  database. Without them do the other steps and say which ones did not run.
"""
