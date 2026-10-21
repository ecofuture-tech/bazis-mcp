# bazis-mcp

The MCP server of a Bazis project (`bazis-mcp` command, `MCPServer` of the official `mcp`
SDK 2.x): the catalog of the Bazis packages and the facts and system checks of the
project, for AI agents, the project of the conversation (`create_project` writes a new
one, `use_project` chooses an existing one), the programs of the machine
(`check_machine`, `install_tools`) and, for a client without a shell, the work on the
project (`add_packages`, `run_command`, the servers, the files); the other tools only read.

How the tools work and what they refuse is in the guide,
`bazis/contrib/mcp/AGENTS.md`; the modules:

- `bazis/contrib/mcp/server.py` — the tools, the resources, the prompts and `main()`;
- `bazis/contrib/mcp/catalog.py` — the installed packages, the snapshot `catalog.json` and
  the guides by sections, within the result limits of the MCP clients;
- `bazis/contrib/mcp/search.py` — `guide_search` (BM25 over the guides and manifests);
- `bazis/contrib/mcp/project.py` — the project served (global state, changed under
  `CHANGE_LOCK`), its creation, status and boundary (`inside`), introspection and checks;
- `bazis/contrib/mcp/machine.py` — `check_machine` and `install_tools` (the closed table
  `COMMANDS`, the consent of the user);
- `bazis/contrib/mcp/commands.py` — `run_command` (the closed table `KINDS`) and
  `add_packages`;
- `bazis/contrib/mcp/processes.py` — the servers and the commands that run, stopped by
  process group, also when bazis-mcp ends;
- `bazis/contrib/mcp/files.py` — `read_file`, `write_file`, `delete_file`, `clean_project`,
  `list_files`;
- `bazis/contrib/mcp/front.py` — the frontend tools (bazis-front);
- `bazis/contrib/mcp/scaffold.py`, `rules.py`, `prompts.py` — the skeleton of a new
  project, the rules and the tasks of an agent, used by bazis-cli too (nothing here
  imports Django);
- `scripts/update_catalog.py` — rebuilds `catalog.json` from PyPI, or from local clones
  with `--from-clones DIR` for trials only: never commit the `catalog.json` it writes.

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
