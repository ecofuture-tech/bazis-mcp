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

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from bazis.contrib.mcp import scaffold
from bazis.contrib.mcp.scaffold import node_problem

from .support import TEST_POSTGRES, database_exists, drop_databases, make_venv


@pytest.fixture(autouse=True)
def released_frontend(monkeypatch):
    """
    bazis-front is that of PyPI unless a test says otherwise.
    """
    monkeypatch.delenv(scaffold.FRONTEND_REQUIREMENT_ENV, raising=False)


def test_package_name(tmp_path):
    assert scaffold.package_name(tmp_path / 'My Shop-API') == 'my_shop_api'
    assert scaffold.package_name(tmp_path / '42') == 'project_42'
    # names that would hide a module, a keyword or the tests
    assert scaffold.package_name(tmp_path / 'django') == 'django_project'
    assert scaffold.package_name(tmp_path / 'class') == 'class_project'
    assert scaffold.package_name(tmp_path / 'tests') == 'tests_project'


def test_package_name_is_checked_in_the_python_asked(tmp_path, monkeypatch):
    """
    The modules a project package must not hide are those of the Python asked, such as that
    of the project: a Python without Django, as that of bazis-mcp, does not know `django`.
    The current directory, where the project is written, is not one of them.
    """
    bare = make_venv(tmp_path, with_packages=False)
    assert scaffold.valid_package_name('django', bare)
    assert not scaffold.valid_package_name('json', bare)
    assert not scaffold.valid_package_name('django') and not scaffold.valid_package_name('bazis')
    (tmp_path / 'shop').mkdir()
    (tmp_path / 'shop' / '__init__.py').write_text('')
    monkeypatch.chdir(tmp_path)
    assert scaffold.valid_package_name('shop') and scaffold.valid_package_name('shop', bare)


def test_scaffold_refuses_a_bad_package_name(tmp_path):
    with pytest.raises(scaffold.ScaffoldError):
        scaffold.write_files(tmp_path / 'x', 'json')


def manage(directory: Path, *args: str) -> subprocess.CompletedProcess:
    """
    Runs `manage.py` of a project with its own settings only, but the libraries of this
    machine (GDAL, GEOS).
    """
    env = {
        k: v for k, v in os.environ.items()
        if not k.startswith(('BS_', 'DJANGO_')) or k.endswith('_LIBRARY_PATH')
    }
    return subprocess.run(
        [sys.executable, 'manage.py', *args],
        cwd=directory, env=env, capture_output=True, text=True, timeout=300,
    )


def doctor(directory: Path) -> list:
    """
    The warnings and errors of `bazis_doctor` of a project. Its infos are left out: without
    the database, bazis 2.13 says that the database checks were skipped (`bazis.database`).
    """
    done = manage(directory, 'bazis_doctor', '--json')
    assert done.returncode == 0, done.stderr[-3000:]
    return [it for it in json.loads(done.stdout) if it['level'] not in ('info', 'debug')]


def test_scaffold_is_a_working_project(tmp_path):
    """
    The skeleton loads and passes the system checks without a database.
    """
    directory = tmp_path / 'store'
    scaffold.write_files(directory, 'store')

    assert doctor(directory) == []
    assert (directory / '.gitignore').read_text().startswith('.env\n')
    # the temporary files of the agent
    assert '.scratch/' in (directory / '.gitignore').read_text().splitlines()
    assert '`.scratch/`' in (directory / 'AGENTS.md').read_text()
    assert 'BS_SECRET_KEY=' in (directory / '.env').read_text()
    assert json.loads((directory / '.mcp.json').read_text())['mcpServers']['bazis']
    # the files of the project are its own, not those of every project in /tmp
    assert 'BS_MEDIA_ROOT=__BASE_DIR__/media\n' in (directory / '.env').read_text()
    done = manage(directory, 'shell', '-c',
                  'from django.conf import settings; print(settings.MEDIA_ROOT, settings.STATIC_ROOT, '
                  "settings.MAILERS['default']['BACKEND'])")
    *roots, mailer = done.stdout.splitlines()[-1].split()
    assert [Path(it).resolve() for it in roots] == [(directory / 'media').resolve(), (directory / 'static').resolve()], done.stderr
    # the mails of development are printed: no SMTP server is needed (`e2e_data`, the tasks)
    assert mailer == 'django.core.mail.backends.console.EmailBackend'
    # the password of the test users of the end-to-end tests, its own, which the settings
    # put in the environment of the commands (`e2e_data`)
    password = re.search(r'^E2E_PASSWORD=(\S{16,})$', (directory / '.env').read_text(), re.M)[1]
    done = manage(directory, 'shell', '-c', "import os; print(os.environ['E2E_PASSWORD'])")
    assert done.stdout.splitlines()[-1] == password, done.stderr
    assert '`BS_BAZIS_EMAIL_BACKEND` of `.env`' in (directory / 'AGENTS.md').read_text()
    # the ports of the project, in its local directory that Git ignores
    ports = json.loads((directory / '.bazis' / 'ports.json').read_text())
    assert set(ports) == set(scaffold.PORTS) and len(set(ports.values())) == 3
    assert (directory / '.bazis' / '.gitignore').read_text() == '*\n'
    assert '`.bazis/`' in (directory / 'AGENTS.md').read_text()


