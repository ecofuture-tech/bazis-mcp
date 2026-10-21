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

import re

from bazis.contrib.mcp import catalog, prompts, scaffold
from bazis.contrib.mcp.rules import FRONTEND_RULES, RULES


def test_frontend_rules():
    for text in ('front_check', 'front_status', 'front_catalog', 'package_guide("bazis-front")',
                 'frontend/AGENTS.md', 'e2e_data', 'E2E_PASSWORD', 'npm run e2e',
                 'frontend/src/bazis/generated/', 'Node.js'):
        assert text in FRONTEND_RULES
    # the ports of the project, never the defaults; one attempt at a flaky test
    rules = ' '.join(FRONTEND_RULES.split())
    for text in ('`.bazis/ports.json`', 'never the defaults 8000 and 5173',
                 '`BAZIS_API_URL=http://localhost:<backend>` in `frontend/.env.local`',
                 '`npm run dev -- --port <frontend>`', '--port <backend>',
                 '`E2E_PORT=<e2e> E2E_PASSWORD=<the same password> npm run e2e`',
                 'one attempt at a fix, then goes to Left for you',
                 'read its introduction',
                 # the final checks of the frontend, once; `tsc` after a change
                 'After a change of the frontend run `npx tsc --noEmit`',
                 'The final checks of the frontend: `front_check` without errors, '
                 '`front_status` with nothing stale', '`npm run build`',
                 # what is never edited, also the copy of the dictionaries of the components
                 '`frontend/src/bazis/i18n/`', '`status` only shows its state',
                 # a formatter of another version and style rewrites the files (round 3, 8)
                 'format only with `npm run format`', 'never `npx prettier`',
                 # the screenshots: their rounds until the report is clean, and their check
                 '`init`, `contract`, `check`, `add`, `design`, `screens`, `e2e`, `shots`, `update`',
                 # the screens are generated: the specs, the extensions and the custom screens
                 'The screens are generated from their specs, never written as TSX',
                 'run `bazis_front screens` after every change of `spec/`',
                 '(`extend: true`, `frontend/src/screens/<id>/extend.tsx`)',
                 '(`custom: true`, `frontend/src/screens/<id>/index.tsx`)',
                 'never into `frontend/src/screens/generated/`', '(`front.W010`)',
                 'leave `--force`, which drops it, to the user',
                 'Never edit `contract/`, `frontend/src/bazis/generated/`, `frontend/src/screens/generated/`',
                 'a text of a spec is a map of those languages or a key of the dictionaries',
                 # the menu of a larger product, the screenshots without a shell, the dates of
                 # the test data that the calendars and the boards show
                 'With more than five links, the navigation is `navigation` of `spec/product.yaml` with '
                 'groups of related screens (`{group, title, items}`)', 'an `icon` (a name of lucide, D013)',
                 'without a shell, `front_screenshot` shows the `file` of a shot of the report',
                 'a tall one in parts, each `part` of which is looked at',
                 'Its dates are relative to the day of the run (`timezone.now() + timedelta(days=3)`',
                 'the day that `expectDay` counts, never `timezone.localdate()`', 'never fixed (`2030-03-04`)',
                 'The screens are done when `bazis_front shots`',
                 'no error in `frontend/.scratch/shots/report.json`', '"The visual check"',
                 'at most three rounds', 'Never commit `frontend/.scratch/`',
                 # the errors left in the report are not stale, yet no work is done with one
                 # that Left for you does not list
                 'The errors left after the third are `shot_errors` of `front_status` (not stale)',
                 'the work is not done while it has one that Left for you does not list',
                 # the warnings are looked into and every screen is looked at (mcp6: 5 of 16
                 # screens looked at, 9 warnings left unread)
                 'Each warning of the report is fixed as well, or listed in Left for you with '
                 'its screen, its code and why it stays',
                 'The screenshots are looked at, one of each screen while the limit of the '
                 'client lasts (`front_screenshot` gives 40 images of a run), the screens '
                 'with errors or warnings and the main ones first',
                 'the screens not looked at go to Left for you in one line, their number and '
                 'their ids, not one by one with a reason',
                 'Without a shell, `reviewed` of `front_status` counts those looked at whole with '
                 '`front_screenshot` and names the others (`not_looked`)',
                 '`front_status` with nothing stale and no `shot_errors` (or each of them in '
                 'Left for you, after the three rounds of the screenshots)',
                 '`npm run build`, `bazis_front screens --check` and `bazis_front shots --check`',
                 'npm run e2e` and `bazis_front shots`, then stop the backend',
                 # the formatter in the final checks, and again after the last edit of a file
                 'and in `frontend/` `npm run format`, `npx tsc --noEmit`, `npm run lint`',
                 'After the last edit of any file of `frontend/`',
                 'run `npm run format` and `npm run lint` again',
                 # the test data stays: no clean-up of the agent (round 7)
                 'It only adds: never remove the test users or the records it made',
                 '(`--clean`)', 'they stay for the user to log in'):
        assert text in rules, text
    assert '--port 8000' not in rules
    assert rules.index('`npm run format`, `npx tsc --noEmit`') < rules.index('`npm run lint`, `npm test`')


