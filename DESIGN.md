---
name: Mosaic product brochure
description: "The Case File: the printed A4 brochure for Weirwood's Mosaic, built as an Indian government case file. Scope: docs/brochure only, not the web app."
colors:
  board: "#a3865a"
  print: "#2a1e10"
  print2: "#3a2a16"
  bond: "#fafaf7"
  white: "#fffefb"
  flag: "#ebe1c8"
  ink: "#161616"
  ink2: "#2b2925"
  muted: "#625c53"
  rule: "#cfc7b8"
  enclosure-edge: "#c4bcac"
  tape: "#b0202a"
  tape-dark: "#931a23"
  violet: "#4f3a86"
  green: "#1d6b4b"
typography:
  display:
    fontFamily: "Mukta, sans-serif"
    fontSize: "94pt"
    fontWeight: 800
    lineHeight: 0.9
    letterSpacing: "0.005em"
  headline-divider:
    fontFamily: "Mukta, sans-serif"
    fontSize: "36pt"
    fontWeight: 800
    lineHeight: 1.02
    letterSpacing: "-0.015em"
  headline-start:
    fontFamily: "Mukta, sans-serif"
    fontSize: "30pt"
    fontWeight: 700
    lineHeight: 1.06
    letterSpacing: "-0.016em"
  headline:
    fontFamily: "Mukta, sans-serif"
    fontSize: "24pt"
    fontWeight: 700
    lineHeight: 1.1
    letterSpacing: "-0.012em"
  title:
    fontFamily: "Mukta, sans-serif"
    fontSize: "12.5pt"
    fontWeight: 600
    lineHeight: 1.2
  lead:
    fontFamily: "Martel, Georgia, serif"
    fontSize: "11.2pt"
    fontWeight: 400
    lineHeight: 1.6
  body:
    fontFamily: "Martel, Georgia, serif"
    fontSize: "10pt"
    fontWeight: 400
    lineHeight: 1.62
  run-in-head:
    fontFamily: "Martel, Georgia, serif"
    fontSize: "10pt"
    fontWeight: 700
    lineHeight: 1
  para-number:
    fontFamily: "Mukta, sans-serif"
    fontSize: "9.6pt"
    fontWeight: 600
    lineHeight: 1.62
    fontFeature: "tnum"
  noting:
    fontFamily: "Mukta, sans-serif"
    fontSize: "9.2pt"
    fontWeight: 500
    lineHeight: 1.38
  caption:
    fontFamily: "Mukta, sans-serif"
    fontSize: "8.6pt"
    fontWeight: 400
    lineHeight: 1.35
  label:
    fontFamily: "Mukta, sans-serif"
    fontSize: "6.4pt"
    fontWeight: 500
    lineHeight: 1.25
    letterSpacing: "0.09em"
  typed:
    fontFamily: "Courier Prime, monospace"
    fontSize: "9pt"
    fontWeight: 400
    letterSpacing: "0"
    fontFeature: "tnum"
  stamp:
    fontFamily: "Mukta, sans-serif"
    fontSize: "10pt"
    fontWeight: 800
    lineHeight: 1.05
    letterSpacing: "0.08em"
rounded:
  none: "0"
  stamp: "0.9mm"
  tab: "1.4mm"
  cut-tab: "1.6mm"
spacing:
  sheet-edge: "16mm"
  margin-column: "26mm"
  column-gap: "10mm"
  main-column: "142mm"
  row: "7.5mm"
  para: "3.4mm"
  para-measure: "120mm"
