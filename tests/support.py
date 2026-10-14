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
The helpers of the tests of the tools.
"""

import json
import subprocess
import sys
from pathlib import Path


SAMPLE_DIR = Path(__file__).resolve().parent.parent / 'sample'

#: a paragraph of a guide, about 16,000 characters
PARAGRAPH = 'A line of the guide that says what to do and why it matters.\n' * 260


def size(call_result) -> int:
    """
    The bytes of the text of a tool result, as a client receives it.
    """
    return len(call_result.content[0].text.encode())


def result(call_result):
    """
    The value a tool returned: the JSON text that every client reads.
    """
    assert not call_result.is_error, call_result.content
    return json.loads(call_result.content[0].text)


def make_venv(directory: Path, with_packages: bool = True) -> Path:
    """
    A `.venv` in `directory` made without installing anything, and its Python: with the
    packages of the tests (their site-packages added by a `.pth` file), as `.venv` of a
    project that `scaffold.create_venv` installed, or without any.
    """
    venv = directory / '.venv'
    subprocess.run([sys.executable, '-m', 'venv', '--without-pip', str(venv)], check=True)
    if with_packages:
        sites = [it for it in sys.path if it.endswith('site-packages')]
        (site_packages(venv) / 'tests.pth').write_text(
            ''.join(f'import site; site.addsitedir({it!r})\n' for it in sites)
        )
    return venv / 'bin' / 'python'


def site_packages(venv: Path) -> Path:
    return next(venv.glob('lib/python*/site-packages'))
