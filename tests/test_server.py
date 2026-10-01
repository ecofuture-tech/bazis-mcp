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
import sys
from importlib import metadata
from pathlib import Path

import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from bazis.contrib.mcp import catalog, project


pytestmark = pytest.mark.anyio

SAMPLE_DIR = Path(__file__).resolve().parent.parent / 'sample'


def result(call_result):
    """
    The value a tool returned: the JSON text that every client reads.
    """
    assert not call_result.is_error, call_result.content
    return json.loads(call_result.content[0].text)


async def test_tools_are_read_only(client):
    tools = (await client.list_tools()).tools
    assert {it.name for it in tools} == {
        'list_packages', 'package_guide', 'project_info', 'run_doctor'
    }
    assert all(it.annotations.read_only_hint for it in tools)


async def test_list_packages(client):
    packages = {
        it['name']: it for it in result(await client.call_tool('list_packages', {}))['packages']
    }

    # every released package, also those not installed
    assert set(catalog.catalog()) <= set(packages)
    assert packages['bazis']['installed_version'] == metadata.version('bazis')
    assert packages['bazis-mcp']['installed_version'] == metadata.version('bazis-mcp')

    permit = packages['bazis-permit']
    assert permit['installed_version'] is None
    assert permit['catalog_version'] == catalog.catalog()['bazis-permit']['version']
    assert 'bazis-users' in permit['requires']
    assert permit['solves']


async def test_package_guide_of_a_package_not_installed(client):
    guide = result(await client.call_tool('package_guide', {'name': 'bazis-permit'}))

    assert guide['installed_version'] is None
    assert 'PermitRouteBase' in guide['agents_md']
    points = {it['name']: it['import'] for it in guide['manifest']['extension_points']}
    assert points['PermitRouteBase'] == 'bazis.contrib.permit.routes_abstract.PermitRouteBase'


async def test_package_guide_of_an_installed_package_is_read_from_it(client):
    from importlib import resources

    guide = result(await client.call_tool('package_guide', {'name': 'bazis'}))

    installed = (resources.files('bazis.core') / 'AGENTS.md').read_text(encoding='utf-8')
    assert guide['installed_version'] == metadata.version('bazis')
    assert guide['agents_md'] == installed
    assert guide['manifest']['package']['name'] == 'bazis'


async def test_package_guide_of_an_unknown_package(client):
    call_result = await client.call_tool('package_guide', {'name': 'bazis-unknown'})

    assert call_result.is_error
    assert 'bazis-permit' in call_result.content[0].text


async def test_project_info(client):
    info = result(
        await client.call_tool('project_info', {'sections': ['models', 'routes', 'settings']})
    )

    assert set(info) == {'models', 'routes', 'settings'}
    product = next(it for it in info['models'] if it['model'] == 'shop.Product')
    assert product['resource'] == 'shop.product'
    assert {'name': 'category', 'model': 'shop.Category', 'to_many': False, 'reverse': False} in (
        product['relations']
    )
    route_sets = {it['route_set'] for it in info['routes']}
    assert 'shop.routes.ProductRouteSet' in route_sets

    settings = {it['name']: it for it in info['settings']}
    assert settings['SECRET_KEY']['value'] == '***'


async def test_run_doctor(client):
    report = result(await client.call_tool('run_doctor', {}))
    assert report == {'ok': True, 'messages': []}

    report = result(await client.call_tool('run_doctor', {'deploy': True}))
    messages = {it['id']: it for it in report['messages']}
    assert messages['bazis.W001']['level'] == 'warning'  # the sample allows any host
    # pytest-django sets the locmem email backend, an error of the deployment checks
    assert messages['mail.E001']['level'] == 'error'
    assert report['ok'] is False


async def test_project_tools_report_a_project_that_cannot_load(client, monkeypatch):
    monkeypatch.setattr(project, '_setup_error', 'The settings x cannot be loaded: boom')

    for name in ('project_info', 'run_doctor'):
        call_result = await client.call_tool(name, {})
        assert call_result.is_error
        assert 'boom' in call_result.content[0].text

    # the catalog works without the project
    assert result(await client.call_tool('list_packages', {}))


async def test_agents_md_resource(client):
    resource = await client.read_resource('bazis://packages/bazis-permit/agents.md')

    assert resource.contents[0].text == catalog.catalog()['bazis-permit']['agents_md']
    assert resource.contents[0].mime_type == 'text/markdown'


async def test_prompts(client):
    assert {it.name for it in (await client.list_prompts()).prompts} == {
        'add_package', 'audit_project'
    }
    prompt = await client.get_prompt('add_package', {'name': 'bazis-author'})
    assert 'package_guide("bazis-author")' in prompt.messages[0].content.text


def test_find_settings(tmp_path, monkeypatch):
    monkeypatch.delenv('DJANGO_SETTINGS_MODULE', raising=False)
    assert project.find_settings(tmp_path) is None

    (tmp_path / 'manage.py').write_text(
        "os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'myproject.settings')\n"
    )
    assert project.find_settings(tmp_path) == 'myproject.settings'

    monkeypatch.setenv('DJANGO_SETTINGS_MODULE', 'other.settings')
    assert project.find_settings(tmp_path) == 'other.settings'


async def test_stdio_server():
    """
    The command `bazis-mcp` serves the project in its directory over stdio: whatever the
    project prints while loading must not break the protocol.
    """
    env = {key: value for key, value in os.environ.items() if key != 'DJANGO_SETTINGS_MODULE'}
    params = StdioServerParameters(
        command=sys.executable,
        args=['-m', 'bazis.contrib.mcp.server', '--project-dir', str(SAMPLE_DIR)],
        env=env,
    )
    async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
        await session.initialize()
        report = result(await session.call_tool('run_doctor', {}))
        info = result(await session.call_tool('project_info', {'sections': ['models']}))

    assert report['ok'] is True, json.dumps(report)
    assert 'shop.Product' in {it['model'] for it in info['models']}


def test_main_keeps_stdout_for_the_protocol(monkeypatch, capsys, tmp_path):
    from bazis.contrib.mcp import server as server_module

    calls = []
    monkeypatch.setattr(
        project, 'setup', lambda *args: (print('loading the project'), calls.append(args))
    )
    monkeypatch.setattr(server_module.server, 'run', lambda: calls.append('run'))

    server_module.main(['--project-dir', str(tmp_path), '--settings', 'myproject.settings'])

    assert calls == [(tmp_path.resolve(), 'myproject.settings'), 'run']
    captured = capsys.readouterr()
    assert captured.out == ''
    assert 'loading the project' in captured.err