def test_rules_of_the_public_screens():
    """
    The guests of a product (bazis-front 0.4.0): an anonymous role whose permit role is for
    anonymous users with the selector `all`, the public screens declared by their `roles`
    and routed by `screens`, never by hand; a guest writes only through a custom action
    declared `public=True` under a throttle (bazis-permit refuses him the routes of the
    entities); a router changed before 0.4.0 is replaced by that of the template.
    """
    rules = ' '.join(FRONTEND_RULES.split())
    for text in ('an anonymous role of `spec/product.yaml` (`anonymous: true`, without a `test_user`)',
                 '`Role(for_anonymous=True)` with permissions of the selector `all` only',
                 # no role that opens the entities to guests who use only the public actions
                 'or none when the guests use only the public actions (no `access` then)',
                 'never create a role for anonymous users that views the entities when the guests '
                 'do not read them, it opens their data to anyone (P030)',
                 'A screen is public when its `roles` lists that role, and only then',
                 '(`PUBLIC_ROUTES`), never a route or a layout of your own in `frontend/src/app/router.tsx`',
                 'A guest only reads through the routes of the entities',
                 'a public screen has no form of the items, deletion, bulk action or move (S044)',
                 'declared `public=True` (S046), limited by a throttle (`BAZIS_THROTTLE_PUBLIC`',
                 'route_declare(StatusyRouteSetBase.action_transit, public=True)',
                 '`permit.W007`', '`permit.W008`', 'BS_BAZIS_WS_ANONYMOUS_COMMON_CHANNEL=true',
                 'a guest who needs an account is given one, say so in Left for you',
                 # the router of a product of bazis-front 0.3: the template, never the side of
                 # the product alone, and no route of the guests by hand
                 'a conflict of `frontend/src/app/router.tsx` is resolved by taking the file of the template',
                 '`frontend/.bazis/base/template@<version>/src/app/router.tsx`',
                 'taking the side of the product alone drops the public routes, S048',
                 'lists their anonymous role in `roles` of their specs and removes its routes and layout'):
        assert text in rules, text
    steps = ' '.join(prompts.FRONTEND_STEPS.split())
    assert 'the users who do not log in are an anonymous role, listed in `roles` of each screen' in steps


def test_rules_of_the_dashboards():
    """
    The numbers of the tiles and the charts are the aggregates of the core (bazis-front
    0.5.0, bazis 2.17.0), never counted in the browser, and what they cannot say is the
    aggregates of a list in an extension: a decimal field for a sum or an average, a field
    the route set filters by, the setting that limits the groups (a chart by week groups its
    days) and the time zone of the axis; after the update the contract is exported again
    with bazis-statusy 2.13, and the removed hook and message are not used.
    """
    rules = ' '.join(FRONTEND_RULES.split())
    for text in ('The numbers of a dashboard are the aggregates of the core (`meta=aggregates`)',
                 'the `value` of a tile (`{sum: <field>}`, `avg`, `min`, `max`) or of a chart (`sum`, `avg`)',
                 'Never count or sum items in the browser',
                 "is `useList` with `meta: ['aggregates']`, `aggregate` and `group` in an extension",
                 '`DecimalField` (the format `decimal` in the contract, S049)',
                 'the route set of the entity filters by the field (S050)',
                 '400 `ERR_AGGREGATE` over more groups than `BAZIS_API_AGGREGATE_GROUPS_MAX` '
                 '(1000 by default, `BS_BAZIS_API_AGGREGATE_GROUPS_MAX`)',
                 'a chart by day or by week groups the days of its periods, so a long one is by '
                 '`month` or has a smaller `last`',
                 'The axis of a chart is in the time zone of the backend (`TIME_ZONE`), not of the browser',
                 'until `bazis_front contract` exports it again',
                 'with the capability `statusy`, the frontend needs `bazis-statusy>=2.13.0` (C004, `front.W006`)',
                 '`useTransitsOf` and the message `board.no_moves` are gone since 0.5: never write code on them'):
        assert text in rules, text
    assert 'a longer `bucket`' not in rules


