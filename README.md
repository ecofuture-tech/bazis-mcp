# bazis-mcp

The [MCP](https://modelcontextprotocol.io) server of a [Bazis](https://github.com/ecofuture-tech/bazis)
project. It gives AI agents (Claude Code, IDEs with MCP support) what they need to build and
check a Bazis project from the project itself rather than from memory:

- the catalog of the Bazis packages, also the ones not installed: what each one solves,
  what it requires, and its guide for agents (`AGENTS.md` and `bazis_manifest.toml`);
- the facts about the project: installed packages, settings (secrets hidden), models and
  routes (`bazis.core.introspect`);
- the system checks of the project and of its Bazis packages (`manage.py bazis_doctor`),
  from bazis 2.13 also those against its database;
- its frontend layer made by bazis-front: the issues of the specs, what is stale and the
  components that can be added (`manage.py bazis_front`);
- a new project created from the conversation (the skeleton, `.venv`, the database), or an
  existing one chosen, with the rules of Bazis for the agent and its task.

The tools only read, but `create_project`, which writes a new project, and `use_project`,
which chooses the project of the next calls. The agent changes the files itself and checks
the result with the server.

## Installation

Install it as a development dependency of the project:

```bash
pip install bazis-mcp
```

Register the server for the MCP client with the directory of `manage.py` (MCP clients
start servers in their own working directory, usually the repository root):

```bash
# Claude Code, run in the repository root
claude mcp add bazis -- .venv/bin/bazis-mcp --project-dir app
```

or in `.mcp.json` of the repository:

```json
{
  "mcpServers": {
    "bazis": {"command": ".venv/bin/bazis-mcp", "args": ["--project-dir", "app"]}
  }
}
```

(`app` is the directory of `manage.py`; leave `--project-dir` out if it is the root.)

To create a project from the conversation, register the server without a project
(`claude mcp add bazis -- uvx bazis-mcp`) and ask for the application: the agent calls
`create_project`, or `use_project` for an existing one, and goes on with the next changes in
the same conversation.

`bazis-mcp [--project-dir DIR] [--settings MODULE]`:

- `--project-dir` — the directory of `manage.py` and `project.env` (default: the current
  directory when it has `manage.py`, else no project until `create_project` or
  `use_project`; the other tools answer "No project" until then);
- `--settings` — the settings module (default: `DJANGO_SETTINGS_MODULE`, or the module
  that `manage.py` sets).

The environment of the project (`project.env`, `BS_*` variables) is read as by
`manage.py`. The project tools run `bazis_introspect` and `bazis_doctor` in a new process
at every call (with the Python of the project: `--python`, else `.venv` of the project
directory or of its parent, else the Python of the server): they see the code as it is
now, while an agent changes it, and they run the project code like `manage.py` does. They
need neither the database nor Redis. If the project cannot be loaded, the catalog tools
still work and the project tools return the error.

`bazis-mcp` is not a Django app: do not add it to `BS_INSTALLED_APPS`.

## Tools

| Tool | Returns |
|---|---|
| `create_project(directory, description, name, frontend, language)` | Creates a project in a new or empty directory (an absolute path, not a temporary one nor inside another project) and serves it: the skeleton (with bazis-front unless `frontend` is false), `.venv` installed from PyPI, the project package `name` and the `language` checked with the Python of the project, the database when PostgreSQL is reachable, the ports; a failed step leaves the directory as it was. Returns the facts, the `rules` and the task `next_steps` |
| `use_project(directory)` | Serves an existing project (the directory of its `manage.py`): its status and its `rules`; the project of the command line keeps its `--settings` and `--python` |
| `project_status()` | The project served: `directory`, `settings`, `python`, `frontend`, `ports`, and `env_keys`, the names of the variables of `.env` (never their values; null without `.env` or for a `.env` that links outside the project, `env_reason` says which) |
| `list_packages` | Every Bazis package: `summary`, `solves`, `requires`, `pairs_well`, `installed_version`, `catalog_version`, `guide_version` |
| `package_guide(name, section)` | The `AGENTS.md` and the manifest of a package (`bazis` for the core), with the titles of its `sections`; a guide with sections whose result would be over 12,000 bytes of JSON comes as its introduction (`complete` false), and `section` returns one section |
| `guide_search(query, package, limit)` | The parts of the guides (AGENTS.md between two headings, extension points and pitfalls of the manifests) that match the query best, of all packages or of one: `package`, `score` and the `section` (readable whole with `package_guide`), `heading` and `text` (an excerpt when `complete` is false), or the `extension_point` or `pitfall` |
| `project_info(sections)` | `packages`, `settings`, `models`, `routes` of the project |
| `run_doctor(deploy)` | The messages of the system checks, from bazis 2.13 with the database checks (or the info `bazis.database` when the database cannot be reached); `ok` is false if there is an error |
| `front_check(layer)` | The issues of the frontend specs (`bazis_front check --json`); `ok` is false if there is an error |
| `front_status()` | The parts of the frontend that are stale (`bazis_front status --json`), by the `bazis_front` command that updates them |
| `front_catalog()` | The assets of bazis-front (components, hooks) with the capabilities and assets they require |

Resources: `bazis://packages/{name}/agents.md`, `bazis://rules` (the rules of Bazis for an
agent) and `bazis://rules/frontend` (those of a product with a frontend). Prompts:
`new_project(description)` (create a project and build it), `change_project(request)`
(change the project served), `add_package(name)` (add a package and make the checks pass),
`audit_project` (review the project against the guides and checks of its packages) and
`build_frontend` (build the frontend with bazis-front, following the steps of its guide,
from the specs to the end-to-end tests).

The frontend tools run `bazis_front` like the other project tools, and
read the registry of the assets from the bazis-front of the project (else from the
catalog). Without bazis-front they say so (`checked: false` with the `reason`) instead of
failing.

A package installed in the Python of the project (the one of the project tools) is
described by its installed files, read again at every call: the server may run with
another Python (bazis-cli runs it with its own), and the packages the agent installs or
upgrades while it runs are seen. The packages that are not installed, and those installed
in a version without a guide (before 2.4), come from `catalog.json`, a snapshot of the
latest releases taken at the release of bazis-mcp; `guide_version` is the version the
guide describes.

The settings are shown with the secrets hidden by `bazis.core.introspect` (by the names
of the settings and keys, the passwords of URLs and the credentials of `Authorization`
values). The tool results go to the model of the MCP client: review what the project keeps
in its settings before connecting it.
