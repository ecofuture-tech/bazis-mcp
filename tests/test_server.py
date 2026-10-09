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
from mcp.shared.exceptions import MCPError

from bazis.contrib.mcp import catalog, project


pytestmark = pytest.mark.anyio

SAMPLE_DIR = Path(__file__).resolve().parent.parent / 'sample'


def size(call_result) -> int:
    """
    The bytes of the text of a tool result, as a client receives it.
    """
    return len(call_result.content[0].text.encode())


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

    guide, text = await read_whole_guide(client, 'bazis')

    installed = (resources.files('bazis.core') / 'AGENTS.md').read_text(encoding='utf-8')
    assert guide['installed_version'] == metadata.version('bazis')
    assert text == installed
    assert {'Models', 'Routes', 'Rules'} <= set(guide['sections'])
    assert guide['manifest']['package']['name'] == 'bazis'


def fake_package(site: Path, version: str, guide: str):
    """
    Installs the distribution bazis-fake (the module `bazis_fake` with its guide) of a
    `version` into the directory `site`, replacing the one there.
    """
    for old in site.glob('bazis_fake-*.dist-info'):
        for file in old.iterdir():
            file.unlink()
        old.rmdir()
    dist_info = site / f'bazis_fake-{version}.dist-info'
    dist_info.mkdir(parents=True)
    (dist_info / 'METADATA').write_text(
        f'Metadata-Version: 2.1\nName: bazis-fake\nVersion: {version}\n'
    )
    module = site / 'bazis_fake'
    module.mkdir(exist_ok=True)
    (module / '__init__.py').write_text('')
    (module / 'AGENTS.md').write_text(guide)
    (module / 'bazis_manifest.toml').write_text('[package]\nname = "bazis-fake"\n')


async def test_packages_are_those_of_the_python_of_the_project_at_every_call(
    client, monkeypatch, tmp_path
):
    """
    The installed packages and their guides are read from the Python of the project, not
    from that of the server (bazis-cli runs the server with its own), and again at every
    call: a package installed or upgraded while the server runs is seen.
    """
    site = tmp_path / 'site-packages'
    # only the processes of the project see this directory, not the server
    monkeypatch.setenv('PYTHONPATH', str(site))
    fake_package(site, '1.0.0', '# bazis-fake\n\nThe guide of 1.0.0.\n')

    def packages(info):
        return {it['name']: it for it in info['packages']}

    listed = packages(result(await client.call_tool('list_packages', {})))
    assert listed['bazis-fake']['installed_version'] == '1.0.0'
    guide = result(await client.call_tool('package_guide', {'name': 'bazis-fake'}))
    assert guide['agents_md'] == '# bazis-fake\n\nThe guide of 1.0.0.\n'

    fake_package(site, '1.1.0', '# bazis-fake\n\nThe guide of 1.1.0.\n')

    listed = packages(result(await client.call_tool('list_packages', {})))
    assert listed['bazis-fake']['installed_version'] == '1.1.0'
    guide = result(await client.call_tool('package_guide', {'name': 'bazis-fake'}))
    assert (guide['installed_version'], guide['guide_version']) == ('1.1.0', '1.1.0')
    assert guide['agents_md'] == '# bazis-fake\n\nThe guide of 1.1.0.\n'
    info = result(await client.call_tool('project_info', {'sections': ['packages']}))
    assert packages(info)['bazis-fake']['version'] == '1.1.0'


async def test_packages_of_a_python_without_bazis(client, monkeypatch, tmp_path):
    """
    A project whose Python has no Bazis yet: the catalog describes every package.
    """
    import venv

    venv.create(tmp_path / '.venv', with_pip=False, symlinks=sys.platform != 'win32')
    monkeypatch.setattr(project, 'project_dir', tmp_path)
    monkeypatch.setattr(project, 'python', None)  # .venv of the project directory

    listed = result(await client.call_tool('list_packages', {}))['packages']
    assert {it['name'] for it in listed} == set(catalog.catalog())
    assert all(it['installed_version'] is None for it in listed)


async def test_packages_of_a_python_with_a_bazis_before_the_introspection(
    client, monkeypatch, tmp_path
):
    """
    A Bazis older than `bazis.core.introspect` (2.4) in the Python of the project: its
    packages are listed with their versions, and the catalog gives their guides.
    """
    import venv

    venv.create(tmp_path / '.venv', with_pip=False, symlinks=sys.platform != 'win32')
    monkeypatch.setattr(project, 'project_dir', tmp_path)
    monkeypatch.setattr(project, 'python', None)
    site = Path(project.run(
        'site', '-c', "import sysconfig; print(sysconfig.get_paths()['purelib'])"
    ).stdout.strip())
    for name, version in (('bazis', '2.3.0'), ('bazis_permit', '2.3.1')):
        dist_info = site / f'{name}-{version}.dist-info'
        dist_info.mkdir()
        (dist_info / 'METADATA').write_text(
            f'Metadata-Version: 2.1\nName: {name.replace("_", "-")}\nVersion: {version}\n'
        )
    (site / 'bazis' / 'core').mkdir(parents=True)  # without introspect.py
    (site / 'bazis' / 'core' / '__init__.py').write_text('')

    listed = {
        it['name']: it for it in result(await client.call_tool('list_packages', {}))['packages']
    }
    assert listed['bazis']['installed_version'] == '2.3.0'
    assert listed['bazis-users']['installed_version'] is None
    guide = result(await client.call_tool('package_guide', {'name': 'bazis-permit'}))
    assert guide['installed_version'] == '2.3.1'
    assert guide['guide_version'] == catalog.catalog()['bazis-permit']['version']
    assert 'PermitRouteBase' in guide['agents_md']