def test_rules_of_the_forms_of_the_actions():
    """
    bazis-front 0.6.0: the form of a guest is the spec of the form of a public custom action
    (its fields named as those of the entity, the result with the answer), its throttle leaves
    room for the end-to-end tests, a decimal is typed by the form (`FieldInput` in code), an
    average shows the decimal places of its field, the top bar folds its links into a menu no
    screen is named as, and the link of the form requires its action; the update replaces
    the custom code that the specs now say.
    """
    rules = ' '.join(FRONTEND_RULES.split())
    for text in ('is a spec too, `primitive: form` with `form.action`, never a custom screen',
                 'name the properties of the body as the fields of the entity',
                 'which the anonymous role must view, S052', 'label the others with `labels`',
                 '`result`, `{title, message}`, whose `{name}` are the properties of its `response_model` (S053)',
                 'give the throttle room for the runs of the tests (`20/hour` answers 429',
                 'it is the only guard of the form against spam',
                 'typed with a point or the comma of the language and sent as `"2.5"`',
                 'is typed as JSON (S054)',
                 'is the `FieldInput` of its field (its `DecimalInput`), never an input or a parse of your own',
                 'A tile of a `value` takes the whole row of a phone',
                 'an average shows the decimal places of its field (`decimal_places`, `places` of the contract)',
                 'into its menu `nav:more` (More) by itself',
                 'never drop or hide links for their number',
                 'never give a screen the id `more`, the mark of that menu (S055)',
                 'give it no `requires` (S030)',
                 'A custom screen that only sends a custom action becomes the form of the action',
                 'a screen with the id `more` is renamed (S055)'):
        assert text in rules, text


def test_rules_of_the_login_with_google_and_the_history_of_the_transits():
    """
    bazis-authing 2.8 starts the Google login of a browser with a POST that binds a one-time
    ticket to the browser (the page same-site with the API, the store token in no URL), which
    bazis-front 0.7.0 offers alone (C005 for the GET of an older one, the contract of format
    10 without `token_param`); bazis-statusy 2.15 keeps the payload of a transit in its
    history, read with the permission `history`, and names its payload type by a classmethod.
    """
    rules = ' '.join(RULES.split())
    for text in ('the payload type of a transit is the classmethod `Model.get_transit_payload_type(transit)` '
                 '(bazis-statusy 2.15; 2.14 does not call it, its payload type is `item.transit_payload_type(transit)`): '
                 'override it, never `transit_payload_type` of an item (its old name)',
                 '`GET /{item_id}/status_history/` (bazis-statusy 2.15): grant `history` only to the roles '
                 'that may read the payloads',
                 '`Annotated[..., NOT_IN_HISTORY]` (`bazis.contrib.statusy.schemas`',
                 'never inside a list or a nested model',
                 'The calculated field `status_history` is the compact history under `view`, without the payloads',
                 'the Google login of a browser is `POST /google-auth-init/` with the store token as the bearer token',
                 'never a URL with the store token',
                 'so the page is same-site with the API (an API of another origin also answers CORS with credentials)'):
        assert text in rules, text
    frontend = ' '.join(FRONTEND_RULES.split())
    for text in ('offers Google only with bazis-authing 2.8 or newer',
                 '`check` warns of the `GET` of an older one (C005): upgrade bazis-authing to 2.8.0 (it requires bazis 2.19)',
                 'a login screen of your own opens Google with `loginInWindow`',
                 'after the update to 0.7 the contract is of format 10',
                 'code that read `CAPABILITIES.authing.token_param` (gone in format 10) uses `loginInWindow`'):
        assert text in frontend, text
    assert 'format 9' not in frontend and 'format 8' not in frontend


def test_rules_of_bazis_front_0_8_0():
    """
    The specs of a product follow YAML 1.2, a decimal or an Enum of a payload is a `string`
    (P017), the files of an upload are in `e2e/fixtures/`, the top bar is cut by links, and
    the users of the labels are a route of the project (P036).
    """
    frontend = ' '.join(FRONTEND_RULES.split())
    for text in ('a text with `: ` or a special first character goes in quotes',
                 '`summary` of `product` is a text or a map of the languages',
                 'the type of such a decimal is `string` (`number` is allowed too, P017), and an Enum '
                 'or a Literal of strings is `string` as well, never `json` (an `IntEnum` is `integer`)',
                 'a file of `frontend/e2e/fixtures/`',
                 'from the first that does not fit',
                 'a group is shared by the row and the menu'):
        assert text in frontend, text
    assert '`front_check` warns P036' in ' '.join(RULES.split())


