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

from .support import SAMPLE_DIR, result


pytestmark = pytest.mark.anyio


REGISTRY = {
    'registry': 1,
    'assets': [
        {'name': 'client', 'kind': 'vendored', 'source': 'client/src',
         'target': 'src/bazis/client', 'files': ['index.ts']},
        {'name': 'transit-bar', 'kind': 'ui', 'source': 'ui/transit-bar',
         'target': 'src/bazis/ui/transit-bar', 'files': ['index.ts'],
         'requires': {'capabilities': ['statusy'], 'assets': ['client']}},
        {'name': 'state-panel', 'kind': 'ui', 'source': 'ui/state-panel',
         'target': 'src/bazis/ui/state-panel', 'files': ['index.ts']},
        {'name': 'template', 'kind': 'template', 'source': 'template', 'target': '.',
         'files': ['package.json'], 'requires': {'assets': ['state-panel']}},
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


def issue(id_, text='', hint=None, level='warning', command=None):
    """An issue of `bazis_front status --json`."""
    return {'id': id_, 'level': level, 'message': text, 'hint': hint, 'command': command}


def status_output(*issues):
    state = {'bazis_front': '1.0.0', 'frontend': '/app/frontend', 'assets': {}, 'generated': {},
             'issues': list(issues)}
    return 0, json.dumps(state), ''


@pytest.fixture
def fake_run(monkeypatch):
    """
    Replaces the processes of the project: `outputs` are the (exit code, stdout, stderr)
    of the calls in their order; the command lines are recorded in `calls`.
    """
    class Fake:
        calls: list[list[str]] = []
        settings: list[str | None] = []
        outputs: list[tuple[int, str, str]] = []

    def run(args, **kwargs):
        Fake.calls.append(args[1:])
        Fake.settings.append(kwargs['env'].get('DJANGO_SETTINGS_MODULE'))
        code, stdout, stderr = Fake.outputs.pop(0)
        return subprocess.CompletedProcess(args, code, stdout, stderr)

    monkeypatch.setattr(project.subprocess, 'run', run)
    return Fake


def probe_output(version='1.0.0', registry=REGISTRY, enabled=True):
    return 0, json.dumps({'version': version, 'registry': registry, 'enabled': enabled}) + '\n', ''


#: the probe of a project without bazis-front
NOT_INSTALLED = probe_output(None, None, None)


async def test_front_check_reports_the_issues(client, fake_run):
    report = {'contract': True, 'errors': 1, 'warnings': 0, 'issues': [SPEC_ISSUE]}
    fake_run.outputs = [
        probe_output(), (1, json.dumps(report), 'CommandError: The specs have 1 errors.\n')
    ]

    checked = result(await client.call_tool('front_check', {'layer': 'product'}))

    assert fake_run.calls[1:] == [
        ['-m', 'django', 'bazis_front', 'check', '--json', '--layer', 'product']
    ]
    # the probe reads the settings of the project
    assert fake_run.settings == ['sample.settings', 'sample.settings']
    assert checked == {'checked': True, 'ok': False, **report}


async def test_front_check_of_valid_specs(client, fake_run):
    report = {'contract': False, 'errors': 0, 'warnings': 0, 'issues': []}
    fake_run.outputs = [probe_output(), (0, json.dumps(report), '')]

    checked = result(await client.call_tool('front_check', {}))

    assert fake_run.calls[1:] == [['-m', 'django', 'bazis_front', 'check', '--json']]
    assert checked['checked'] is True and checked['ok'] is True


async def test_front_check_without_spec(client, fake_run):
    refusal = '/app/spec does not exist: `manage.py bazis_front init` creates it with the frontend.'
    fake_run.outputs = [probe_output(), (1, '', f'CommandError: {refusal}\n')]

    checked = result(await client.call_tool('front_check', {}))

    assert checked == {'checked': False, 'reason': refusal}


async def test_front_check_of_a_layer_that_does_not_exist(client):
    call_result = await client.call_tool('front_check', {'layer': 'backend'})

    assert call_result.is_error


@pytest.mark.parametrize(
    ('probe', 'reason'),
    [(NOT_INSTALLED, front.NOT_INSTALLED), (probe_output(enabled=False), front.NOT_ENABLED)],
    ids=['not installed', 'not enabled'],
)
@pytest.mark.parametrize('tool', ['front_check', 'front_status'])
async def test_front_tools_without_bazis_front(client, fake_run, tool, probe, reason):
    fake_run.outputs = [probe]

    assert result(await client.call_tool(tool, {})) == {'checked': False, 'reason': reason}
    assert len(fake_run.calls) == 1  # bazis_front and the system checks are not run


async def test_front_check_with_settings_that_fail(client, fake_run):
    # the probe cannot read the settings: the command reports why
    fake_run.outputs = [
        probe_output(enabled=None), (1, '', "ModuleNotFoundError: No module named 'missing'\n")
    ]

    call_result = await client.call_tool('front_check', {})

    assert call_result.is_error
    assert "No module named 'missing'" in call_result.content[0].text


@requires_front
async def test_front_tools_with_settings_that_fail(client, monkeypatch):
    monkeypatch.setattr(project, 'settings_module', 'missing.settings')

    for tool in ('front_check', 'front_status'):
        call_result = await client.call_tool(tool, {})
        assert call_result.is_error
        assert "No module named 'missing'" in call_result.content[0].text


@requires_front
async def test_front_tools_on_the_sample_without_its_app(client):
    # bazis-front is installed, the sample has no "bazis.contrib.front" in INSTALLED_APPS
    for tool in ('front_check', 'front_status'):
        checked = result(await client.call_tool(tool, {}))
        assert checked == {'checked': False, 'reason': front.NOT_ENABLED}


async def test_front_status(client, fake_run):
    issues = [
        issue('front.W001', 'The contract is stale: contract.json differs from the backend.',
              'Export it with `manage.py bazis_front contract`.', command='contract'),
        issue('front.W005', 'The theme is stale.', 'Generate it with `manage.py bazis_front design`.',
              command='design'),
        issue('front.W002', 'P011 (error) spec/product.yaml#/entities/0/resource: ...'),
        issue('front.W002', 'P020 (warning) spec/product.yaml#/entities/0/access: ...'),
        issue('front.I001', 'The contract is not checked: the database is not migrated.',
              level='info'),
        issue('front.W007', 'Copies of bazis-front were changed in the frontend.'),
    ]
    fake_run.outputs = [probe_output(), status_output(*issues)]

    status = result(await client.call_tool('front_status', {}))

    assert fake_run.calls[1] == ['-m', 'django', 'bazis_front', 'status', '--json']
    assert status == {
        'checked': True,
        'version': '1.0.0',
        'up_to_date': False,
        'stale': {'contract': [issues[0]], 'design': [issues[1]]},
        'spec_issues': 2,
        'shot_errors': [],
        'messages': [issues[4], issues[5]],
    }


async def test_front_status_up_to_date(client, fake_run):
    # the errors of the report of the screenshots are not stale (no command updates them),
    # and apart: the final checks want none that the summary does not list
    report = issue('front.W009', 'The report of the last screenshots has 2 errors.',
                   'Fix them and take the screenshots again with `manage.py bazis_front shots`.')
    fake_run.outputs = [probe_output(), status_output(report)]

    status = result(await client.call_tool('front_status', {}))

    assert status['up_to_date'] is True and status['stale'] == {}
    assert status['shot_errors'] == [report] and status['messages'] == []

    # the screenshots never taken: no report, the same check
    missing = issue('front.W009', 'The screenshots were not taken: run `manage.py bazis_front shots`.',
                    'Run it with the backend and the frontend of the end-to-end tests.')
    fake_run.outputs = [probe_output(), status_output(missing)]

    status = result(await client.call_tool('front_status', {}))

    assert status['up_to_date'] is True and status['shot_errors'] == [missing] and status['messages'] == []


async def test_front_status_of_an_application_that_cannot_load(client, fake_run):
    fake_run.outputs = [probe_output(), (1, '', "ImportError: cannot import name 'x'\n")]

    call_result = await client.call_tool('front_status', {})

    assert call_result.is_error
    assert "cannot import name 'x'" in call_result.content[0].text


async def test_front_catalog_of_the_installed_bazis_front(client, fake_run, monkeypatch):
    monkeypatch.setattr(catalog, 'catalog', lambda: {})
    fake_run.outputs = [probe_output(enabled=False)]  # the registry needs no app

    assets = result(await client.call_tool('front_catalog', {}))

    assert fake_run.calls == [['-c', front.PROBE]]
    assert assets['source'] == 'installed'
    assert assets['version'] == assets['installed_version'] == '1.0.0'
    assert assets['assets'] == [
        {'name': 'client', 'kind': 'vendored', 'target': 'src/bazis/client',
         'capabilities': [], 'requires': []},
        {'name': 'transit-bar', 'kind': 'ui', 'target': 'src/bazis/ui/transit-bar',
         'capabilities': ['statusy'], 'requires': ['client']},
        {'name': 'state-panel', 'kind': 'ui', 'target': 'src/bazis/ui/state-panel',
         'capabilities': [], 'requires': []},
        # the components that `init` copies are those the template requires
        {'name': 'template', 'kind': 'template', 'target': '.',
         'capabilities': [], 'requires': ['state-panel']},
    ]


async def test_front_catalog_from_the_catalog(client, fake_run, monkeypatch):
    entry = {'name': 'bazis-front', 'version': '1.1.0', 'manifest': {}, 'agents_md': '',
             'registry': REGISTRY}
    monkeypatch.setattr(catalog, 'catalog', lambda: {'bazis-front': entry})
    fake_run.outputs = [NOT_INSTALLED]

    assets = result(await client.call_tool('front_catalog', {}))

    assert assets['source'] == 'catalog'
    assert assets['version'] == '1.1.0'
    assert assets['installed_version'] is None
    assert [it['name'] for it in assets['assets']] == ['client', 'transit-bar', 'state-panel', 'template']


async def test_front_catalog_without_bazis_front(client, fake_run, monkeypatch):
    monkeypatch.setattr(catalog, 'catalog', lambda: {})
    fake_run.outputs = [NOT_INSTALLED]

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
    # the starter design is its layers in theme.yaml; tokens.json defines no token of its own
    import yaml  # a dependency of bazis-front

    design_dir = front_project / 'spec' / 'design'
    theme = yaml.safe_load((design_dir / 'theme.yaml').read_text())
    assert {'preset', 'palette', 'fonts', 'shape', 'surface'} <= theme.keys()
    assert set(json.loads((design_dir / 'tokens.json').read_text())) <= {'$schema', '$description'}
    theme['palette'] = 'forest' if theme['palette'] != 'forest' else 'ember'
    (design_dir / 'theme.yaml').write_text(yaml.safe_dump(theme))

    checked = result(await client.call_tool('front_check', {}))
    assert checked['ok'] is False and checked['contract'] is True
    # the starter home, a dashboard without tiles, is the overview of the template once the
    # product declares an entity (the warning S026)
    assert [it['code'] for it in checked['issues']] == ['P011', 'S026']
    design = result(await client.call_tool('front_check', {'layer': 'design'}))
    assert design['ok'] is True and design['issues'] == []

    status = result(await client.call_tool('front_status', {}))
    assert status['spec_issues'] == 2
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

    from .test_server import read_whole_guide

    # a guide longer than a result comes by its sections
    guide, text = await read_whole_guide(client, 'bazis-front')

    installed = (resources.files('bazis.contrib.front') / 'AGENTS.md').read_text(encoding='utf-8')
    assert guide['installed_version'] == metadata.version('bazis-front')
    assert text == installed


@requires_front
def test_layers_are_those_of_bazis_front():
    from typing import get_args

    from bazis.contrib.front.spec import validate
    from bazis.contrib.mcp import server

    assert get_args(server.LAYERS) == validate.LAYERS
