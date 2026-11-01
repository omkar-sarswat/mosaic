# Development

Follow [getting started](getting-started.md) for installation. Run commands from the repository root unless a section says otherwise.

## Backend and frontend

```bash
python -m pip install -e .
drishti serve
```

For interface development, open a second terminal:

```bash
cd web
npm ci
npm run dev
```

The Vite server proxies `/api` to `http://127.0.0.1:8000`. Production assets are built with `npm run build` and served by FastAPI from `web/dist/`.

## Available checks

| Check | Command | What it verifies |
| --- | --- | --- |
| Python syntax | `python -m compileall -q drishti` | Application modules compile. |
| API import | `python -c "from drishti.api.app import app; print(app.title)"` | Required dependencies are importable and the app can be constructed. |
| CLI | `drishti --help` | Command entry point is installed. |
| Frontend build | `npm run build` in `web/` | TypeScript checks and Vite production bundling. |
| Frontend lint | `npm run lint` in `web/` | Configured Oxlint rules; existing findings should be distinguished from regressions. |
| Demo pipeline | `drishti demo --no-serve --no-portraits --no-redteam` | World generation and analysis when the selected database does not already exist. |
| Audit | `drishti audit verify` | Integrity of the selected database’s audit chain. |
| Pattern catalogue | `drishti patterns catalog` | Detector descriptions and mission-track metadata. |

These checks are not a full behavioural test suite. The current snapshot does not ship `tests/` or `bench/`, even though historical research refers to them. CI performs the Python syntax/import and frontend build checks; it does not certify access-control completeness or benchmark results.

## Isolate demonstration work

Set a dedicated database path before creating a new world. Keep every generated file under `var/`.

```powershell
# PowerShell
$env:DRISHTI_DB = Join-Path (Get-Location) 'var/development-demo/drishti.db'
drishti demo --no-serve --no-portraits --no-redteam
drishti audit verify
drishti serve
```

```bash
# macOS / Linux
export DRISHTI_DB="$PWD/var/development-demo/drishti.db"
drishti demo --no-serve --no-portraits --no-redteam
drishti audit verify
drishti serve
```

Do not use `--fresh` against a database containing work you need to keep. For PostgreSQL, use the explicit initialisation and population commands documented in the deployment guide.

## Browser checks

The `scripts/` directory includes Playwright utilities such as `check_workspace.py`, `check_ui.py`, and screenshot scripts. They target particular revisions of the interface and may need selector updates as the app changes.

```bash
python -m pip install playwright
python scripts/check_workspace.py http://127.0.0.1:8000
```

`check_workspace.py` launches an installed Google Chrome via Playwright. It records captures and a report under `var/ui-review/workbench/`. Use synthetic data and a disposable database; normal browsing can create audit events.

For a UI change, verify the affected workspace in both themes, at a desktop size and a narrow viewport. Check keyboard focus, loading and error states, masked fields, and whether policy refusals remain understandable. Include actual screenshots in the pull request when the appearance changes.

## Dependencies and optional features

The Python package declares its runtime requirements in `pyproject.toml`; the frontend lockfile is `web/package-lock.json`. Use `npm ci` for reproducible frontend installs. Python requirements currently use lower bounds, so installations at different times may resolve different versions.

| Extra | Install | Purpose |
| --- | --- | --- |
| `oidc` | `python -m pip install -e ".[oidc]"` | JWT verification for Keycloak. |
| `postgres` | `python -m pip install -e ".[postgres]"` | PostgreSQL driver. |
| `vision` | `python -m pip install -e ".[vision]"` | OpenCV face-comparison runtime; model files are separate. |
| `ml` | `python -m pip install -e ".[ml]"` | Optional scikit-learn linkage tooling. |
| `splink` | `python -m pip install -e ".[splink]"` | Optional Splink experiments. |

## Documentation changes

Keep command names tied to the current source. Use repository-relative image links and describe synthetic records accurately. Do not replace dated historical measurements with unsupported current claims. See [documentation standards](documentation-standards.md) and [CONTRIBUTING.md](../CONTRIBUTING.md).
