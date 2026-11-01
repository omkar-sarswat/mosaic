# Mosaic web application

The React and TypeScript interface for Mosaic by Weirwood. It connects to the FastAPI service in [`drishti/`](../drishti/) and uses the active identity and case context for requests.

## Run

Use Node 22.12 or newer in the Node 22 line. Start the backend on port 8000, then run from this directory:

```bash
npm ci
npm run dev
```

Open Vite’s printed URL. `/api` requests are proxied to `http://127.0.0.1:8000` by [`vite.config.ts`](vite.config.ts).

## Build and check

```bash
npm run build
npm run lint
```

The build runs TypeScript checks and writes `dist/`. FastAPI serves this directory when running the combined app. `npm run preview` previews the static frontend build; use the combined backend server for an end-to-end application check.

## Source map

- `src/App.tsx`: navigation, account and case context, workspace composition.
- `src/api.ts`: HTTP client and identity handling.
- `src/views/`: investigation, record, operations, and governance workspaces.
- `src/components/`: shared controls and visual components.
- `public/brand/`: official Weirwood mark variants.

The current graph implementation uses Graphology and Sigma; charts use ECharts, and maps use MapLibre. Blueprint and Mantine supply UI components.

See [development](../docs/development.md), [architecture](../docs/architecture.md), and [contributing](../CONTRIBUTING.md) for the full workflow.
