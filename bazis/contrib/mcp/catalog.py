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
The Bazis packages known to the server: those installed in the Python of the project with
their own manifests and AGENTS.md, read again at every call, and the others from
`catalog.json`, a snapshot of the latest releases made by `scripts/update_catalog.py`.

Needs no Django settings: an agent can choose packages before the project works.
"""

import json
from functools import cache
from importlib import resources
from pathlib import Path

import pydantic_core

from . import project


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
    All known packages by name. The installed packages and their guides are those of the
    Python of the project at the time of the call (`project.packages`): the guide (manifest
    and AGENTS.md) of an installed package comes from its files; a package that is not installed, or installed in a version
    without a guide (before 2.4), is described by the catalog. `guide_version` is the
    version the guide describes. `project.ProjectError` if the Python of the project cannot
    list its packages.
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
    for installed in project.packages():
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


#: the longest result of `package_guide`, in bytes of its JSON as the MCP SDK sends it
#: (`json_size`; about 10,000 tokens): a longer guide is read section by section, so that a
#: result stays well under the limits of the MCP clients on the output of a tool (Claude
#: Code: 25,000 tokens)
RESULT_LIMIT = 40_000
#: the longest text of a part of a guide, in bytes of its JSON string; the rest of
#: RESULT_LIMIT is left to the other fields of a result (the versions, the titles of the
#: sections). The introduction comes with the manifest: its parts are shorter by the size
#: of the manifest
GUIDE_LIMIT = 30_000
#: the shortest limit of a part of the introduction, whatever the size of the manifest
INTRODUCTION_MIN = 2_000
#: the most bytes of JSON of one character (`\u001f`): a line longer than a limit is cut
#: into pieces of `limit // CHAR_MAX` characters
CHAR_MAX = 6

#: the title of the text of a guide before its first `## ` heading
INTRODUCTION = 'Introduction'


def json_size(value) -> int:
    """
    The size of a value in the JSON of a tool result: bytes of UTF-8, indented, as the MCP
    SDK serializes a result.
    """
    return len(pydantic_core.to_json(value, indent=2))


def _pieces(text: str, limit: int) -> list[tuple[str, int]]:
    """
    The lines of a text with the size of each in a JSON string (without the quotes); a line
    over the `limit` is cut into pieces that fit it.
    """
    result = []
    for line in text.splitlines(keepends=True):
        size = json_size(line) - 2
        if size <= limit:
            result.append((line, size))
            continue
        step = max(limit // CHAR_MAX, 1)
        for start in range(0, len(line), step):
            piece = line[start:start + step]
            result.append((piece, json_size(piece) - 2))
    return result


def sections(
    text: str, limit: int = GUIDE_LIMIT, introduction_limit: int | None = None
) -> list[tuple[str, str]]:
    """
    An AGENTS.md as its sections, in order: the introduction (titled INTRODUCTION) before
    the first `## ` heading outside a code block, then each `## ` section with its heading
    and its subsections. A section over the `limit` (the introduction: over the
    `introduction_limit`, by default the `limit`) in bytes of JSON is cut at line ends (a
    longer line within it) into parts titled `<title> (1/n)`, each within the limit.
    """
    found: list[list] = [[INTRODUCTION, '']]
    fenced = False
    for line in text.splitlines(keepends=True):
        if line.startswith('```'):
            fenced = not fenced
        elif not fenced and line.startswith('## '):
            found.append([line[3:].strip(), ''])
        found[-1][1] += line
    introduction = bool(found[0][1])
    if not introduction:
        del found[0]
    result = []
    for index, (title, body) in enumerate(found):
        budget = limit
        if introduction and index == 0 and introduction_limit is not None:
            budget = introduction_limit
        parts, sizes = [''], [0]
        for piece, size in _pieces(body, budget):
            if parts[-1] and sizes[-1] + size > budget:
                parts.append('')
                sizes.append(0)
            parts[-1] += piece
            sizes[-1] += size
        if len(parts) == 1:
            result.append((title, body))
        else:
            result += [(f'{title} ({i}/{len(parts)})', part) for i, part in enumerate(parts, 1)]
    return result


def guide(package: dict, section: str | None = None) -> dict:
    """
    The guide of a package: its manifest and its AGENTS.md, whole when the result fits in
    RESULT_LIMIT, else with the first part of the guide, its introduction (`complete`
    false); `sections` lists the titles of its sections (a long introduction is listed as
    `Introduction (1/n)` and so on). With a `section`, the text of that section only
    (KeyError of the section and the titles if there is no such section). Every result
    fits in RESULT_LIMIT.
    """
    text = package['agents_md'] or ''
    manifest = package['manifest']
    parts = sections(
        text, introduction_limit=max(GUIDE_LIMIT - json_size(manifest), INTRODUCTION_MIN)
    )
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
    whole = {
        **info,
        'manifest': manifest,
        'agents_md': package['agents_md'],
        'complete': True,
        'sections': titles,
    }
    if json_size(whole) <= RESULT_LIMIT:
        return whole
    return {**whole, 'agents_md': parts[0][1], 'complete': False}


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