def test_cache_of_the_skeleton_is_that_of_the_server(tmp_path, monkeypatch):
    """
    The Redis of `.env` is that of the environment of the server (its database is not the
    one of the product, whose tests share it with its backend), else the default; the
    answer to the agent never has its password.
    """
    monkeypatch.delenv(scaffold.CACHE_LOCATION, raising=False)
    scaffold.write_files(tmp_path / 'default', 'store')
    assert f'\nBS_CACHES__DEFAULT__LOCATION={scaffold.DEFAULT_CACHE}\n' in (
        tmp_path / 'default' / '.env'
    ).read_text()
    assert scaffold.DEFAULT_CACHE == 'redis://localhost:6379/0'
    assert scaffold.cache_location(shown=True) == scaffold.DEFAULT_CACHE

    monkeypatch.setenv(scaffold.CACHE_LOCATION, 'redis://:s3cret@127.0.0.1:6400/1')
    scaffold.write_files(tmp_path / 'server', 'store')
    assert '\nBS_CACHES__DEFAULT__LOCATION=redis://:s3cret@127.0.0.1:6400/1\n' in (
        tmp_path / 'server' / '.env'
    ).read_text()
    assert scaffold.cache_location(shown=True) == 'redis://***@127.0.0.1:6400/1'

    monkeypatch.setenv(scaffold.CACHE_LOCATION, 'redis://127.0.0.1:6400/2')
    assert scaffold.cache_location(shown=True) == 'redis://127.0.0.1:6400/2'
    monkeypatch.setenv(scaffold.CACHE_LOCATION, '')
    assert scaffold.cache_location() == scaffold.DEFAULT_CACHE


def test_users_app_is_written_once(tmp_path):
    """
    The files of the team's users are written when missing and never over the project's own.
    """
    assert [it.name for it in scaffold.write_users(tmp_path)] == ['__init__.py', 'routes.py', 'router.py']
    assert (tmp_path / 'users' / 'router.py').read_text() == scaffold.USERS_ROUTER_PY
    (tmp_path / 'users' / 'routes.py').write_text('# own\n')
    (tmp_path / 'users' / 'router.py').unlink()

    assert [it.name for it in scaffold.write_users(tmp_path)] == ['router.py']
    assert (tmp_path / 'users' / 'routes.py').read_text() == '# own\n'
    assert scaffold.write_users(tmp_path) == []


def test_users_app_is_a_working_part_of_a_project(tmp_path):
    """
    The route set of the team registered in the root router of the skeleton: the checks of
    the project pass (also `users.E002`, which the registration satisfies), the migrations
    are made, and the user resource is a route of the application.
    """
    pytest.importorskip('bazis.contrib.users')
    directory = tmp_path / 'store'
    scaffold.write_files(directory, 'store')
    scaffold.write_users(directory)
    (directory / 'users' / 'models.py').write_text(
        'from bazis.contrib.users.models_abstract import (\n'
        '    AnonymousUserAbstract, UserAbstract, UserLanguageMixin,\n'
        ')\n'
        'from bazis.core.models_abstract import JsonApiMixin, UuidMixin\n\n\n'
        'class User(JsonApiMixin, UuidMixin, UserLanguageMixin, UserAbstract):\n'
        '    pass\n\n\n'
        'class AnonymousUser(AnonymousUserAbstract):\n'
        '    pass\n'
    )
    (directory / 'users' / 'apps.py').write_text(
        'from bazis.contrib.users.apps import UsersConfig as UsersConfigBase\n\n\n'
        "class UsersConfig(UsersConfigBase):\n    name = 'users'\n"
    )
    env = directory / 'project.env'
    env.write_text(
        env.read_text().replace("BS_INSTALLED_APPS='[]'", "BS_INSTALLED_APPS='[\"users\"]'")
        + 'BS_AUTH_USER_MODEL=users.User\n'
        'BS_AUTH_ANONYMOUS_USER_MODEL=users.models.AnonymousUser\n'
    )
    router = directory / 'store' / 'router.py'
    router.write_text(router.read_text() + "router.register('users.router')\n")

    assert doctor(directory) == []
    done = manage(directory, 'makemigrations', 'users')
    assert done.returncode == 0, done.stderr[-2000:]
    assert (directory / 'users' / 'migrations' / '0001_initial.py').is_file()
    done = manage(directory, 'shell', '-c',
                  'from bazis.core.app import app; from bazis.core import introspect; '
                  "print(sorted({p for p, r in introspect.iter_routes_with_paths(app.routes) if '/user' in p})[:2])")
    assert "/api/v1/users/user/" in done.stdout, done.stderr[-2000:]


