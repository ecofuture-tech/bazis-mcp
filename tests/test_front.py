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
The tools of the frontend layer (bazis-front). The outputs of `manage.py bazis_front` and
`bazis_doctor` are faked where a case needs a frontend that the sample has not; the tests
at the end run them for real on a copy of the sample with bazis-front, when it is
installed.
"""

import json
import os
import shutil
import subprocess
import sys
from importlib import metadata
from importlib.util import find_spec
from pathlib import Path

import pytest

from bazis.contrib.mcp import catalog, front, project


pytestmark = pytest.mark.anyio

SAMPLE_DIR = Path(__file__).resolve().parent.parent / 'sample'

REGISTRY = {
    'registry': 1,
    'assets': [
        {'name': 'client', 'kind': 'vendored', 'source': 'client/src',
         'target': 'src/bazis/client', 'files': ['index.ts']},
        {'name': 'transit-bar', 'kind': 'ui', 'source': 'ui/transit-bar',
         'target': 'src/bazis/ui/transit-bar', 'files': ['index.ts'],
         'requires': {'capabilities': ['statusy'], 'assets': ['client']}},
        {'name': 'state-panel', 'kind': 'ui', 'source': 'ui/state-panel',
         'target': 'src/bazis/ui/state-panel', 'files': ['index.ts'], 'init': True},
    ],
}
SPEC_ISSUE = {
    'code': 'P011', 'file': 'spec/product.yaml', 'hint': 'Use the JSON:API type of a resource.',
    'layer': 'product', 'message': 'The resource `shop.missing` is not in the contract.',
    'path': '/entities/0/resource', 'severity': 'error',
}

requires_front = pytest.mark.skipif(
    find_spec('bazis.contrib.front') is None, reason='bazis-front is not installed'
)


def result(call_result):
    assert not call_result.is_error, call_result.content
    return json.loads(call_result.content[0].text)


def message(id_, text='', hint=None, level='warning'):
    return {'id': id_, 'level': level, 'message': text, 'hint': hint, 'object': None}


@pytest.fixture
def fake_run(monkeypatch):
    """
    Replaces the processes of the project: `outputs` are the (exit code, stdout, stderr)
    of the calls in their order; the command lines are recorded in `calls`.
    """
    class Fake:
        calls: list[list[str]] = []
        outputs: list[tuple[int, str, str]] = []

    def run(args, **kwargs):
        Fake.calls.append(args[1:])
        code, stdout, stderr = Fake.outputs.pop(0)
        return subprocess.CompletedProcess(args, code, stdout, stderr)

    monkeypatch.setattr(project.subprocess, 'run', run)
    return Fake


def probe_output(version=None, registry=None):
    return 0, json.dumps({'version': version, 'registry': registry}) + '\n', ''


async def test_front_check_reports_the_issues(client, fake_run):
    report = {'contract': True, 'errors': 1, 'warnings': 0, 'issues': [SPEC_ISSUE]}
    fake_run.outputs = [(1, json.dumps(report), 'CommandError: The specs have 1 errors.\n')]

    checked = result(await client.call_tool('front_check', {'layer': 'product'}))

    assert fake_run.calls == [
        ['-m', 'django', 'bazis_front', 'check', '--json', '--layer', 'product']
    ]
    assert checked == {'checked': True, 'ok': False, **report}


async def test_front_check_of_valid_specs(client, fake_run):
    report = {'contract': False, 'errors': 0, 'warnings': 0, 'issues': []}
    fake_run.outputs = [(0, json.dumps(report), '')]

    checked = result(await client.call_tool('front_check', {}))

    assert fake_run.calls == [['-m', 'django', 'bazis_front', 'check', '--json']]
    assert checked['checked'] is True and checked['ok'] is True


async def test_front_check_without_spec(client, fake_run):
    refusal = '/app/spec does not exist: `manage.py bazis_front init` creates it with the frontend.'
    fake_run.outputs = [(1, '', f'CommandError: {refusal}\n')]

    checked = result(await client.call_tool('front_check', {}))

    assert checked == {'checked': False, 'reason': refusal}


async def test_front_check_of_a_layer_that_does_not_exist(client):
    call_result = await client.call_tool('front_check', {'layer': 'backend'})

    assert call_result.is_error


async def test_front_check_without_bazis_front(client):
    # the sample has no "bazis.contrib.front" in its INSTALLED_APPS: Django has no command
    checked = result(await client.call_tool('front_check', {}))

    assert checked == {'checked': False, 'reason': front.NOT_ENABLED}


async def test_front_status(client, fake_run):
    doctor = [
        message('front.W001', 'The contract is stale: contract.json differs from the backend.',
                'Export it with `manage.py bazis_front contract`.'),
        message('front.W005', 'The theme is stale.', 'Generate it with `manage.py bazis_front design`.'),
        message('front.W002', 'P011 (error) spec/product.yaml#/entities/0/resource: ...'),
        message('front.W002', 'P020 (warning) spec/product.yaml#/entities/0/access: ...'),
        message('front.I001', 'The contract is not checked: the database is not migrated.',
                level='info'),
        message('bazis.W001', 'ALLOWED_HOSTS allows any host.'),
    ]
    fake_run.outputs = [probe_output('1.0.0', REGISTRY), (0, json.dumps(doctor), '')]

    status = result(await client.call_tool('front_status', {}))

    assert fake_run.calls[1] == ['-m', 'django', 'bazis_doctor', '--json']
    assert status == {
        'checked': True,
        'version': '1.0.0',
        'up_to_date': False,
        'stale': {'contract': [doctor[0]], 'design': [doctor[1]]},
        'spec_issues': 2,
        'messages': [doctor[4]],
    }


async def test_front_status_up_to_date(client, fake_run):
    fake_run.outputs = [probe_output('1.0.0', REGISTRY), (0, '[]', '')]

    status = result(await client.call_tool('front_status', {}))

    assert status['up_to_date'] is True and status['stale'] == {}


async def test_front_status_without_bazis_front(client, fake_run):
    fake_run.outputs = [probe_output()]

    status = result(await client.call_tool('front_status', {}))

    assert status == {'checked': False, 'reason': front.NOT_INSTALLED}
    assert len(fake_run.calls) == 1  # the system checks are not run


async def test_front_status_of_an_application_that_cannot_load(client, fake_run):
    doctor = [message('bazis.app', "The application cannot be loaded: ImportError('x')",
                      level='critical')]
    fake_run.outputs = [probe_output('1.0.0', REGISTRY), (1, json.dumps(doctor), '')]

    call_result = await client.call_tool('front_status', {})

    assert call_result.is_error
    assert 'cannot be loaded' in call_result.content[0].text


async def test_front_catalog_of_the_installed_bazis_front(client, fake_run, monkeypatch):
    monkeypatch.setattr(catalog, 'catalog', lambda: {})
    fake_run.outputs = [probe_output('1.0.0', REGISTRY)]

    assets = result(await client.call_tool('front_catalog', {}))

    assert fake_run.calls == [['-c', front.PROBE]]
    assert assets['source'] == 'installed'
    assert assets['version'] == assets['installed_version'] == '1.0.0'
    assert assets['assets'] == [
        {'name': 'client', 'kind': 'vendored', 'target': 'src/bazis/client',
         'capabilities': [], 'requires': [], 'init': False},
        {'name': 'transit-bar', 'kind': 'ui', 'target': 'src/bazis/ui/transit-bar',
         'capabilities': ['statusy'], 'requires': ['client'], 'init': False},
        {'name': 'state-panel', 'kind': 'ui', 'target': 'src/bazis/ui/state-panel',
         'capabilities': [], 'requires': [], 'init': True},
    ]


async def test_front_catalog_from_the_catalog(client, fake_run, monkeypatch):
    entry = {'name': 'bazis-front', 'version': '1.1.0', 'manifest': {}, 'agents_md': '',
             'registry': REGISTRY}
    monkeypatch.setattr(catalog, 'catalog', lambda: {'bazis-front': entry})
    fake_run.outputs = [probe_output()]

    assets = result(await client.call_tool('front_catalog', {}))

    assert assets['source'] == 'catalog'
    assert assets['version'] == '1.1.0'
    assert assets['installed_version'] is None
    assert [it['name'] for it in assets['assets']] == ['client', 'transit-bar', 'state-panel']


async def test_front_catalog_without_bazis_front(client, fake_run, monkeypatch):
    monkeypatch.setattr(catalog, 'catalog', lambda: {})
    fake_run.outputs = [probe_output()]

    assets = result(await client.call_tool('front_catalog', {}))

    assert assets['source'] is None
    assert assets['assets'] == []
    assert 'pip install bazis-front' in assets['reason']


def test_probe_with_a_python_without_bazis_front(tmp_path, monkeypatch):
    """
    The probe runs in the Python of the project: one without bazis-front (here the Python of
    the tests without its site-packages) has none, and the catalog describes it when it has
    a release of it.
    """
    python = tmp_path / 'python'
    python.write_text(f'#!/bin/sh\nexec {sys.executable} -S "$@"\n')
    python.chmod(0o755)
    monkeypatch.setattr(project, 'python', str(python))

    assert front.package() is None
    assets = front.assets()
    if 'bazis-front' in catalog.catalog():
        assert assets['source'] == 'catalog'
    else:  # not released yet
        assert assets['source'] is None


def test_probe_of_a_python_that_does_not_exist(tmp_path, monkeypatch):
    monkeypatch.setattr(project, 'python', str(tmp_path / 'missing' / 'python'))

    with pytest.raises(project.ProjectError, match='Reading bazis-front cannot run the Python of the project'):
        front.package()


@pytest.fixture
def front_project(tmp_path, monkeypatch):
    """
    A copy of the sample with bazis-front in its apps and a frontend made by
    `bazis_front init` (without Node), served by the server.
    """
    copy = tmp_path / 'sample'
    shutil.copytree(SAMPLE_DIR, copy, ignore=shutil.ignore_patterns('__pycache__'))
    # the tests export project.env and BASE_DIR of the sample; the environment wins over
    # project.env
    monkeypatch.setenv('BS_INSTALLED_APPS', '["shop", "bazis.contrib.front"]')
    monkeypatch.setenv('BS_BASE_DIR', str(copy))
    monkeypatch.setattr(project, 'project_dir', copy)
    monkeypatch.setattr(project, 'settings_module', 'sample.settings')
    return copy


def bazis_front(directory: Path, *args: str):
    env = dict(os.environ, DJANGO_SETTINGS_MODULE='sample.settings', PYTHONPATH=str(directory))
    done = subprocess.run(
        [sys.executable, '-m', 'django', 'bazis_front', *args],
        cwd=directory, env=env, capture_output=True, text=True,
    )
    assert done.returncode == 0, done.stderr


@requires_front
async def test_front_tools_on_a_project(client, front_project):
    # bazis-front is enabled, the frontend is not created yet
    checked = result(await client.call_tool('front_check', {}))
    assert checked['checked'] is False
    assert checked['reason'].endswith(
        'spec does not exist: `manage.py bazis_front init` creates it with the frontend.'
    )

    bazis_front(front_project, 'init', '--no-node')

    # the starters of the specs are valid; there is no contract yet
    checked = result(await client.call_tool('front_check', {}))
    assert checked == {
        'checked': True, 'ok': True, 'contract': False, 'errors': 0, 'warnings': 0, 'issues': []
    }
    status = result(await client.call_tool('front_status', {}))
    assert status['checked'] is True
    assert status['version'] == metadata.version('bazis-front')
    assert set(status['stale']) == {'contract'}
    assert status['stale']['contract'][0]['id'] == 'front.W001'

    # a spec with an error and a design changed after the theme was generated
    bazis_front(front_project, 'contract', '--no-node')
    product = front_project / 'spec' / 'product.yaml'
    product.write_text(
        product.read_text().replace(
            'entities: []', 'entities:\n  - id: product\n    resource: shop.missing\n    fields: []'
        )
    )
    tokens_file = front_project / 'spec' / 'design' / 'tokens.json'
    tokens = json.loads(tokens_file.read_text())
    tokens['color']['background']['$value'] = 'oklch(0.97 0.003 264)'
    tokens_file.write_text(json.dumps(tokens))

    checked = result(await client.call_tool('front_check', {}))
    assert checked['ok'] is False and checked['contract'] is True
    assert [it['code'] for it in checked['issues']] == ['P011']
    design = result(await client.call_tool('front_check', {'layer': 'design'}))
    assert design['ok'] is True and design['issues'] == []

    status = result(await client.call_tool('front_status', {}))
    assert status['spec_issues'] == 1
    assert set(status['stale']) == {'contract', 'design'}
    assert 'bazis_front design' in status['stale']['design'][0]['hint']
    # without Node schema.d.ts is not generated: the contract stays stale
    assert 'schema.d.ts' in status['stale']['contract'][0]['message']


@requires_front
async def test_front_catalog_of_the_project(client):
    from importlib import resources

    registry = json.loads(
        (resources.files('bazis.contrib.front') / 'assets' / 'registry.json').read_text()
    )

    assets = result(await client.call_tool('front_catalog', {}))

    assert assets['source'] == 'installed'
    assert assets['version'] == metadata.version('bazis-front')
    assert [it['name'] for it in assets['assets']] == [it['name'] for it in registry['assets']]
    transit_bar = next(it for it in assets['assets'] if it['name'] == 'transit-bar')
    assert transit_bar['capabilities'] == ['statusy']
    assert 'react-statusy' in transit_bar['requires']


@requires_front
async def test_package_guide_of_bazis_front(client):
    from importlib import resources

    guide = result(await client.call_tool('package_guide', {'name': 'bazis-front'}))

    installed = (resources.files('bazis.contrib.front') / 'AGENTS.md').read_text(encoding='utf-8')
    assert guide['installed_version'] == metadata.version('bazis-front')
    assert guide['agents_md'] == installed
