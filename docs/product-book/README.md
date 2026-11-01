# Mosaic — company and product book

The finished publication is `../Mosaic-Product-Book.pdf`. This reference-led October 2026 edition contains **120 A4 portrait pages**, **88 original screenshot figures**, eight company and product sections, and 17 detailed feature chapters. It follows the user-provided nine-page visual reference.

The cover combines the actual Weirwood tree logo with a generated city illustration. Interior pages use compact headers, numbered sections, black typography, red markers, native diagrams, a roles table and detailed two-column explanations. The final PDF has approximately 32,000 words including navigation and references. Product figures show the synthetic demonstration and retain their original PNG dimensions.

## Rebuild

Install the dependencies from `requirements.txt` and provide a locally installed Chrome browser. From the repository root:

```powershell
.venv/Scripts/python.exe -X utf8 docs/product-book/build.py
```

The source folder can be relocated. Run `python build.py` from its new location; the PDF is written to the parent directory. The renderer loads all assets locally and blocks HTTP requests. A layout or missing-asset failure stops the build before replacing the deliverable.

For representative browser previews without replacing the PDF:

```powershell
python build_reference.py --preview
```

For independent PDF verification:

```powershell
python verify_pdf.py
```

Verification renders every PDF page with PDFium, strictly parses the PDF, checks A4 dimensions and internal destinations, and verifies the original dimensions of all 88 embedded screenshot figures. It produces final-PDF contact sheets and selected full-page renders.

## Editable sources

- `build.py`: entry point for the final edition.
- `build_reference.py`: page composition, diagrams, navigation, font-metric column balancing and export.
- `reference.css`: A4 layout, typography and print rules.
- `editorial_content.py`: company and feature narratives.
- `reference_content.py`: expanded explanations and screen-specific reading guidance.
- `screen_editorial.py`: formal figure titles, descriptions and control corrections.
- `screen_sequence.py`: individual operating sequences.
- `content_base.py`, `screens.json`, `details.py`: underlying screenshot inventory, ordering and control coverage. The historical layout functions in `content_base.py` are not executed by the final build.
- `book-reference.html`: generated offline HTML, with the same balanced text layout used by the PDF.
- `shots/`, `brand/`, `fonts/`, `assets/`: original figures, supplied identity, local fonts and cover artwork.
- `assets/IMAGE-PROMPT.md`: exact cover-generation prompt and provenance. The built-in image-generation tool was used; no API CLI was used.
- `RESEARCH.md`: reference study and final design rationale.
- `page-manifest.json`, `coverage.md`: page and figure maps.
- `validation.json`: production verification record for the delivered PDF.

TeX Gyre Heros Regular and Bold are used under the bundled GUST Font License. Reference publications are not redistributed in the source archive. Diagnostic test-result screenshots are excluded from the publication and archive. The graph readability revision strengthens relationship colours and minimum line widths, keeps background connections visible during selection, increases fitting margins and improves flow-diagram contrast in the application. Affected figures were retaken from the isolated synthetic demonstration in light mode at 2880 × 1800 pixels, with wider browser viewports for complete financial routes. The workspace-appearance figure now also uses light mode. These are original browser captures, without painted or composited graph connections.

## Demonstration scope

Investigative names, accounts and case scenarios are synthetic. Geographic reference information and public alerts can include real place or agency names. The cover is a conceptual illustration, not an operational map. The publication makes no invented customer, deployment, certification or performance claims.

Previous builders and draft previews retained in the workspace are historical working material. Use `build.py` or `build_reference.py` to reproduce this final edition.

The graph revision and hashes of its 16 replacement browser captures are recorded in `graph-recapture.json`. Original screenshots and the preceding PDF are backed up outside the source package.

The selected-entity revision retakes ten node-link figures after entity selection. The company example uses a focused neighbourhood; positions were adjusted with live UI dragging to separate links. Direction arrowheads are larger, and the Connections graph has a taller canvas. All screenshots remain uncomposited browser captures of synthetic demonstration records.
