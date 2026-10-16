# bazis-mcp

The MCP server of a Bazis project (`bazis-mcp` command, `MCPServer` of the official `mcp`
SDK 2.x): the catalog of the Bazis packages and the facts and system checks of the
project, for AI agents, the project of the conversation (`create_project` writes a new
one, `use_project` chooses an existing one), the programs of the machine
(`check_machine`, `install_tools`) and, for a client without a shell, the work on the
project (`add_packages`, `run_command`, the servers, the files); the other tools only read.

- `bazis/contrib/mcp/server.py` — the tools, the resources, the prompts and `main()`;
- `bazis/contrib/mcp/catalog.py` — the packages installed in the Python of the project
  (`project.packages`, read at every call) and the snapshot `catalog.json`,
  and the guides by sections (measured on the JSON of a result: a guide with sections
  whose result would be over `WHOLE_LIMIT` comes as its introduction, so that an agent
  reads only the sections it needs, and is read section by section, each part within
  `GUIDE_LIMIT`, so that a result of `package_guide` stays under `RESULT_LIMIT`, below the
  output limit of the MCP clients, 25,000 tokens in Claude Code);
- `bazis/contrib/mcp/search.py` — `guide_search`: the AGENTS.md of the packages cut at
  their headings within the sections of `package_guide` (`catalog.guide_parts`), and the
  extension points and pitfalls of the manifests, ranked by BM25 without dependencies;
  each text within `TEXT_LIMIT`, so that `LIMIT_MAX` results stay under `RESULT_LIMIT`;
- `bazis/contrib/mcp/project.py` — the project served (none until `create_project` or
  `use_project` when the server starts outside a project), its creation (all or nothing),
  its status, `inside` (the boundary of the paths of the project), loading the project,
  `bazis.core.introspect` and the system checks. The project served is global state of
  the process (the tools run in worker threads): `create` and `use` change it under
  `CHANGE_LOCK`, one at a time, and `use` reads the facts of a project before serving it;
- `bazis/contrib/mcp/machine.py` — the programs a project needs on this machine (`check`,
  without writing anything) and their installation (`plan`, `install`): only the commands
  of the closed table `COMMANDS` (Homebrew; apt, whose sudo commands go to the user), as
  argv without a shell, never a command of the caller. `install_tools` gets the consent of
  the user through `Resolve` (`Elicit` when the client supports elicitation, on every
  protocol of the SDK), else `confirmed_by_user`;
- `bazis/contrib/mcp/commands.py` — `run_command`: the closed table `KINDS` (manage,
  pytest, npm, npx, pip), its arguments checked (no character of a shell, no `..`, no path
  outside the project, no `--basetemp` of pytest, arguments only for the `NPM_ARGUMENTS`
  after `--`, npx with `--no` from `frontend/node_modules`), run as argv
  without a shell in a new process group with `TIMEOUT` and progress (the group killed on
  an exception too), `E2E_PORT` and `E2E_PASSWORD` set and the password hidden in the
  output; `add_packages` (the closure of `requires` in the catalog, `requirements.txt`,
  pip, `scaffold.raise_minimums`); pip only with `venv_python` (never `sys.executable`)
  and `requirements()` of PyPI only. These limits keep an agent from mistakes and misuse,
  not a boundary against the code of the project, which the commands run;
- `bazis/contrib/mcp/processes.py` — the servers of the project (uvicorn, vite) started in
  the background (`start_new_session`, the log in `.bazis/logs`), the registry under
  `LOCK` of the servers (`RUNNING`) and of the commands that run (`COMMANDS`, of
  `commands.execute`), their stop by process group (SIGTERM, then SIGKILL; `terminate`
  stops several groups together), `stop_all` at `atexit` and by `stop_on_signals`
  (SIGTERM, SIGINT, the signals that come meanwhile ignored; installed by `main`), after
  which nothing starts (`CLOSED`, checked under `LOCK` by `start` and `commands.execute`);
- `bazis/contrib/mcp/files.py` — `read_file`, `write_file`, `delete_file`, `list_files`
  within `project.inside`, `.env` never read nor written, `NOT_WRITTEN` and `generated/`
  never written (the names compared in any case, and with `os.path.samefile`), what is
  never written never deleted, nor `NOT_DELETED` of the project directory (a symbolic link
  deleted itself), the sizes bounded by `catalog.RESULT_LIMIT` and `WRITE_LIMIT`;
