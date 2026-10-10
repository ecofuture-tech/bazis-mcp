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
`guide_search`: the parts of the guides that answer a query, readable whole with
`package_guide`.
"""

import pytest

from bazis.contrib.mcp import catalog, search

from .test_server import PARAGRAPH, result, size


pytestmark = pytest.mark.anyio

#: a guide with a subsection, a code block with lines like headings, and a long section
#: split into parts by package_guide whose second part holds a subsection
GUIDE = (
    '# bazis-alpha\n\nThe introduction of alpha.\n\n'
    '## Setup\n\nAdd the app to BS_INSTALLED_APPS.\n\n'
    '### Throttle\n\nPublic actions are limited by the throttle: 429 with Retry-After.\n\n'
    '```python\n### not a heading\n## not a section\nclass Shelf: ...\n```\n\n'
    f'## Models\n\n{PARAGRAPH}\n### Details\n\n{PARAGRAPH}{PARAGRAPH}\n'
    'The lighthouse keeps the ledger.\n\n'
    '## Rules\n\nShort rule about invoices.\n'
)


def package(name: str, guide: str, manifest: dict | None = None) -> dict:
    return {'name': name, 'installed_version': '1.0.0', 'catalog_version': None,
            'guide_version': '1.0.0', 'manifest': manifest or {'package': {'name': name}},
            'agents_md': guide}


@pytest.fixture
def guides(monkeypatch):
    alpha = package('bazis-alpha', GUIDE, {
        'package': {'name': 'bazis-alpha'},
        'extension_points': [{'name': 'ShelfRouteBase.restock_item',
                              'import': 'bazis.contrib.alpha.routes.ShelfRouteBase',
                              'use_when': 'fill a shelf'}],
        'pitfalls': [{'text': 'an invoice without a shelf is refused', 'check': 'alpha.E001'}],
    })
    beta = package('bazis-beta', '# bazis-beta\n\n## Invoices\n\nInvoices of beta.\n')
    monkeypatch.setattr(
        catalog, 'packages', lambda: {'bazis-alpha': alpha, 'bazis-beta': beta}
    )


async def search_results(client, **arguments) -> list[dict]:
    return result(await client.call_tool('guide_search', arguments))['results']


async def section_text(client, name: str, section: str) -> str:
    guide = result(await client.call_tool('package_guide', {'name': name, 'section': section}))
    return guide['agents_md']


async def test_a_subsection_is_found_with_its_section(client, guides):
    found = (await search_results(client, query='throttling of public actions'))[0]

    assert (found['package'], found['section'], found['heading']) == (
        'bazis-alpha', 'Setup', 'Throttle'
    )
    assert found['complete'] is True
    assert found['text'].startswith('### Throttle\n')
    # the code block belongs to the subsection: its lines are not headings
    assert '### not a heading' in found['text']
    assert found['text'] in await section_text(client, 'bazis-alpha', found['section'])


async def test_a_subsection_in_a_part_of_a_long_section(client, guides):
    found = (await search_results(client, query='lighthouse ledger'))[0]

    assert (found['section'], found['heading']) == ('Models (2/2)', 'Details')
    assert found['complete'] is False  # the subsection is longer than TEXT_LIMIT
    assert catalog.json_size(found['text']) - 2 <= search.TEXT_LIMIT
    assert 'The lighthouse keeps the ledger.' in found['text']
    assert found['text'] in await section_text(client, 'bazis-alpha', found['section'])


async def test_the_manifest_is_searched(client, guides):
    found = await search_results(client, query='restock_item')
    assert found[0]['extension_point']['name'] == 'ShelfRouteBase.restock_item'

    found = await search_results(client, query='invoice shelf')
    pitfall = next(it for it in found if 'pitfall' in it)
    assert pitfall['pitfall']['check'] == 'alpha.E001'


async def test_the_title_counts_more_than_the_text(client, guides):
    found = await search_results(client, query='invoices')

    assert (found[0]['package'], found[0]['section']) == ('bazis-beta', 'Invoices')
    assert found == sorted(found, key=lambda it: -it['score'])


async def test_the_search_of_one_package(client, guides):
    found = await search_results(client, query='invoices', package='bazis-alpha')
    assert found and {it['package'] for it in found} == {'bazis-alpha'}

    call_result = await client.call_tool(
        'guide_search', {'query': 'invoices', 'package': 'bazis-gamma'}
    )
    assert call_result.is_error
    assert 'bazis-alpha' in call_result.content[0].text


async def test_no_results(client, guides):
    assert await search_results(client, query='zeppelin') == []
    assert await search_results(client, query='the of and') == []  # no words to search


async def test_the_limit(client, guides):
    assert len(await search_results(client, query='invoices shelf throttle', limit=1)) == 1

    for limit in (0, search.LIMIT_MAX + 1):
        call_result = await client.call_tool('guide_search', {'query': 'shelf', 'limit': limit})
        assert call_result.is_error


async def test_the_guides_of_the_packages(client):
    """
    The guides of the catalog and of the installed packages: every result can be read
    whole with `package_guide`, and the most results stay under the limit of a result.
    """
    found = await search_results(client, query='validate_item')
    assert found[0]['package'] == 'bazis'

    call_result = await client.call_tool(
        'guide_search', {'query': 'route model field permission', 'limit': search.LIMIT_MAX}
    )
    assert size(call_result) <= catalog.RESULT_LIMIT
    found = result(call_result)['results']
    assert len(found) == search.LIMIT_MAX
    for item in found:
        if 'text' in item:
            text = await section_text(client, item['package'], item['section'])
            assert item['text'] in text, (item['package'], item['section'])


def test_an_excerpt_of_a_long_paragraph():
    idf = {'matter': 1.0}
    text = '# Title\n\n' + PARAGRAPH + 'It matters.\n'
    excerpt = search.excerpt(text, idf)
    assert excerpt in text and 'matters' in excerpt
    assert catalog.json_size(excerpt) - 2 <= search.TEXT_LIMIT

    line = 'it matters ' * 1000 + '\n'  # a line longer than the limit
    excerpt = search.excerpt(line, idf)
    assert line.startswith(excerpt) and catalog.json_size(excerpt) - 2 <= search.TEXT_LIMIT


def test_words():
    # an identifier also by its parts; the endings stripped where four letters are left
    assert search.words('PermitRouteBase.validate_item') == [
        'permitroutebas', 'permit', 'rout', 'base', 'validate_item', 'validat', 'item'
    ]
    assert search.words('routes Route') == ['rout', 'rout']
    assert search.words('throttle throttled throttling') == ['throttl'] * 3
    assert search.words('How to send the e-mails') == ['send', 'e', 'mail']
