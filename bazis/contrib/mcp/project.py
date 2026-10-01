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
The Bazis project the server runs in: loading its settings and application, its facts and
its system checks.
"""

import os
import re
import sys
from pathlib import Path


SETTINGS_RE = re.compile(r"""DJANGO_SETTINGS_MODULE['"]\s*,\s*['"]([\w.]+)['"]""")


class ProjectError(Exception):
    """
    The project cannot be loaded; the message says why.
    """


#: the error of loading the settings, if any (the catalog still works without them)
_setup_error: str | None = None


def find_settings(project_dir: Path) -> str | None:
    """
    The settings module of the project: `DJANGO_SETTINGS_MODULE`, or the default that
    `manage.py` sets.
    """
    if module := os.environ.get('DJANGO_SETTINGS_MODULE'):
        return module
    manage = project_dir / 'manage.py'
    if manage.is_file() and (match := SETTINGS_RE.search(manage.read_text(encoding='utf-8'))):
        return match.group(1)
    return None


def setup(project_dir: Path, settings_module: str | None = None) -> None:
    """
    Loads the Django settings of the project in `project_dir` (the directory of
    `manage.py` and `project.env`). An error is kept and reported by the project tools.
    """
    global _setup_error

    import django

    os.chdir(project_dir)
    sys.path.insert(0, str(project_dir))
    settings_module = settings_module or find_settings(project_dir)
    if not settings_module:
        _setup_error = (
            f'No settings module: {project_dir} has no manage.py that sets '
            'DJANGO_SETTINGS_MODULE. Pass --settings or set DJANGO_SETTINGS_MODULE.'
        )
        return
    os.environ['DJANGO_SETTINGS_MODULE'] = settings_module
    try:
        django.setup()
    except Exception as err:
        _setup_error = f'The settings {settings_module} cannot be loaded: {err!r}'


def require_settings() -> None:
    if _setup_error:
        raise ProjectError(_setup_error)
    from django.conf import settings

    if not settings.configured:
        raise ProjectError('The Django settings are not loaded.')


def load_app():
    """
    The FastAPI application of the project (the checks and the facts of the routes need it).
    """
    require_settings()
    try:
        from bazis.core.app import app
    except Exception as err:
        raise ProjectError(f'The application cannot be loaded: {err!r}') from err
    return app


def info(sections: list[str] | None = None) -> dict:
    from bazis.core import introspect

    data = introspect.project_info(load_app())
    if sections:
        data = {key: value for key, value in data.items() if key in sections}
    return data


def doctor(deploy: bool = False) -> dict:
    """
    The Django system checks of the project, as `manage.py bazis_doctor --json` runs them.
    """
    from django.core import checks

    load_app()
    messages = [m for m in checks.run_checks(include_deployment_checks=deploy) if not m.is_silenced()]
    return {
        'ok': not any(m.level >= checks.ERROR for m in messages),
        'messages': [
            {
                'id': m.id,
                'level': _level_name(m.level),
                'message': m.msg,
                'hint': m.hint,
                'object': str(m.obj) if m.obj is not None else None,
            }
            for m in messages
        ],
    }


def _level_name(level: int) -> str:
    from django.core import checks

    for name in ('CRITICAL', 'ERROR', 'WARNING', 'INFO', 'DEBUG'):
        if level >= getattr(checks, name):
            return name.lower()
    return 'debug'