components:
  sheet:
    backgroundColor: "{colors.bond}"
    textColor: "{colors.ink2}"
    typography: "{typography.body}"
    width: "210mm"
    height: "297mm"
  jacket:
    backgroundColor: "{colors.board}"
    textColor: "{colors.print}"
    width: "210mm"
    height: "297mm"
  pasted-label:
    backgroundColor: "{colors.bond}"
    textColor: "{colors.ink}"
    padding: "11mm 12mm 12mm"
  fore-edge-tab:
    backgroundColor: "{colors.flag}"
    textColor: "{colors.muted}"
    rounded: "{rounded.tab}"
    width: "6.6mm"
    height: "30mm"
  fore-edge-tab-open:
    backgroundColor: "{colors.board}"
    textColor: "{colors.print}"
    rounded: "{rounded.tab}"
    width: "9.6mm"
    height: "30mm"
  noting:
    textColor: "{colors.green}"
    typography: "{typography.noting}"
    width: "{spacing.margin-column}"
  enclosure-crop:
    backgroundColor: "#ffffff"
    rounded: "{rounded.none}"
  stamp-corner:
    textColor: "{colors.violet}"
    typography: "{typography.stamp}"
    rounded: "{rounded.stamp}"
    padding: "1.6mm 1.4mm 1.4mm"
    width: "{spacing.margin-column}"
  typed-entry:
    textColor: "{colors.ink}"
    typography: "{typography.typed}"
  form-label:
    textColor: "{colors.muted}"
    typography: "{typography.label}"
---

# Design System: Mosaic product brochure

> **Scope.** This file governs one printed surface only: the Mosaic product brochure, built by `docs/brochure/build.py` with `docs/brochure/brochure.css` into `docs/Mosaic-Brochure.pdf` (48 A4 pages). It does **not** govern the Mosaic web app (`web/src`, `workspace.css`). The app keeps its own rules: neutral surfaces, status colour only on text, icons and dots, no pastel fills and no violet. Nothing below (kraft, tape red, stamp violet, green notings, Courier Prime, Mukta, Martel) may be carried into the app UI.

## Overview

**Creative North Star: "The Case File"**

The brochure is the file on Mosaic: an Indian government case file made to the highest standard an officer has ever held. A kraft jacket opens and closes it. Inside are white bond noting sheets, punched twice and ruled for a margin, written as a note is written: numbered paragraphs, run-in heads, short printed notes in the margin, and screenshots attached as numbered enclosures. Seven kraft divider leaves, one per flag A to G, separate the sections, and every sheet carries stepped flags on its fore-edge, so the reader always knows where they are in the file.

The register is official and calm, never theatrical. Everything in the world is something a real file holds: a printed form, a typed entry, a ruled register, a rubber stamp certifying a state, one red tape. Colour belongs to materials (board, bond, tape, stamp ink, printed green), not to decoration. Density is that of a well-kept note: one column of text, generous rule-to-rule rhythm, and screenshots that take whatever space the text leaves.

The finish is professional, not playful: English only, no handwriting, no tilted cards, no decorative stamps. The world refuses the enterprise brochure entirely: no kickers or eyebrows, no icon-card grids, no hero-metric rows, no dark openers, no browser-framed screenshots, no Inter.

**Key Characteristics:**
- Kraft jacket front and back, and seven kraft divider leaves with a dark cut tab and a pasted bond label.
- White bond sheets: two punch holes, a 26mm ruled margin column, a 142mm main column, file-number header, typed page number.
- Stepped fore-edge flags on every sheet; the open section's flag stands proud in kraft.
- Numbered paragraphs in one column, numbers hung at the margin rule, run-in heads in Martel 700.
- Green printed margin notes under a short green rule.
- Screenshots as "Encl. N" enclosures: hairline edge, soft lift shadow, never a browser frame.
- Violet rubber-stamp state marks with an ink-grain mask, stamped in the margin, never over product UI.
- Three voices: Mukta prints, Martel writes, Courier Prime types.

## Colors

A material palette: every colour is a physical substance in a case file, and each substance has one job.

### Primary
- **Kraft Board** (board): the jacket, the divider leaves and the open fore-edge flag. Always carried by the procedural `brand/kraft-board.jpg` texture over the flat colour; never used as a flat fill on a bond sheet.
- **Board Print** (print, print2): ink printed onto kraft (form rules, labels, the subject box, the back-cover footer). Only on board.

### Secondary
- **Lal Fita Red** (tape, tape-dark): the one woven red tape across the jacket (lower third on the cover, upper third on the back). It echoes the red tile of the Weirwood mark. Nowhere else.
- **Stamp Violet** (violet): rubber-stamp ink for state marks (Synthetic records, Action authorised, Approved, Sealed, Confirmation, Audited, Red lines) and the single company seal on the front jacket. Always multiplied through the ink-grain mask at 0.86 to 0.9 opacity.

