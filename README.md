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
- the programs a project needs on this machine (Python, uv, Node.js, PostgreSQL, Redis,
  GDAL, gettext) and their installation with the package manager, once the user agrees;
- a new project created from the conversation (the skeleton, `.venv`, the database), or an
  existing one chosen, with the rules of Bazis for the agent and its task;
- for a client without a shell or files of its own: the files of the project, its
  commands from a closed table, its servers and its Bazis packages.

The tools only read, but `create_project`, which writes a new project, `use_project`,
which chooses the project of the next calls, `install_tools`, which installs programs of
the machine, and the tools of the project: `add_packages`, `run_command`, `start_server`,
`stop_server`, `write_file` and `delete_file`. They never run a command of the caller: the commands come
from closed tables, as argv without a shell, and the files stay in the project directory.

## Create an app from Claude

Connect the server once; there is nothing to configure and no Bazis to install by hand.

```bash
# Claude Code
claude mcp add bazis -- uvx bazis-mcp
```

For Claude Desktop, add the server to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "bazis": {"command": "uvx", "args": ["bazis-mcp"]}
  }
}
```

Then ask for the application, naming the folder:

> Create me an app for booking meeting rooms, in the folder `~/apps/rooms`.

and go on in the same conversation:

> Add room photos to the project.

What happens:

1. The machine is checked for the programs a project needs.
2. What is missing is listed, and nothing is installed before you confirm.
3. The project is created in the folder you named.
4. The rules and guides of Bazis are loaded for the agent.
5. The project is built and its checks are run.

The machine needs Python 3.12 or newer, uv, Node.js, PostgreSQL with PostGIS and Redis.
The server checks them and offers to install what is missing.

Limits:

- Windows is not supported for the servers of a project.
- The confirmation is asked through the client (elicitation); a client without it asks you
  to confirm in words, and the agent goes on after your answer.
- Files are read and written only inside the project; `.env` is never read.

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

Each tool in one line; what it returns and what it refuses is in the guide for agents,
[bazis/contrib/mcp/AGENTS.md](bazis/contrib/mcp/AGENTS.md), which also says what its
limits protect from.

| Tool | What it does |
|---|---|
| `check_machine()` | Finds the programs a project needs on this machine, without changing anything |
| `install_tools(names, confirmed_by_user)` | Installs them from a closed table of commands (Homebrew, apt), once the user agrees |
| `create_project(directory, description, name, frontend, language)` | Creates a project in a new or empty directory (skeleton, `.venv`, database, ports) and serves it |
| `use_project(directory)` | Serves an existing project; the project served chosen again keeps its `--settings` and `--python` |
| `project_status()` | The facts of the project served, with the names of the variables of `.env`, never their values |
| `add_packages(names)` | Adds Bazis packages and those they require to `requirements.txt` and installs them from PyPI into `.venv` |
| `run_command(kind, args)` | Runs a command of a closed table (`manage`, `pytest`, `pip`, `npm`, `npx`) as argv without a shell |
| `start_server(which)`, `stop_server(which)`, `server_logs(which, lines)` | The backend and the dev server of the frontend, in the background |
| `read_file`, `write_file`, `delete_file`, `list_files` | The files of the project directory; `.env` is never read nor written |
| `list_packages` | Every Bazis package: what it solves and requires, its installed and catalog versions |
| `package_guide(name, section)` | The `AGENTS.md` and the manifest of a package, whole or by sections |
| `guide_search(query, package, limit)` | The parts of the guides that match a query best |
| `project_info(sections)` | The packages, settings (secrets hidden), models and routes of the project |
| `run_doctor(deploy)` | The system checks of the project and of its Bazis packages |
| `front_check(layer)` | The issues of the frontend specs (bazis-front) |
| `front_status()` | The parts of the frontend that are stale |
| `front_catalog()` | The assets of bazis-front with what they require |
| `front_screenshot(file, part=1)` | A screenshot of the last run of `bazis_front shots`, as an image; a tall one in parts |

Resources: `bazis://packages/{name}/agents.md`, `bazis://rules` (the rules of Bazis for an
agent) and `bazis://rules/frontend` (those of a product with a frontend). Prompts:
`new_project(description)` (create a project and build it), `change_project(request)`
(change the project served), `add_package(name)` (add a package and make the checks pass),
`audit_project` (review the project against the guides and checks of its packages) and
`build_frontend` (build the frontend with bazis-front, following the steps of its guide,
from the specs to the end-to-end tests and the screenshots of the screens).

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
