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

`python scripts/update_catalog.py --from-clones DIR` reads the same files from the local
clones `DIR/<package>` instead (a package without a clone is left out), with the version
`git describe` of the clone marked `(clone)`: for trials against unreleased code, the
result is not committed.
"""

import argparse
import io
import json
import subprocess
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
    'bazis-notify',
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


def read_entry(name: str, version: str, read) -> dict:
    """
    The entry of the package from its files: `read(path)` returns the content of the file
    at `path` in the package (wheel or clone), or None if there is none.
    """
    path = module_path(name)
    manifest = read(f'{path}/bazis_manifest.toml')
    agents_md = read(f'{path}/AGENTS.md')
    if manifest is None or agents_md is None:
        raise SystemExit(f'{name} {version}: no manifest or AGENTS.md')
    entry = {
        'name': name,
        'version': version,
        'manifest': tomllib.loads(manifest.decode()),
        'agents_md': agents_md.decode(),
    }
    if name == 'bazis-front':
        registry = read(f'{path}/{FRONT_REGISTRY}')
        if registry is None:
            raise SystemExit(f'{name} {version}: no {FRONT_REGISTRY}')
        entry['registry'] = json.loads(registry)
    return entry


def pypi_entry(name: str) -> dict | None:
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

    with zipfile.ZipFile(io.BytesIO(fetch(wheels[0]['url']))) as wheel:
        files = set(wheel.namelist())
        return read_entry(name, version, lambda path: wheel.read(path) if path in files else None)


def clone_entry(clones: Path, name: str) -> dict | None:
    clone = clones / name
    if not (clone / 'pyproject.toml').is_file():
        return None  # no clone
    describe = subprocess.run(
        ['git', 'describe', '--tags', '--always', '--dirty'],
        cwd=clone, capture_output=True, text=True, check=True,
    ).stdout.strip()
    version = describe.removeprefix('v') + ' (clone)'

    def read(path: str) -> bytes | None:
        file = clone / path
        return file.read_bytes() if file.is_file() else None

    return read_entry(name, version, read)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument(
        '--from-clones', type=Path, metavar='DIR',
        help='read the packages from the local clones DIR/<package> instead of PyPI '
             '(for trials against unreleased code, not committed)',
    )
    args = parser.parse_args()

    catalog = []
    for name in PACKAGES:
        if args.from_clones:
            entry = clone_entry(args.from_clones, name)
        else:
            entry = pypi_entry(name)
        if entry is None:
            source = f'no clone in {args.from_clones}' if args.from_clones else 'not on PyPI'
            print(f'{name}: {source}, left out', file=sys.stderr)
            continue
        print(f'{name} {entry["version"]}', file=sys.stderr)
        catalog.append(entry)
    CATALOG.write_text(json.dumps(catalog, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
