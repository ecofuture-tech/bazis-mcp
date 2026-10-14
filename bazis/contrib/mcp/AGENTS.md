# bazis-mcp — guide for AI agents

The MCP server of a Bazis project. It gives an agent the catalog of the Bazis packages
(also the ones not installed) with their guides, and the facts and system checks of the
project it serves: the one it runs in, or the one created (`create_project`) or chosen
(`use_project`) in the conversation, and the programs a project needs on the machine
(`check_machine`), installed once the user agrees (`install_tools`). For a client without
a shell or files of its own it also reads and writes the files of the project, runs its
commands from a closed table, starts its servers and adds its Bazis packages; the other
tools only read.

## Setup

Install it as a development dependency of the project (`pip install bazis-mcp`) and
register the command for the MCP client with the directory of `manage.py` (the client
starts it in its own working directory):

```bash
claude mcp add bazis -- .venv/bin/bazis-mcp --project-dir <directory of manage.py>
```

Without a project (`uvx bazis-mcp`, started anywhere) it serves none until the agent calls
`create_project` or `use_project`: the other tools answer "No project: call create_project
or use_project".

`bazis-mcp [--project-dir DIR] [--settings MODULE]` serves the project in `DIR` (default:
the current directory when it has `manage.py`) with `project.env` and the settings module of `manage.py` (or
`DJANGO_SETTINGS_MODULE`). The project tools run its management commands at every call (so they
see the current code) with the Python of the project: `--python`, else `.venv` of `DIR` or
of its parent, else the Python of the server. It is not a Django app: do not add it to `BS_INSTALLED_APPS`.

## Tools

The programs of the machine:

- `check_machine()` — the programs a project needs here, found without changing anything:
  `python` (that of the project, else that of the server, 3.12 or newer), `uv`, `node`
  (with npm, for the frontend), `postgresql`, `postgresql-service` (a server on port 5432),
  `redis`, `redis-service` (port 6379), `gdal`, `gettext`. For each one `required_for`,
  `status` (`ok`, `missing`, `old`, `stopped` for a server), `found`, `install_command`
  (from the closed table of the package `manager`: Homebrew on macOS, apt on Debian and
  Ubuntu; null without one, and for the Python of a project: create its `.venv` again with
  a newer Python) and `needs_sudo`; `missing` names those not `ok`. The keg-only
  PostgreSQL of Homebrew is found in `<prefix>/opt/postgresql@18/bin`.
- `install_tools(names, confirmed_by_user=False)` — runs the `install_command` of the
  programs `names` (names of `check_machine`; a server is started by its `-service` name),
  never another command, as argv without a shell, once the user agrees: the client asks
  the user when it supports elicitation, else `confirmed_by_user` must be true, set only
  after the user said yes in the conversation. Without that nothing runs and `to_confirm`
  lists the commands. They run in the order of `check_machine` (a program before its
  server). `installed` has the result of each command (`ok`, the end of its `output`); `run_yourself` the programs it does not install (a command with sudo, as all
  those of apt, a Homebrew this user cannot run, no package manager or no command in it)
  with the `reason` and the command for the user, or null.

The project of the conversation:

- `create_project(directory, description, name=None, frontend=True, language=None)` — a
  new project in `directory` (an absolute path to a new or empty directory; a temporary
  directory, the home directory and a directory inside another project are refused),
  served from then on: the skeleton (bazis-front in its requirements and apps unless
  `frontend` is false, which needs Node.js), `.venv` installed from PyPI, the project
  package `name` (default: from the name of the directory) checked against the modules of
  the Python of the project, the `language` of the product (a code of Django such as `ru`,
  `pt-br`; default English, until the agent sets that of the description), the database
  when PostgreSQL is reachable (`database` says what was done) and the `ports`. A failed
  step leaves the directory as it was. `rules` are the rules to follow, `next_steps` the
  task of building the project.
- `use_project(directory)` — serves the existing project in `directory` (the directory of
  its `manage.py`): its status and its `rules`. The project served changes only once its
  status is read; the project of the command line keeps its `--settings` and `--python`.
- `project_status()` — `directory`, `settings`, `python`, `frontend` (made by
  `bazis_front init`; `use_project` adds the rules of the frontend then), `ports` (null
  until chosen or when `.bazis/ports.json` cannot be read) and `env_keys`: the names of the
  variables of `.env` (read as python-dotenv reads it; a line without `=` and a name that
  is not an identifier are not variables), never their values; null without
  `.env` or for a `.env` that links outside the project directory, `env_reason` says which.

`create_project` and `use_project` run one call at a time: a second call waits for the
first one to end.

The work on the project served (never a command or a path of the caller outside them):

