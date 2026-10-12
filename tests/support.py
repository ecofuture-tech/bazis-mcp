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
