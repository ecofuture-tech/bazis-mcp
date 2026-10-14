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
                 'format only with `npm run format`', 'never `npx prettier`'):
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
                 '`permit.W005`', '`statusy.W003`', '`bazis.database`'):
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
    one the agent creates is reported); the summary has fixed sections, with the gaps of
    the guides.
    """
    rules = ' '.join(RULES.split())
    for text in ('then give it its installed release as the minimum: `<name>>=X.Y.Z`',
                 'without a suffix such as `.post1.dev3`',
                 'A requirement that the task gives is written as it is', 'never lower a minimum',
                 '`.scratch/`', '`/tmp`',
                 'also of the test users', '`E2E_PASSWORD`',
                 'The database of `.env` is created by `bazis new`', 'Never drop or recreate it',
                 'never delete or generate again the applied ones', 'CREATE EXTENSION postgis',
                 'already has data of another project or could not be inspected',
                 'it is not ready', 'never migrate it',
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

