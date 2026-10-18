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
The project of the conversation: `create_project`, `use_project`, `project_status`, the
tools without a project, the rules and the prompts of a project.
"""

import os
import shutil
import sys
import time

import anyio
import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from bazis.contrib.mcp import catalog, project, prompts, rules, scaffold

from .support import (
    SAMPLE_DIR,
    TEST_POSTGRES,
    drop_databases,
    make_venv,
    result,
    site_packages,
)


pytestmark = pytest.mark.anyio

#: the existing tools, which need a project
PROJECT_TOOLS = {
    'project_info': {},
    'run_doctor': {},
    'front_check': {},
    'front_status': {},
    'front_catalog': {},
    'project_status': {},
    'add_packages': {'names': ['bazis-permit']},
    'run_command': {'kind': 'manage', 'args': ['check']},
    'start_server': {'which': 'backend'},
    'server_logs': {'which': 'backend'},
    'read_file': {'path': 'manage.py'},
    'write_file': {'path': 'notes.txt', 'content': 'x'},
    'delete_file': {'path': 'notes.txt'},
    'list_files': {},
}


@pytest.fixture
def no_project(monkeypatch):
    monkeypatch.setattr(project, 'project_dir', None)
    monkeypatch.setattr(project, 'python', None)


@pytest.fixture
def machine(monkeypatch):
    """
    The projects are created in `tmp_path`, which is in a temporary directory of this
    machine: the tests take it as a lasting one. Their `.venv` has the packages of the
    tests, made without installing (`make_venv`), Node.js is found, bazis-front is that of
    PyPI and PostgreSQL cannot be reached (the settings of the database in the environment).
    The settings of the tests (of the sample project) are not those of the new projects,
    only the libraries of this machine (GDAL, GEOS).
    """
    monkeypatch.setattr(project, 'temp_dirs', lambda: [])
    monkeypatch.setattr(scaffold, 'node_problem', lambda: None)
    monkeypatch.setattr(scaffold, 'create_venv', make_venv)
    monkeypatch.delenv(scaffold.FRONTEND_REQUIREMENT_ENV, raising=False)
    for key in list(os.environ):
        if key.startswith(('BS_', 'DJANGO_')) and not key.endswith('_LIBRARY_PATH'):
            monkeypatch.delenv(key)
    for key, value in dict(HOST='127.0.0.1', PORT='9', NAME='store').items():
        monkeypatch.setenv(f'BS_DATABASES__DEFAULT__{key}', value)


def error(call_result) -> str:
    """
    The message of a tool error, after `Error executing tool <name>: `.
    """
    assert call_result.is_error, call_result.content
    prefix, message = call_result.content[0].text.split(': ', 1)
    assert prefix.startswith('Error executing tool '), prefix
    return message


def text_of(call_result) -> str:
    return call_result.content[0].text


async def test_tools_without_a_project(client, no_project, monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    for name, args in PROJECT_TOOLS.items():
        assert error(await client.call_tool(name, args)) == project.NO_PROJECT, name

    # the projects one level below the current directory, which a client that starts the
    # server again (a new conversation) chooses: not a file, nor a deeper project
    for path in ('shop/manage.py', 'blog/manage.py', 'apps/deep/manage.py', 'notes/readme.md'):
        (tmp_path / path).parent.mkdir(parents=True)
        (tmp_path / path).write_text('')
    (tmp_path / 'file').write_text('')
    assert error(await client.call_tool('project_status', {})) == (
        f'{project.NO_PROJECT} The projects in the current directory: '
        f'use_project("{tmp_path.resolve() / "blog"}"), use_project("{tmp_path.resolve() / "shop"}").'
    )


@pytest.mark.skipif(os.geteuid() == 0, reason='root reads any directory')
async def test_no_project_skips_a_directory_that_cannot_be_read(client, no_project, monkeypatch, tmp_path):
    """
    A directory without access hides only itself from the projects listed in the error.
    """
    monkeypatch.chdir(tmp_path)
    for path in ('locked', 'shop'):
        (tmp_path / path).mkdir()
    (tmp_path / 'shop' / 'manage.py').write_text('')
    (tmp_path / 'locked').chmod(0)
    try:
        assert error(await client.call_tool('project_status', {})) == (
            f'{project.NO_PROJECT} The projects in the current directory: '
            f'use_project("{tmp_path.resolve() / "shop"}").'
        )
    finally:
        (tmp_path / 'locked').chmod(0o755)


async def test_catalog_without_a_project(client, no_project):
    """
    The catalog describes the released packages without a project, none installed: the
    packages are chosen before the project is created.
    """
    packages = result(await client.call_tool('list_packages', {}))['packages']
    assert {it['name'] for it in packages} == set(catalog.catalog())
    assert all(it['installed_version'] is None for it in packages)

    guide = result(await client.call_tool('package_guide', {'name': 'bazis'}))
    assert guide['installed_version'] is None
    assert guide['guide_version'] == catalog.catalog()['bazis']['version']
    found = result(await client.call_tool('guide_search', {'query': 'routes'}))
    assert found['results']


async def test_create_project(client, no_project, machine, tmp_path):
    directory = tmp_path / 'My Shop'
    call_result = await client.call_tool(
        'create_project',
        {'directory': str(directory), 'description': 'Каталог товаров', 'frontend': False,
         'language': 'ru-RU'},
    )
    created = result(call_result)

    assert created['directory'] == str(directory.resolve())
    assert created['name'] == 'my_shop'
    assert created['language'] == ['ru', 'Русский']
    assert 'BS_LANGUAGE_CODE=ru\n' in (directory / 'project.env').read_text(encoding='utf-8')
    assert created['database'].startswith('PostgreSQL 127.0.0.1:9 cannot be reached')
    assert created['ports'] == scaffold.project_ports(directory)
    assert created['rules'] == rules.RULES
    assert created['next_steps'] == prompts.new_prompt(
        'Каталог товаров', 'my_shop', False, ('ru', 'Русский'), created['database'],
        created['ports'],
    )
    assert len(text_of(call_result).encode()) < catalog.RESULT_LIMIT

    # the new project is served: the tools run it with its Python
    status = result(await client.call_tool('project_status', {}))
    assert status['directory'] == str(directory.resolve())
    assert status['settings'] == 'my_shop.settings'
    assert status['python'] == str(directory.resolve() / '.venv' / 'bin' / 'python')
    assert status['frontend'] is False
    assert {'BS_SECRET_KEY', 'BS_DATABASES__DEFAULT__PASSWORD', 'E2E_PASSWORD'} <= set(
        status['env_keys']
    )
    doctor = result(await client.call_tool('run_doctor', {}))
    assert doctor['ok'] is True, doctor

    # the values of .env are never returned
    for key in ('BS_SECRET_KEY=', 'E2E_PASSWORD='):
        secret = next(
            line.split('=', 1)[1] for line in (directory / '.env').read_text().splitlines()
            if line.startswith(key)
        )
        assert secret not in text_of(call_result)
        assert secret not in text_of(await client.call_tool('project_status', {}))


@pytest.mark.skipif(not TEST_POSTGRES, reason='BAZIS_CLI_TEST_POSTGRES is not set')
async def test_create_project_on_a_taken_database(client, no_project, machine, monkeypatch, tmp_path):
    """
    The database of the name of the project has the data of another project (one in a
    directory of the same name): it is left as it is, the new project gets a database of
    its own, set in its `.env`, and `project_status` names it.
    """
    import psycopg

    host, port = TEST_POSTGRES.rsplit(':', 1)
    name = f'bazis_cli_test_{os.getpid()}'
    monkeypatch.delenv('BS_DATABASES__DEFAULT__NAME')
    for key, value in dict(HOST=host, PORT=port, USER='postgres', PASSWORD='postgres').items():
        monkeypatch.setenv(f'BS_DATABASES__DEFAULT__{key}', value)
    server = dict(host=host, port=port, user='postgres', password='postgres', autocommit=True)
    try:
        with psycopg.connect(dbname='postgres', **server) as database:
            database.execute(f'CREATE DATABASE "{name}"')
        with psycopg.connect(dbname=name, **server) as database:
            database.execute('CREATE TABLE django_migrations (id serial)')

        created = result(await client.call_tool(
            'create_project',
            {'directory': str(tmp_path / name), 'description': 'A library', 'frontend': False},
        ))
        assert created['database'].startswith(
            f'Taken on PostgreSQL {host}:{port} and left as they are (data of another '
            f'project, or no access): `{name}`. Created the database `{name}_2`'
        )
        assert created['database'] in created['next_steps']
        status = result(await client.call_tool('project_status', {}))
        assert status['database_name'] == f'{name}_2'
        assert result(await client.call_tool('run_doctor', {}))['ok'] is True
    finally:
        drop_databases(server, name)


async def test_create_project_with_a_frontend(client, no_project, machine, tmp_path):
    created = result(await client.call_tool(
        'create_project', {'directory': str(tmp_path / 'desk'), 'description': 'A help desk'}
    ))

    assert created['frontend'] is True and created['language'] is None
    assert created['rules'] == f'{rules.RULES}\n{rules.FRONTEND_RULES}'
    assert 'bazis-front is in `requirements.txt`' in created['next_steps']
    assert scaffold.FRONTEND_REQUIREMENT in (tmp_path / 'desk' / 'requirements.txt').read_text()


async def test_create_project_needs_node_for_a_frontend(
    client, no_project, machine, monkeypatch, tmp_path
):
    monkeypatch.setattr(scaffold, 'node_problem', lambda: 'node and npm not found')

    message = error(await client.call_tool(
        'create_project', {'directory': str(tmp_path / 'desk'), 'description': 'A help desk'}
    ))
    assert message == 'node and npm not found. Install it, or pass frontend false for a backend only.'
    assert not (tmp_path / 'desk').exists()


async def test_create_project_refusals(client, machine, monkeypatch, tmp_path):
    """
    A relative path, the home directory, a directory with files and one inside another
    project are refused before anything is written, and the project served stays.
    """
    (tmp_path / 'full').mkdir()
    (tmp_path / 'full' / 'notes.txt').write_text('x')
    (tmp_path / 'other' / 'apps').mkdir(parents=True)
    (tmp_path / 'other' / 'manage.py').write_text('')

    cases = {
        'shop': 'shop is not an absolute path.',
        str(tmp_path / 'full'): 'The home directory cannot be a project',
        str(tmp_path / 'full' / 'notes.txt'): 'is not an empty directory',
        str(tmp_path / 'other' / 'apps' / 'shop'): f'is inside the project {tmp_path / "other"}',
    }
    monkeypatch.setenv('HOME', str(tmp_path / 'full'))
    for directory, reason in cases.items():
        message = error(await client.call_tool(
            'create_project', {'directory': directory, 'description': 'A shop'}
        ))
        assert reason in message, message
    assert not (tmp_path / 'other' / 'apps' / 'shop').exists()
    assert sorted(os.listdir(tmp_path / 'full')) == ['notes.txt']
    assert project.project_dir == SAMPLE_DIR

    # a directory with files that is not the home directory
    monkeypatch.setenv('HOME', str(tmp_path / 'home'))
    assert 'is not an empty directory' in error(await client.call_tool(
        'create_project', {'directory': str(tmp_path / 'full'), 'description': 'A shop'}
    ))


async def test_create_project_refuses_a_temporary_directory(client, tmp_path):
    message = error(await client.call_tool(
        'create_project', {'directory': str(tmp_path / 'shop'), 'description': 'A shop'}
    ))
    assert message.endswith('is in a temporary directory, which the system empties.')
    assert not (tmp_path / 'shop').exists()


async def test_a_failed_creation_leaves_the_directory_as_it_was(
    client, machine, monkeypatch, tmp_path
):
    """
    A language that Django does not know, checked after `.venv`: the directory and its
    missing parents are removed. A name that hides a module of the Python of the project
    (not of the server: the server has no Django in a real run): an empty directory stays
    empty. The project served stays.
    """
    missing = tmp_path / 'new' / 'shop'
    message = error(await client.call_tool(
        'create_project',
        {'directory': str(missing), 'description': 'A shop', 'frontend': False, 'language': 'xx'},
    ))
    assert message.startswith("'xx' is not a language of Django")
    assert not (tmp_path / 'new').exists()

    def venv_with_a_module(directory):
        python = make_venv(directory)
        (site_packages(directory / '.venv') / 'shop_lib.py').write_text('')
        return python

    monkeypatch.setattr(scaffold, 'create_venv', venv_with_a_module)
    empty = tmp_path / 'empty'
    empty.mkdir()
    message = error(await client.call_tool(
        'create_project',
        {'directory': str(empty), 'description': 'A shop', 'name': 'shop_lib', 'frontend': False},
    ))
    assert message.startswith("'shop_lib' cannot be the project package: it would hide a module")
    assert list(empty.iterdir()) == []
    assert project.project_dir == SAMPLE_DIR

    # a module of the server too is refused before anything is written
    assert "'django' cannot be the project package" in error(await client.call_tool(
        'create_project',
        {'directory': str(empty), 'description': 'A shop', 'name': 'django', 'frontend': False},
    ))
    assert list(empty.iterdir()) == []


async def test_creations_run_one_at_a_time(client, no_project, machine, monkeypatch, tmp_path):
    """
    Two calls of create_project in the same directory at once: the second waits for the
    first and is refused, the project of the first stays whole and served.
    """
    def slow_venv(directory):
        time.sleep(1)
        return make_venv(directory)

    monkeypatch.setattr(scaffold, 'create_venv', slow_venv)
    directory = tmp_path / 'shop'
    calls = []

    async def create(name):
        calls.append(await client.call_tool(
            'create_project',
            {'directory': str(directory), 'description': 'A shop', 'name': name,
             'frontend': False},
        ))

    async with anyio.create_task_group() as group:
        group.start_soon(create, 'shop')
        group.start_soon(create, 'store')

    failed = [it for it in calls if it.is_error]
    created = [result(it) for it in calls if not it.is_error]
    assert len(failed) == 1 and len(created) == 1
    assert 'is not an empty directory' in error(failed[0])
    name = created[0]['name']
    assert (directory / name / 'settings.py').is_file() and (directory / '.venv').is_dir()
    assert project.project_dir == directory.resolve()


async def test_a_failed_creation_keeps_the_files_of_its_parent(client, machine, tmp_path):
    parent = tmp_path / 'work'
    parent.mkdir()
    (parent / 'notes.txt').write_text('mine')
    (parent / 'old').mkdir()

    error(await client.call_tool(
        'create_project',
        {'directory': str(parent / 'new' / 'shop'), 'description': 'A shop', 'frontend': False,
         'language': 'xx'},
    ))
    assert sorted(os.listdir(parent)) == ['notes.txt', 'old']
    assert (parent / 'notes.txt').read_text() == 'mine'


async def test_create_project_refuses_a_link_to_a_temporary_directory(
    client, machine, monkeypatch, tmp_path
):
    scratch = tmp_path / 'scratch'
    scratch.mkdir()
    monkeypatch.setattr(project, 'temp_dirs', lambda: [scratch.resolve()])
    (tmp_path / 'shop').symlink_to(scratch / 'shop')

    message = error(await client.call_tool(
        'create_project', {'directory': str(tmp_path / 'shop'), 'description': 'A shop'}
    ))
    assert message.endswith('is in a temporary directory, which the system empties.')
    assert not (scratch / 'shop').exists()
    assert project.project_dir == SAMPLE_DIR


async def test_use_project(client, no_project, tmp_path):
    """
    The project changes during the conversation: the tools serve the one chosen last.
    """
    first, second = tmp_path / 'first', tmp_path / 'second'
    for copy in (first, second):
        shutil.copytree(SAMPLE_DIR, copy, ignore=shutil.ignore_patterns('__pycache__'))
    with (second / 'shop' / 'models.py').open('a') as file:
        file.write(
            "\n\nclass Coupon(DtMixin, UuidMixin, JsonApiMixin):\n"
            "    code = models.CharField('Code', max_length=20)\n"
        )

    async def models():
        info = result(await client.call_tool('project_info', {'sections': ['models']}))
        return {it['model'] for it in info['models']}

    used = result(await client.call_tool('use_project', {'directory': str(first)}))
    assert used['directory'] == str(first.resolve())
    assert used['settings'] == 'sample.settings' and used['python'] == sys.executable
    assert used['frontend'] is False and used['ports'] is None and used['env_keys'] is None
    assert used['env_reason'] == 'The project has no .env.'
    assert used['rules'] == rules.RULES
    assert 'shop.Coupon' not in await models()

    result(await client.call_tool('use_project', {'directory': str(second)}))
    assert 'shop.Coupon' in await models()
    assert result(await client.call_tool('project_status', {}))['directory'] == str(second.resolve())

    # what is not a project is refused, the project served stays
    assert error(await client.call_tool('use_project', {'directory': 'first'})) == (
        'first is not an absolute path.'
    )
    assert 'is not a project: it has no manage.py' in error(
        await client.call_tool('use_project', {'directory': str(tmp_path)})
    )
    assert project.project_dir == second.resolve()


async def test_project_status_names_the_variables_of_env_only(client, monkeypatch, tmp_path):
    shutil.copytree(SAMPLE_DIR, tmp_path / 'sample', ignore=shutil.ignore_patterns('__pycache__'))
    directory = tmp_path / 'sample'
    monkeypatch.setattr(project, 'project_dir', directory)
    (directory / '.env').write_text(
        '# a comment\nBS_SECRET_KEY=value-of-the-secret\n\nexport BS_DEBUG=true\n'
        'not a variable\nBS_EMPTY=\n'
        'BS_PEM="-----BEGIN PRIVATE KEY-----\nLEAKED=pem-body\n-----END PRIVATE KEY-----"\n'
    )

    call_result = await client.call_tool('project_status', {})
    status = result(call_result)
    # the lines of a value in quotes are not variables
    assert status['env_keys'] == ['BS_SECRET_KEY', 'BS_DEBUG', 'BS_EMPTY', 'BS_PEM']
    assert status['env_reason'] is None
    for value in ('value-of-the-secret', 'LEAKED', 'pem-body'):
        assert value not in text_of(call_result)

    # the lines without `=` (a pasted token, the lines of a PEM without quotes) and the names
    # that are no identifiers (the last line of that PEM) are not variables; a value of
    # base64 keeps its name
    (directory / '.env').write_text(
        'BS_A=1\nghp_PastedToken0123456789\nBS_KEY=YWJjZA==\nmy-key=x\n'
        'BS_PEM=-----BEGIN PRIVATE KEY-----\nMIIEvQIBADANBgkqhkiG9w0BAQEFAASC\n'
        'h5Lk+9w0B/AQEFAASC==\n-----END PRIVATE KEY-----\nBS_B=2\n'
    )
    call_result = await client.call_tool('project_status', {})
    assert result(call_result)['env_keys'] == ['BS_A', 'BS_KEY', 'BS_PEM', 'BS_B']
    for value in ('ghp_PastedToken', 'YWJjZA', 'MIIEvQIBADAN', 'h5Lk', 'my-key'):
        assert value not in text_of(call_result)

    # a .env of another directory is not read
    outside = tmp_path / 'secrets.env'
    outside.write_text('BS_OTHER=secret-of-another-directory\n')
    (directory / '.env').unlink()
    (directory / '.env').symlink_to(outside)
    call_result = await client.call_tool('project_status', {})
    status = result(call_result)
    assert status['env_keys'] is None
    assert status['env_reason'] == '.env links outside the project directory: it is not read.'
    assert 'BS_OTHER' not in text_of(call_result)


async def test_project_status_names_the_database(client, monkeypatch, tmp_path):
    """
    The name of the database as the settings take it: from the environment of the server,
    which the commands of the project get, else from its env file (`BS_ENV_FILE` of that
    environment, `.env` by default), else from `project.env`.
    """
    (tmp_path / 'manage.py').write_text('')
    monkeypatch.setattr(project, 'project_dir', tmp_path)
    monkeypatch.delenv('BS_DATABASES__DEFAULT__NAME', raising=False)
    monkeypatch.delenv('BS_ENV_FILE', raising=False)

    async def name():
        return result(await client.call_tool('project_status', {}))['database_name']

    assert await name() is None
    (tmp_path / 'project.env').write_text('BS_DATABASES__DEFAULT__NAME=shared\n')
    assert await name() == 'shared'
    (tmp_path / '.env').write_text('BS_SECRET_KEY=secret\nBS_DATABASES__DEFAULT__NAME=shop_2\n')
    assert await name() == 'shop_2'
    # the env file of `BS_ENV_FILE` of the environment instead of `.env`, as the settings read it
    monkeypatch.setenv('BS_ENV_FILE', 'local.env')
    assert await name() == 'shared'
    (tmp_path / 'local.env').write_text('BS_DATABASES__DEFAULT__NAME=local\n')
    assert await name() == 'local'
    # an env file outside the project is not read, nor taken for absent
    outside = tmp_path.parent / f'{tmp_path.name}-outside.env'
    outside.write_text('BS_DATABASES__DEFAULT__NAME=outside\n')
    monkeypatch.setenv('BS_ENV_FILE', str(outside))
    assert await name() is None
    monkeypatch.setenv('BS_ENV_FILE', str(tmp_path / 'local.env'))
    assert await name() == 'local'
    monkeypatch.setenv('BS_DATABASES__DEFAULT__NAME', 'from_environment')
    assert await name() == 'from_environment'


@pytest.mark.parametrize('content', ['{"backend": 8001', '[]', '{"backend": "x"}'])
async def test_project_status_with_broken_ports(client, monkeypatch, tmp_path, content):
    (tmp_path / 'manage.py').write_text('')
    (tmp_path / '.bazis').mkdir()
    (tmp_path / '.bazis' / 'ports.json').write_text(content)
    monkeypatch.setattr(project, 'project_dir', tmp_path)

    assert result(await client.call_tool('project_status', {}))['ports'] is None
    assert (tmp_path / '.bazis' / 'ports.json').read_text() == content  # only read


async def test_use_project_reads_the_facts_before_serving(client, tmp_path):
    """
    A project with a .env outside it is chosen without its variables; one whose facts
    cannot be read is refused and the project served stays.
    """
    directory = tmp_path / 'shop'
    shutil.copytree(SAMPLE_DIR, directory, ignore=shutil.ignore_patterns('__pycache__'))
    (tmp_path / 'secrets.env').write_text('BS_OTHER=1\n')
    (directory / '.env').symlink_to(tmp_path / 'secrets.env')

    used = result(await client.call_tool('use_project', {'directory': str(directory)}))
    assert used['directory'] == str(directory.resolve()) and used['env_keys'] is None
    assert project.project_dir == directory.resolve()

    broken = tmp_path / 'broken'
    broken.mkdir()
    (broken / 'manage.py').write_text('')
    (broken / '.env').write_text('BS_DEBUG=true\n')
    (broken / '.env').chmod(0)
    try:
        assert 'Permission denied' in error(
            await client.call_tool('use_project', {'directory': str(broken)})
        )
    finally:
        (broken / '.env').chmod(0o644)
    assert project.project_dir == directory.resolve()


async def test_use_project_keeps_the_options_of_the_command_line(client, monkeypatch, tmp_path):
    """
    The project of the command line chosen again keeps its --settings and --python; another
    project has its own.
    """
    other = tmp_path / 'other'
    shutil.copytree(SAMPLE_DIR, other, ignore=shutil.ignore_patterns('__pycache__'))
    project.configure(SAMPLE_DIR, 'sample.settings_local', '/opt/python/bin/python3')

    used = result(await client.call_tool('use_project', {'directory': str(SAMPLE_DIR)}))
    assert used['settings'] == 'sample.settings_local'
    assert used['python'] == '/opt/python/bin/python3'
    assert project.settings_module == 'sample.settings_local'
    assert project.python == '/opt/python/bin/python3'

    used = result(await client.call_tool('use_project', {'directory': str(other)}))
    assert used['settings'] == 'sample.settings' and used['python'] == sys.executable
    assert project.settings_module is None and project.python is None


def test_inside(monkeypatch, tmp_path):
    directory = tmp_path / 'shop'
    (directory / 'app').mkdir(parents=True)
    (directory / 'link').symlink_to(tmp_path)
    monkeypatch.setattr(project, 'project_dir', directory)

    assert project.inside('app/../models.py') == directory / 'models.py'
    assert project.inside(directory / 'app') == directory / 'app'
    for path in ('../other', tmp_path / 'other', 'link/other', '/etc/passwd'):
        with pytest.raises(project.ProjectError, match='is outside the project directory'):
            project.inside(path)

    monkeypatch.setattr(project, 'project_dir', None)
    with pytest.raises(project.ProjectError, match=project.NO_PROJECT):
        project.inside('app')


async def test_rules_resources(client):
    resource = await client.read_resource('bazis://rules')
    assert resource.contents[0].text == rules.RULES
    assert resource.contents[0].mime_type == 'text/markdown'
    resource = await client.read_resource('bazis://rules/frontend')
    assert resource.contents[0].text == rules.FRONTEND_RULES


async def test_project_prompts(client, monkeypatch, tmp_path):
    prompt = await client.get_prompt('new_project', {'description': 'A shop of books'})
    text = prompt.messages[0].content.text
    assert text.startswith('Create a Bazis project: A shop of books\n')
    assert '`create_project`' in text and '`next_steps`' in text
    assert text.index('`check_machine`') < text.index('`install_tools`') < text.index('`create_project`')
    assert '`run_command`' in text and '`start_server`' in text

    # the project served, without a frontend
    prompt = await client.get_prompt('change_project', {'request': 'Add coupons'})
    assert prompt.messages[0].content.text == prompts.change_prompt('Add coupons')

    # a product with a frontend: its steps and its ports
    (tmp_path / 'frontend').mkdir()
    (tmp_path / 'frontend' / 'bazis-front.lock.json').write_text('{}')
    monkeypatch.setattr(project, 'project_dir', tmp_path)
    prompt = await client.get_prompt('change_project', {'request': 'Add coupons'})
    assert prompt.messages[0].content.text == prompts.change_prompt(
        'Add coupons', ports=scaffold.project_ports(tmp_path)
    )

    # no project: it is chosen first
    monkeypatch.setattr(project, 'project_dir', None)
    prompt = await client.get_prompt('change_project', {'request': 'Add coupons'})
    text = prompt.messages[0].content.text
    assert text.startswith('Call `use_project` with the directory of the project first')
    assert text.endswith(prompts.change_prompt('Add coupons'))


@pytest.mark.parametrize('in_project', [True, False])
def test_main_without_a_project_directory(monkeypatch, tmp_path, in_project):
    """
    Without --project-dir the current directory is the project when it has manage.py; else
    there is none until create_project or use_project.
    """
    from bazis.contrib.mcp import server as server_module

    monkeypatch.setattr(server_module.server, 'run', lambda: None)
    monkeypatch.setattr(server_module.processes, 'stop_on_signals', lambda: None)
    monkeypatch.setattr(project, 'project_dir', None)
    if in_project:
        (tmp_path / 'manage.py').write_text('')
    monkeypatch.chdir(tmp_path)

    server_module.main([])

    assert project.project_dir == (tmp_path.resolve() if in_project else None)


async def test_stdio_server_without_a_project(tmp_path):
    """
    `bazis-mcp` started outside a project, as a client starts `uvx bazis-mcp`: the project
    tools say that there is none and name the project of its directory, the catalog and the
    rules are there.
    """
    (tmp_path / 'shop').mkdir()
    (tmp_path / 'shop' / 'manage.py').write_text('')
    params = StdioServerParameters(
        command=sys.executable,
        args=['-m', 'bazis.contrib.mcp.server'],
        env={key: value for key, value in os.environ.items() if key != 'DJANGO_SETTINGS_MODULE'},
        cwd=tmp_path,
    )
    async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
        await session.initialize()
        status = await session.call_tool('project_status', {})
        packages = await session.call_tool('list_packages', {})
        resource = await session.read_resource('bazis://rules')

    assert status.is_error and status.content[0].text.endswith(
        f'{project.NO_PROJECT} The projects in the current directory: '
        f'use_project("{tmp_path.resolve() / "shop"}").'
    )
    assert not packages.is_error
    assert all(it['installed_version'] is None for it in result(packages)['packages'])
    assert resource.contents[0].text == rules.RULES
