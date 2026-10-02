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
    if manage.is_file() and (match := SETTINGS_RE.search(manage.read_text(encoding='utf-8', errors='replace'))):
        return match.group(1)
    return None


def setup(project_dir: Path, settings_module: str | None = None) -> None:
    """
    Loads the Django settings of the project in `project_dir` (the directory of
    `manage.py` and `project.env`). An error is kept and reported by the project tools.
    """
    global _setup_error

    try:
        _setup_error = _setup(project_dir, settings_module)
    except (Exception, SystemExit) as err:
        _setup_error = f'The project in {project_dir} cannot be loaded: {err!r}'


def _setup(project_dir: Path, settings_module: str | None) -> str | None:
    import django

    os.chdir(project_dir)
    sys.path.insert(0, str(project_dir))
    settings_module = settings_module or find_settings(project_dir)
    if not settings_module:
        return (
            f'No settings module: {project_dir} has no manage.py that sets '
            'DJANGO_SETTINGS_MODULE. Pass --project-dir, --settings or set DJANGO_SETTINGS_MODULE.'
        )
    os.environ['DJANGO_SETTINGS_MODULE'] = settings_module
    try:
        django.setup()
    except (Exception, SystemExit) as err:
        return f'The settings {settings_module} cannot be loaded: {err!r}'
    return None


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
    except (Exception, SystemExit) as err:
        raise ProjectError(f'The application cannot be loaded: {err!r}') from err
    return app


def info(sections: list[str] | None = None) -> dict:
    """
    The requested sections of `bazis.core.introspect.project_info` (default: all). The
    packages need neither the settings nor the application, the routes need the application.
    """
    from bazis.core import introspect

    sections = sections or ['packages', 'settings', 'models', 'routes']
    data = {}
    if 'packages' in sections:
        data['packages'] = introspect.packages()
    if 'settings' in sections:
        require_settings()
        data['settings'] = introspect.settings_info()
    if 'models' in sections:
        require_settings()
        data['models'] = introspect.models_info()
    if 'routes' in sections:
        data['routes'] = introspect.routes_info(load_app())
    return data


def doctor(deploy: bool = False) -> dict:
    """
    The Django system checks of the project, as `manage.py bazis_doctor --json` runs them.
    """
    from bazis.core import introspect

    load_app()
    messages = introspect.check_messages(deploy)
    return {
        'ok': not any(it['level'] in ('error', 'critical') for it in messages),
        'messages': messages,
    }
