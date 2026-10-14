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

import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from bazis.contrib.mcp import catalog, project, prompts, rules, scaffold

from .support import SAMPLE_DIR, make_venv, result, site_packages


pytestmark = pytest.mark.anyio

#: the existing tools, which need a project
PROJECT_TOOLS = {
    'list_packages': {},
    'package_guide': {'name': 'bazis'},
    'guide_search': {'query': 'routes'},
    'project_info': {},
    'run_doctor': {},
    'front_check': {},
    'front_status': {},
    'front_catalog': {},
    'project_status': {},
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


async def test_tools_without_a_project(client, no_project):
    for name, args in PROJECT_TOOLS.items():
        assert error(await client.call_tool(name, args)) == project.NO_PROJECT, name


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
    assert {'BS_SECRET_KEY', 'BS_DATABASES__DEFAULT__PASSWORD'} <= set(status['env_keys'])
    doctor = result(await client.call_tool('run_doctor', {}))
    assert doctor['ok'] is True, doctor

    # the values of .env are never returned
    secret = next(
        line.split('=', 1)[1] for line in (directory / '.env').read_text().splitlines()
        if line.startswith('BS_SECRET_KEY=')
    )
    assert secret not in text_of(call_result)
    assert secret not in text_of(await client.call_tool('project_status', {}))


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
    )

    call_result = await client.call_tool('project_status', {})
    assert result(call_result)['env_keys'] == ['BS_SECRET_KEY', 'BS_DEBUG', 'BS_EMPTY']
    assert 'value-of-the-secret' not in text_of(call_result)

    # a .env of another directory is not read
    outside = tmp_path / 'secrets.env'
    outside.write_text('BS_OTHER=1\n')
    (directory / '.env').unlink()
    (directory / '.env').symlink_to(outside)
    assert 'is outside the project directory' in error(await client.call_tool('project_status', {}))


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
    monkeypatch.setattr(project, 'project_dir', None)
    if in_project:
        (tmp_path / 'manage.py').write_text('')
    monkeypatch.chdir(tmp_path)

    server_module.main([])

    assert project.project_dir == (tmp_path.resolve() if in_project else None)


async def test_stdio_server_without_a_project(tmp_path):
    """
    `bazis-mcp` started outside a project, as a client starts `uvx bazis-mcp`: the project
    tools say that there is none, the rules are there.
    """
    params = StdioServerParameters(
        command=sys.executable,
        args=['-m', 'bazis.contrib.mcp.server'],
        env={key: value for key, value in os.environ.items() if key != 'DJANGO_SETTINGS_MODULE'},
        cwd=tmp_path,
    )
    async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
        await session.initialize()
        packages = await session.call_tool('list_packages', {})
        resource = await session.read_resource('bazis://rules')

    assert packages.is_error and packages.content[0].text.endswith(project.NO_PROJECT)
    assert resource.contents[0].text == rules.RULES
