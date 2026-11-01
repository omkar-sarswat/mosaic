# Mosaic product brochure

A 48-page A4 brochure for Weirwood and Mosaic, for print and screen, designed as "The Case File": a kraft file
jacket front and back, white noting sheets inside with a ruled margin, fore-edge flags A–G, numbered paragraphs, green
margin notes, and product screenshots attached as numbered enclosures.

Contents:

1. Cover and a note on the file, with the index of flags
2. Flag A, Who we are: company introduction, particulars, name and mark, principles
3. Flag B, Introducing Mosaic: the workspace, Mosaic at a glance, what Mosaic does
4. Flag C, Why you need Mosaic: the problem, one person in six records, before and after
5. Flag D, What we deliver: deliverables and roles, every agency
6. Flag E, Advantages: why agencies choose Mosaic, safeguards and red lines
7. Flag F, Capabilities: 13 capabilities, two sheets each (promise, main screen and numbered points; then two more
   screens), plus the draft BSA s.63 certificate
8. Flag G, Technology, and the back cover with the demonstration request

Rules: English only. Every screenshot is whole (never cropped), sits inside the text column, and carries a title and a
two-to-three-sentence explanation. Nothing is filled with colour. The full design system is in `/DESIGN.md`.

Files:

- `build.py`: all copy, the screenshot explanations (`SHOT_TEXT`) and the page structure; writes `../Mosaic-Brochure.pdf`
- `brochure.css`: all styling
- `fonts/`: self-hosted Mukta, Martel and Courier Prime (SIL OFL licences included)
- `brand/`: logo, `kraft-board.jpg` (from `make_kraft.py`) and `ink-grain.png` (from `make_ink.py`)
- `render_previews.py`: renders the PDF to PNG pages and contact sheets in `var/tmp/brochure-render`

Screenshots come from `../product-book/shots/`; every record shown is synthetic.

Rebuild: `python build.py` (needs Playwright and a local Chrome). It reports the free space on every sheet and any
overflow. Previews: `PYTHONPATH=E:/GOTHAM/var/tmp/pylib python render_previews.py 1.6`.
