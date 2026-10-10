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
`scripts/update_catalog.py --from-clones`: the version of a clone is the one it is built
with, a version that a minimum `>=<catalog_version>` can name.
"""

import importlib.util
import subprocess
from pathlib import Path

import pytest


SCRIPT = Path(__file__).resolve().parent.parent / 'scripts' / 'update_catalog.py'

PYPROJECT = """\
[project]
name = "bazis-fake"
dynamic = ["version"]

[tool.setuptools_scm]
version_scheme = "no-guess-dev"
local_scheme = "no-local-version"
"""


@pytest.fixture
def update_catalog():
    spec = importlib.util.spec_from_file_location('update_catalog', SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def git(clone: Path, *args: str):
    subprocess.run(
        ['git', '-c', 'user.name=Test', '-c', 'user.email=test@example.com', *args],
        cwd=clone, check=True, capture_output=True,
    )


def test_the_version_of_a_clone(update_catalog, tmp_path, monkeypatch):
    pytest.importorskip('setuptools_scm')
    monkeypatch.delenv('SETUPTOOLS_SCM_PRETEND_VERSION', raising=False)
    monkeypatch.delenv('SETUPTOOLS_SCM_PRETEND_VERSION_FOR_BAZIS_FAKE', raising=False)
    clone = tmp_path / 'bazis-fake'
    module = clone / 'bazis' / 'contrib' / 'fake'
    module.mkdir(parents=True)
    (clone / 'pyproject.toml').write_text(PYPROJECT)
    (module / 'bazis_manifest.toml').write_text('[package]\nname = "bazis-fake"\n')
    (module / 'AGENTS.md').write_text('# bazis-fake\n')
    git(clone, 'init', '-q')
    git(clone, 'add', '.')
    git(clone, 'commit', '-q', '-m', 'first')
    git(clone, 'tag', 'v1.2.0')
    (module / 'AGENTS.md').write_text('# bazis-fake\n\nUnreleased.\n')
    git(clone, 'commit', '-q', '-am', 'second')

    entry = update_catalog.clone_entry(tmp_path, 'bazis-fake')
    assert entry['version'] == '1.2.0.post1.dev1'
    assert entry['agents_md'] == '# bazis-fake\n\nUnreleased.\n'

    # the version the trials build the clone with
    monkeypatch.setenv('SETUPTOOLS_SCM_PRETEND_VERSION_FOR_BAZIS_FAKE', '1.3.0')
    assert update_catalog.clone_entry(tmp_path, 'bazis-fake')['version'] == '1.3.0'

    assert update_catalog.clone_entry(tmp_path, 'bazis-missing') is None
