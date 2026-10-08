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
        'list_packages', 'package_guide', 'project_info', 'run_doctor',
        'front_check', 'front_status', 'front_catalog',
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
    assert permit['guide_version'] == permit['catalog_version']
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


async def test_package_guide_of_a_package_installed_without_a_guide(client, monkeypatch):
    # bazis-permit before 2.4 ships no AGENTS.md and no manifest: the catalog describes it
    old = {'name': 'bazis-permit', 'version': '2.3.1', 'module': 'bazis.contrib.permit',
           'manifest': None, 'agents_md': None}
    monkeypatch.setattr(catalog.introspect, 'packages', lambda: [old])

    guide = result(await client.call_tool('package_guide', {'name': 'bazis-permit'}))

    assert guide['installed_version'] == '2.3.1'
    assert guide['guide_version'] == catalog.catalog()['bazis-permit']['version']
    assert guide['agents_md'] == catalog.catalog()['bazis-permit']['agents_md']


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
    assert report['ok'] is True


async def test_project_tools_report_a_project_that_cannot_load(client, monkeypatch):
    monkeypatch.setattr(project, 'settings_module', 'missing.settings')

    for name, args in [
        ('project_info', {}), ('project_info', {'sections': ['models']}), ('run_doctor', {}),
        ('front_check', {}),
    ]:
        call_result = await client.call_tool(name, args)
        assert call_result.is_error
        assert 'missing' in call_result.content[0].text

    # the catalog and the installed packages work without the project
    assert result(await client.call_tool('list_packages', {}))
    info = result(await client.call_tool('project_info', {'sections': ['packages']}))
    assert 'bazis' in {it['name'] for it in info['packages']}


@pytest.mark.parametrize('case', ['no manage.py', 'no directory'])
def test_project_errors(tmp_path, monkeypatch, case):
    monkeypatch.delenv('DJANGO_SETTINGS_MODULE', raising=False)
    monkeypatch.setattr(project, 'settings_module', None)
    monkeypatch.setattr(
        project, 'project_dir', tmp_path / 'missing' if case == 'no directory' else tmp_path
    )

    with pytest.raises(project.ProjectError):
        project.doctor()


async def test_project_changes_are_seen_without_restarting(client, monkeypatch, tmp_path):
    """
    An agent changes the project while the server runs: the next call sees the change.
    """
    import shutil

    copy = tmp_path / 'sample'
    shutil.copytree(SAMPLE_DIR, copy, ignore=shutil.ignore_patterns('__pycache__'))
    monkeypatch.setattr(project, 'project_dir', copy)
    monkeypatch.setattr(project, 'settings_module', 'sample.settings')

    def models():
        return {it['model'] for it in project.info(['models'])['models']}

    assert 'shop.Coupon' not in models()
    with (copy / 'shop' / 'models.py').open('a') as file:
        file.write("\n\nclass Coupon(DtMixin, UuidMixin, JsonApiMixin):\n"
                   "    code = models.CharField('Code', max_length=20)\n")
    assert 'shop.Coupon' in models()


def test_json_after_other_output():
    assert project.parse_json('loading...\n[{"id": "x"}]\n') == [{'id': 'x'}]
    assert project.parse_json('nothing') is None


async def test_agents_md_resource(client):
    resource = await client.read_resource('bazis://packages/bazis-permit/agents.md')

    assert resource.contents[0].text == catalog.catalog()['bazis-permit']['agents_md']
    assert resource.contents[0].mime_type == 'text/markdown'


async def test_prompts(client):
    assert {it.name for it in (await client.list_prompts()).prompts} == {
        'add_package', 'audit_project', 'build_frontend'
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
    The command `bazis-mcp` serves the project in its directory over stdio.
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


async def test_stdio_server_with_settings_that_fail():
    params = StdioServerParameters(
        command=sys.executable,
        args=['-m', 'bazis.contrib.mcp.server', '--project-dir', str(SAMPLE_DIR),
              '--settings', 'missing.settings'],
        env={key: value for key, value in os.environ.items() if key != 'DJANGO_SETTINGS_MODULE'},
    )
    async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
        await session.initialize()
        doctor = await session.call_tool('run_doctor', {})
        packages = result(await session.call_tool('list_packages', {}))

    assert doctor.is_error
    assert "No module named 'missing'" in doctor.content[0].text
    assert packages['packages']


def test_main(monkeypatch, tmp_path):
    from bazis.contrib.mcp import server as server_module

    monkeypatch.setattr(server_module.server, 'run', lambda: None)
    monkeypatch.setattr(project, 'project_dir', project.project_dir)
    monkeypatch.setattr(project, 'settings_module', None)
    monkeypatch.setattr(project, 'python', None)

    server_module.main(['--project-dir', str(tmp_path), '--settings', 'myproject.settings'])

    assert project.project_dir == tmp_path.resolve()
    assert project.settings_module == 'myproject.settings'
    assert project.python is None


def test_find_python(tmp_path, monkeypatch):
    monkeypatch.setattr(project, 'python', None)
    assert project.find_python(tmp_path / 'app') == sys.executable

    venv_python = tmp_path / '.venv' / 'bin' / 'python'
    venv_python.parent.mkdir(parents=True)
    venv_python.touch()
    assert project.find_python(tmp_path / 'app') == str(venv_python)  # the venv of the parent

    monkeypatch.setattr(project, 'python', '/usr/bin/python3')
    assert project.find_python(tmp_path / 'app') == '/usr/bin/python3'
