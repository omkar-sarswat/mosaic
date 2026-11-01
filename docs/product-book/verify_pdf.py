"""Independent checks of the delivered PDF, including PDFium rendering.

Requires pypdf, Pillow and pypdfium2. Run after build.py.
"""
from pathlib import Path
import json
import re
from collections import Counter
from PIL import Image, ImageDraw
from pypdf import PdfReader
import pypdfium2 as pdfium

HERE=Path(__file__).resolve().parent
path=HERE.parent/'Mosaic-Product-Book.pdf'
report=json.loads((HERE/'validation.json').read_text(encoding='utf-8'))
reader=PdfReader(path,strict=True)
refs={p.indirect_reference.idnum:i for i,p in enumerate(reader.pages)}
link_count=0
for p in reader.pages:
    expected_width,expected_height=[n*72/25.4 for n in report['page_mm']]
    assert abs(float(p.mediabox.width)-expected_width)<2
    assert abs(float(p.mediabox.height)-expected_height)<2
    for ref in p.get('/Annots',[]):
        a=ref.get_object()
        dest=a.get('/Dest')
        if dest:
            if isinstance(dest,str):
                assert dest in reader.named_destinations, 'Missing named PDF destination'
                assert reader.get_destination_page_number(reader.named_destinations[dest]) in range(len(reader.pages))
            else:
                assert dest[0].idnum in refs, 'Broken internal PDF link'
            link_count+=1

for s in report['screens']:
    p=reader.pages[s['page']-1]
    images=[x.get_object() for x in p['/Resources'].get('/XObject',{}).values()]
    dimensions=[(int(x['/Width']),int(x['/Height'])) for x in images if x.get('/Subtype')=='/Image']
    assert tuple(s['pixels']) in dimensions, f'Screenshot downsampled or missing on page {s["page"]}'

doc=pdfium.PdfDocument(str(path))
assert len(doc)==report['pages_actual']
dest=HERE/'previews/final-pdf';dest.mkdir(exist_ok=True)
thumbs=[]
for i in range(len(doc)):
    page=doc[i]
    bitmap=page.render(scale=.6)
    im=bitmap.to_pil().convert('RGB')
    assert im.getextrema()!=((255,255),(255,255),(255,255)), f'Blank rendered page {i+1}'
    im.thumbnail((250,354));thumbs.append((i+1,im.copy()))
    bitmap.close();page.close()
for start in range(0,len(thumbs),16):
    chunk=thumbs[start:start+16];sheet=Image.new('RGB',(1040,((len(chunk)+3)//4)*385),'#dedbd5');draw=ImageDraw.Draw(sheet)
    for j,(n,im) in enumerate(chunk):
        x=(j%4)*260+5;y=(j//4)*385+22;sheet.paste(im,(x,y));draw.text((x,y-17),f'PDF page {n:03}',fill='black')
    sheet.save(dest/f'contact-{start//16+1:02}.jpg',quality=90)
for n in (1,2,3,4,5,6,7,8,9,10,11,12,18,21,27,36,37,39,51,52,53,54,55,56,57,64,67,70,71,72,74,75,90,110,116,len(doc)):
    page=doc[n-1];bitmap=page.render(scale=2);bitmap.to_pil().save(dest/f'page-{n:03}.png');bitmap.close();page.close()
doc.close()
report.update(independent_renderer='PDFium',pages_rendered=len(reader.pages),original_screenshot_dimensions_preserved=True,internal_links_verified=link_count,strict_pdf_parse=True)
(HERE/'validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(f'PDFium rendered all {len(reader.pages)} pages. Verified {len(report["screens"])} full-resolution screenshots and {link_count} internal links. Strict PDF parsing passed.')
