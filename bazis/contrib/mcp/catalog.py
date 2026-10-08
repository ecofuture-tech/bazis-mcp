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

import importlib
import json
from functools import cache
from importlib import resources
from pathlib import Path

from bazis.core import introspect


@cache
def catalog() -> dict[str, dict]:
    """
    The snapshot of the released packages by name: version, manifest and AGENTS.md text
    (and `registry`, the assets of bazis-front).
    """
    text = (resources.files(__package__) / 'catalog.json').read_text(encoding='utf-8')
    return {entry['name']: entry for entry in json.loads(text)}


def packages() -> dict[str, dict]:
    """
    All known packages by name. The guide (manifest and AGENTS.md) of an installed package
    comes from its files; a package that is not installed, or installed in a version
    without a guide (before 2.4), is described by the catalog. `guide_version` is the
    version the guide describes.
    """
    result = {
        name: {
            'name': name,
            'installed_version': None,
            'catalog_version': entry['version'],
            'guide_version': entry['version'],
            'manifest': entry['manifest'],
            'agents_md': entry['agents_md'],
        }
        for name, entry in catalog().items()
    }
    importlib.invalidate_caches()  # packages installed while the server runs
    for installed in introspect.packages():
        name = installed['name']
        package = result.setdefault(
            name,
            {'name': name, 'catalog_version': None, 'guide_version': None,
             'manifest': None, 'agents_md': None},
        )
        package['installed_version'] = installed['version']
        if installed['manifest'] and installed['agents_md']:
            package['guide_version'] = installed['version']
            package['manifest'] = installed['manifest']
            package['agents_md'] = Path(installed['agents_md']).read_text(encoding='utf-8')
    return result


#: the longest text of an AGENTS.md in one result of `package_guide` (characters, about 8,000
#: tokens): a longer guide is read section by section, so that a result stays well under the
#: limits of the MCP clients on the output of a tool (Claude Code: 25,000 tokens)
GUIDE_LIMIT = 30_000

#: the title of the text of a guide before its first `## ` heading
INTRODUCTION = 'Introduction'


def sections(text: str) -> list[tuple[str, str]]:
    """
    An AGENTS.md as its sections, in order: the introduction (title '') before the first
    `## ` heading outside a code block, then each `## ` section with its heading and its
    subsections. A section longer than GUIDE_LIMIT is cut at line ends into parts titled
    `<title> (1/n)`. The introduction is titled INTRODUCTION.
    """
    found: list[list] = [[INTRODUCTION, '']]
    fenced = False
    for line in text.splitlines(keepends=True):
        if line.startswith('```'):
            fenced = not fenced
        elif not fenced and line.startswith('## '):
            found.append([line[3:].strip(), ''])
        found[-1][1] += line
    if not found[0][1]:
        del found[0]
    result = []
    for title, body in found:
        parts = ['']
        for line in body.splitlines(keepends=True):
            if parts[-1] and len(parts[-1]) + len(line) > GUIDE_LIMIT:
                parts.append('')
            parts[-1] += line
        if len(parts) == 1:
            result.append((title, body))
        else:
            result += [(f'{title} ({i}/{len(parts)})', part) for i, part in enumerate(parts, 1)]
    return result


def guide(package: dict, section: str | None = None) -> dict:
    """
    The guide of a package: its manifest and its AGENTS.md, whole when it is no longer than
    GUIDE_LIMIT, else its introduction (`complete` false); `sections` lists the titles of
    its sections (a long introduction is listed as `Introduction (1/n)` and so on). With a
    `section`, the text of that section only (KeyError of the section and the titles if
    there is no such section).
    """
    text = package['agents_md'] or ''
    parts = sections(text)
    titles = [title for title, _ in parts if title != INTRODUCTION]
    info = {
        key: package[key]
        for key in ('name', 'installed_version', 'catalog_version', 'guide_version')
    }
    if section is not None:
        wanted = section.strip().removeprefix('## ').strip().casefold()
        for title, body in parts:
            if title.casefold() == wanted:
                return {**info, 'section': title, 'agents_md': body, 'sections': titles}
        raise KeyError(section, titles)
    complete = len(text) <= GUIDE_LIMIT
    return {
        **info,
        'manifest': package['manifest'],
        'agents_md': package['agents_md'] if complete else parts[0][1],
        'complete': complete,
        'sections': titles,
    }


def summary(package: dict) -> dict:
    """
    The short description of a package for choosing packages.
    """
    info = (package['manifest'] or {}).get('package', {})
    return {
        'name': package['name'],
        'installed_version': package['installed_version'],
        'catalog_version': package['catalog_version'],
        'guide_version': package['guide_version'],
        'summary': info.get('summary'),
        'solves': info.get('solves', []),
        'requires': info.get('requires', []),
        'pairs_well': info.get('pairs_well', []),
    }