async def test_packages_of_a_python_that_fails(client, monkeypatch, tmp_path):
    monkeypatch.setattr(project, 'python', str(tmp_path / 'missing' / 'python'))

    call_result = await client.call_tool('list_packages', {})
    assert call_result.is_error
    assert 'cannot run the Python of the project' in call_result.content[0].text

    # the resource of the guides says why too
    with pytest.raises(MCPError) as error:
        await client.read_resource('bazis://packages/bazis-permit/agents.md')
    assert 'cannot run the Python of the project' in str(error.value)


async def test_package_guide_of_a_package_installed_without_a_guide(client, monkeypatch):
    # bazis-permit before 2.4 ships no AGENTS.md and no manifest: the catalog describes it
    old = {'name': 'bazis-permit', 'version': '2.3.1', 'module': 'bazis.contrib.permit',
           'manifest': None, 'agents_md': None}
    monkeypatch.setattr(project, 'packages', lambda: [old])

    guide = result(await client.call_tool('package_guide', {'name': 'bazis-permit'}))

    assert guide['installed_version'] == '2.3.1'
    assert guide['guide_version'] == catalog.catalog()['bazis-permit']['version']
    assert guide['agents_md'] == catalog.catalog()['bazis-permit']['agents_md']


async def test_package_guide_of_an_unknown_package(client):
    call_result = await client.call_tool('package_guide', {'name': 'bazis-unknown'})

    assert call_result.is_error
    assert 'bazis-permit' in call_result.content[0].text


#: a paragraph of a guide, about 16,000 characters
PARAGRAPH = 'A line of the guide that says what to do and why it matters.\n' * 260

#: a guide longer than the limit of a result: the introduction, a `## ` line in a code block
#: (not a heading), a section with a subsection longer than the limit, a short section
LONG_GUIDE = (
    '# bazis-long\n\nThe introduction.\n\n'
    f'## Setup\n\n{PARAGRAPH}\n```markdown\n## not a heading\n```\n\n'
    f'## Models\n\n{PARAGRAPH}\n### Details\n\n{PARAGRAPH}\n'
    '## Rules\n\nShort.\n'
)


@pytest.fixture
def long_guide(monkeypatch):
    package = {'name': 'bazis-long', 'installed_version': '1.0.0', 'catalog_version': None,
               'guide_version': '1.0.0', 'manifest': {'package': {'name': 'bazis-long'}},
               'agents_md': LONG_GUIDE}
    monkeypatch.setattr(catalog, 'packages', lambda: {'bazis-long': package})


async def test_a_long_guide_is_read_by_sections(client, long_guide):
    """
    A guide longer than the limit comes as its introduction and the titles of its sections,
    which are read one by one; together they are the whole guide.
    """
    call_result = await client.call_tool('package_guide', {'name': 'bazis-long'})
    guide = result(call_result)

    assert len(LONG_GUIDE) > catalog.GUIDE_LIMIT
    assert size(call_result) < catalog.GUIDE_LIMIT
    assert guide['complete'] is False
    assert guide['agents_md'] == '# bazis-long\n\nThe introduction.\n\n'
    assert guide['manifest'] == {'package': {'name': 'bazis-long'}}
    assert guide['sections'] == ['Setup', 'Models (1/2)', 'Models (2/2)', 'Rules']

    texts = [guide['agents_md']]
    for title in guide['sections']:
        call_result = await client.call_tool(
            'package_guide', {'name': 'bazis-long', 'section': title}
        )
        section = result(call_result)
        assert size(call_result) <= catalog.RESULT_LIMIT
        assert section['section'] == title and 'manifest' not in section
        assert section['sections'] == guide['sections']
        texts.append(section['agents_md'])
    assert ''.join(texts) == LONG_GUIDE
    assert texts[1].startswith('## Setup\n') and '## not a heading' in texts[1]
    assert texts[2].startswith('## Models\n') and '### Details' in texts[2] + texts[3]

    # the title as written in the guide, in any case
    for title in ('rules', '## Rules', ' RULES '):
        rules = result(await client.call_tool(
            'package_guide', {'name': 'bazis-long', 'section': title}
        ))
        assert rules['agents_md'] == '## Rules\n\nShort.\n'


