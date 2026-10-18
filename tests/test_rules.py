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

from bazis.contrib.mcp import prompts, scaffold
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
                 'Every screen of the last report is looked at, one of its screenshots at least',
                 '`reviewed` of `front_status` counts those looked at whole with `front_screenshot` '
                 'and names the others (`not_looked`)',
                 '`front_status` with nothing stale and no `shot_errors` (or each of them in '
                 'Left for you, after the three rounds of the screenshots)',
                 '`npm run build`, `bazis_front screens --check` and `bazis_front shots --check`',
                 'npm run e2e` and `bazis_front shots`, then stop the backend'):
        assert text in rules, text
    assert '--port 8000' not in rules


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
    assert named == ['run_doctor', 'front_check', 'front_status', 'frontend/', 'npx tsc --noEmit',
                     'npm run lint', 'npm test', 'npm run build', 'bazis_front screens --check',
                     'bazis_front shots --check', 'npm run e2e', 'bazis_front shots']
    for name in named:
        assert f'`{name}`' in frontend or f'`{name}`' in rules, name