def test_rules_of_the_files_of_guests_the_exports_and_the_flows_of_several_users():
    """
    bazis-uploadable 2.8 takes the files of guests (service1: photos as data URLs in JSON, 239
    lines of a custom screen), bazis 2.21 labels the choices of a body by `TextChoices`, and
    bazis-front 0.9 says in the specs the public form with files, the export of a file and a
    scenario of several users; an amount of a notification is formatted in the language, the
    specs are checked by the tool, and the outputs are removed by `clean_project`.
    """
    rules = ' '.join(RULES.split())
    for text in ('the anonymous uploads of bazis-uploadable 2.8, never a file in JSON',
                 '`BS_BAZIS_FILE_UPLOAD_ANONYMOUS=true` with `BS_BAZIS_FILE_UPLOAD_MAX_SIZE`',
                 'the body takes `list[UploadedFileId]`, the tokens the uploads answered',
                 '`FileUpload.objects.anonymous(tokens)` for a guest, by id among his own for a user',
                 '`uploadable_clean_anonymous` in cron', '`client_max_body_size`', '`X-Forwarded-For`',
                 '`number_format(amount, decimal_pos=2, force_grouping=True)` (`django.utils.formats`)',
                 '`clean_project` removes it with the outputs of the builds and the tests'):
        assert text in rules, text
    frontend = ' '.join(FRONTEND_RULES.split())
    for text in ('check the specs with `front_check`', 'never `bazis_front check` through `run_command`',
                 'A choice of a body is the `TextChoices` of the model (its labels, bazis 2.21), never a `Literal` (S058)',
                 'a long text has no `max_length`',
                 'The specs say what was code of your own',
                 'the files of a public form (`FilesField`) with the anonymous uploads on (S057)',
                 'an export (the form of an action that answers a file, `access_action` view, the rows of '
                 'its `restrict_queryset`; bazis-bg only for a long one)',
                 '`as: <role>`', '`remember` of what the server made, a number or an id, never the echo '
                 'of a text typed', 'After the update to 0.9 (a contract of format 11) a custom screen or test of your '
                 'own that did them becomes the spec'):
        assert text in frontend, text


def test_the_codes_of_the_rules_are_those_of_bazis_front():
    """
    Every code of `check` that the rules of the frontend name is one of the table of the
    guide of bazis-front in the catalog, the guide that the agent reads.
    """
    guide = catalog.catalog()['bazis-front']['agents_md']
    named = set(re.findall(r'\b([CDPSV]\d{3})\b', FRONTEND_RULES))
    assert {'C002', 'C004', 'C005', 'P030', 'P035', 'S030', 'S044', 'S045', 'S046', 'S047', 'S048',
            'S049', 'S050', 'S052', 'S053', 'S054', 'S055', 'S057', 'S058'} <= named
    for code in named:
        assert f'| `{code}` |' in guide, code


def test_the_declarations_and_the_test_data_are_said_once():
    """
    Roles, statuses and transits are declared in `roles.py` and `workflow.py` (the rules of
    every task); the contract is exported after migrate, and `e2e_data` only adds the test
    users and the records of the scenarios (the rules of the frontend). The steps repeat
    neither.
    """
    rules = ' '.join(FRONTEND_RULES.split())
    steps = ' '.join(prompts.FRONTEND_STEPS.split())
    assert 'statuses and transits of the workflows that `migrate` applied' in rules
    assert 'the e2e data command recommended by bazis-front' in rules
    assert 'it creates only a user per `test_user`' in rules
    for text in (rules, steps):
        assert 'data migration' not in text and '`roles.py`' not in text
    assert 'e2e_data' not in steps