def test_project_ports(tmp_path):
    """
    The ports are chosen free once and kept; a missing or broken file is written again.
    """
    ports = scaffold.project_ports(tmp_path)
    assert list(ports) == ['backend', 'frontend', 'e2e'] and 8000 not in ports.values()
    assert scaffold.project_ports(tmp_path) == ports
    (tmp_path / '.bazis' / 'ports.json').write_text('{"backend": 1}')
    again = scaffold.project_ports(tmp_path)
    assert set(again) == set(scaffold.PORTS)
    assert json.loads((tmp_path / '.bazis' / 'ports.json').read_text()) == again


def test_release():
    """
    The minimum a version satisfies: its release, also of a build after it; none of a
    version before its release.
    """
    assert scaffold.release('2.16.0') == '2.16.0'
    assert scaffold.release('2.15.1.post1.dev12') == '2.15.1'
    assert scaffold.release('2.16.0+local') == '2.16.0'
    for version in ('2.16.0rc1', '2.16.0.dev3', '2.15.1-12-gc4e2997 (clone)', ''):
        assert scaffold.release(version) is None, version


def test_requirements_are_raised_to_the_installed_releases(tmp_path, monkeypatch):
    """
    `create_venv` raises the minimums of the skeleton to the installed releases, numbers
    only, never lowers them, and keeps the other lines.
    """
    monkeypatch.setenv(scaffold.FRONTEND_REQUIREMENT_ENV, '/src/bazis-front')
    scaffold.write_files(tmp_path, 'store', frontend=True)
    installed = {
        'bazis': '2.16.0.post1.dev4', 'bazis-mcp': '2.4.5rc1', 'bazis-test-utils': '2.0.0',
    }

    def run(command, **kwargs):
        if command[1:3] == ['-c', scaffold.INSTALLED_VERSIONS_PY]:
            assert set(command[3:]) == {'bazis', 'bazis-mcp', 'bazis-test-utils'}
            return subprocess.CompletedProcess(command, 0, json.dumps(installed), '')
        return subprocess.CompletedProcess(command, 0, '', '')

    scaffold.create_venv(tmp_path, run=run)
    assert (tmp_path / 'requirements.txt').read_text().splitlines() == [
        'bazis>=2.19.1', '/src/bazis-front',
    ]
    # a pre-release does not satisfy its release, an older one does not lower the minimum
    assert (tmp_path / 'requirements-dev.txt').read_text().splitlines() == [
        '-r requirements.txt', *scaffold.REQUIREMENTS_DEV,
    ]


def test_product_language():
    """
    A code is matched by itself, else by its base code, as the core matches the language of
    a request; the name is the own name of the language.
    """
    for code in ('ru', 'ru-RU', 'RU', 'ru_RU', ' ru '):
        assert scaffold.product_language(code) == ('ru', 'Русский')
    assert scaffold.product_language('pt_BR') == ('pt-br', 'Português Brasileiro')
    assert scaffold.product_language('zh-cn')[0] == 'zh-hans'
    assert scaffold.product_language('en-US') == ('en', 'English')
    with pytest.raises(scaffold.ScaffoldError, match='not a language of Django'):
        scaffold.product_language('xx')


def test_product_language_needs_django():
    """
    The language is read by a Python with Django, that of the project: one without it, or
    none, is an error that says why.
    """

    def without_django(command, **kwargs):
        assert command[0] == '/p/python' and command[-1] == 'ru'
        error = "Traceback\nModuleNotFoundError: No module named 'django'"
        return subprocess.CompletedProcess(command, 1, '', error)

    with pytest.raises(scaffold.ScaffoldError) as raised:
        scaffold.product_language('ru', '/p/python', run=without_django)
    assert str(raised.value) == (
        "The language 'ru' could not be checked: ModuleNotFoundError: No module named 'django'"
    )
    with pytest.raises(scaffold.ScaffoldError, match="'ru' could not be checked: "):
        scaffold.product_language('ru', '/nonexistent/python')


def test_scaffold_in_a_language(tmp_path):
    """
    The skeleton of a product in Russian: Russian alone, as bazis-front has its dictionary,
    and the checks of the translations (bazis.W005) pass.
    """
    english = tmp_path / 'en'
    scaffold.write_files(english, 'store')
    env = (english / 'project.env').read_text(encoding='utf-8')
    assert """BS_LANGUAGES='[["en", "English"]]'""" in env and 'BS_LANGUAGE_CODE=en\n' in env

    directory = tmp_path / 'store'
    scaffold.write_files(directory, 'store')
    scaffold.set_language(directory, scaffold.product_language('ru'), {'en', 'ru'})

    env = (directory / 'project.env').read_text(encoding='utf-8')
    assert """BS_LANGUAGES='[["ru", "Русский"]]'""" in env
    assert 'BS_LANGUAGE_CODE=ru\n' in env
    # the other settings are kept
    def others(env):
        return [it for it in env.splitlines() if not it.startswith(('BS_LANGUAGES=', 'BS_LANGUAGE_CODE='))]

    assert others(env) == others((english / 'project.env').read_text(encoding='utf-8'))
    assert doctor(directory) == []


