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
The search in the guides of the packages (`guide_search`): an agent finds the part of a
guide that answers its question without reading the whole guide.

The documents are the parts of each AGENTS.md between two headings (`##` to `######`,
outside code blocks), within the sections that `package_guide` serves (`catalog.guide_parts`,
so that the `section` of a result can be read whole with it), and the extension points and
pitfalls of each manifest, without the map of the sections of an introduction (MAP), which
only names the sections that hold the answers. They are ranked by BM25 on their words, the
words of their headings counting `TITLE_WEIGHT` times.
"""

import math
import re
from collections import Counter

from . import catalog


#: how many times a word of the heading (and of the section) counts in the text under it
TITLE_WEIGHT = 3
#: the parameters of BM25: the saturation of a repeated word, the weight of the length
K1 = 1.2
B = 0.75
#: the longest text of a result, in bytes of its JSON string: a longer part of a guide
#: comes as an excerpt around the words of the query (`complete` false); with the most
#: results (LIMIT_MAX) a result stays under catalog.RESULT_LIMIT
TEXT_LIMIT = 3_000
LIMIT_MAX = 10

WORD_RE = re.compile(r'\w+')
#: the humps of an identifier: `PermitRouteBase` is also `permit`, `route`, `base`
HUMP_RE = re.compile(r'[A-Z]+(?![a-z])|[A-Z]?[a-z]+|\d+')
#: a heading inside a section (the sections are cut at `## `)
HEADING_RE = re.compile(r'#{3,6}\s+(.*)')
#: the heading of the map of the sections in the introduction of a guide (a table of the
#: sections with when to read each): read with the introduction, not a result of the search
MAP = 'The sections'
SUFFIXES = ('ing', 'ed', 'es', 's', 'e')
STOPWORDS = frozenset(
    'a an and are as at be by can do does for from how i in is it its of on or that the '
    'this to what when where which with'.split()
)


def stem(word: str) -> str:
    """
    A word without its first English ending that leaves at least four letters, so that
    `throttle`, `throttled` and `throttling` are the same word.
    """
    for suffix in SUFFIXES:
        if word.endswith(suffix) and len(word) - len(suffix) >= 4:
            return word[: -len(suffix)]
    return word


def words(text: str) -> list[str]:
    """
    The words of a text for the search: each word in lower case, and an identifier also as
    its parts (`validate_item`: `validate_item`, `validate`, `item`), all stemmed.
    """
    result = []
    for token in WORD_RE.findall(text):
        parts = [it for part in token.split('_') for it in HUMP_RE.findall(part)]
        if len(parts) <= 1:
            parts = []
        for word in (token, *parts):
            word = word.lower()
            if word not in STOPWORDS:
                result.append(stem(word))
    return result


def _chunks(package: dict) -> list[dict]:
    """
    The AGENTS.md of a package cut at its headings within the sections of `package_guide`:
    `section` (its title in `sections`), `heading` (the heading the text is under inside
    the section, None at its top) and `text`.
    """
    result = []
    parts = catalog.guide_parts(package)
    # one reading of the lines of all the parts: a code block of a section cut into parts
    # goes on in its next part
    marks = catalog.markdown_lines(line for _, body in parts for line in body.splitlines(keepends=True))
    for section, body in parts:
        heading = None
        title = catalog.base_title(section)
        if result and title != section and title == catalog.base_title(result[-1]['section']):
            heading = result[-1]['heading']  # the next part of the same section
        lines = []
        for line in body.splitlines(keepends=True):
            _, is_heading = next(marks)
            if is_heading and (match := HEADING_RE.match(line)):
                if ''.join(lines).strip():
                    result.append({'section': section, 'heading': heading, 'text': ''.join(lines)})
                heading, lines = match[1].strip(), []
            lines.append(line)
        if ''.join(lines).strip():
            result.append({'section': section, 'heading': heading, 'text': ''.join(lines)})
    return result


def documents(packages: list[dict]) -> list[dict]:
    """
    The documents of the search in the guides of the `packages`, each with its `words` and
    the words of its `title`, and the fields of its result.
    """
    result = []
    for package in packages:
        name = package['name']
        for chunk in _chunks(package):
            title = catalog.base_title(chunk['section'])
            if title == catalog.INTRODUCTION:
                if chunk['heading'] == MAP:
                    continue
                title = ''
            result.append({
                'result': {'package': name, **chunk},
                'words': words(chunk['text']),
                'title': words(f'{title} {chunk["heading"] or ""}'),
            })
        manifest = package['manifest'] or {}
        for kind, key in (('extension_point', 'extension_points'), ('pitfall', 'pitfalls')):
            for item in manifest.get(key, []):
                result.append({
                    'result': {'package': name, kind: item},
                    'words': words(' '.join(str(it) for it in item.values())),
                    'title': words(str(item.get('name', ''))),
                })
    return result


def search(packages: list[dict], query: str, limit: int = 5) -> list[dict]:
    """
    The `limit` documents of the guides of the `packages` that match the `query` best, as
    results: `package`, `score` and either `section`, `heading`, `text` and `complete` (the
    text of a part of the AGENTS.md, an excerpt if it is longer than TEXT_LIMIT), or
    `extension_point` or `pitfall` (the item of the manifest). Only documents with a word
    of the query.
    """
    terms = list(dict.fromkeys(words(query)))
    docs = documents(packages)
    if not terms or not docs:
        return []
    counts = [Counter(doc['words']) + Counter({w: TITLE_WEIGHT for w in doc['title']})
              for doc in docs]
    lengths = [len(doc['words']) + TITLE_WEIGHT * len(doc['title']) for doc in docs]
    average = sum(lengths) / len(docs) or 1
    idf = {}
    for term in terms:
        found = sum(1 for count in counts if term in count)
        idf[term] = math.log(1 + (len(docs) - found + 0.5) / (found + 0.5))
    scored = []
    for doc, count, length in zip(docs, counts, lengths, strict=True):
        score = 0.0
        for term in terms:
            tf = count.get(term, 0)
            if tf:
                score += idf[term] * tf * (K1 + 1) / (tf + K1 * (1 - B + B * length / average))
        if score > 0:
            scored.append((score, doc))
    scored.sort(key=lambda it: -it[0])
    return [_result(doc['result'], score, idf) for score, doc in scored[:limit]]


def _result(found: dict, score: float, idf: dict[str, float]) -> dict:
    result = {**found, 'score': round(score, 2)}
    if 'text' in found:
        result['complete'] = _fits(found['text'])
        if not result['complete']:
            result['text'] = excerpt(found['text'], idf)
    return result


def _blocks(text: str) -> list[str]:
    """
    The paragraphs of a text (a code block is one), each with the blank lines after it.
    """
    blocks, fenced, blank = [''], False, False
    for line in text.splitlines(keepends=True):
        if line.strip() and blank and not fenced:
            blocks.append('')
        blocks[-1] += line
        if line.startswith('```'):
            fenced = not fenced
        blank = not line.strip()
    return [it for it in blocks if it]


def _fits(text: str) -> bool:
    return catalog.json_size(text) - 2 <= TEXT_LIMIT


def _weight(text: str, idf: dict[str, float]) -> float:
    found = set(words(text))
    return sum(value for term, value in idf.items() if term in found)


def excerpt(text: str, idf: dict[str, float]) -> str:
    """
    The part of a long text around the words of the query (`idf`, their weights) within
    TEXT_LIMIT: the paragraph with most of them and the paragraphs around it that fit, or
    the lines of that paragraph from the first one with the best words.
    """
    blocks = _blocks(text)
    weights = [_weight(block, idf) for block in blocks]
    best = weights.index(max(weights))
    start, end = best, best + 1
    if not _fits(blocks[best]):
        lines = blocks[best].splitlines(keepends=True)
        line_weights = [_weight(line, idf) for line in lines]
        first = line_weights.index(max(line_weights))
        result = ''
        for line in lines[first:]:
            if not _fits(result + line):
                break
            result += line
        return result or lines[first]
    grown = True
    while grown:
        grown = False
        if end < len(blocks) and _fits(''.join(blocks[start:end + 1])):
            end, grown = end + 1, True
        if start > 0 and _fits(''.join(blocks[start - 1:end])):
            start, grown = start - 1, True
    return ''.join(blocks[start:end])
