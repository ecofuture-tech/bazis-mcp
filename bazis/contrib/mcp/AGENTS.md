# bazis-mcp — guide for AI agents

The MCP server of a Bazis project. It gives an agent the catalog of the Bazis packages
(also the ones not installed) with their guides, and the facts and system checks of the
project it runs in. All tools only read; the agent changes the files itself.

## Setup

Install it as a development dependency of the project (`pip install bazis-mcp`) and
register the command for the MCP client with the directory of `manage.py` (the client
starts it in its own working directory):

```bash
claude mcp add bazis -- .venv/bin/bazis-mcp --project-dir <directory of manage.py>
```

`bazis-mcp [--project-dir DIR] [--settings MODULE]` serves the project in `DIR` (default:
the current directory) with `project.env` and the settings module of `manage.py` (or
`DJANGO_SETTINGS_MODULE`). The project tools run its management commands at every call (so they
see the current code) with the Python of the project: `--python`, else `.venv` of `DIR` or
of its parent, else the Python of the server. It is not a Django app: do not add it to `BS_INSTALLED_APPS`.

## Tools

- `list_packages` — every Bazis package: `summary`, `solves`, `requires`, `pairs_well`,
  `installed_version` (null if not installed in the Python of the project),
  `catalog_version` and `guide_version`. The installed packages are read from the Python of
  the project at every call, so a package installed or upgraded meanwhile is seen.
- `package_guide(name, section=None)` — AGENTS.md and manifest of a package (`bazis` for
  the core). An installed package is described by its installed files (read at every
  call), the others (and installed versions without a guide, before 2.4) by the catalog;
  `guide_version` says which. `sections` lists the titles of the `## ` sections of the
  AGENTS.md. A guide whose result with the manifest would be over 40,000 bytes of JSON
  (the core, bazis-front) is not returned whole, so that every result stays under the
  output limit of the client: `complete` is false and `agents_md` is the introduction;
  read every section you need with `section` (a title of `sections`; a section over
  30,000 bytes is split into parts `<title> (1/n)`).
- `project_info(sections)` — `packages`, `settings` (secrets hidden), `models`, `routes`
  of the project (`bazis.core.introspect`).
- `run_doctor(deploy)` — the Django system checks with the checks of the Bazis packages
  (`manage.py bazis_doctor`); `ok` is false if there is an error. From bazis 2.13 also the
  database checks against the database `default` (the declarations against the rows);
  the info `bazis.database` says they were skipped because the database cannot be
  reached: start it to check the data.

The frontend layer of the project (bazis-front, its guide is `package_guide("bazis-front")`):

- `front_check(layer)` — the issues of the specs in `spec/` (`manage.py bazis_front check
  --json`): `ok`, `contract` (false: not checked against `contract/contract.json`),
  `errors`, `warnings` and `issues` with `code`, `severity`, `file`, `path` and `hint`;
  `layer` (`product`, `screens`, `design`) reports one layer.
- `front_status()` — what is stale, without Node: the checks `front.*` of `bazis_doctor`
  in `stale` by the `bazis_front` command that updates the part (`contract`, `design`,
  `e2e`, `update`), `spec_issues` (the number of issues, see `front_check`), the other
  `front.*` messages (such as a contract not checked before `migrate`).
- `front_catalog()` — the assets that `bazis_front init` and `add` copy: `kind`, `target`,
  the `capabilities` they need in the contract, the assets they `requires`, `init`; from the
  bazis-front of the project, else from the catalog (`source`).

Without bazis-front, installed and with `"bazis.contrib.front"` in `INSTALLED_APPS` (or
without `spec/` for `front_check`), they return `checked: false` (`source: null` for
`front_catalog`) with the `reason` and the fix, not an error.

The resource `bazis://packages/{name}/agents.md` is the AGENTS.md of a package; the prompts
`add_package(name)`, `audit_project` and `build_frontend` describe these tasks step by step.

## Rules

- Choose packages by `solves` and read `package_guide` before using a package; follow the
  guide of the installed version (when `guide_version` differs from `installed_version`,
  upgrade the package or check the guide against its code).
- Run `run_doctor` and the tests after every change. If the project cannot be loaded, the
  project tools return the error and the catalog tools still work.
- The catalog of the packages that are not installed is a snapshot made at the release of
  bazis-mcp; their latest version may be newer.