@pytest.mark.parametrize(('code', 'dictionaries', 'languages'), [
    ('ru', {'en', 'ru'}, '[["ru", "Русский"]]'),
    # English is the fallback of a language without a dictionary of the frontend
    ('de', {'en', 'ru'}, '[["de", "Deutsch"], ["en", "English"]]'),
    ('ru', set(), '[["ru", "Русский"], ["en", "English"]]'),
    ('en', {'en', 'ru'}, '[["en", "English"]]'),
    ('en', set(), '[["en", "English"]]'),
])
def test_english_is_the_fallback_of_a_language_without_a_dictionary(
    tmp_path, code, dictionaries, languages
):
    scaffold.write_files(tmp_path / 'store', 'store')
    scaffold.set_language(tmp_path / 'store', scaffold.product_language(code), dictionaries)

    env = (tmp_path / 'store' / 'project.env').read_text(encoding='utf-8')
    assert f"BS_LANGUAGES='{languages}'\n" in env and f'BS_LANGUAGE_CODE={code}\n' in env


def test_front_languages(tmp_path):
    """
    The dictionaries of the bazis-front installed in the Python asked: none without it.
    """
    assert scaffold.front_languages(make_venv(tmp_path, with_packages=False)) == set()
    assert scaffold.front_languages('/nonexistent/python') == set()
    pytest.importorskip('bazis.contrib.front')
    assert {'en', 'ru'} <= scaffold.front_languages()


def test_bazis_messages_keeps_the_catalogs_of_the_project(tmp_path):
    """
    The loop of the rules in a new project: `bazis_messages make` creates `locale/` and writes
    the msgids of the project there (never into the catalog of a package), also a msgid of a
    package declared with `gettext_noop` in `<project>/translations.py` (bazis.W004), `apply`
    of `locale/translations.json` fills and compiles it.
    """
    if shutil.which('xgettext') is None:
        pytest.skip('gettext is not installed')
    directory = tmp_path / 'store'
    scaffold.write_files(directory, 'store')
    scaffold.set_language(directory, ('ru', 'Русский'), {'en', 'ru'})
    (directory / 'store' / 'texts.py').write_text(
        "from django.utils.translation import gettext_lazy as _\n\nTITLE = _('A text of the shop')\n"
    )
    (directory / 'store' / 'translations.py').write_text(
        "from django.utils.translation import gettext_noop\n\nPACKAGE_MSGIDS = [gettext_noop('Name')]\n"
    )
    done = manage(directory, 'bazis_messages', 'make')
    assert done.returncode == 0, done.stderr[-3000:]
    status = json.loads(done.stdout)['ru']
    assert status['catalogs'] == ['locale/ru/LC_MESSAGES/django.po']
    assert {'msgid': 'A text of the shop'} in status['untranslated']
    assert {'msgid': 'Name'} in status['untranslated']

    translations = {'ru': {it['msgid']: f'[{it["msgid"]}]' for it in status['untranslated']}}
    (directory / 'locale' / 'translations.json').write_text(json.dumps(translations), encoding='utf-8')
    done = manage(directory, 'bazis_messages', 'apply', 'locale/translations.json', '--check')
    assert done.returncode == 0, done.stdout + done.stderr[-3000:]
    catalog = directory / 'locale' / 'ru' / 'LC_MESSAGES'
    assert 'msgstr "[A text of the shop]"' in (catalog / 'django.po').read_text(encoding='utf-8')
    assert (catalog / 'django.mo').is_file()


def test_tests_of_a_scaffold_keep_their_cache_keys_apart(tmp_path):
    """
    The conftest of the skeleton gives the cache keys of the tests a prefix of their own, new
    at every run, in every thread (the endpoints run in a thread pool); it works without
    Redis (here an address where nothing listens).
    """
    pytest.importorskip('pytest_django')
    directory = tmp_path / 'store'
    scaffold.write_files(directory, 'store')
    (directory / 'tests' / 'test_cache.py').write_text("""\
import threading

from django.core.cache import cache


def test_prefix():
    keys = [cache.make_key('x')]
    thread = threading.Thread(target=lambda: keys.append(cache.make_key('x')))
    thread.start()
    thread.join()
    prefix = keys[0].split(':')[0]
    assert prefix.startswith('store-tests-') and len(prefix) == len('store-tests-') + 8
    assert keys[1] == keys[0]
""")
    env = {
        **{k: v for k, v in os.environ.items()
           if not k.startswith(('BS_', 'DJANGO_')) or k.endswith('_LIBRARY_PATH')},
        'BS_CACHES__DEFAULT__LOCATION': 'redis://127.0.0.1:1/0',
    }
    done = subprocess.run(
        [sys.executable, '-m', 'pytest', '-q', '-p', 'no:cacheprovider'],
        cwd=directory, env=env, capture_output=True, text=True, timeout=300,
    )
    assert done.returncode == 0, (done.stdout + done.stderr)[-3000:]
    assert '1 passed' in done.stdout


