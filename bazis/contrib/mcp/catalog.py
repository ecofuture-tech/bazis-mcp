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
The Bazis packages known to the server: the installed ones with their own manifests and
AGENTS.md, and the others from `catalog.json`, a snapshot of the latest releases made by
`scripts/update_catalog.py`.

Needs no Django settings: an agent can choose packages before the project works.
"""

import json
from functools import cache
from importlib import resources
from pathlib import Path

from bazis.core import introspect


@cache
def catalog() -> dict[str, dict]:
    """
    The snapshot of the released packages by name: version, manifest and AGENTS.md text.
    """
    text = (resources.files(__package__) / 'catalog.json').read_text(encoding='utf-8')
    return {entry['name']: entry for entry in json.loads(text)}


def packages() -> dict[str, dict]:
    """
    All known packages by name. An installed package is described by its own files,
    a package that is not installed by the catalog.
    """
    result = {
        name: {
            'name': name,
            'installed_version': None,
            'catalog_version': entry['version'],
            'manifest': entry['manifest'],
            'agents_md': entry['agents_md'],
        }
        for name, entry in catalog().items()
    }
    for installed in introspect.packages():
        name = installed['name']
        agents_md = installed['agents_md']
        result[name] = {
            'name': name,
            'installed_version': installed['version'],
            'catalog_version': result.get(name, {}).get('catalog_version'),
            'manifest': installed['manifest'],
            'agents_md': Path(agents_md).read_text(encoding='utf-8') if agents_md else None,
        }
    return result


def summary(package: dict) -> dict:
    """
    The short description of a package for choosing packages.
    """
    info = (package['manifest'] or {}).get('package', {})
    return {
        'name': package['name'],
        'installed_version': package['installed_version'],
        'catalog_version': package['catalog_version'],
        'summary': info.get('summary'),
        'solves': info.get('solves', []),
        'requires': info.get('requires', []),
        'pairs_well': info.get('pairs_well', []),
    }
