# Repository assets and attribution

The repository includes the application source, build configuration, official Weirwood identity, product publications, original documentation images, and the small data assets used by the local demonstration. Dependencies and generated operational state are rebuilt or provisioned separately.

## Included

| Path | Content and provenance |
| --- | --- |
| `brand/` | Official Weirwood tree-mark variants supplied with the project. The README uses the dark and light 512-pixel variants. |
| `docs/Mosaic-*.pdf` | The existing brochure, product guide, and product book. |
| `docs/product-book/shots/` | Original screenshots of the synthetic demonstration, retained at their source dimensions. |
| `docs/brochure/`, `docs/product-guide/`, `docs/product-book/` | Publication builders, editorial sources, artwork, fonts, and their local notices. |
| `data/reference/` | LGD-code tables, district boundaries, and OSM hospital reference data, attributed in [NOTICE](../NOTICE). |
| `data/samples/sachet/` | Saved public disaster-alert snapshot. |
| `data/samples/faces/` | Synthetic demonstration images, including provenance in the [sample README](../data/samples/faces/README.txt). |
| `models/matcher.json` | Small record-matching parameter file. |

The product-book cover uses a conceptual generated illustration; its [image prompt and provenance](product-book/assets/IMAGE-PROMPT.md) are retained. Product screenshots are application captures, not generated mockups.

## Excluded from Git

- `var/`: local databases, evidence copies, exports, logs, tool downloads, and verification output.
- `.venv/`, `node_modules/`, `web/dist/`, bytecode, package metadata, and editor/agent caches.
- Private environment files, keys, and credentials.
- `data/external/` benchmark payloads, while retaining their README/source notes. The local downloads exceed a gigabyte and are not required to start the app.
- `data/models/` downloaded model binaries. Obtain the optional YuNet and SFace models with `python scripts/fetch_models.py`.
- Third-party reference publications downloaded into `docs/product-book/research/`. Their sources are discussed in the product-book research notes; the publications are not redistributed here.

Exclusion from Git does not remove these files from a developer’s machine.

## Licenses

The application’s [Apache 2.0 license](../LICENSE) and existing [NOTICE](../NOTICE) are preserved. Public geographic data, fonts, images, and downloaded models retain their own terms. Source notes and licenses are located beside the relevant assets. The application license does not replace those terms.

Historical benchmark descriptions are in [the external-data README](../data/external/README.md) and [the benchmark report](research/10-external-benchmarks.md). The `bench/` scripts referenced by that report are not included in this snapshot.