def test_scaffold_with_a_frontend(tmp_path):
    backend, product = tmp_path / 'backend', tmp_path / 'product'
    scaffold.write_files(backend, 'store')
    scaffold.write_files(product, 'store', frontend=True)

    assert 'bazis-front' not in (backend / 'requirements.txt').read_text()
    assert "BS_INSTALLED_APPS='[]'" in (backend / 'project.env').read_text()
    assert '## Frontend' not in (backend / 'AGENTS.md').read_text()

    assert (product / 'requirements.txt').read_text().splitlines() == [
        *scaffold.REQUIREMENTS, 'bazis-front>=0.8.0',
    ]
    assert """BS_INSTALLED_APPS='["bazis.contrib.front"]'""" in (product / 'project.env').read_text()
    agents_md = (product / 'AGENTS.md').read_text()
    assert '## Frontend' in agents_md and 'frontend/AGENTS.md' in agents_md
    # the screens are generated from their specs, the screenshots never committed
    assert 'bazis_front screens' in agents_md and '`frontend/src/screens/generated/`' in agents_md
    assert 'bazis_front shots' in agents_md and '`frontend/.scratch/shots/` (not committed)' in agents_md
    # the agent creates the frontend with `bazis_front init`, after choosing the packages
    assert not (product / 'frontend').exists() and not (product / 'spec').exists()


def test_frontend_requirement_override(tmp_path, monkeypatch):
    """
    A bazis-front that is not on PyPI: a path or a URL instead of the requirement.
    """
    monkeypatch.setenv(scaffold.FRONTEND_REQUIREMENT_ENV, ' /wheels/bazis_front-0.1.0-py3-none-any.whl ')
    scaffold.write_files(tmp_path, 'store', frontend=True)
    requirements = (tmp_path / 'requirements.txt').read_text().splitlines()
    assert requirements[-1] == '/wheels/bazis_front-0.1.0-py3-none-any.whl'
    assert not any(line.startswith('bazis-front') for line in requirements)

    monkeypatch.setenv(scaffold.FRONTEND_REQUIREMENT_ENV, '')
    assert scaffold.frontend_requirement() == scaffold.FRONTEND_REQUIREMENT


def test_scaffold_with_a_frontend_is_a_working_project(tmp_path):
    """
    With bazis-front installed, the skeleton of a product passes the system checks before
    its frontend exists.
    """
    pytest.importorskip('bazis.contrib.front')
    directory = tmp_path / 'store'
    scaffold.write_files(directory, 'store', frontend=True)

    assert doctor(directory) == []


def node_version(stdout: str, returncode: int = 0):
    def run(command, **kwargs):
        assert command == ['/usr/bin/node', '--version']
        return subprocess.CompletedProcess(command, returncode, stdout, '')

    return run


def test_node_problem(monkeypatch):
    found = {'node': '/usr/bin/node', 'npm': '/usr/bin/npm'}
    monkeypatch.setattr(scaffold.shutil, 'which', found.get)
    assert node_problem(node_version('v22.12.0\n')) is None
    assert node_problem(node_version('v24.1.3\n')) is None

    too_old = node_problem(node_version('v22.11.9\n'))
    assert too_old.startswith('Node.js v22.11.9 is too old') and '22.12 or newer' in too_old
    assert node_problem(node_version('v18.20.0\n')).startswith('Node.js v18.20.0 is too old')
    assert node_problem(node_version('', 1)).startswith('`node --version` failed')

    del found['npm']
    assert node_problem().startswith('npm not found')
    found.clear()
    assert node_problem().startswith('node and npm not found')


def test_node_version_is_that_of_the_template():
    """
    NODE_VERSION follows `engines.node` of the template of bazis-front.
    """
    pytest.importorskip('bazis.contrib.front')
    from importlib.resources import files

    package = json.loads(
        files('bazis.contrib.front').joinpath('assets/template/package.json').read_text()
    )
    assert package['engines']['node'] == '>=' + '.'.join(map(str, scaffold.NODE_VERSION))


def test_scaffold_refuses_a_directory_with_files(tmp_path):
    (tmp_path / 'file.txt').write_text('x')
    with pytest.raises(scaffold.ScaffoldError):
        scaffold.write_files(tmp_path, 'x')