### Tertiary
- **Printed Green** (green): margin notings, their short top rule, and the annotation strokes on the mark specimen. Text and hairlines only, never a fill.

### Neutral
- **Bond** (bond): every noting sheet and every pasted label (divider labels, the back-cover request slip).
- **Bright Bond** (white): authored exhibits that sit on the sheet (the name slips, the architecture core, the mark specimen).
- **Flag Card** (flag): closed fore-edge flags.
- **Carbon** (ink): headings, typed entries, run-in heads, paragraph numbers, register first columns.
- **Carbon Soft** (ink2): body text and heavy rules (form tops, register heads, the sign-off rule).
- **Faded Print** (muted): form labels, folio, closed flag text, dotted leaders.
- **Ruling** (rule): the margin rule, header rule, register and index row rules.
- **Enclosure Edge** (enclosure-edge): the 0.2mm hairline around enclosures, slips and the specimen.

### Named Rules
**The One Tape Rule.** Lal fita red appears once per jacket, as the woven band, and never on a bond sheet.

**The Stamp Ink Rule.** Violet is stamp ink and only stamp ink. It certifies a state (or seals the jacket once); it never colours text, rules, fills or headings.

**The Printed Green Rule.** Green is the margin's voice: notings and annotation lines only. Nothing is filled with colour. Where Mosaic is set against the old way (the before-and-after register), the Mosaic column is drawn like the Mosaic box of the architecture diagram: a white panel framed in ink, headed in spaced capitals, its entries in Mukta, while "As it stands" recedes as a plain ruled list in grey Martel.

## Typography

**Display Font:** Mukta (with sans-serif), weights 400 to 800, self-hosted
**Body Font:** Martel (with Georgia, serif), 400 and 700
**Label/Mono Font:** Courier Prime (with monospace), 400 and 700

**Character:** Mukta is the printed voice of the form (headings, labels, notings, stamps); Martel is the officer's written note; Courier Prime is the typewriter that fills the form. Each face has exactly one role.

### Hierarchy
- **Display** (Mukta 800, 94pt, 0.9, uppercase): MOSAIC in the cover's subject box. Once.
- **Headline, divider** (Mukta 800, 36pt, 1.02): the flag title on each divider's pasted label.
- **Headline, opening sheet** (Mukta 700, 30pt, 1.06): the first sheet behind a divider, which also opens 6mm lower.
- **Headline** (Mukta 700, 24pt, 1.1, balanced, max 136mm): every other sheet title.
- **Title** (Mukta 600, 12.5pt, 1.2): sub-heads within a sheet.
- **Lead** (Martel 400, 11.2pt, 1.6, max 130mm): one sentence or two under a sheet title.
- **Body** (Martel 400, 10pt, 1.62, max 120mm): numbered paragraphs. Run-in heads in Martel 700, carbon, ending with a full stop.
- **Paragraph number** (Mukta 600, 9.6pt, tabular): hung 4.9mm left of the paragraph.
- **Noting** (Mukta 500, 9.2pt, 1.38, green): margin notes, upright.
- **Caption** (Mukta 400, 8.6pt): enclosure captions, after the typed "Encl. N".
- **Label** (Mukta 500, 6.4pt, 0.09em, uppercase, faded print): form field labels only (File no., Page, Subject, Issued by, Date, register column heads).
- **Typed** (Courier Prime 400, 9pt, tabular): typed form entries only: file number, page numbers, enclosure and flag numbers, form values. 700 for enclosure and flag numbers.
- **Stamp** (Mukta 800, 10pt, 0.08em, uppercase; sub-line 600, 5.8pt, 0.14em): inside stamps only.

### Named Rules
**The Three Voices Rule.** Mukta prints, Martel writes, Courier Prime types. Courier Prime never sets prose or headings; Martel never sets labels.

**The Label Belongs To A Field Rule.** The uppercase label names a form field and sits beside or above the value it labels. It never sits above a heading as a kicker.

## Layout