def test_the_rules_follow_the_released_stack():
    """
    The rules of every task and the skeleton use the released stack: the declarations of
    bazis-permit and bazis-statusy applied by migrate, the pytest plugin of bazis-test-utils
    (no hand-written fixture of the triggers or of the declared data), `notify()` of
    bazis-ws, and the database checks of `run_doctor`.
    """
    rules = ' '.join(RULES.split())
    for text in ('`<app>/roles.py`', '`<app>/workflow.py`', 'never created by data migrations',
                 'keeps those migrations as history without effect (`operations = []`',
                 '`django_db_setup`', 'notify(users, lambda user: notification(...))',
                 'publish_changed(item)', "router.register('bazis.contrib.ws.router')",
                 # with bazis-notify a notification is its own, never a second message
                 'Notify a user with `notify` of bazis-notify when the project has it',
                 'never a second message of bazis-ws', 'without bazis-notify, with `notify(users',
                 '`permit.W005`', '`statusy.W003`', '`bazis.database`',
                 # a task of the backend never takes the screenshots for run_doctor
                 '`front.W009` (the screenshots of the frontend not taken, or their errors) in a '
                 'task that changes no screen, spec or design of the frontend'):
        assert text in rules, text
    assert 'clear_cache' not in rules and 'data migrations set' not in rules

    conftest = scaffold.CONFTEST_PY
    assert 'def django_db_setup' not in conftest and 'pgtrigger install' not in conftest
    assert 'plugin of bazis-test-utils' in conftest and '`bazis_declared`' in conftest
    assert 'data migration' not in scaffold.AGENTS_MD_FRONTEND


def test_rules_of_the_packages_and_of_what_the_agent_leaves():
    """
    The minimum of a package is its installed release, in numbers; temporary files stay in
    the project, secrets stay out of the messages, the database of `bazis new` is kept (and
    one the agent creates is reported; one with data is not migrated, the one chosen
    instead is); the summary has fixed sections, with the gaps of the guides.
    """
    rules = ' '.join(RULES.split())
    for text in ('then give it its installed release as the minimum: `<name>>=X.Y.Z`',
                 'without a suffix such as `.post1.dev3`',
                 'A requirement that the task gives is written as it is', 'never lower a minimum',
                 # nothing uninstalls: a package no longer used is left to the user
                 'stays installed in `.venv` (nothing here uninstalls)',
                 '`.venv/bin/python -m pip uninstall <name>` for the user, never as a step of yours',
                 '`.scratch/`', '`/tmp`',
                 'also of the test users', '`E2E_PASSWORD`',
                 'The database of `.env` is created by `bazis new`', 'Never drop or recreate it',
                 'never delete or generate again the applied ones', 'CREATE EXTENSION postgis',
                 'already has data of another project or could not be inspected',
                 'it is not ready', 'never migrate it',
                 # a database chosen instead of the taken ones and set in `.env` is ready
                 'When it says that databases were taken and left as they are and that `.env` '
                 'sets another one, only the taken ones are not ready (never change them): '
                 'the one `.env` sets is the database of the project, migrate it.',
                 'Your last message is a short summary with exactly these section headings',
                 'none left out and none of your own instead',
                 'Built (', 'Packages (', 'Run (', 'Outside the files (', 'such as the database',
                 'Left for you (', 'Guide gaps (',
                 'Run the final checks once, after the last change',
                 'run again only the checks that failed',
                 # `run_doctor` after a change, the tests among the final checks
                 'After a change run `run_doctor`',
                 'The final checks are `run_doctor`, the tests and, with a frontend, the checks of its rules'):
        assert text in rules, text
    assert 'catalog_version' not in rules
    assert '.scratch/' in scaffold.GITIGNORE.splitlines()


def test_rules_of_the_guides():
    """
    A guide is read by its introduction and the sections a step needs; the sources of the
    packages only for a fact the guide lacks, named in the summary.
    """
    rules = ' '.join(RULES.split())
    for text in ('read the introduction, then a section (`package_guide(name, section)`) '
                 'when a step needs it, never all of them in advance',
                 'do not read the sources of its packages',
                 '`frontend/src/bazis/` and `frontend/e2e/bazis/`',
                 'Only when the guide lacks a fact you need, read the source',
                 'name the gap in "Guide gaps" of the summary', '`guide_search`'):
        assert text in rules, text


def test_rules_of_the_points_and_of_the_routes_that_restrict_themselves():
    """
    A location is a point of the core, near and sorted by the distance by the core; a route
    that restricts its objects itself is not declared public (bazis-permit 2.10).
    """
    rules = ' '.join(RULES.split())
    for text in ('`PointField`', '`geography=True`', 'never two `FloatField`s',
                 '`filter=<field>__near=<lon>,<lat>,5km`', '`sort=<field>__distance(<lon>,<lat>)`',
                 'never by a distance computed in Python or SQL of your own',
                 '`point_distance`/`point_within` of `bazis.core.utils.geo`',
                 'needs no `permit_public = True`', '`FileUploadRouteSet` of bazis-uploadable',
                 'applies it in its `get_queryset`',
                 'the routes of bazis-bg', 'only on a route whose data is public'):
        assert text in rules, text


