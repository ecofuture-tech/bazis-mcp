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
Rebuilds `bazis/contrib/mcp/catalog.json` from the latest releases of the Bazis packages
on PyPI: the manifest and the AGENTS.md of each package, read from its wheel, and the
registry of the assets of bazis-front (`front_catalog`). A package that is not on PyPI yet
is left out.

Run it before a release of bazis-mcp: `python scripts/update_catalog.py`.
"""

import io
import json
import sys
import tomllib
import urllib.error
import urllib.request
import zipfile
from pathlib import Path


# the Bazis packages in the order of their dependencies
PACKAGES = [
    'bazis',
    'bazis-test-utils',
    'bazis-users',
    'bazis-ws',
    'bazis-bulk',
    'bazis-uploadable',
    'bazis-author',
    'bazis-authing',
    'bazis-permit',
    'bazis-statusy',
    'bazis-bg',
    'bazis-async-background',
    'bazis-async-request',
    'bazis-front',
]

#: the registry of the assets of bazis-front in its module, read into its entry
FRONT_REGISTRY = 'assets/registry.json'

CATALOG = Path(__file__).resolve().parent.parent / 'bazis' / 'contrib' / 'mcp' / 'catalog.json'


def module_path(name: str) -> str:
    if name == 'bazis':
        return 'bazis/core'
    if name == 'bazis-test-utils':
        return 'bazis_test_utils'
    return 'bazis/contrib/' + name.removeprefix('bazis-').replace('-', '_')


def fetch(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=60) as response:
        return response.read()


def package_entry(name: str) -> dict | None:
    try:
        info = json.loads(fetch(f'https://pypi.org/pypi/{name}/json'))
    except urllib.error.HTTPError as err:
        if err.code == 404:
            return None  # not released yet
        raise
    version = info['info']['version']
    wheels = [it for it in info['urls'] if it['packagetype'] == 'bdist_wheel']
    if not wheels:
        raise SystemExit(f'{name} {version}: no wheel on PyPI')

    path = module_path(name)
    with zipfile.ZipFile(io.BytesIO(fetch(wheels[0]['url']))) as wheel:
        files = set(wheel.namelist())
        manifest_file = f'{path}/bazis_manifest.toml'
        agents_file = f'{path}/AGENTS.md'
        if manifest_file not in files or agents_file not in files:
            raise SystemExit(f'{name} {version}: the wheel has no manifest or AGENTS.md')
        entry = {
            'name': name,
            'version': version,
            'manifest': tomllib.loads(wheel.read(manifest_file).decode()),
            'agents_md': wheel.read(agents_file).decode(),
        }
        if name == 'bazis-front':
            registry_file = f'{path}/{FRONT_REGISTRY}'
            if registry_file not in files:
                raise SystemExit(f'{name} {version}: the wheel has no {FRONT_REGISTRY}')
            entry['registry'] = json.loads(wheel.read(registry_file))

    return entry


def main() -> None:
    catalog = []
    for name in PACKAGES:
        entry = package_entry(name)
        if entry is None:
            print(f'{name}: not on PyPI, left out', file=sys.stderr)
            continue
        print(f'{name} {entry["version"]}', file=sys.stderr)
        catalog.append(entry)
    CATALOG.write_text(json.dumps(catalog, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