def test_create_venv_with_pip(tmp_path, monkeypatch):
    scaffold.write_files(tmp_path, 'store')
    monkeypatch.setattr(scaffold.shutil, 'which', lambda name: None)
    monkeypatch.chdir(tmp_path.parent)
    commands = []

    def run(command, **kwargs):
        commands.append(command)
        assert kwargs['cwd'] == tmp_path
        return subprocess.CompletedProcess(command, 0, '', '')

    # a relative directory: the commands run in it, so their paths are absolute
    python = scaffold.create_venv(Path(tmp_path.name), run=run)

    assert commands[0] == [sys.executable, '-m', 'venv', str(tmp_path / '.venv')]
    assert commands[1][:3] == [str(python), '-m', 'pip']
    assert commands[1][-1] == str(tmp_path / 'requirements-dev.txt')


def test_create_venv_with_uv(tmp_path, monkeypatch):
    """
    A bazis-front from FRONTEND_REQUIREMENT_ENV (a checkout) is built again, not taken from
    the cache of uv, which keeps the build of an older commit; the released one is not.
    """
    scaffold.write_files(tmp_path, 'store')
    monkeypatch.setattr(scaffold.shutil, 'which', lambda name: '/usr/bin/uv')
    commands = []

    def run(command, **kwargs):
        commands.append(command)
        return subprocess.CompletedProcess(command, 0, '', '')

    monkeypatch.delenv(scaffold.FRONTEND_REQUIREMENT_ENV, raising=False)
    python = scaffold.create_venv(tmp_path, run=run)
    assert commands[0][:3] == ['/usr/bin/uv', 'venv', '--quiet']
    assert commands[1][:3] == ['/usr/bin/uv', 'pip', 'install']
    assert commands[1][-2:] == ['-r', str(tmp_path / 'requirements-dev.txt')]
    assert str(python) in commands[1]
    assert '--refresh-package' not in commands[1]

    commands.clear()
    monkeypatch.setenv(scaffold.FRONTEND_REQUIREMENT_ENV, '/src/bazis-front')
    scaffold.create_venv(tmp_path, run=run)
    refresh = commands[1].index('--refresh-package')
    assert commands[1][refresh + 1] == 'bazis-front'


def test_create_database(tmp_path):
    """
    The script runs in the directory of the project with its Python; its outcome, printed
    as JSON, is what `bazis new` says to the user and the agent.
    """
    commands = []
    server = 'BS_DATABASES__DEFAULT__HOST=db\nBS_DATABASES__DEFAULT__PORT=5432\n'
    (tmp_path / '.env').write_text(server)

    def runner(stdout, stderr=''):
        def run(command, **kwargs):
            commands.append((command, kwargs['cwd']))
            return subprocess.CompletedProcess(command, 0, stdout, stderr)

        return run

    def outcome(outcome, **extra):
        result = {'name': 'store', 'server': 'db:5432', 'host': 'db', 'port': '5432',
                  'outcome': outcome, **extra}
        return scaffold.create_database(tmp_path, 'store', '/p/python', run=runner(json.dumps(result)))

    assert outcome('created') == 'Created the database `store` on PostgreSQL db:5432.'
    assert (tmp_path / '.env').read_text() == server
    command, cwd = commands[0]
    assert command == ['/p/python', '-c', scaffold.CREATE_DATABASE_PY, 'store'] and cwd == tmp_path
    assert outcome('exists') == 'The database `store` exists on PostgreSQL db:5432 without tables.'
    # the database and PostGIS are separate outcomes
    assert outcome('created', postgis='extension "postgis" is not available') == (
        'Created the database `store` on PostgreSQL db:5432, but PostGIS is not installed in '
        'it: extension "postgis" is not available'
    )
    assert outcome('exists', postgis='permission denied') == (
        'The database `store` exists on PostgreSQL db:5432 without tables, but PostGIS is not '
        'installed in it: permission denied'
    )
    # it exists but could not be opened: not presented as empty, not ready
    uninspected = outcome('uninspected', detail='permission denied for database "store"')
    assert uninspected.startswith(
        'The database `store` exists on PostgreSQL db:5432 but could not be inspected: '
        'permission denied for database "store".'
    )
    assert 'without tables' not in uninspected and 'not ready' in uninspected
    # tables of another project: not the database of this one
    has_data = outcome('has_data')
    assert has_data.startswith('The database `store` on PostgreSQL db:5432 already has data')
    assert '`BS_DATABASES__DEFAULT__NAME` in `.env`' in has_data
    unreachable = outcome('unreachable', detail='connection refused')
    assert 'cannot be reached (connection refused)' in unreachable and 'not created' in unreachable
    assert outcome('failed', detail='permission denied') == (
        'The database `store` was not created on PostgreSQL db:5432: permission denied'
    )
    assert 'not on PostgreSQL' in outcome('other')
    # the database is on the server of the environment of the caller, not of `.env`: the
    # server is set in `.env`, once
    (tmp_path / '.env').write_text('BS_DATABASES__DEFAULT__HOST=localhost\nBS_DATABASES__DEFAULT__PORT=5432\n')
    assert outcome('created', server='localhost:5433', host='localhost', port='5433').endswith(
        '`.env` sets it: `BS_DATABASES__DEFAULT__PORT=5433`.'
    )
    assert (tmp_path / '.env').read_text() == (
        'BS_DATABASES__DEFAULT__HOST=localhost\nBS_DATABASES__DEFAULT__PORT=5433\n'
    )
    assert outcome('exists', server='localhost:5433', host='localhost', port='5433').endswith('tables.')
    # no database, no server: `.env` is left as it is
    assert 'cannot be reached' in outcome('unreachable', detail='x', port='1')
    assert 'PORT=5433' in (tmp_path / '.env').read_text()
    # the databases of the name are taken: the one prepared instead is set in .env
    (tmp_path / '.env').write_text('BS_DEBUG=true\nBS_DATABASES__DEFAULT__NAME=store\nE2E_PASSWORD=x\n')
    assert outcome('failed', name='store_2', taken=['store'], detail='permission denied') == (
        'Taken on PostgreSQL db:5432 and left as they are (data of another project, or no '
        'access): `store`. The database `store_2` was not created on PostgreSQL db:5432: '
        'permission denied. Set `BS_DATABASES__DEFAULT__NAME` in `.env` to a free database '
        'before migrating.'
    )
    assert 'NAME=store\n' in (tmp_path / '.env').read_text()
    assert outcome('created', name='store_3', taken=['store', 'store_2']) == (
        'Taken on PostgreSQL db:5432 and left as they are (data of another project, or no '
        'access): `store`, `store_2`. Created the database `store_3` on PostgreSQL db:5432. '
        '`.env` sets it: `BS_DATABASES__DEFAULT__NAME=store_3`.'
    )
    assert (tmp_path / '.env').read_text() == (
        'BS_DEBUG=true\nBS_DATABASES__DEFAULT__NAME=store_3\nE2E_PASSWORD=x\n'
    )
    # `.env` has no line of the name (it comes from `project.env`): the line is added
    (tmp_path / '.env').write_text('BS_DEBUG=true\nE2E_PASSWORD=x')
    assert outcome('exists', name='store_2', taken=['store']).endswith(
        '`.env` sets it: `BS_DATABASES__DEFAULT__NAME=store_2`.'
    )
    assert (tmp_path / '.env').read_text() == (
        'BS_DEBUG=true\nE2E_PASSWORD=x\nBS_DATABASES__DEFAULT__NAME=store_2\n'
    )
    # the script failed: its last error line
    failed = scaffold.create_database(tmp_path, 'store', run=runner('', 'Traceback\nImportError: x'))
    assert failed == 'The database of the project was not created: ImportError: x'

    def broken(command, **kwargs):
        raise subprocess.TimeoutExpired(command, 120)

    assert 'was not created' in scaffold.create_database(tmp_path, 'store', run=broken)


