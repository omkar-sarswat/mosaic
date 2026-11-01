# Research and design rationale — revised edition

The redesign followed examination of original publisher and institutional material, including four downloaded PDFs, publisher-provided book spreads and a museum exhibition. References were reviewed as page images, not only search descriptions. The reference files are retained in `research/` for this working session and are not included in the distributable source archive.

## References examined

1. [Neue Grafik / New Graphic Design / Graphisme Actuel, 1958–1965 — Lars Müller Publishers](https://www.lars-mueller-publishers.com/neue-grafiknew-graphic-designgraphisme-actuel-1958-1965). The publisher’s spreads show a disciplined relationship between large visual subjects, compact supporting text and shared alignment axes. The scale of a visual changes with its importance; the page does not use a fixed decorative heading and caption formula. Application: larger product screenshots, captions aligned with the image, and different editorial masters for introductory and technical material.

2. [Suisse typeface technical documentation — Swiss Typefaces, PDF](https://www.swisstypefaces.com/media/ul/fonts/pdf/2020-11-26_swisstypefaces_Suisse.pdf). Pages 1–3, 10–11 and 15 were inspected. The document uses strong changes in type scale while keeping labels and technical annotations subordinate. Application: a restrained grotesk family, clearly separated display and reading sizes, quiet running information and consistent numerical references. The proprietary Suisse fonts are not used.

3. [The Typographic Grid — Hans Rudolf Bosshard, Niggli](https://niggli.ch/en/products/der-typografische-raster). The publisher’s proportion and modular-grid spreads demonstrate how different image and text arrangements can share a governing structure. Application: a common column system with separate masters for company narrative, chapter explanations, standard screenshots, dense screen annotations and portrait document outputs.

4. [Lars Müller Publishers, Autumn 2026 catalogue, PDF](https://www.lars-mueller-publishers.com/sites/default/files/2026-04/LMP%202026%20Autumn.pdf). Pages 1, 3–7, 11 and 15 were examined. Text and visual material are organised by information type, with alignment maintaining continuity across changing content. Application: distinguish corporate positioning, process explanation, illustrated interface details and reference navigation.

5. [Lars Müller Publishers, 2017/2018 programme, PDF](https://www.lars-mueller-publishers.com/sites/default/files/verlagsprogramm_e_2017-18_es.pdf). The cover and selected editorial spreads were inspected for pacing, visual scale and caption placement. Application: images should occupy a deliberate portion of the page, while explanatory text should have a readable measure rather than merely fill the remaining area.

6. [NASA Graphics Standards Manual, 1976 — NASA, PDF](https://www.nasa.gov/wp-content/uploads/2015/01/nasa_graphics_manual_nhb_1430-2_jan_1976.pdf). The index, identity, reproduction and stationery pages were examined as an example of systematic institutional documentation. This is a supporting corporate-manual reference, not a Swiss publication. Application: formal section names, precise operational descriptions, consistent navigation and restrained use of the supplied identity.

7. [The Swiss Grid — Poster House](https://swissgrid.posterhouse.org/). The exhibition provides historical context for the movement and its different practitioners. It supports treating the grid as an organising method rather than a prescribed red-and-black decorative style.

## What was wrong with the first edition

- A portrait format reduced a landscape interface to a small horizontal strip.
- Nearly every page repeated the same title, screenshot, paragraph and rule.
- Space accumulated below the text without contributing to hierarchy or reading order.
- Some feature descriptions were promotional summaries rather than explanations of operation.
- Repeated generic examples added length without adding enough information.
- The company introduction did not establish the product scope and institutional operating model in sufficient detail.

## Decisions for the revised edition

- **Format:** A4 portrait, 210 × 297 mm, following the user’s explicit correction and subsequent nine-page visual reference. The earlier landscape study is superseded.
- **Grid:** 180 mm live width with 15 mm side margins. Company and feature explanations use two reading columns. Screenshots occupy the upper part of their page, with detailed explanations below. Portrait outputs use a separate master.
- **Type:** TeX Gyre Heros Regular and Bold, an openly licensed Helvetica-compatible family. The original font names and GUST licence are retained. [CTAN font information](https://ctan.org/tex-archive/fonts/tex-gyre).
- **Hierarchy:** restrained running information, substantial functional headings, readable body text and clearly subordinate image references. No ornamental typography or distorted letterforms.
- **Colour:** near-black, paper white and restrained red section markers, with pale grey-blue panels reserved for diagrams and structured information. Interface screenshots retain their original colours.
- **Images:** one original screenshot per illustrated page. No blur, decorative crop, fake device frame or screenshot collage. Portrait outputs receive a dedicated document master.
- **Content:** formal company overview and product operating model; detailed chapter explanations organised around purpose, inputs, workflow, outputs and controls; individual descriptions of secondary views and dialogs.
- **Pacing:** introductory company pages, substantive chapter introductions, illustrated screen pages and a concise index. The chapter pages add information rather than acting as empty separators.
- **Claims:** no invented customer list, deployment history, performance results, company size or compliance certification. Product capabilities are described from the repository and demonstration.

## Production checks

Review representative pages at full size before the full build. Check overflow, image dimensions, font loading, reading order, internal navigation and every printed page. Render the finished PDF through an independent renderer. Keep design research and production validation outside the customer-facing product book.

The design principles are adapted to Weirwood and Mosaic. Reference page layouts, images, branding and text are not reproduced in the delivered book.

## User-provided direction and final implementation

The user supplied a nine-page reference showing a split photographic cover, compact branded headers, black functional headings, red section markers, numbered subsections, structured diagrams and substantive two-column text. The final edition follows that composition with the actual Weirwood tree logo and verified product content. It does not adopt the reference’s substitute slash logo or unsupported product claims.

The city image was generated specifically for the cover using the built-in image-generation tool. Its exact prompt and asset provenance are recorded in `assets/IMAGE-PROMPT.md`. The architecture and workflow diagrams are native HTML/SVG elements. All 88 product figures are original screenshots, with one per illustrated page.

The final build is `build_reference.py`, launched through `build.py`. It checks every page against the footer safety area, balances screenshot text using actual rendered font metrics and preserves readable body sizes. The independent verifier checks the delivered PDF rather than relying only on browser previews.
