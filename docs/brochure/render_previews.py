"""Render docs/Mosaic-Brochure.pdf pages to PNG and build contact sheets.

    python render_previews.py [scale] [pages...]     # pages 1-based; default all
"""
import sys
from pathlib import Path

import pypdfium2 as pdfium
from PIL import Image

PDF = Path("E:/GOTHAM/docs/Mosaic-Brochure.pdf")
OUT = Path("E:/GOTHAM/var/tmp/brochure-render")
OUT.mkdir(parents=True, exist_ok=True)
scale = float(sys.argv[1]) if len(sys.argv) > 1 else 1.2
doc = pdfium.PdfDocument(str(PDF))
pages = [int(p) for p in sys.argv[2:]] or list(range(1, len(doc) + 1))
imgs = []
for n in pages:
    im = doc[n - 1].render(scale=scale).to_pil().convert("RGB")
    im.save(OUT / f"p{n:02d}.png")
    imgs.append(im)
if len(sys.argv) <= 2:
    # contact sheets of 8 pages (4 x 2)
    tw = 520
    th = int(tw * 297 / 210)
    for s in range(0, len(imgs), 8):
        sheet = Image.new("RGB", (4 * tw + 50, 2 * th + 30), (90, 90, 90))
        for i, im in enumerate(imgs[s:s + 8]):
            sheet.paste(im.resize((tw, th), Image.LANCZOS), (10 + (i % 4) * (tw + 10), 10 + (i // 4) * (th + 10)))
        sheet.save(OUT / f"contact-{s // 8 + 1}.png")
print("rendered", len(imgs), "pages to", OUT)
