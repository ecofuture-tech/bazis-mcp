# bazis-mcp — guide for AI agents

The MCP server of a Bazis project. It gives an agent the catalog of the Bazis packages
(also the ones not installed) with their guides, and the facts and system checks of the
project it runs in. All tools only read; the agent changes the files itself.

## Setup

Install it as a development dependency of the project (`pip install bazis-mcp`) and
register the command for the MCP client, run in the directory of `manage.py`:

```bash
claude mcp add bazis -- .venv/bin/bazis-mcp
```

`bazis-mcp [--project-dir DIR] [--settings MODULE]` loads the project in `DIR` (default:
the current directory) with `project.env` and the settings module of `manage.py` (or
`DJANGO_SETTINGS_MODULE`). It is not a Django app: do not add it to `BS_INSTALLED_APPS`.

## Tools

- `list_packages` — every Bazis package: `summary`, `solves`, `requires`, `pairs_well`,
  `installed_version` (null if not installed) and `catalog_version`.
- `package_guide(name)` — AGENTS.md and manifest of a package (`bazis` for the core).
  An installed package is described by its installed files, the others by the catalog.
- `project_info(sections)` — `packages`, `settings` (secrets hidden), `models`, `routes`
  of the project (`bazis.core.introspect`).
- `run_doctor(deploy)` — the Django system checks with the checks of the Bazis packages
  (`manage.py bazis_doctor`); `ok` is false if there is an error.

The resource `bazis://packages/{name}/agents.md` is the AGENTS.md of a package; the prompts
`add_package(name)` and `audit_project` describe these tasks step by step.

## Rules

- Choose packages by `solves` and read `package_guide` before using a package; follow the
  guide of the installed version.
- Run `run_doctor` and the tests after every change. If the project cannot be loaded, the
  project tools return the error and the catalog tools still work.
- The catalog of the packages that are not installed is a snapshot made at the release of
  bazis-mcp; their latest version may be newer.
