# Getting started with Mosaic

This guide runs the synthetic demonstration on your own machine. The internal command is `drishti`; the application it serves is Mosaic by Weirwood.

## Prerequisites

- Python 3.11 or newer; Python 3.12 is the recommended baseline.
- Node.js 22.12 or newer in the Node 22 release line, and npm.
- Git and a modern desktop browser.
- Network access to install dependencies. The saved alert snapshot avoids a live-feed dependency during demo generation.

## Install

```bash
git clone https://github.com/omkar-sarswat/mosaic.git
cd mosaic
python -m venv .venv
```

Activate on Windows PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
```

Activate on macOS or Linux:

```bash
source .venv/bin/activate
```

If PowerShell execution policy prevents activation, use `.\.venv\Scripts\python.exe` and `.\.venv\Scripts\drishti.exe` directly instead of changing machine-wide policy.

```bash
python -m pip install -e .
cd web
npm ci
npm run build
cd ..
drishti demo --no-portraits --no-redteam
```

Open [localhost:8000](http://127.0.0.1:8000). Keep the terminal running. Stop the server with **Ctrl+C**.

## What the first run creates

The pipeline loads the bundled geography and saved public alerts, creates synthetic records and scenarios, runs record matching and analytical detectors, and opens demonstration cases. It stores the database and runtime files under `var/`, which is excluded from Git.

`--no-portraits` skips optional synthetic portrait assignment. `--no-redteam` skips adversary simulation during first setup. The rest of the demo pipeline still runs. `drishti demo` reuses an existing database; `drishti serve` starts only the server.

`drishti demo --fresh` **deletes and rebuilds the selected SQLite database**. Use it only for disposable demonstration data. Prefer a separate database path when experimenting; see [deployment configuration](deployment.md).

## Explore a case

1. Choose a demonstration account from the account menu.
2. Select one of its existing cases. Different roles and agencies see different options.
3. Press **Ctrl+K** and search for a name or identifier from that case.
4. Inspect the dossier’s source references, relationships, financial activity, and timeline.
5. Open **Network**, **Money trail**, or **Connections** from the investigation navigation.
6. Inspect **Cases** for its board, requests, evidence, and reports.
7. Switch to an appropriate supervisor to review a protected action, or to oversight to inspect audit events.

The default sign-in experience is a synthetic role picker. It is development authentication, not a deployment identity system.

## Optional face-search demonstration

Face search needs OpenCV and the YuNet/SFace models:

```bash
python -m pip install -e ".[vision]"
python scripts/fetch_models.py
```

The downloader places model binaries in `data/models/`, outside Git. Review their upstream terms before deployment. The default face engine uses CPU inference. Existing sample faces are documented as synthetic in [data/samples/faces/README.txt](../data/samples/faces/README.txt).

A database created before the models were available may not have its face gallery populated. Build a separate disposable demo database after installing the models to exercise the full workflow. Face search operates on a selected face in case evidence, returns candidates, and requires a separate officer for confirmation.

## Develop the interface

Run the backend in one terminal:

```bash
drishti serve
```

In a second terminal:

```bash
cd web
npm run dev
```

Open the URL printed by Vite. Its `/api` proxy points to port 8000. For the combined application without Vite, rebuild `web/dist` and open port 8000.

## Troubleshooting

| Symptom | Check |
| --- | --- |
| `drishti` is not recognised | Activate the virtual environment or run its executable directly. Re-run `python -m pip install -e .` from the repository root. |
| UI missing or stale at port 8000 | Run `npm ci` and `npm run build` inside `web/`; FastAPI serves that build. |
| Vite reports an unsupported Node engine | Use the documented Node 22 baseline; older Node 20 releases may not satisfy this Vite version. |
| API requests fail in the Vite UI | Start the backend on port 8000 and inspect its terminal output. |
| A record or workspace is unavailable | Check account role, active case, purpose, and clearance. Missing access can be an intentional policy decision. |
| Face search is unavailable | Install the `vision` extra and fetch the model files; then use a demo database with a seeded gallery. |
| Map background is missing | Check the tile service connection. Core records do not supply an offline basemap. |
| Demo starts with unexpected records | `drishti demo` reused an existing database. Use a separate `DRISHTI_DB` path for a clean experiment. |

[Documentation index](README.md).