A4 portrait (210 x 297mm), zero page margin, one fixed sheet per page. Bond sheets place content 16mm in from each edge, under a 7.2mm file-number header (left: label and typed file number; right: label and typed two-digit page number) and above a folio (Weirwood · Mosaic, and the section name) that starts at the margin rule.

The sheet is two columns: a **26mm margin column** and a **142mm main column**, separated by a 10mm gap, with a 0.25mm ruled line at 45.4mm from the left edge running the sheet's height. Two punch holes sit at 105.8mm and 185.8mm in the left edge. The margin column holds notings and stamps; the main column holds everything else, in one column. Paragraph text keeps a 120mm measure. Rows stack 7.5mm apart; numbered paragraphs 3.4mm apart. The first sheet behind each divider starts 6mm lower and uses the larger heading.

Fore-edge flags, 30mm tall, step down the right edge at 34mm + 33mm per flag (A to G). The divider leaf's cut tab sits in the same position as its flag, so the leaves and the sheets index alike.

There is no two-up: screenshots are never set small beside text. Every enclosure sits inside the main column (142mm), right of the ruled margin line, which is never crossed. Each capability takes two sheets: the promise, the main screen and the numbered paras, then a continuation sheet (title + typed "contd.") carrying two more screens. The architecture diagram uses five tracks (sources, arrow, Mosaic core, arrow, users).

**The Whole Screen Rule.** A screenshot is never cropped and never made small. If a sheet runs over, `build.py` narrows its enclosures slightly, never below 85% of their width, keeping the whole image; if that is not enough, the content moves to another sheet. Adding pages is preferred to shrinking anything.

## Elevation & Depth

Depth is physical and quiet: paper lying on paper. Things pasted or attached to the sheet (enclosures, slips, the architecture core, the specimen) lift by one soft, blurred shadow; things pasted onto kraft (divider labels, the request slip) lift a little more; the flags and the tape cast their own small shadows. Nothing floats, glows or uses a hard offset.

### Shadow Vocabulary
- **Lift** (`box-shadow: 0 .7mm 2mm rgba(52,40,20,.16), 0 .1mm .3mm rgba(52,40,20,.14)`): enclosure crops, slips, the architecture core, the specimen.
- **Pasted on board** (`box-shadow: 0 1.2mm 3.2mm rgba(40,24,6,.32), 0 .2mm .4mm rgba(40,24,6,.25)`): divider labels and the back-cover request slip.
- **Tape** (`box-shadow: 0 .8mm 1.6mm rgba(40,20,5,.38), 0 .2mm .3mm rgba(40,20,5,.3)`): the red tape band.
- **Flag** (`box-shadow: -.3mm .3mm .9mm rgba(60,40,10,.16)`; open `-.4mm .4mm 1.2mm rgba(60,40,10,.3)`; cut tab `-.5mm .5mm 1.4mm rgba(40,24,6,.4)`): fore-edge flags and divider tabs.
- **Punch hole** (`box-shadow: inset 0 .5mm .9mm rgba(30,18,4,.55), 0 .2mm .1mm rgba(255,255,255,.7)`): the two holes.

### Named Rules
**The Paper On Paper Rule.** Every shadow is warm, blurred and small. A shadow means "attached to this sheet", never "interactive" or "important".

## Shapes

Rectangular and ruled, like stationery. Enclosures, slips, labels, registers and the subject box have square corners. Only cut card is rounded: fore-edge flags (1.4mm on the inner corners), divider cut tabs (1.6mm) and stamp frames (0.9mm). The company seal is the only circle. Rules carry the structure: 0.25mm for ruling, 0.35 to 0.45mm for form tops and heavy box edges, dotted 0.35mm for leaders, dashed 0.3mm for the safeguard ring in the architecture diagram. The subject box and stamps double their edge (an outline inset or outset by about 1.1 to 1.3mm), as printed forms and rubber stamps do.

## Components

### Kraft jacket (cover and back)
Full-bleed board texture. Top row: the Weirwood mark (13mm) and WEIRWOOD tracked at 0.32em, left; a ruled file-number field, right. The cover holds a ruled, double-edged subject box (30mm label column) with MOSAIC at display scale and its purpose typed on ruled lines; three form rows (Issued by, Purpose, Edition); the red tape at 199mm; the violet seal bottom right. The back holds the tape at 66mm, a pasted bond request slip with four ruled typed fields, an about paragraph and a footer line.

