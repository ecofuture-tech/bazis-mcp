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
`stop_server` and `write_file`. They never run a command of the caller: the commands come
from closed tables, as argv without a shell, and the files stay in the project directory.

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
| `check_machine()` | The programs a project needs on this machine, found without changing anything: for each one what it is `required_for`, its `status` (`ok`, `missing`, `old`, `stopped` for a server), what was `found`, the `install_command` of the package `manager` (Homebrew on macOS, apt on Debian and Ubuntu; null without one, and for the Python of a project, whose `.venv` is created again) and `needs_sudo`; `missing` names those not `ok` |
| `install_tools(names, confirmed_by_user)` | Runs the `install_command` of the programs `names` of `check_machine`, and nothing else, in the order of `check_machine`, once the user agrees: the client asks the user when it supports elicitation, else `confirmed_by_user` must be true; without that nothing runs and `to_confirm` lists the commands. A command with sudo, a Homebrew this user cannot run or no package manager: `run_yourself` gives the command (or null) for the user to run |
| `create_project(directory, description, name, frontend, language)` | Creates a project in a new or empty directory (an absolute path, not a temporary one nor inside another project) and serves it: the skeleton (with bazis-front unless `frontend` is false), `.venv` installed from PyPI, the project package `name` and the `language` checked with the Python of the project, the database when PostgreSQL is reachable, the ports; a failed step leaves the directory as it was. Returns the facts, the `rules` and the task `next_steps` |
| `use_project(directory)` | Serves an existing project (the directory of its `manage.py`): its status and its `rules`; the project of the command line keeps its `--settings` and `--python` |
| `add_packages(names)` | Adds the Bazis packages `names` (names of the catalog) and those they require to `requirements.txt`, with the version of the catalog as the minimum, installs `requirements-dev.txt` from PyPI into `.venv` and raises the minimums to the installed releases; when pip fails, `requirements.txt` stays as it was. The apps and settings are added by the agent as the guides say |
| `run_command(kind, args)` | Runs a command of a closed table as argv without a shell, with a timeout of 600 seconds and its progress reported: `manage` (makemigrations, migrate, check, bazis_doctor, collectstatic, e2e_data, `bazis_front <subcommand>`, `bazis_messages <subcommand>`), `pytest`, `pip` (`install -r requirements-dev.txt` only) in the project directory; `npm` (`install` and `ci` alone; the scripts build, lint, test, e2e, format, with the filters of the tests after `--` for test and e2e) and `npx` (`tsc --noEmit`, `playwright install chromium`, from `frontend/node_modules` only: `npx --no` never downloads) in `frontend/`. The arguments have no character of a shell, no `..` and no path outside the project. `E2E_PORT` (`.bazis/ports.json`) and `E2E_PASSWORD` (`.env`) are set by the server, never shown. Returns `exit_code`, `ok`, `timed_out` and the ends of `stdout` and `stderr` |
| `start_server(which)`, `stop_server(which)`, `server_logs(which, lines)` | The `backend` (`uvicorn <package>.main:app`) and the dev server of the `frontend` (`npm run dev`) on their ports of `.bazis/ports.json`, in the background, their output in `.bazis/logs/<which>.log`; refused when the port is taken by another process. Stopped with the processes they started (SIGTERM, then SIGKILL), and when bazis-mcp ends |
| `read_file(path, offset, limit)`, `write_file(path, content)`, `list_files(subdir)` | The files of the project directory (symbolic links resolved): `.env` is never read nor written, `.venv/`, `.git/`, `contract/` and the `generated/` directories are never written (these names in any case, and a hard link to `.env`); a file read fits in a result (about 40,000 bytes), a longer one is read in parts (its lines from `offset`, at most `limit`, `next_offset` the line to read next), a file written has at most 1,000,000 bytes |
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