def project_database_env(monkeypatch, host: str, port: str, name: str | None) -> None:
    """
    The settings of the database of a project in the environment, as a user may set them,
    the `name` of the database too unless it is None (that of `.env`); the settings module
    is that of the project, not of the tests.
    """
    monkeypatch.delenv('DJANGO_SETTINGS_MODULE', raising=False)
    for key in [k for k in os.environ if k.startswith('BS_DATABASES__') or k == 'BS_ENV_FILE']:
        monkeypatch.delenv(key)
    for key, value in dict(HOST=host, PORT=port, NAME=name, USER='postgres',
                           PASSWORD='postgres').items():
        if value is not None:
            monkeypatch.setenv(f'BS_DATABASES__DEFAULT__{key}', value)


def test_create_database_of_a_project_without_postgres(tmp_path, monkeypatch):
    """
    The real script with the settings of a project: a server that cannot be reached is
    skipped with a message, `bazis new` goes on.
    """
    directory = tmp_path / 'store'
    scaffold.write_files(directory, 'store')
    project_database_env(monkeypatch, '127.0.0.1', '9', 'store')

    message = scaffold.create_database(directory, 'store')
    assert message.startswith('PostgreSQL 127.0.0.1:9 cannot be reached ('), message
    assert message.endswith('the database `store` is not created.')


