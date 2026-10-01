# bazis-mcp

The [MCP](https://modelcontextprotocol.io) server of a [Bazis](https://github.com/ecofuture-tech/bazis)
project. It gives AI agents (Claude Code, IDEs with MCP support) what they need to build and
check a Bazis project from the project itself rather than from memory:

- the catalog of the Bazis packages, also the ones not installed: what each one solves,
  what it requires, and its guide for agents (`AGENTS.md` and `bazis_manifest.toml`);
- the facts about the project: installed packages, settings (secrets hidden), models and
  routes (`bazis.core.introspect`);
- the system checks of the project and of its Bazis packages (`manage.py bazis_doctor`).

All tools only read. The agent changes the files itself and checks the result with the
server.

## Installation

Install it as a development dependency of the project:

```bash
pip install bazis-mcp
```

Register the server for the MCP client; it runs in the directory of `manage.py`:

```bash
# Claude Code
claude mcp add bazis -- .venv/bin/bazis-mcp
```

or in `.mcp.json` of the project:

```json
{
  "mcpServers": {
    "bazis": {"command": ".venv/bin/bazis-mcp", "args": []}
  }
}
```

`bazis-mcp [--project-dir DIR] [--settings MODULE]`:

- `--project-dir` — the directory of `manage.py` and `project.env` (default: the current
  directory);
- `--settings` — the settings module (default: `DJANGO_SETTINGS_MODULE`, or the module
  that `manage.py` sets).

The environment of the project (`project.env`, `BS_*` variables) is read as by
`manage.py`. The server needs neither the database nor Redis. It loads the settings and
the application of the project, so it runs the project code like `manage.py` does. If the
project cannot be loaded, the catalog tools still work and the project tools return the
error.

`bazis-mcp` is not a Django app: do not add it to `BS_INSTALLED_APPS`.

## Tools

| Tool | Returns |
|---|---|
| `list_packages` | Every Bazis package: `summary`, `solves`, `requires`, `pairs_well`, `installed_version`, `catalog_version` |
| `package_guide(name)` | The `AGENTS.md` and the manifest of a package (`bazis` for the core) |
| `project_info(sections)` | `packages`, `settings`, `models`, `routes` of the project |
| `run_doctor(deploy)` | The messages of the system checks; `ok` is false if there is an error |

Resource: `bazis://packages/{name}/agents.md`. Prompts: `add_package(name)` (add a package
and make the checks pass) and `audit_project` (review the project against the guides and
checks of its packages).

An installed package is described by its installed files. The packages that are not
installed come from `catalog.json`, a snapshot of the latest releases taken at the release
of bazis-mcp.
