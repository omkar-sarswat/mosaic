# Mosaic — product and capabilities guide

This separate 30-page A4 publication explains what Mosaic does, why it was built, how government agencies can use it, and all 17 principal capability areas. It includes 22 original application screenshots and detailed narrative sections. The approved 120-page product book is retained as a separate reference.

The guide follows the approved visual system: TeX Gyre Heros, black typography, red section markers, two-column narrative, compact running headers and the existing cover illustration.

**Premium edition (22 October 2026).** Screenshots run the full 180 mm text measure. Body text is 9.6 pt (10 pt on narrative pages) with balanced line breaks. Each section opens with a three-point highlight strip under its lead, carries bold emphasis on the phrases that matter, and keeps every subsection whole within one column. Narrative pages close with a statement pinned to the foot of the page.

## Editable content and scripts

- `content.py`: all section titles, introductions and explanations. Mark a key phrase with `**double asterisks**` to print it bold; `keys` holds the three highlight points; `quote` holds a narrative page's closing statement.
- `manuscript.md`: generated readable manuscript for editorial review.
- `build.py`: offline HTML and PDF generation, layout checks and bookmarks.
- `guide.css`: guide-specific layout; `reference.css`: copied base visual system.
- `measure.py`: reports the free space left on every page after `build.py --preview` (aim for under 9 mm; negative means overflow).
- `verify.py`: independent PDFium rendering, strict PDF parsing, A4 and link checks, and exact decoded screenshot-pixel comparison.
- `package.py`: source archive, six-page preview PDF and overview image.
- `prepare_sources.py`: initial copying of approved assets from the adjacent product book. Packaged sources already include these assets.
- `coverage.json` and `coverage.md`: mapping of all 88 reference workflows to guide sections. This is an editorial coverage map, not a claim that every individual control is illustrated in the shorter guide.
- `provenance.json`: source-publication fingerprint. Verification checks that the original book remains unchanged when available.

## Rebuild

Install `requirements.txt` in your Python environment and use a locally installed Chrome browser. From this folder:

```powershell
python build.py
python verify.py
python package.py
```

The output is `../Mosaic-Product-Guide.pdf`. `python build.py --preview` checks and renders the HTML layout without replacing the PDF. The scripts do not write to the original product book. The source archive is self-contained; no connection to the running application or external image service is required for rebuilding.

The build checks fonts, image loading and page overflow before replacing its deliverable. Verification renders every page and checks the source dimensions and exact pixels of each screenshot. No screenshots are composited or altered. The selected network examples retain the approved selected-entity state and clear connection layout.

## Editorial scope

Prepared 22 October 2026 from the inspected implementation and approved product reference. Investigative identities and cases shown are synthetic demonstration material. Descriptions distinguish available workflows from operational deployment, measured outcomes and institutional endorsement. The cover city is the conceptual illustration generated for the approved book; it is reused in this companion guide. Product screenshots are original application captures. TeX Gyre Heros font licensing is included in `fonts/`.