- `bazis/contrib/mcp/front.py` — the frontend layer (bazis-front): `bazis_front check`,
  `bazis_front status` (its issues grouped by their `command`) and the registry of the
  assets;
- `bazis/contrib/mcp/scaffold.py`, `rules.py`, `prompts.py` — the skeleton of a new project
  and its `.venv`, `.bazis/ports.json`, the database, the language of the product and the
  modules the project package must not hide (read by a Python with Django, that of the
  project: nothing here imports Django), the rules of
  Bazis for an agent (`RULES`, `FRONTEND_RULES`) and its tasks (`new_prompt`, `add_prompt`,
  `change_prompt`); bazis-cli builds its commands on them;
- `scripts/update_catalog.py` — rebuilds `catalog.json` from the wheels on PyPI;
  `--from-clones DIR` reads the same files from the local clones `DIR/<package>` (the
  version is the one the clone is built with: setuptools-scm, honouring
  `SETUPTOOLS_SCM_PRETEND_VERSION_FOR_<PACKAGE>`, so that it can be written as a minimum).
  The local mode is only for trials against unreleased code: never commit the
  `catalog.json` it writes.

The project tools run `python -m django bazis_introspect/bazis_doctor/bazis_front` (and
read the installed packages and the registry of bazis-front with `python -c`) in a new
process at every call, so that they see the current code and packages of the project, and
the server never imports the project (stdout is the protocol channel of the stdio
transport).

The sample project used by the tests is in `sample/`, the tests are in `tests/`.

## Running the tests

The tests need neither PostgreSQL nor Redis (only GDAL for the PostGIS backend).
Run them from the `sample` directory:

```bash
cd sample
BS_DEBUG=true \
BS_SECRET_KEY=local-secret-key-that-is-long-enough-0123456789 \
BS_DATABASES__DEFAULT__HOST=localhost BS_DATABASES__DEFAULT__NAME=bazis \
BS_DATABASES__DEFAULT__USER=postgres BS_DATABASES__DEFAULT__PASSWORD=postgres \
BS_CACHES__DEFAULT__LOCATION=redis://localhost:6379/1 \
python -m pytest ../tests -o addopts="" -p no:cacheprovider
```

The tests of the skeleton (`tests/test_scaffold.py`) run `bazis_doctor` in generated
projects; those of a product with a frontend run only where bazis-front is installed, and
those that create the database of a project (also when its name is taken:
`scaffold.create_database` then creates `<name>_N` and sets it in `.env`, also through
`create_project`) with `BAZIS_CLI_TEST_POSTGRES=host:port` (a PostgreSQL server with
PostGIS, user and password `postgres`; they drop what they create).

Lint: `ruff check bazis tests sample scripts`.

## Releasing

A release is the tag `vX.Y.Z` on `main`: the Build and Publish workflow builds the package
(the version comes from the tag through setuptools-scm) and publishes it to PyPI
(pre-releases `-alphaN`/`-betaN`/`-rcN` go to Test PyPI) and creates the GitHub release.

Claude Code sessions cannot push tags. Release through the **Release** workflow instead:

1. Rebuild the catalog with `python scripts/update_catalog.py` after the releases of the
   other Bazis packages, and commit it.
2. Make sure the changes are merged into `main` and the Tests workflow is green on the
   `main` head commit (the Release workflow checks this and refuses otherwise).
3. Add the release notes as `docs/releases/X.Y.Z.md` in the change being released.
4. Start the workflow `release.yml` on `ref: main` with the input `version: X.Y.Z`
   (GitHub API: `POST /repos/ecofuture-tech/bazis-mcp/actions/workflows/release.yml/dispatches`;
   with the GitHub MCP tools: `actions_run_trigger`, method `run_workflow`).
5. The Release run creates the annotated tag and starts Build and Publish on it. Check
   that both runs succeed and that the version appears on https://pypi.org/project/bazis-mcp/.

bazis-mcp is released after the other Bazis packages: its catalog describes their latest
releases. Pick the version by semver: breaking changes (tools renamed or removed, their
results changed) bump the minor version while the project is below 3.0.