@pytest.mark.skipif(not TEST_POSTGRES, reason='BAZIS_CLI_TEST_POSTGRES is not set')
def test_create_database_of_a_project(tmp_path, monkeypatch):
    """
    The database of the settings of the project is created with PostGIS, once: the second
    run finds it, and one with tables is reported as the data of another project. Its name
    comes from the environment: no other database is chosen. The server of the environment
    is set in `.env` (the skeleton says localhost:5432), once.
    """
    import psycopg

    host, port = TEST_POSTGRES.rsplit(':', 1)
    name = f'bazis_cli_test_{os.getpid()}'
    directory = tmp_path / 'store'
    scaffold.write_files(directory, 'store')
    project_database_env(monkeypatch, host, port, name)
    server = dict(host=host, port=port, user='postgres', password='postgres', autocommit=True)
    try:
        assert scaffold.create_database(directory, 'store') == (
            f'Created the database `{name}` on PostgreSQL {host}:{port}. `.env` sets it: '
            f'`BS_DATABASES__DEFAULT__HOST={host}`, `BS_DATABASES__DEFAULT__PORT={port}`.'
        )
        assert f'\nBS_DATABASES__DEFAULT__PORT={port}\n' in (directory / '.env').read_text()
        # PostGIS, whose table is no data of a project
        assert scaffold.create_database(directory, 'store') == (
            f'The database `{name}` exists on PostgreSQL {host}:{port} without tables.'
        )
        with psycopg.connect(dbname=name, **server) as database:
            query = "SELECT 1 FROM pg_extension WHERE extname = 'postgis'"
            assert database.execute(query).fetchone()
            # the data of a project
            database.execute('CREATE TABLE django_migrations (id serial)')
        assert 'already has data, probably of another project' in scaffold.create_database(directory, 'store')
        assert not database_exists(server, f'{name}_2')
    finally:
        drop_databases(server, name)


@pytest.mark.skipif(not TEST_POSTGRES, reason='BAZIS_CLI_TEST_POSTGRES is not set')
def test_create_database_with_a_taken_name(tmp_path, monkeypatch):
    """
    The name of `.env` is that of a database with tables (of another project, such as one
    in a directory of the same name), and the next one that of a database that cannot be
    opened: they are left as they are, the first free `<name>_N` is created and set in
    `.env`. The next run keeps it: an empty database is that of the project.
    """
    import psycopg

    host, port = TEST_POSTGRES.rsplit(':', 1)
    name = f'bazis_cli_test_{os.getpid()}'
    directory = tmp_path / name
    scaffold.write_files(directory, name)
    project_database_env(monkeypatch, host, port, None)
    server = dict(host=host, port=port, user='postgres', password='postgres', autocommit=True)
    env = directory / '.env'
    try:
        with psycopg.connect(dbname='postgres', **server) as database:
            database.execute(f'CREATE DATABASE "{name}"')
            database.execute(f'CREATE DATABASE "{name}_2" ALLOW_CONNECTIONS false')
        with psycopg.connect(dbname=name, **server) as database:
            database.execute('CREATE TABLE librarian (id serial)')

        chosen = (
            f'Taken on PostgreSQL {host}:{port} and left as they are (data of another '
            f'project, or no access): `{name}`, `{name}_2`. Created the database `{name}_3` '
            f'on PostgreSQL {host}:{port}. `.env` sets it: `BS_DATABASES__DEFAULT__NAME={name}_3`, '
            f'`BS_DATABASES__DEFAULT__HOST={host}`, `BS_DATABASES__DEFAULT__PORT={port}`.'
        )
        assert scaffold.create_database(directory, name) == chosen
        assert f'\nBS_DATABASES__DEFAULT__NAME={name}_3\n' in env.read_text()
        assert f'NAME={name}\n' not in env.read_text()
        with psycopg.connect(dbname=name, **server) as database:
            assert database.execute('SELECT count(*) FROM librarian').fetchone() == (0,)
        with psycopg.connect(dbname=f'{name}_3', **server) as database:
            query = "SELECT 1 FROM pg_extension WHERE extname = 'postgis'"
            assert database.execute(query).fetchone()

        assert scaffold.create_database(directory, name) == (
            f'The database `{name}_3` exists on PostgreSQL {host}:{port} without tables.'
        )
        assert f'\nBS_DATABASES__DEFAULT__NAME={name}_3\n' in env.read_text()
        assert not database_exists(server, f'{name}_4')
    finally:
        drop_databases(server, name)


def test_requirements_are_the_latest_releases():
    """
    The skeleton requires at least the releases of the catalog of bazis-mcp, which its
    guides describe, bazis-front too: an agent never starts from an older Bazis.
    """
    from bazis.contrib.mcp import catalog

    def version(text):
        return tuple(int(part) for part in text.split('.')[:3])

    released = catalog.catalog()
    for requirement in [*scaffold.REQUIREMENTS, *scaffold.REQUIREMENTS_DEV, scaffold.FRONTEND_REQUIREMENT]:
        name, minimum = requirement.split('>=')
        if name in released:
            assert version(minimum) >= version(released[name]['version']), requirement


def test_bazis_is_required_as_bazis_front_requires_it():
    """
    The minimum of bazis of the skeleton is not older than that of bazis-front, which every
    product installs: the agent never starts from a Bazis that bazis-front replaces.
    """
    pytest.importorskip('bazis.contrib.front')
    import re
    from importlib import metadata

    def version(text):
        return tuple(int(part) for part in text.split('.')[:3])

    front = next(
        match.group(1) for it in metadata.requires('bazis-front')
        if (match := re.fullmatch(r'bazis\s*>=\s*([\d.]+)', it))
    )
    ours = next(it.split('>=')[1] for it in scaffold.REQUIREMENTS if it.startswith('bazis>='))
    assert version(ours) >= version(front)