- `add_packages(names)` — adds the Bazis packages `names` (names of the catalog; another
  name is refused) and those they require (`requires` of their manifests) that the
  requirements do not name yet to `requirements.txt`, with the version of the catalog as
  the minimum, installs `requirements-dev.txt` from PyPI into `.venv`
  (`python -m pip install -r requirements-dev.txt`) and raises the minimums to the
  installed releases: `added`, `required` (named already), `installed` (their versions)
  and `install` (the result of pip; when it fails or the call fails meanwhile,
  `requirements.txt` stays as it was).
  pip (here and in `run_command`) installs only into the Python of the project, `.venv`
  or `--python`, never into that of bazis-mcp (without one it is refused: the user creates
  `.venv`), and only from PyPI: every line of `requirements.txt` and
  `requirements-dev.txt` is a requirement (a name, its `[extras]` and versions, a
  comment), or `-r requirements.txt` in `requirements-dev.txt`; a URL, `git+`, a path,
  `-e`, another `-r`, `-c`, `--index-url`, `--find-links` or another option of pip, and
  an environment marker are refused before pip runs.
  The apps and settings (`BS_INSTALLED_APPS`) are added by the agent as the guides say.
- `run_command(kind, args=[])` — a command of a closed table, as argv without a shell,
  with a timeout of 600 seconds (the group of its processes is killed then, and when the
  call fails meanwhile, such as when the client is gone) and its progress reported every 5
  seconds: `manage` (`.venv/bin/python manage.py`: makemigrations,
  migrate, check, bazis_doctor, collectstatic, e2e_data, `bazis_front` with one of its
  subcommands, `bazis_messages` with one of its actions), `pytest` (`python -m pytest`) and
  `pip` (only `install -r requirements-dev.txt`) in the project directory, `npm` (`npm
  install` and `npm ci` without arguments, the dependencies of the frontend after
  `bazis_front add` or `update`; `npm run` of build, lint, test, e2e, format, not dev, and
  only test and e2e take arguments, after `--`: the names of tests and the options
  `-t`/`--testNamePattern` of test, `-g`/`--grep`, `--grep-invert`, `--project`,
  `--workers` of e2e) and `npx` (only `tsc --noEmit` and `playwright install chromium`,
  as `npx --no`: a tool of `frontend/node_modules`, never downloaded; without it the
  command is refused) in `frontend/`. npm and npx are found on the `PATH` (`npm.cmd` on
  Windows). An argument with a character of a shell, with `..` or with a path outside the
  project (also through a symbolic link) is refused, and so are the options of `manage`
  that choose other settings (`--settings`, `--pythonpath`, also abbreviated) and those
  of `pytest` that remove or write the paths they name or change its configuration,
  plugins or settings (`--basetemp`, `--junitxml`/`--junit-xml`, `--log-file`, `--debug`,
  `--rootdir`, `--confcutdir`, `-c`/`--config-file`, `-o`/`--override-ini`, `-p`,
  `--pyargs`, `--ds`, `--dc`, also in a group such as `-vp`, and `@<file>`).
  The commands read no stdin (pass `--noinput` where Django asks), and get the settings
  module of the project, `E2E_PORT` of `.bazis/ports.json` and `E2E_PASSWORD` of `.env`
  (a new project has one), whose value is hidden in their output. Returns `command`,
  `directory`, `exit_code` (null after the timeout), `ok`, `timed_out` and the last 10,000
  bytes of `stdout` and `stderr`.
- `start_server(which)` — `backend` (`python -m uvicorn <project package>.main:app --port
  <backend>`) or `frontend` (`npm run dev -- --port <frontend> --strictPort` in
  `frontend/`), on the ports of `.bazis/ports.json`, in the background in a new process
  group, the output in `.bazis/logs/<which>.log`; it waits up to 60 seconds for the port:
  `pid`, `port`, `url`, `running`, `ready`, and the `exit_code` and `output` of a server
  that ended at once. Refused when it runs already or another process has its port.
- `stop_server(which)` — SIGTERM to its group, SIGKILL after 10 seconds: `stopped` and
  `exit_code`, or the `reason`. The servers started stop when bazis-mcp ends, also by
  SIGTERM (as a client ends its server) or SIGINT. On Windows a
  process group is not stopped: only the process itself is (the processes it started,
  such as the node of `npm run dev` or of a command over its timeout, may stay), so the
  servers and the long commands are not supported there.
- `server_logs(which, lines=100)` — the last lines of its log (at most 20,000 bytes) and
  whether it is `running`.
