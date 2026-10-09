# bazis-mcp

The MCP server of a Bazis project (`bazis-mcp` command, `MCPServer` of the official `mcp`
SDK 2.x): the catalog of the Bazis packages and the facts and system checks of the
project, for AI agents. All tools only read.

- `bazis/contrib/mcp/server.py` — the tools, the resource, the prompts and `main()`;
- `bazis/contrib/mcp/catalog.py` — the packages installed in the Python of the project
  (`project.packages`, read at every call) and the snapshot `catalog.json`,
  and the guides by sections (`GUIDE_LIMIT`: a longer AGENTS.md is read section by
  section, so that a result of `package_guide` stays under the output limit of the MCP
  clients, 25,000 tokens in Claude Code);
- `bazis/contrib/mcp/project.py` — loading the project, `bazis.core.introspect` and the
  system checks;
- `bazis/contrib/mcp/front.py` — the frontend layer (bazis-front): `bazis_front check`, the
  checks `front.*` and the registry of the assets;
- `scripts/update_catalog.py` — rebuilds `catalog.json` from the wheels on PyPI.

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