### Divider leaf
A kraft leaf before each flag A to G. A dark cut tab (multiplied kraft, light text) in the flag's fore-edge position, and a pasted bond label: typed "Flag X", the flag title, the question the flag answers, and its contents as an index (sheet titles and typed page numbers; for flag F, typed enclosure numbers).

### Noting sheet
Bond, punched, ruled margin, header and folio as in Layout, with the fore-edge flags. The closed flags are flag card with faded text; the open section's flag is 9.6mm wide in kraft with board print.

### Numbered paragraphs
One column, max 120mm. The number hangs at the margin rule in Mukta 600; the run-in head is Martel 700 carbon, ending in a full stop, and the text runs on.

### Noting
A short Mukta 500 green note in the margin column, under a 0.45mm green rule, printed upright. One per row at most; it states the promise of the row beside it.

### Enclosure
A screenshot attached as evidence. Caption line: typed "Encl. N" (700) then a Mukta caption. Below: the whole screenshot, square-cornered, with a 0.2mm enclosure-edge hairline, a white ground and the Lift shadow. The image is always the complete screen; it is never cropped. Below the screen, an explanation of two or three sentences (Martel 9.6pt) says what the screen shows, what the officer does there and why it matters. Enclosures are numbered in one sequence through the file.

### Rubber stamp
Violet ink, 0.6mm frame with an inset 0.25mm outline, Mukta 800 uppercase main line and a ruled sub-line, multiplied through `brand/ink-grain.png`, at 0.9 opacity, set at 0.4 of its nominal angle (between 1.2 and 2.4 degrees). A stamp records a state the product actually enforces. It is stamped in the margin column beside the enclosure it certifies, 26mm wide, and never over a screenshot.

### Registers and forms
- **Register:** a full-width ruled table; 0.4mm carbon rules top and bottom, column heads as form labels, ruling between cells, first column Mukta 600 carbon.
- **Index:** ruled rows with typed flag or enclosure numbers and typed two-digit page numbers.
- **Particulars:** a 30mm label column and value rows over ruling.
- **Dotted-leader list:** item, dotted leader in faded print, typed figure at 12pt 700.
- **Sign-off:** a 60mm block at the right, under a 0.35mm rule: "For Weirwood", the typed signatory and date.

### Name slips exhibit
An authored enclosure: six bright-bond slips in three columns, each with a form label (the source system), the name as that system records it (typed, 11pt 700) and a muted note. The slips sit square.

### Architecture diagram
Five tracks: sources and users as ruled lists under form-label heads, thin drawn arrows, and a bright-bond Mosaic core with ruled bond blocks and a dashed safeguard ring.

## Do's and Don'ts

### Do:
- **Do** keep every new sheet on the noting grid: 26mm margin column, 142mm main column, ruled margin, punch holes, file-number header, typed page number, fore-edge flags.
- **Do** write sheet content as numbered paragraphs with Martel 700 run-in heads, one column, numbers hung at the margin rule.
- **Do** attach every screenshot as a numbered "Encl. N" enclosure with a hairline edge and the Lift shadow, and show the whole screen at full width.
- **Do** put state marks in violet stamp ink in the margin beside the enclosure they certify, and only for a state the product enforces.
- **Do** keep each face to its role: Mukta prints, Martel writes, Courier Prime types.
- **Do** keep the brochure in English only.

### Don't:
- **Don't** apply this world to the Mosaic web app: no kraft, tape red, stamp violet, green notings or these faces in `web/src`.
- **Don't** add Hindi or bilingual labels.
- **Don't** use handwriting fonts (Kalam is retired), tilt cards, slips or enclosures, or add stamps that certify nothing.
- **Don't** stamp over product UI.
- **Don't** add kickers or eyebrows above headings, icon-card grids, hero-metric rows, dark openers or browser-framed screenshots.
- **Don't** use Inter.
- **Don't** use red anywhere but the one tape band, or violet anywhere but stamp ink.