- `read_file(path, offset=0, limit=None)`, `write_file(path, content)`,
  `list_files(subdir='')` — the files of the project directory (a path relative to it or
  absolute in it, symbolic links resolved). `.env` is never read nor written
  (`project_status` gives the names of its variables); `.venv/`, `.git/`, `contract/` and
  the `generated/` directories are never written. These names count in any case (`.ENV`
  is `.env`), and so does a file that is the same as one of them (a hard link to `.env`).
  A file read is UTF-8 text: its lines from `offset` (the first is 0), at most `limit`,
  in a result of about 40,000 bytes at most; `next_offset` is the line to read next, null
  at the end, so a longer file is read in parts. A file written has at most 1,000,000
  bytes, its directories are created; `list_files` lists one directory (`name`, `type`:
  `directory`, `file`, `link` never followed, `other`; `size`), at most 400 entries.

The catalog and the project served:

- `list_packages` — every Bazis package: `summary`, `solves`, `requires`, `pairs_well`,
  `installed_version` (null if not installed in the Python of the project),
  `catalog_version` and `guide_version`. The installed packages are read from the Python of
  the project at every call, so a package installed or upgraded meanwhile is seen.
- `package_guide(name, section=None)` — AGENTS.md and manifest of a package (`bazis` for
  the core). An installed package is described by its installed files (read at every
  call), the others (and installed versions without a guide, before 2.4) by the catalog;
  `guide_version` says which. `sections` lists the titles of the `## ` sections of the
  AGENTS.md. A guide with sections whose result with the manifest would be over 12,000
  bytes of JSON is not returned whole, so that an agent reads only the sections it needs
  (and every result stays under the output limit of the client: 40,000 bytes for a guide
  without sections): `complete` is false and `agents_md` is the introduction, which maps
  the sections; read a section with `section` when the step at hand needs it (a title of
  `sections`; a section over 30,000 bytes is split into parts `<title> (1/n)`).
- `guide_search(query, package=None, limit=5)` — the parts of the guides that match the
  words of the query (identifiers such as `validate_item` too), of all packages or of one:
  the AGENTS.md cut at its headings (without the map of the sections, `### The sections`
  of an introduction) and the extension points and pitfalls of the manifests, ranked by
  BM25 with the words of the headings counting more. A result has
  `package`, `score` and either `section` (a title for `package_guide(name, section)`),
  `heading` (the subsection, null at the top of the section) and `text` (whole up to
  3,000 bytes, else an excerpt around the words with `complete` false), or
  `extension_point` or `pitfall`. `limit` is at most 10.
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
- `front_status()` — what is stale, without Node: the issues of `bazis_front status --json`
  in `stale` by the `bazis_front` command that updates the part (`contract`, `design`,
  `e2e`, `update`), `spec_issues` (the number of issues, see `front_check`), the other
  issues in `messages` (such as a contract not checked before `migrate`).
- `front_catalog()` — the assets that `bazis_front init` and `add` copy: `kind`, `target`,
  the `capabilities` they need in the contract, the assets they `requires`, `init`; from the
  bazis-front of the project, else from the catalog (`source`).

Without bazis-front, installed and with `"bazis.contrib.front"` in `INSTALLED_APPS` (or
without `spec/` for `front_check`), they return `checked: false` (`source: null` for
`front_catalog`) with the `reason` and the fix, not an error.

The resource `bazis://packages/{name}/agents.md` is the AGENTS.md of a package,
`bazis://rules` and `bazis://rules/frontend` the rules of an agent (also in the results of
`create_project` and `use_project`); the prompts `new_project(description)`,
`change_project(request)`, `add_package(name)`, `audit_project` and `build_frontend`
describe these tasks step by step (`build_frontend` with the steps of the guide of
bazis-front).

## Rules

- Before creating a project, call `check_machine`; list the `missing` programs to the user
  with what they are for and their `install_command`, and call `install_tools` only after
  the user said yes. Give the user the `run_yourself` commands, then check again.
- Without a project, create it (`create_project`) or choose it (`use_project`) first; the
  rules speak of the current directory: it is `directory` of the project. Change only the
  files in it, and never read `.env` (`project_status` gives the names of its variables).
- Run the commands of the rules with `run_command`, the servers with `start_server` and
  `stop_server`, and add Bazis packages with `add_packages`; never in another way.
- Choose packages by `solves` and read `package_guide` before using a package; follow the
  guide of the installed version. Find the section that answers a question with
  `guide_search` instead of reading every section (when `guide_version` differs from `installed_version`,
  upgrade the package or check the guide against its code).
- Run `run_doctor` after a change, and the tests once the change is done. If the project
  cannot be loaded, the project tools return the error and the catalog tools still work.
- The catalog of the packages that are not installed is a snapshot made at the release of
  bazis-mcp; their latest version may be newer.