def test_rules_of_the_languages_and_the_tests():
    rules = ' '.join(RULES.split())
    for text in ('gettext_lazy', 'English msgids', 'locale/<language>/LC_MESSAGES/django.po',
                 'manage.py bazis_messages`, run in the project root', '`locale/translations.json`',
                 '`apply locale/translations.json --check`', 'Keep the JSON file in the project',
                 'Never write a script that edits the `.po` files',
                 'never run `makemessages` or `compilemessages` yourself',
                 'Remove from the file the msgids that `apply` reports as `unknown`',
                 'needs GNU gettext', 'never work around it',
                 'bazis.W004', '`<project>/translations.py`', '`gettext_noop`',
                 'the catalog of the project wins', 'bazis.W005',
                 'never flush', 'cache.clear()', "cache.delete_pattern('*')",
                 'the flush applies the declarations again', 'bazis.contrib.users.token',
                 'users.E002', 'UserLanguageMixin'):
        assert text in rules, text
    assert 'makemessages -l' not in rules and 'django-admin compilemessages' not in rules
    frontend = ' '.join(FRONTEND_RULES.split())
    for text in ('t()', 'frontend/src/i18n/<language>.ts', '`languages` and `language`'):
        assert text in frontend, text


def test_rules_of_the_coverage_of_the_tests():
    """
    The tests cover the description (its rules, its roles both ways, parallel requests for
    every limit and uniqueness, at least 10), with `parallel` of bazis-test-utils or the
    threads it stands for in an older release; the step of the backend names them.
    """
    rules = ' '.join(RULES.split())
    for text in ('a test for every rule and invariant it states', 'a limit, a uniqueness, a rule of a status',
                 'one of what it may not (403, 404 or 422)', 'its `test_user` in a spec',
                 'for an anonymous role, a request without a token: 401 or 403',
                 'for every limit and uniqueness a test of parallel requests',
                 '`@pytest.mark.django_db(transaction=True)`', '`parallel` of `bazis_test_utils` when its guide has it',
                 '`threading.Barrier`', 'each closing its database connections',
                 'the answers that succeed are 201 or 200 (a change or a transit)',
                 'the others 409 or 422, never a 5xx', 'At least 10 tests',
                 'none of the framework itself'):
        assert text in rules, text
    assert 'Write tests for the behavior you add' not in rules
    steps = ' '.join(prompts.FRONTEND_STEPS.split())
    assert 'the tests and the translations that the rules require' in steps
    assert 'at least 10' not in steps.lower()



def test_rules_of_an_agent_without_a_shell():
    """
    The commands of the rules run through the tools of the MCP server when the agent has no
    shell; bazis-cli, whose agent has one, keeps the same rules.
    """
    rules = ' '.join(RULES.split())
    for text in ('Without a shell, with the tools of the MCP server `bazis` only',
                 'run the commands of these rules with `run_command`',
                 '`.venv/bin/python manage.py <command>` is `run_command("manage", ["<command>"])`',
                 '`start_server` and `stop_server`', '`add_packages`',
                 'look at the screenshots of the frontend with `front_screenshot`'):
        assert text in rules, text


def test_a_next_change_ends_with_all_the_final_checks():
    """
    A change asked after the first in the conversation (a resumed session, without a task)
    runs the whole round of the final checks, not only those of what it changed (mcp6:
    neither vitest nor the build nor the lint after the second change); a task of a change of
    a product names them, each one a final check of the rules of the frontend.
    """
    rules = ' '.join(RULES.split())
    assert ('A next change asked in the conversation ends with the whole round again, also the '
            'checks of the parts it did not change') in rules

    change = ' '.join(prompts.frontend_change('the change').split())
    checks = change.split('also the checks of what the change does not touch: ', 1)[1]
    frontend = ' '.join(FRONTEND_RULES.split()).split('The final checks of the frontend: ', 1)[1]
    named = re.findall(r'`([^`]+)`', checks)
    assert named == ['run_doctor', 'front_check', 'front_status', 'frontend/', 'npm run format',
                     'npx tsc --noEmit', 'npm run lint', 'npm test', 'npm run build', 'bazis_front screens --check',
                     'bazis_front shots --check', 'npm run e2e', 'bazis_front shots']
    for name in named:
        assert f'`{name}`' in frontend or f'`{name}`' in rules, name