async def test_an_unknown_section_of_a_guide(client, long_guide):
    call_result = await client.call_tool(
        'package_guide', {'name': 'bazis-long', 'section': 'Models'}
    )

    assert call_result.is_error
    assert 'Setup, Models (1/2), Models (2/2), Rules' in call_result.content[0].text


async def read_whole_guide(client, name: str) -> tuple[dict, str]:
    """
    The default result of the guide of a package and the text of the guide put together
    from its results; every result fits in RESULT_LIMIT.
    """
    call_result = await client.call_tool('package_guide', {'name': name})
    assert size(call_result) <= catalog.RESULT_LIMIT, name
    guide = result(call_result)
    if guide['complete']:
        return guide, guide['agents_md'] or ''
    texts = []
    if not guide['sections'] or not guide['sections'][0].startswith(catalog.INTRODUCTION):
        texts.append(guide['agents_md'])  # an introduction that is not split
    for title in guide['sections']:
        call_result = await client.call_tool('package_guide', {'name': name, 'section': title})
        assert size(call_result) <= catalog.RESULT_LIMIT, (name, title)
        texts.append(result(call_result)['agents_md'])
    return guide, ''.join(texts)


async def test_every_guide_fits_in_a_result(client):
    """
    The guides of the catalog and of the installed packages: the default result and every
    section stay under the limits of the MCP clients on the output of a tool, and together
    they are the whole guide. The guide of the core with its manifest is over the limit
    though its text alone is not: it is read by sections.
    """
    for name, package in catalog.packages().items():
        guide, text = await read_whole_guide(client, name)
        assert text == (package['agents_md'] or ''), name
    core = catalog.packages()['bazis']
    if catalog.json_size(core['agents_md']) + catalog.json_size(core['manifest']) > (
        catalog.RESULT_LIMIT
    ):
        guide, _ = await read_whole_guide(client, 'bazis')
        assert guide['complete'] is False and guide['sections']


async def test_a_guide_that_is_hard_to_fit(client, monkeypatch):
    """
    The limit is that of the JSON of a result: a text under GUIDE_LIMIT characters with a
    large manifest, characters that JSON escapes or encodes in several bytes, a long
    introduction and a line longer than the limit are all served within it.
    """
    escaped = 'A "quoted" \\path\\ and\ttabs: Кириллица — ✓.\n' * 400
    manifest = {'package': {'name': 'bazis-hard', 'solves': ['x' * 100] * 150}}
    guide_text = (
        '# bazis-hard\n\n' + escaped + '## Setup\n\n' + escaped * 2
        + '## Line\n\n' + 'y' * 100_000 + '\n## Rules\n\nShort.\n'
    )
    package = {'name': 'bazis-hard', 'installed_version': '1.0.0', 'catalog_version': None,
               'guide_version': '1.0.0', 'manifest': manifest, 'agents_md': guide_text}
    monkeypatch.setattr(catalog, 'packages', lambda: {'bazis-hard': package})

    guide, text = await read_whole_guide(client, 'bazis-hard')

    assert text == guide_text
    assert guide['complete'] is False and guide['manifest'] == manifest
    assert any(it.startswith('Line (') for it in guide['sections'])

    # the text alone under GUIDE_LIMIT characters, but not its JSON with the manifest
    package['agents_md'] = '# bazis-hard\n\n' + escaped[: catalog.GUIDE_LIMIT - 100]
    assert len(package['agents_md']) < catalog.GUIDE_LIMIT
    guide, text = await read_whole_guide(client, 'bazis-hard')
    assert text == package['agents_md'] and guide['complete'] is False


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
        ('project_info', {}), ('project_info', {'sections': ['models']}), ('run_doctor', {})
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

    with pytest.raises(project.ProjectError) as error:
        project.doctor()
    if case == 'no directory':
        assert 'does not exist' in str(error.value)
    else:
        assert 'No settings module' in str(error.value)


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


@pytest.mark.parametrize('guide_text', [
    pytest.param('# bazis-long\n\n' + PARAGRAPH * 2, id='no-headings'),
    pytest.param(
        '# bazis-long\n\n' + PARAGRAPH * 2 + '## Rules\n\nShort.\n', id='long-introduction'
    ),
])
def test_every_listed_section_of_a_guide_is_retrievable(guide_text):
    """
    The parts of an introduction longer than the limit are listed under the title
    `Introduction (i/n)` and can be requested by it; the parts make up the whole guide.
    """
    package = {'name': 'bazis-long', 'installed_version': '1.0.0', 'catalog_version': None,
               'guide_version': '1.0.0', 'manifest': None, 'agents_md': guide_text}
    listed = catalog.guide(package)['sections']

    assert listed[:2] == ['Introduction (1/2)', 'Introduction (2/2)']
    texts = [catalog.guide(package, title)['agents_md'] for title in listed]
    assert ''.join(texts) == guide_text
    assert catalog.guide(package, 'introduction (2/2)')['agents_md'] == texts[1]
    with pytest.raises(KeyError) as error:
        catalog.guide(package, 'Missing')
    assert error.value.args == ('Missing', listed)
