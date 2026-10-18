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

import pytest

from bazis.contrib.mcp import prompts


def test_new_prompt_of_a_product():
    """
    The prompt of a product with a frontend follows the steps of the guide of bazis-front
    (never a copy of them), with what bazis-cli adds: the packages, `.venv`, the
    description, the rounds of the screenshots, the final checks of the rules and the ports.
    """
    ports = {'backend': 8123, 'frontend': 5199, 'e2e': 5201}
    prompt = ' '.join(prompts.new_prompt('A help desk', 'helpdesk', frontend=True, ports=ports).split())

    order = [
        'backend 8123, the dev server of the frontend 5199, the dev server of the end-to-end tests 5201',
        '"Building the frontend of a product"', 'package_guide("bazis-front")',
        'package_guide("bazis")', 'list_packages', '.venv/bin/python manage.py',
        'Step 2', 'the specs describe the description', 'what a role may not do',
        'the `navigation` in groups once it has more than five links', 'front_check',
        'Step 3', 'the tests and the translations that the rules require', 'run_doctor',
        'Step 6', 'spec/screens/<id>.yaml', 'bazis_front screens', '`run_command`', '`npm install`',
        'frontend/src/screens/<id>/extend.tsx', '(`custom`)', 't()', 'front_catalog', 'Step 7',
        'npx playwright install chromium',
        'Step 9', 'uvicorn helpdesk.main:app --port <backend>', 'bazis_front shots',
        'frontend/.scratch/shots/report.json', '`front_screenshot`',
        'the screens with errors or warnings and the main ones first', '"The visual check"',
        'at most three rounds',
        '`shot_errors` of `front_status`', 'Left for you',
        'Fix each warning of the report too, or list it there with why it stays',
        'The screens not looked at go to Left for you in one line, their number and their ids; '
        'without a shell, `reviewed` of `front_status` names them (`not_looked`)', 'Exit 2 means nothing was shot',
        'Step 10', 'the final checks of the rules',
        'npm run dev -- --port <frontend>',
    ]
    positions = [prompt.index(text) for text in order]
    assert positions == sorted(positions)
    assert 'A help desk' in prompt and '8000' not in prompt
    # the rounds of the screenshots replace the one look of before
    assert 'One pass' not in prompt
    # the steps of the guide and the rules are not repeated
    for text in ('bazis_front init', 'e2e_data', 'npm run build', 'At least 10'):
        assert text not in prompt, text


def test_a_change_of_a_product_generates_its_screens_again():
    ports = {'backend': 8123, 'frontend': 5199, 'e2e': 5201}
    prompt = ' '.join(prompts.change_prompt('Add coupons', ports=ports).split())
    assert 'Generate the screens again (`bazis_front screens`' in prompt
    assert 'an extension (`extend`) or a custom screen only for what the specs cannot say' in prompt
    assert 'bazis_front add' not in prompt


def test_new_prompt_of_a_backend():
    prompt = prompts.new_prompt('A help desk', 'helpdesk')
    assert 'helpdesk/router.py' in prompt
    assert 'bazis_front' not in prompt and 'front_check' not in prompt


#: the steps of the guide of bazis-front that FRONTEND_STEPS names: how each begins, and what
#: it does
FRONTEND_GUIDE_STEPS = {
    1: ('Install bazis-front', 'bazis_front init'),
    2: ('Describe the product', 'spec/product.yaml'),
    3: ('Build the backend', 'roles.py'),
    5: ('Run `python manage.py bazis_front check`', 'bazis_front check'),
    6: ('Generate the screens', 'bazis_front screens'),
    7: ('Design the product', 'bazis_front design'),
    8: ('Generate the end-to-end tests', 'bazis_front e2e'),
    9: ('Take the screenshots', 'bazis_front shots'),
    10: ('Check the frontend', 'npx tsc'),
}


def test_frontend_steps_are_those_of_the_guide_of_bazis_front():
    """
    FRONTEND_STEPS refers to the steps of "Building the frontend of a product" in the
    introduction of the guide of bazis-front by their numbers: they must be those steps.
    """
    pytest.importorskip('bazis.contrib.front')
    import re
    from importlib.resources import files

    guide = (files('bazis.contrib.front') / 'AGENTS.md').read_text(encoding='utf-8')
    introduction = guide.split('\n## ', 1)[0]
    section = introduction.split('\n### Building the frontend of a product\n', 1)
    assert len(section) == 2, 'the introduction has no "### Building the frontend of a product"'
    steps = {
        int(number): ' '.join(text.split())
        for number, text in re.findall(
            r'^(\d+)\. (.*?)(?=^\d+\. |^\S|\Z)', section[1].split('\n### ', 1)[0], re.M | re.S
        )
    }

    named = {int(it) for it in re.findall(r'[Ss]tep (\d+)', prompts.FRONTEND_STEPS)}
    assert named == set(FRONTEND_GUIDE_STEPS)
    for number, (start, action) in FRONTEND_GUIDE_STEPS.items():
        assert steps.get(number, '').startswith(start), (number, steps.get(number))
        assert action in steps[number], (number, steps[number])



def test_every_task_ends_with_the_summary_and_a_change_with_the_formatter():
    """
    The long session forgets the one line of the rules about the summary: every task repeats
    its headings as its last line; a change of a product runs the formatter first.
    """
    ports = {'backend': 8123, 'frontend': 5199, 'e2e': 5201}
    tasks = [
        prompts.new_prompt('A help desk', 'helpdesk'),
        prompts.new_prompt('A help desk', 'helpdesk', frontend=True, ports=ports),
        prompts.add_prompt('bazis-ws'),
        prompts.add_prompt('bazis-ws', frontend=True, ports=ports),
        prompts.change_prompt('Add coupons'),
        prompts.change_prompt('Add coupons', ports=ports),
        prompts.change_prompt('Add coupons', resumed=True),
    ]
    for task in tasks:
        assert task.strip().endswith(prompts.SUMMARY), task
    for heading in ('Built', 'Packages', 'Run', 'Outside the files', 'Left for you', 'Guide gaps'):
        assert heading in prompts.SUMMARY
    change = ' '.join(prompts.change_prompt('Add coupons', ports=ports).split())
    assert 'in `frontend/` `npm run format`, `npx tsc --noEmit`, `npm run lint`' in change
